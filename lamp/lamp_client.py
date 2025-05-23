# lamp/lamp_client.py
import json
import time
import uuid
from pathlib import Path
import sys # Untuk menambahkan common ke path

# Tambahkan direktori common ke sys.path agar bisa import mqtt_utils
COMMON_DIR = Path(__file__).resolve().parent.parent / 'common'
sys.path.append(str(COMMON_DIR))

from mqtt_utils import (
    GLOBAL_SETTINGS,
    create_mqtt_client,
    publish_message,
    subscribe_to_topics,
    disconnect_client
)
# Import Properties dan PacketTypes jika diperlukan langsung di sini
from mqtt_utils import Properties, PacketTypes

# --- Mengambil Konfigurasi dari GLOBAL_SETTINGS ---
# Konfigurasi broker, TLS, auth, dll. akan dihandle oleh create_mqtt_client()

# Topik dari config
topics_config = GLOBAL_SETTINGS.get("topics", {})
LAMP_COMMAND_TOPIC = topics_config.get("lamp_command")
LAMP_STATUS_TOPIC = topics_config.get("lamp_status") # Untuk status ON/OFF reguler
LAMP_LWT_TOPIC = topics_config.get("lamp_lwt")       # Untuk status online/offline/lwt

# Konfigurasi QoS dan Retain dari GLOBAL_SETTINGS
DEFAULT_QOS_LAMP = GLOBAL_SETTINGS.get("default_qos", 1) # Default QoS untuk publish & subscribe
LWT_QOS_LAMP = GLOBAL_SETTINGS.get("lwt_qos", 1)
LWT_RETAIN_LAMP = GLOBAL_SETTINGS.get("lwt_retain", True)

# Konfigurasi Advanced (digunakan untuk message expiry saat publish status)
mqtt_advanced_cfg = GLOBAL_SETTINGS.get("mqtt_advanced_settings", {})
DEFAULT_MESSAGE_EXPIRY_LAMP_STATUS = mqtt_advanced_cfg.get("default_message_expiry_interval")


CLIENT_ID_PREFIX = GLOBAL_SETTINGS.get('client_id_prefix', 'lamp_v5_')
CLIENT_ID = f"{CLIENT_ID_PREFIX}{str(uuid.uuid4())[:8]}"

# Validasi konfigurasi dasar topik
if not all([LAMP_COMMAND_TOPIC, LAMP_STATUS_TOPIC]): # LWT opsional
    print(f"Error ({CLIENT_ID}): Missing critical lamp configuration (command or status topic). Check settings.json.")
    exit(1)
if not LAMP_LWT_TOPIC:
    print(f"Warning ({CLIENT_ID}): Lamp LWT topic ('lamp_lwt') not found in config. LWT functionality will be disabled for {CLIENT_ID}.")

# Status internal lampu
lamp_state_on = False # Lampu awalnya mati

print(f"--- Lamp Client MQTTv5 ({CLIENT_ID}) ---")
# Info broker akan di-print oleh mqtt_utils
print(f"Command Topic (Subscribe): {LAMP_COMMAND_TOPIC}, QoS: {DEFAULT_QOS_LAMP}")
print(f"Regular Status Topic (Publish): {LAMP_STATUS_TOPIC}, QoS: {DEFAULT_QOS_LAMP}")
if LAMP_LWT_TOPIC:
    print(f"LWT & Online/Offline Status Topic: {LAMP_LWT_TOPIC}, QoS: {LWT_QOS_LAMP}, Retain: {LWT_RETAIN_LAMP}")
print("-" * 30)


# LWT Payloads untuk lampu ini
LAMP_LWT_PAYLOAD_ONLINE = None
LAMP_LWT_PAYLOAD_OFFLINE_UNEXPECTED = None # Untuk will_set
LAMP_LWT_PAYLOAD_OFFLINE_GRACEFUL = None   # Untuk disconnect normal
if LAMP_LWT_TOPIC:
    timestamp_now = time.time()
    LAMP_LWT_PAYLOAD_ONLINE = json.dumps({"client_id": CLIENT_ID, "status": "online", "timestamp": timestamp_now})
    LAMP_LWT_PAYLOAD_OFFLINE_UNEXPECTED = json.dumps({"client_id": CLIENT_ID, "status": "offline_unexpected", "timestamp": timestamp_now})
    LAMP_LWT_PAYLOAD_OFFLINE_GRACEFUL = json.dumps({"client_id": CLIENT_ID, "status": "offline_graceful", "timestamp": timestamp_now})


