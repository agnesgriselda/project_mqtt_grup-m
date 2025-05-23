# control_panel/panel_client.py
import paho.mqtt.client as mqtt 
import json
import time
import uuid
from pathlib import Path
import sys # Untuk menambahkan common ke path

# Tambahkan direktori common ke sys.path agar bisa import mqtt_utils
COMMON_DIR = Path(__file__).resolve().parent.parent / 'common'
sys.path.append(str(COMMON_DIR))

from mqtt_utils import (
    GLOBAL_SETTINGS, # Akses settings yang sudah diload oleh mqtt_utils
    create_mqtt_client, 
    publish_message, 
    subscribe_to_topics, 
    disconnect_client
)
# Import Properties dan PacketTypes jika diperlukan langsung di sini (misal untuk membuat UserProperty)
from mqtt_utils import Properties, PacketTypes


# --- Path Konfigurasi (digunakan oleh mqtt_utils.load_settings) ---
# SCRIPT_DIR = Path(__file__).resolve().parent
# CONFIG_FILE_PATH = SCRIPT_DIR.parent / 'config' / 'settings.json' # Tidak perlu load config manual lagi

# config = load_config() # Tidak perlu, GLOBAL_SETTINGS dari mqtt_utils sudah ada

# --- Mengambil Konfigurasi dari GLOBAL_SETTINGS ---
BROKER_ADDRESS = GLOBAL_SETTINGS.get("broker_address") # Tetap sama
BROKER_PORT_DEFAULT = GLOBAL_SETTINGS.get("broker_port") # Tetap sama (digunakan jika TLS false)

# Konfigurasi Advanced (port TLS, dll. akan dihandle oleh create_mqtt_client)
mqtt_advanced_cfg = GLOBAL_SETTINGS.get("mqtt_advanced_settings", {})
DEFAULT_MESSAGE_EXPIRY_PANEL = mqtt_advanced_cfg.get("default_message_expiry_interval")

# Topik dari config
topics_config = GLOBAL_SETTINGS.get("topics", {})
TEMPERATURE_TOPIC = topics_config.get("temperature") # Tetap sama
LAMP_COMMAND_TOPIC = topics_config.get("lamp_command") # Tetap sama
LAMP_STATUS_TOPIC = topics_config.get("lamp_status") # Tetap sama
SENSOR_LWT_TOPIC = topics_config.get("sensor_lwt") # Tetap sama
LAMP_LWT_TOPIC = topics_config.get("lamp_lwt") # Tetap sama

# Topik baru untuk panel
PANEL_LWT_TOPIC = topics_config.get("panel_lwt")
LAMP_COMMAND_RESPONSE_BASE = topics_config.get("lamp_command_response_base")

# Daftar subscribe dari panel_specific_settings
panel_specific_cfg = GLOBAL_SETTINGS.get("panel_specific_settings", {})
PANEL_SUBSCRIBED_TOPICS_STR_LIST = panel_specific_cfg.get("subscribed_topics_list", [])


CLIENT_ID_PREFIX = GLOBAL_SETTINGS.get('client_id_prefix', 'panel_v5_') # Ambil dari global
CLIENT_ID = f"{CLIENT_ID_PREFIX}{str(uuid.uuid4())[:8]}" # Tetap sama
DEFAULT_QOS_PANEL = GLOBAL_SETTINGS.get("default_qos", 1) # Ambil dari global, default ke 1 jika tidak ada
LWT_QOS_PANEL = GLOBAL_SETTINGS.get("lwt_qos", 1) # Ambil dari global
LWT_RETAIN_PANEL = GLOBAL_SETTINGS.get("lwt_retain", True) # Ambil dari global

# LWT Payloads untuk panel ini
PANEL_LWT_PAYLOAD_ONLINE = None
PANEL_LWT_PAYLOAD_OFFLINE = None
if PANEL_LWT_TOPIC:
    PANEL_LWT_PAYLOAD_ONLINE = json.dumps({"client_id": CLIENT_ID, "status": "online", "timestamp": time.time()})
    PANEL_LWT_PAYLOAD_OFFLINE = json.dumps({"client_id": CLIENT_ID, "status": "offline", "timestamp": time.time()})


