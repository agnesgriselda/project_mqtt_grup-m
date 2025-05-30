# lamp/lamp_client.py
import paho.mqtt.client as mqtt # Untuk konstanta jika diperlukan, meski mungkin tidak langsung
import json
import time
import uuid
from pathlib import Path
import sys

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
# Import Properties dan PacketTypes jika suatu saat perlu membuat properties secara manual di sini
# from mqtt_utils import Properties, PacketTypes


# --- Mengambil Konfigurasi dari GLOBAL_SETTINGS ---
topics_config = GLOBAL_SETTINGS.get("topics", {})
LAMP_COMMAND_TOPIC = topics_config.get("lamp_command")
LAMP_STATUS_TOPIC = topics_config.get("lamp_status") # Untuk status ON/OFF reguler
LAMP_LWT_TOPIC = topics_config.get("lamp_lwt")       # Untuk status online/offline/lwt

DEFAULT_QOS_LAMP = GLOBAL_SETTINGS.get("default_qos", 1) # Default QoS untuk publish & subscribe
LWT_QOS_LAMP = GLOBAL_SETTINGS.get("lwt_qos", 1)
LWT_RETAIN_LAMP = GLOBAL_SETTINGS.get("lwt_retain", True)

mqtt_advanced_cfg = GLOBAL_SETTINGS.get("mqtt_advanced_settings", {})
# Message Expiry untuk status reguler akan diambil dari GLOBAL_SETTINGS oleh publish_message
# jika tidak di-override secara spesifik saat memanggil publish_message.
DEFAULT_MESSAGE_EXPIRY_LAMP_STATUS = mqtt_advanced_cfg.get("default_message_expiry_interval")


CLIENT_ID_PREFIX = GLOBAL_SETTINGS.get('client_id_prefix', 'lamp_m5_') # Contoh prefix baru
CLIENT_ID = f"{CLIENT_ID_PREFIX}{str(uuid.uuid4())[:8]}"

# Validasi konfigurasi dasar topik
if not all([LAMP_COMMAND_TOPIC, LAMP_STATUS_TOPIC]):
    print(f"Error ({CLIENT_ID}): Missing lamp command or status topic in configuration. Exiting.")
    exit(1)
if not LAMP_LWT_TOPIC:
    print(f"Warning ({CLIENT_ID}): Lamp LWT topic ('lamp_lwt') not found in config. LWT functionality will be disabled for {CLIENT_ID}.")

# Status internal lampu
lamp_state_on = False # Lampu awalnya mati

print(f"--- Lamp Client MQTTv5 ({CLIENT_ID}) ---")
# (Anda bisa menambahkan print info broker dari GLOBAL_SETTINGS.get("broker_address") jika mau)
print(f"Command Topic (Subscribe): {LAMP_COMMAND_TOPIC}, QoS: {DEFAULT_QOS_LAMP}")
print(f"Regular Status Topic (Publish): {LAMP_STATUS_TOPIC}, QoS: {DEFAULT_QOS_LAMP}, Retain: True") # Status reguler selalu retain
if LAMP_LWT_TOPIC:
    print(f"LWT & Online/Offline Status Topic: {LAMP_LWT_TOPIC}, QoS: {LWT_QOS_LAMP}, Retain: {LWT_RETAIN_LAMP}")
if DEFAULT_MESSAGE_EXPIRY_LAMP_STATUS is not None:
    print(f"Default Message Expiry for status publishes (from settings): {DEFAULT_MESSAGE_EXPIRY_LAMP_STATUS}s")
print("-" * 30)

# Buat payload LWT di sini agar timestamp-nya update saat skrip dijalankan
LAMP_LWT_PAYLOAD_ONLINE_str = json.dumps({"client_id": CLIENT_ID, "status": "online", "timestamp": time.time()}) if LAMP_LWT_TOPIC else None
LAMP_LWT_PAYLOAD_OFFLINE_UNEXPECTED_str = json.dumps({"client_id": CLIENT_ID, "status": "offline_unexpected", "timestamp": time.time()}) if LAMP_LWT_TOPIC else None
# Template untuk offline graceful, timestamp akan diisi saat disconnect
LAMP_LWT_PAYLOAD_OFFLINE_GRACEFUL_template = {"client_id": CLIENT_ID, "status": "offline_graceful"} if LAMP_LWT_TOPIC else {}