def publish_regular_lamp_status_v5(client):
    """Mempublikasikan status ON/OFF reguler lampu dengan fitur MQTTv5."""
    global lamp_state_on
    status_payload_dict = {"client_id": CLIENT_ID, "state": "ON" if lamp_state_on else "OFF", "timestamp": time.time()}
    payload_json = json.dumps(status_payload_dict)
    
    # Properti untuk status reguler
    status_props = Properties(PacketTypes.PUBLISH)
    status_props.ContentType = "application/json"
    # UserProperty bisa ditambahkan jika perlu, misal versi firmware lampu
    # status_props.UserProperty = [("firmware_version", "1.2.3")]

    # Message Expiry untuk status (opsional, bisa diambil dari config)
    if DEFAULT_MESSAGE_EXPIRY_LAMP_STATUS is not None and int(DEFAULT_MESSAGE_EXPIRY_LAMP_STATUS) > 0:
        status_props.MessageExpiryInterval = int(DEFAULT_MESSAGE_EXPIRY_LAMP_STATUS)
    
    # Status reguler DI-RETAIN agar klien baru langsung tahu state ON/OFF
    result = publish_message(
        client,
        LAMP_STATUS_TOPIC,
        payload_json,
        qos=DEFAULT_QOS_LAMP,
        retain=True, # Status lampu sebaiknya di-retain
        user_properties=status_props.UserProperty, # Ambil dari properti yang sudah dibuat
        content_type=status_props.ContentType,     # Ambil dari properti yang sudah dibuat
        message_expiry_interval=status_props.MessageExpiryInterval # Ambil dari properti
    )
    
    if result and result.rc == mqtt.MQTT_ERR_SUCCESS:
        print(f"Lamp ({CLIENT_ID}) Regular Status Published (mid: {result.mid}, RETAINED): {payload_json} to '{LAMP_STATUS_TOPIC}'")
    else:
        err_code = result.rc if result else "N/A (Publish failed before sending)"
        print(f"Lamp ({CLIENT_ID}) Failed to enqueue regular status for publishing (Error: {err_code})")

# --- Callback MQTT Spesifik untuk Lampu ---
def on_connect_lamp(client, userdata, flags, rc, properties=None):
    # Fungsi _default_on_connect di mqtt_utils akan menangani print dasar dan publish LWT online
    if rc == 0:
        print(f"Lamp ({CLIENT_ID}): Connected logic specific to lamp.")
        # Subscribe ke topik perintah lampu
        if LAMP_COMMAND_TOPIC:
            sub_props_cmd = Properties(PacketTypes.SUBSCRIBE)
            # sub_props_cmd.SubscriptionIdentifier = 456 # Contoh
            subscribe_to_topics(client, [(LAMP_COMMAND_TOPIC, DEFAULT_QOS_LAMP)], sub_properties=sub_props_cmd)
        
        # Publikasikan status awal reguler (misalnya "OFF")
        publish_regular_lamp_status_v5(client)
    # else case sudah dihandle oleh _default_on_connect di mqtt_utils

def on_message_lamp(client, userdata, msg):
    global lamp_state_on
    command_payload_str = ""
    try:
        command_payload_str = msg.payload.decode()
        print(f"\nLamp ({CLIENT_ID}) Received command on '{msg.topic}' (QoS {msg.qos}): '{command_payload_str}'")

        # --- Menampilkan Properti Pesan MQTTv5 ---
        if msg.properties:
            print("  Message Properties:")
            props_dict = vars(msg.properties) # Mendapatkan dict dari properties
            for prop_name, prop_value in props_dict.items():
                if prop_value is not None and prop_name != "names":
                    if prop_name == "CorrelationData" and isinstance(prop_value, bytes):
                        print(f"    {prop_name}: {prop_value.decode('utf-8', errors='ignore')}")
                    elif prop_name == "UserProperty" and isinstance(prop_value, list):
                        print(f"    {prop_name}:")
                        for k, v_prop in prop_value: print(f"      - {k}: {v_prop}")
                    else:
                        print(f"    {prop_name}: {prop_value}")
        
        new_state_on = lamp_state_on
        cmd_upper = command_payload_str.upper()

        if cmd_upper == "ON":
            new_state_on = True
            print(f"Lamp ({CLIENT_ID}) Processing command: Turning ON")
        elif cmd_upper == "OFF":
            new_state_on = False
            print(f"Lamp ({CLIENT_ID}) Processing command: Turning OFF")
        elif cmd_upper == "TOGGLE": # Tambahkan TOGGLE
            new_state_on = not lamp_state_on
            print(f"Lamp ({CLIENT_ID}) Processing command: Toggling to {'ON' if new_state_on else 'OFF'}")
        else:
            print(f"Lamp ({CLIENT_ID}) Unknown command received: '{command_payload_str}'")
            # --- Lampu sebagai RESPONDER untuk command tidak dikenal ---
            response_topic_req = getattr(msg.properties, 'ResponseTopic', None)
            correlation_data_req = getattr(msg.properties, 'CorrelationData', None)
            if response_topic_req:
                err_payload = {"client_id": CLIENT_ID, "error": "Unknown command", "received_command": command_payload_str}
                publish_message(client, response_topic_req, json.dumps(err_payload), 
                                qos=DEFAULT_QOS_LAMP, 
                                correlation_data=correlation_data_req,
                                content_type="application/json")
                print(f"  Sent error response for unknown command to {response_topic_req}")
            return 

        state_changed = (new_state_on != lamp_state_on)
        if state_changed:
            lamp_state_on = new_state_on
            # Publikasikan status reguler baru setelah diubah
            publish_regular_lamp_status_v5(client)
        else:
            print(f"Lamp ({CLIENT_ID}) State unchanged ({'ON' if lamp_state_on else 'OFF'}), no regular status update needed.")

        # --- Lampu sebagai RESPONDER untuk command yang berhasil diproses ---
        response_topic_req = getattr(msg.properties, 'ResponseTopic', None)
        correlation_data_req = getattr(msg.properties, 'CorrelationData', None)
        if response_topic_req:
            resp_payload = {
                "client_id": CLIENT_ID, 
                "command_processed": cmd_upper,
                "new_state": "ON" if lamp_state_on else "OFF",
                "state_changed": state_changed,
                "timestamp": time.time()
            }
            publish_message(client, response_topic_req, json.dumps(resp_payload), 
                            qos=DEFAULT_QOS_LAMP, 
                            correlation_data=correlation_data_req,
                            content_type="application/json")
            print(f"  Sent command_processed response to {response_topic_req}")

    except UnicodeDecodeError:
        print(f"Lamp ({CLIENT_ID}) Could not decode command payload as UTF-8 from topic '{msg.topic}'. Payload: {msg.payload}")
    except Exception as e:
        print(f"Lamp ({CLIENT_ID}) Error processing command from topic '{msg.topic}': {e} (Payload: {msg.payload})")