# Validasi konfigurasi dasar (sebagian besar sudah dihandle mqtt_utils)
if not BROKER_ADDRESS: # BROKER_PORT akan dihandle oleh create_mqtt_client
    print("Error: Missing broker_address in configuration. Check settings.json.")
    exit(1)

print(f"--- Panel Client MQTTv5 ({CLIENT_ID}) ---")
print(f"Target Broker: {BROKER_ADDRESS}") # Port akan ditentukan oleh TLS setting
# Info topik yang relevan untuk panel
# (Tidak perlu print semua, karena daftar subscribe dinamis)
print(f"Subscribing to topics listed in 'panel_specific_settings.subscribed_topics_list'")
if LAMP_COMMAND_TOPIC: print(f"Lamp Command Topic (Publish): {LAMP_COMMAND_TOPIC}")
if PANEL_LWT_TOPIC: print(f"Panel LWT Topic: {PANEL_LWT_TOPIC}")


# Untuk melacak request yang dikirim oleh panel (misal, command ke lampu)
active_panel_requests = {} # key: correlation_id, value: {'response_topic': str, 'timestamp': float, 'command': str}


# --- Callback MQTT Spesifik untuk Panel ---
def on_connect_panel(client, userdata, flags, rc, properties=None):
    # Fungsi _default_on_connect di mqtt_utils akan menangani print dasar dan publish LWT online
    # Di sini kita hanya fokus pada subscribe
    if rc == 0:
        topics_to_subscribe_tuples = []
        for topic_name_str in PANEL_SUBSCRIBED_TOPICS_STR_LIST:
            if topic_name_str:
                topics_to_subscribe_tuples.append((topic_name_str, DEFAULT_QOS_PANEL))
        
        if topics_to_subscribe_tuples:
            print(f"Panel ({CLIENT_ID}): Requesting subscriptions for: {topics_to_subscribe_tuples}")
            # MQTTv5: bisa set properties saat subscribe
            sub_props = Properties(PacketTypes.SUBSCRIBE)
            # sub_props.SubscriptionIdentifier = 789 # Contoh
            subscribe_to_topics(client, topics_to_subscribe_tuples, sub_properties=sub_props)
        else:
            print(f"Panel ({CLIENT_ID}): No topics configured for panel to subscribe to in 'panel_specific_settings.subscribed_topics_list'.")