is_lamp_connected_flag = False # Flag untuk menandakan koneksi sudah siap

def publish_regular_lamp_status_v5(client):
    """Mempublikasikan status ON/OFF reguler lampu dengan fitur MQTTv5."""
    global lamp_state_on
    status_payload_dict = {"client_id": CLIENT_ID, "state": "ON" if lamp_state_on else "OFF", "timestamp": time.time()}
    payload_json = json.dumps(status_payload_dict)
    
    # Properti untuk status reguler
    user_props_status = [("device_type", "smart_led_v2.1"), ("room", "living_room")] # Contoh UserProperty
    content_type_status = "application/json"
    # Message Expiry akan diambil dari default config oleh publish_message

    result = publish_message(
        client,
        topic=LAMP_STATUS_TOPIC,
        payload=payload_json,
        qos=DEFAULT_QOS_LAMP,
        retain=True, # Status lampu reguler selalu di-retain
        user_properties=user_props_status,
        content_type=content_type_status,
        message_expiry_interval=DEFAULT_MESSAGE_EXPIRY_LAMP_STATUS # Bisa juga di-override di sini jika perlu
    )
    
    if result and result.rc == mqtt.MQTT_ERR_SUCCESS: # Gunakan mqtt.MQTT_ERR_SUCCESS
        print(f"Lamp ({CLIENT_ID}) Regular Status Published (mid: {result.mid}, RETAINED): {payload_json} to '{LAMP_STATUS_TOPIC}'")
    else:
        err_code = result.rc if result else "N/A (Publish Failed before sending)"
        print(f"Lamp ({CLIENT_ID}) Failed to enqueue regular status for publishing (Error: {err_code})")

# --- Callback MQTT Spesifik untuk Lampu ---
def on_connect_lamp(client, userdata, flags, rc, properties=None):
    global is_lamp_connected_flag
    if rc == 0: # Koneksi berhasil
        is_lamp_connected_flag = True
        print(f"Lamp ({CLIENT_ID}): Custom on_connect. Connection logic activated. Ready for commands.")
        # Subscribe ke topik perintah lampu
        if LAMP_COMMAND_TOPIC:
            # Bisa tambahkan properties saat subscribe jika perlu (misal Subscription Identifier)
            subscribe_to_topics(client, [(LAMP_COMMAND_TOPIC, DEFAULT_QOS_LAMP)])
        
        # Publikasikan status awal reguler (misalnya "OFF") dengan retain=True
        publish_regular_lamp_status_v5(client)
    # _default_on_connect di mqtt_utils akan menghandle print detail koneksi dan publish LWT online