def on_publish_lamp(client, userdata, mid, properties=None):
    print(f"Lamp ({CLIENT_ID}) Message Published (mid: {mid})")

def on_subscribe_lamp(client, userdata, mid, granted_qos, properties=None):
    print(f"Lamp ({CLIENT_ID}) Subscription Confirmed for '{LAMP_COMMAND_TOPIC}' (mid: {mid}). Granted QoS: {granted_qos}")
    if properties:
        print(f"  Subscribe Properties from Broker: {vars(properties)}")

def on_disconnect_lamp(client, userdata, rc, properties=None):
    print(f"Lamp ({CLIENT_ID}) Disconnected from MQTT Broker (rc: {rc}).")
    if properties:
        print(f"  Broker DISCONNECT Properties: {vars(properties)}")

def run_lamp():
    # Membuat client menggunakan mqtt_utils
    # LWT untuk lampu ini akan di-set oleh create_mqtt_client
    client = create_mqtt_client(
        client_id=CLIENT_ID,
        on_connect_custom=on_connect_lamp,
        on_message_custom=on_message_lamp,
        on_publish_custom=on_publish_lamp,
        on_subscribe_custom=on_subscribe_lamp,
        on_disconnect_custom=on_disconnect_lamp,
        lwt_topic=LAMP_LWT_TOPIC,
        lwt_payload_online=LAMP_LWT_PAYLOAD_ONLINE, # Untuk dipublish manual oleh _default_on_connect
        lwt_payload_offline=LAMP_LWT_PAYLOAD_OFFLINE_UNEXPECTED, # Untuk will_set
        lwt_qos=LWT_QOS_LAMP,
        lwt_retain=LWT_RETAIN_LAMP
    )

    if not client:
        print(f"Lamp ({CLIENT_ID}): Failed to create or connect MQTT client. Exiting.")
        return

    print(f"Lamp ({CLIENT_ID}) running, waiting for commands on '{LAMP_COMMAND_TOPIC}'. Press Ctrl+C to exit.")
    print("-" * 30)
    try:
        # Menggunakan loop_start() agar bisa mengirim pesan 'offline_graceful' dengan benar
        client.loop_start()
        while True:
            time.sleep(1) # Jaga agar thread utama tetap hidup
    except KeyboardInterrupt:
        print(f"\nLamp ({CLIENT_ID}) Exiting due to Ctrl+C...")
    except Exception as e:
        print(f"An error occurred in the lamp main loop: {e}")
    finally:
        print("-" * 30)
        # Saat disconnect normal (Ctrl+C), publish status "offline_graceful"
        if LAMP_LWT_TOPIC and client.is_connected() and LAMP_LWT_PAYLOAD_OFFLINE_GRACEFUL:
            print(f"Lamp ({CLIENT_ID}) Publishing 'offline_graceful' LWT/status to '{LAMP_LWT_TOPIC}'...")
            # Update timestamp untuk payload graceful offline
            payload_graceful_offline_updated = json.loads(LAMP_LWT_PAYLOAD_OFFLINE_GRACEFUL)
            payload_graceful_offline_updated["timestamp"] = time.time()
            
            publish_message(
                client,
                LAMP_LWT_TOPIC,
                json.dumps(payload_graceful_offline_updated),
                qos=LWT_QOS_LAMP,
                retain=LWT_RETAIN_LAMP
            )
            time.sleep(0.5) # Beri sedikit waktu agar pesan terkirim sebelum disconnect

        # Menggunakan disconnect_client dari mqtt_utils
        disconnect_client(client, reason_string=f"Lamp {CLIENT_ID} normal shutdown")
        print(f"Lamp ({CLIENT_ID}) Disconnected by mqtt_utils.")

if __name__ == '__main__':
    run_lamp()