def on_message_panel(client, userdata, msg):
    # Logika on_message Anda yang sudah ada, dengan penyesuaian untuk properties
    try:
        topic = msg.topic
        decoded_payload = msg.payload.decode()
        
        print(f"\nPanel ({CLIENT_ID}) Received message on '{topic}' (QoS {msg.qos}, Retain {msg.retain}):")
        print(f"  Payload: {decoded_payload}")

        # --- Menampilkan Properti Pesan MQTTv5 ---
        if msg.properties:
            print("  Message Properties:")
            props_dict = vars(msg.properties)
            for prop_name, prop_value in props_dict.items():
                if prop_value is not None and prop_name != "names":
                    if prop_name == "CorrelationData" and isinstance(prop_value, bytes):
                        print(f"    {prop_name}: {prop_value.decode('utf-8', errors='ignore')}")
                    elif prop_name == "UserProperty" and isinstance(prop_value, list):
                        print(f"    {prop_name}:")
                        for k, v_prop in prop_value: print(f"      - {k}: {v_prop}")
                    else:
                        print(f"    {prop_name}: {prop_value}")
        
        # --- Penanganan jika ini adalah response untuk request yang dikirim panel ---
        correlation_id_resp = None
        if msg.properties and hasattr(msg.properties, 'CorrelationData'):
            correlation_id_resp = msg.properties.CorrelationData.decode('utf-8', errors='ignore')

        if correlation_id_resp and correlation_id_resp in active_panel_requests:
            request_details = active_panel_requests.pop(correlation_id_resp) # Hapus setelah diproses
            print(f"  [RESPONSE MATCHED] For Correlation ID: {correlation_id_resp}")
            print(f"  Original command was: {request_details.get('command', 'N/A')}")
            try:
                response_data = json.loads(decoded_payload)
                print(f"  Parsed Response Data: {response_data}")
            except json.JSONDecodeError:
                print(f"  Response Data (Raw): {decoded_payload}")
            # Unsubscribe dari topic response (jika dibuat unik per request)
            client.unsubscribe(request_details['response_topic'])
            print(f"  Unsubscribed from response topic: {request_details['response_topic']}")
            return # Pesan sudah ditangani sebagai response

        # --- Penanganan pesan reguler (bukan response ke panel) ---
        # Logika parsing payload Anda yang sudah ada
        parsed_data = None
        try:
            parsed_data = json.loads(decoded_payload)
        except json.JSONDecodeError:
            print(f"  └── Payload is not valid JSON. Treating as raw string for LWT.")
            # Hanya proses LWT jika payload adalah string sederhana dan topik adalah LWT
            is_lwt_topic = False
            for lwt_key in ["sensor_lwt", "lamp_lwt", "panel_lwt"]: # Cek semua kemungkinan LWT dari config
                if topics_config.get(lwt_key) == topic:
                    is_lwt_topic = True
                    break
            if is_lwt_topic and isinstance(decoded_payload, str) and decoded_payload.lower() in ["online", "offline"]:
                 print(f"  └── Parsed LWT (simple string from '{topic}') -> Status: {decoded_payload.upper()}")
            return # Keluar jika bukan JSON dan bukan LWT string sederhana


        if parsed_data:
            # --- Panel sebagai RESPONDER untuk request suhu ---
            if TEMPERATURE_TOPIC and topic == TEMPERATURE_TOPIC:
                response_topic_req = getattr(msg.properties, 'ResponseTopic', None)
                correlation_data_req = getattr(msg.properties, 'CorrelationData', None)
                if response_topic_req: # Ini adalah request
                    print(f"  └── Temperature data is a REQUEST. Responding to {response_topic_req}")
                    resp_payload = {"status": "temperature_acknowledged_by_panel", "panel_id": CLIENT_ID, "original_data": parsed_data}
                    # publish_message dari mqtt_utils sudah menangani pembuatan Properties
                    publish_message(client, response_topic_req, json.dumps(resp_payload), 
                                    qos=DEFAULT_QOS_PANEL, 
                                    correlation_data=correlation_data_req, # Kirim kembali correlation data
                                    message_expiry_interval=60) # Response ini kadaluarsa setelah 1 menit
                else: # Ini data suhu biasa
                    count = parsed_data.get("count", "N/A")
                    temperature = parsed_data.get("temperature")
                    unit = parsed_data.get("unit", "N/A")
                    if temperature is not None:
                        print(f"  └── Parsed SENSOR DATA (Msg #{count}) -> Temp: {temperature}°{unit}")
                    else:
                        print(f"  └── 'temperature' key not found in sensor JSON.")
            
            elif LAMP_STATUS_TOPIC and topic == LAMP_STATUS_TOPIC:
                lamp_current_state = parsed_data.get("state") # Asumsi payload JSON punya key "state"
                if lamp_current_state is not None:
                    print(f"  └── Parsed LAMP STATUS -> Lamp is: {str(lamp_current_state).upper()}")
                else:
                    print(f"  └── 'state' key not found in lamp status JSON.")

            # Penanganan LWT yang payloadnya JSON
            elif SENSOR_LWT_TOPIC and topic == SENSOR_LWT_TOPIC:
                device_id = parsed_data.get("client_id", "Unknown Sensor")
                status = parsed_data.get("status", "unknown_status")
                print(f"  └── Parsed SENSOR LWT/STATUS -> Device: {device_id}, Status: {status.upper()}")

            elif LAMP_LWT_TOPIC and topic == LAMP_LWT_TOPIC:
                device_id = parsed_data.get("client_id", "Unknown Lamp")
                status = parsed_data.get("status", "unknown_status")
                print(f"  └── Parsed LAMP LWT/STATUS -> Device: {device_id}, Status: {status.upper()}")
            
            # Tambahkan penanganan untuk PANEL_LWT_TOPIC jika panel subscribe ke LWT nya sendiri (biasanya tidak)
            # atau LWT dari device lain yang belum tercakup
            elif topic in PANEL_SUBSCRIBED_TOPICS_STR_LIST: # Jika topic lain yang disubscribe
                 print(f"  └── Parsed data from subscribed topic '{topic}': {parsed_data}")
        
        # else: # Jika payload bukan JSON dan sudah ditangani di atas
        #     print(f"  └── Message on unhandled topic or non-JSON payload not specifically processed.")


    except UnicodeDecodeError:
        print(f"Panel ({CLIENT_ID}) Could not decode payload as UTF-8 from topic '{msg.topic}'. Payload: {msg.payload}")
    except Exception as e:
        print(f"Panel ({CLIENT_ID}) Error processing message from topic '{msg.topic}': {e} (Payload: {msg.payload})")