def on_message_lamp(client, userdata, msg):
    global lamp_state_on
    command_payload_str = ""
    try:
        command_payload_str = msg.payload.decode('utf-8')
        print(f"\nLamp ({CLIENT_ID}) Received command on '{msg.topic}' (QoS {msg.qos}): '{command_payload_str}'")

        # Tampilkan properties jika ada (untuk debugging MQTTv5)
        if msg.properties:
            print("  Message Properties:")
            props_dict = vars(msg.properties)
            for prop_name, prop_value in props_dict.items():
                if prop_value is not None and prop_name != "names":
                    if prop_name == "CorrelationData" and isinstance(prop_value, bytes):
                        print(f"    {prop_name}: {prop_value.decode('utf-8', errors='replace')}")
                    elif prop_name == "UserProperty" and isinstance(prop_value, list):
                        print(f"    {prop_name}:")
                        for k_prop, v_prop in prop_value: print(f"      - {k_prop}: {v_prop}")
                    else:
                        print(f"    {prop_name}: {prop_value}")
        
        # Ambil ResponseTopic dan CorrelationData dari properties pesan masuk
        response_topic_req = getattr(msg.properties, 'ResponseTopic', None) if msg.properties else None
        correlation_data_req_bytes = getattr(msg.properties, 'CorrelationData', None) if msg.properties else None
        
        new_state_on = lamp_state_on
        cmd_upper = command_payload_str.upper()
        processed_ok = False
        state_changed = False
        error_message_str = None

        if cmd_upper == "ON":
            new_state_on = True
            processed_ok = True
        elif cmd_upper == "OFF":
            new_state_on = False
            processed_ok = True
        elif cmd_upper == "TOGGLE": # Tambahkan command TOGGLE
            new_state_on = not lamp_state_on
            processed_ok = True
        else:
            error_message_str = f"Command '{command_payload_str}' is not recognized by lamp {CLIENT_ID}."
            print(f"Lamp ({CLIENT_ID}) Unknown command received: '{command_payload_str}'")
            # processed_ok tetap False

        if processed_ok:
            state_changed = (new_state_on != lamp_state_on)
            if state_changed:
                lamp_state_on = new_state_on
                print(f"Lamp ({CLIENT_ID}) State changed to: {'ON' if lamp_state_on else 'OFF'}")
                publish_regular_lamp_status_v5(client) # Publikasikan status reguler baru
            else:
                print(f"Lamp ({CLIENT_ID}) State already {'ON' if lamp_state_on else 'OFF'}. No change in state.")
        
        # Kirim response jika ada ResponseTopic yang diminta oleh pengirim perintah
        if response_topic_req:
            resp_user_props = []
            if processed_ok:
                resp_payload_dict = {
                    "client_id": CLIENT_ID, 
                    "command_received": cmd_upper,
                    "processed_status": "success",
                    "new_lamp_state": "ON" if lamp_state_on else "OFF",
                    "state_was_changed": state_changed,
                    "timestamp": time.time()
                }
                resp_user_props = [("response_type", "command_ack")]
            else: # Jika perintah tidak dikenal atau error lain
                resp_payload_dict = {
                    "client_id": CLIENT_ID,
                    "command_received": command_payload_str, # Kirim perintah asli
                    "processed_status": "error",
                    "error_code": "UNKNOWN_COMMAND",
                    "message": error_message_str or "Failed to process command.",
                    "timestamp": time.time()
                }
                resp_user_props = [("response_type", "command_nack"), ("error_detail", "invalid_action")]
            
            print(f"  Sending response to topic: {response_topic_req}")
            publish_message(
                client,
                topic=response_topic_req,
                payload=json.dumps(resp_payload_dict),
                qos=DEFAULT_QOS_LAMP, # QoS untuk response, bisa 0 atau 1
                correlation_data=correlation_data_req_bytes, # Kirim kembali correlation data
                user_properties=resp_user_props,
                content_type="application/json",
                message_expiry_interval=60 # Response ini valid selama 1 menit
            )

    except UnicodeDecodeError:
        print(f"Lamp ({CLIENT_ID}) Could not decode command payload as UTF-8 from topic '{msg.topic}'. Payload: {msg.payload}")
    except Exception as e:
        print(f"Lamp ({CLIENT_ID}) Error processing command from topic '{msg.topic}': {e} (Payload: {msg.payload})")


def on_publish_lamp(client, userdata, mid, properties=None):
    print(f"Lamp ({CLIENT_ID}) Message Published (mid: {mid}) - Confirmed by broker (for QoS > 0).")

def on_subscribe_lamp(client, userdata, mid, granted_qos, properties=None):
    print(f"Lamp ({CLIENT_ID}) Subscription Confirmed for '{LAMP_COMMAND_TOPIC}' (mid: {mid}). Granted QoS: {granted_qos}")
    if properties and hasattr(properties, 'ReasonString'): # Contoh cek properti di Suback
        print(f"  Subscribe Ack Properties Reason: {properties.ReasonString}")

def on_disconnect_lamp(client, userdata, rc, properties=None):
    global is_lamp_connected_flag
    is_lamp_connected_flag = False
    print(f"Lamp ({CLIENT_ID}) Disconnected from MQTT Broker (rc: {rc}).")
    if properties and hasattr(properties, 'ReasonString'):
        print(f"  Broker Disconnect Reason: {properties.ReasonString}")


def run_lamp():
    global is_lamp_connected_flag
    is_lamp_connected_flag = False # Pastikan flag false di awal

    client = create_mqtt_client(
        client_id=CLIENT_ID,
        on_connect_custom=on_connect_lamp,
        on_message_custom=on_message_lamp,
        on_publish_custom=on_publish_lamp,
        on_subscribe_custom=on_subscribe_lamp,
        on_disconnect_custom=on_disconnect_lamp,
        lwt_topic=LAMP_LWT_TOPIC,
        lwt_payload_online=LAMP_LWT_PAYLOAD_ONLINE_str,
        lwt_payload_offline=LAMP_LWT_PAYLOAD_OFFLINE_UNEXPECTED_str,
        lwt_qos=LWT_QOS_LAMP,
        lwt_retain=LWT_RETAIN_LAMP
    )
    if not client:
        print(f"Lamp ({CLIENT_ID}): Failed to create MQTT client from utils. Exiting.")
        return

    client.loop_start() # Gunakan loop_start agar bisa kirim offline_graceful dengan benar
    print(f"Lamp ({CLIENT_ID}) running. Waiting for connection to be ready...")
    
    # Tunggu hingga koneksi benar-benar siap
    connection_timeout_seconds = 20
    start_wait_time = time.time()
    while not is_lamp_connected_flag and (time.time() - start_wait_time < connection_timeout_seconds):
        time.sleep(0.2)

    if not is_lamp_connected_flag:
        print(f"ERROR ({CLIENT_ID}): Lamp failed to establish connection within {connection_timeout_seconds}s timeout. Exiting.")
        disconnect_client(client, LAMP_LWT_TOPIC, None, LWT_QOS_LAMP, LWT_RETAIN_LAMP, reason_string=f"Lamp {CLIENT_ID} connection timeout")
        return
    
    print(f"Lamp ({CLIENT_ID}) Connection ready. Waiting for commands on '{LAMP_COMMAND_TOPIC}'...")
    print("-" * 30)
    try:
        while True:
            if not is_lamp_connected_flag: # Jika koneksi putus di tengah jalan
                print(f"WARNING ({CLIENT_ID}): Lamp connection lost. Waiting for Paho to attempt reconnect or loop to exit.")
                time.sleep(5) # Beri waktu Paho reconnect
                continue # Coba lagi di iterasi berikutnya
            time.sleep(1) # Jaga agar thread utama tetap hidup, Paho loop di background
    except KeyboardInterrupt:
        print(f"\nLamp ({CLIENT_ID}) Exiting due to Ctrl+C...")
    except Exception as e:
        print(f"An error occurred in the lamp main loop: {e}")
    finally:
        print("-" * 30)
        # Siapkan payload untuk LWT offline graceful
        payload_graceful_offline_final_str = None
        if LAMP_LWT_TOPIC and LAMP_LWT_PAYLOAD_OFFLINE_GRACEFUL_template: # Pastikan template ada
            temp_payload_offline = dict(LAMP_LWT_PAYLOAD_OFFLINE_GRACEFUL_template) # Buat salinan
            temp_payload_offline["timestamp"] = time.time() # Update timestamp
            payload_graceful_offline_final_str = json.dumps(temp_payload_offline)
        
        disconnect_client(
            client,
            lwt_topic=LAMP_LWT_TOPIC,
            lwt_payload_offline_graceful=payload_graceful_offline_final_str,
            lwt_qos=LWT_QOS_LAMP,
            lwt_retain=LWT_RETAIN_LAMP,
            reason_string=f"Lamp {CLIENT_ID} normal shutdown"
        )
        print(f"Lamp ({CLIENT_ID}) Disconnected by mqtt_utils.")

if __name__ == '__main__':
    run_lamp()