def on_subscribe_panel(client, userdata, mid, granted_qos, properties=None): # Tambah properties
    print(f"Panel ({CLIENT_ID}) Subscription Confirmed by Broker (mid: {mid}). Granted QoS list: {granted_qos}")
    if properties: # MQTTv5
        print(f"  Subscribe Properties from Broker: {vars(properties)}")

def on_publish_panel(client, userdata, mid, properties=None): # Tambah properties
    # Untuk QoS > 0, ini adalah konfirmasi dari broker.
    # Untuk QoS 0, callback ini mungkin dipanggil segera oleh Paho (tergantung versi) atau tidak sama sekali.
    print(f"Panel ({CLIENT_ID}) Message Published (mid: {mid})")
    # if properties: # Jarang ada properties di PUBACK/PUBCOMP dari broker ke client
    #    print(f"  Publish Ack Properties: {vars(properties)}")

def on_disconnect_panel(client, userdata, rc, properties=None): # Tambah properties
    print(f"Panel ({CLIENT_ID}) Disconnected from MQTT Broker (rc: {rc}).")
    if properties: # MQTTv5
        print(f"  Broker DISCONNECT Properties: {vars(properties)}")
    # Logika reconnect bisa ditambahkan di sini jika diinginkan


def run_panel():
    # Membuat client menggunakan mqtt_utils
    # LWT untuk panel ini akan di-set oleh create_mqtt_client
    client = create_mqtt_client(
        client_id=CLIENT_ID,
        on_connect_custom=on_connect_panel,
        on_message_custom=on_message_panel,
        on_subscribe_custom=on_subscribe_panel,
        on_publish_custom=on_publish_panel,
        on_disconnect_custom=on_disconnect_panel,
        lwt_topic=PANEL_LWT_TOPIC,
        lwt_payload_online=PANEL_LWT_PAYLOAD_ONLINE, # Untuk dipublish manual oleh _default_on_connect
        lwt_payload_offline=PANEL_LWT_PAYLOAD_OFFLINE # Untuk will_set
        # lwt_qos dan lwt_retain akan diambil dari GLOBAL_SETTINGS jika tidak di-override di sini
    )

    if not client:
        print(f"Panel ({CLIENT_ID}): Failed to create or connect MQTT client. Exiting.")
        return

    client.loop_start() # Gunakan loop_start untuk operasi non-blocking
    print(f"Panel ({CLIENT_ID}) running. Ready to send commands and receive updates. Press Ctrl+C to exit.")
    print("-" * 30)

    try:
        time.sleep(1) # Beri sedikit waktu agar koneksi dan subscribe awal selesai diproses

        if LAMP_COMMAND_TOPIC:
            print("\n--- Lamp Control Interface ---")
            while True:
                cmd_input = input("Enter lamp command (ON/OFF/TOGGLE/EXIT): ").strip().upper()
                if cmd_input == "EXIT":
                    break
                if cmd_input in ["ON", "OFF", "TOGGLE"]:
                    print(f"Panel ({CLIENT_ID}) Sending command '{cmd_input}' to lamp...")
                    
                    # --- Request/Response Pattern untuk command lampu ---
                    correlation_id_lamp = None
                    response_topic_for_lamp_cmd = None
                    user_props_lamp = [("source_panel", CLIENT_ID), ("command_timestamp", str(time.time()))]

                    if LAMP_COMMAND_RESPONSE_BASE: # Jika kita ingin response
                        correlation_id_lamp = str(uuid.uuid4())
                        response_topic_for_lamp_cmd = f"{LAMP_COMMAND_RESPONSE_BASE}{correlation_id_lamp}"
                        
                        # Simpan detail request
                        active_panel_requests[correlation_id_lamp] = {
                            'response_topic': response_topic_for_lamp_cmd,
                            'timestamp': time.time(),
                            'command': cmd_input
                        }
                        # Subscribe ke topic response yang baru dibuat (QoS untuk response bisa 0 atau 1)
                        subscribe_to_topics(client, [(response_topic_for_lamp_cmd, 1)])
                        print(f"  Panel subscribed to '{response_topic_for_lamp_cmd}' for lamp command response.")

                    # Menggunakan publish_message dari mqtt_utils
                    result = publish_message(
                        client,
                        LAMP_COMMAND_TOPIC, 
                        cmd_input, # Payload bisa JSON jika lampu mengharapkan JSON
                        qos=DEFAULT_QOS_PANEL,
                        message_expiry_interval=DEFAULT_MESSAGE_EXPIRY_PANEL, # Ambil dari config
                        response_topic=response_topic_for_lamp_cmd, # Akan None jika LAMP_COMMAND_RESPONSE_BASE tidak ada
                        correlation_data=correlation_id_lamp,       # Akan None jika tidak ada
                        user_properties=user_props_lamp,
                        content_type="text/plain" # Atau "application/json" jika payload JSON
                    )

                    if result and result.rc == mqtt.MQTT_ERR_SUCCESS:
                        print(f"Panel ({CLIENT_ID}) Lamp command '{cmd_input}' (mid: {result.mid}) enqueued.")
                        if correlation_id_lamp:
                            print(f"  Expecting response with Correlation ID: {correlation_id_lamp}")
                    else:
                        err_code = result.rc if result else "N/A (Publish failed before sending)"
                        print(f"Panel ({CLIENT_ID}) Failed to enqueue lamp command '{cmd_input}' (Error: {err_code})")
                        # Cleanup jika publish gagal
                        if correlation_id_lamp and correlation_id_lamp in active_panel_requests:
                            del active_panel_requests[correlation_id_lamp] 
                            if response_topic_for_lamp_cmd: client.unsubscribe(response_topic_for_lamp_cmd)
                else:
                    print("Invalid command. Please use ON, OFF, TOGGLE, or EXIT.")
        else:
            print("Panel ({CLIENT_ID}) No lamp command topic configured. Running in listen-only mode.")
            while True: # Jaga agar tetap berjalan jika hanya mode listen
                time.sleep(1)

    except KeyboardInterrupt:
        print(f"\nPanel ({CLIENT_ID}) Exiting due to Ctrl+C...")
    except Exception as e:
        print(f"An error occurred in the panel's main loop: {e}")
    finally:
        print("-" * 30)
        
        # Cleanup subscriptions untuk response yang mungkin masih aktif
        if client and client.is_connected(): # Pastikan client ada dan terhubung
            for corr_id, details in list(active_panel_requests.items()):
                print(f"  Cleaning up subscription for pending response: {details['response_topic']}")
                client.unsubscribe(details['response_topic'])
        
        # Menggunakan disconnect_client dari mqtt_utils
        disconnect_client(client, reason_string=f"Panel {CLIENT_ID} normal shutdown")
        print(f"Panel ({CLIENT_ID}) Disconnected by mqtt_utils.")

if __name__ == '__main__':
    run_panel()