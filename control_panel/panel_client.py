import paho.mqtt.client as mqtt
import json
import time
import uuid
from pathlib import Path

# --- Path Konfigurasi ---
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE_PATH = SCRIPT_DIR.parent / 'config' / 'settings.json'
# --- Akhir Path Konfigurasi ---

def load_config():
    try:
        with open(CONFIG_FILE_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file {CONFIG_FILE_PATH} not found.")
        exit()
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {CONFIG_FILE_PATH}.")
        exit()
    except Exception as e:
        print(f"An unexpected error occurred while loading config: {e}")
        exit()

config = load_config()

BROKER_ADDRESS = config.get("broker_address")
BROKER_PORT = config.get("broker_port")

# Topik untuk Sensor Suhu
TEMPERATURE_TOPIC = config.get("topics", {}).get("temperature")

# Topik untuk Lampu
LAMP_COMMAND_TOPIC = config.get("topics", {}).get("lamp_command")
LAMP_STATUS_TOPIC = config.get("topics", {}).get("lamp_status")

# Topik untuk LWT
SENSOR_LWT_TOPIC = config.get("topics", {}).get("sensor_lwt")
LAMP_LWT_TOPIC = config.get("topics", {}).get("lamp_lwt")

CLIENT_ID_PREFIX = config.get('client_id_prefix', 'panel_')
CLIENT_ID = f"{CLIENT_ID_PREFIX}{str(uuid.uuid4())[:8]}"
DEFAULT_QOS = config.get("default_qos", 0)
LWT_SUBSCRIBE_QOS = config.get("lwt_qos", 1) # QoS untuk subscribe ke LWT

# Validasi konfigurasi dasar
if not BROKER_ADDRESS or not BROKER_PORT:
    print("Error: Missing broker_address or broker_port in configuration. Check settings.json.")
    exit()

print(f"--- Panel Client ({CLIENT_ID}) ---")
print(f"Target Broker: {BROKER_ADDRESS}:{BROKER_PORT}")
if TEMPERATURE_TOPIC: print(f"Temperature Topic (Subscribe): {TEMPERATURE_TOPIC}")
if LAMP_STATUS_TOPIC: print(f"Lamp Status Topic (Subscribe): {LAMP_STATUS_TOPIC}")
if LAMP_COMMAND_TOPIC: print(f"Lamp Command Topic (Publish): {LAMP_COMMAND_TOPIC}")
if SENSOR_LWT_TOPIC: print(f"Sensor LWT Topic (Subscribe): {SENSOR_LWT_TOPIC}")
if LAMP_LWT_TOPIC: print(f"Lamp LWT Topic (Subscribe): {LAMP_LWT_TOPIC}")
print(f"Default QoS for publish/subscribe: {DEFAULT_QOS}")
print(f"QoS for LWT subscription: {LWT_SUBSCRIBE_QOS}")


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Panel ({CLIENT_ID}) Connected to MQTT Broker (rc: {rc})")
        
        # Subscribe ke topik suhu jika ada
        if TEMPERATURE_TOPIC:
            (result, mid) = client.subscribe(TEMPERATURE_TOPIC, qos=DEFAULT_QOS)
            if result == mqtt.MQTT_ERR_SUCCESS:
                print(f"Panel ({CLIENT_ID}) Subscribe request sent for '{TEMPERATURE_TOPIC}' (QoS {DEFAULT_QOS}, mid: {mid})")

        # Subscribe ke topik status lampu jika ada
        if LAMP_STATUS_TOPIC:
            (result, mid) = client.subscribe(LAMP_STATUS_TOPIC, qos=DEFAULT_QOS)
            if result == mqtt.MQTT_ERR_SUCCESS:
                print(f"Panel ({CLIENT_ID}) Subscribe request sent for '{LAMP_STATUS_TOPIC}' (QoS {DEFAULT_QOS}, mid: {mid})")
        
        # Subscribe ke topik LWT Sensor jika ada
        if SENSOR_LWT_TOPIC:
            (result, mid) = client.subscribe(SENSOR_LWT_TOPIC, qos=LWT_SUBSCRIBE_QOS)
            if result == mqtt.MQTT_ERR_SUCCESS:
                print(f"Panel ({CLIENT_ID}) Subscribe request sent for Sensor LWT '{SENSOR_LWT_TOPIC}' (QoS {LWT_SUBSCRIBE_QOS}, mid: {mid})")
        
        # Subscribe ke topik LWT Lampu jika ada
        if LAMP_LWT_TOPIC:
            (result, mid) = client.subscribe(LAMP_LWT_TOPIC, qos=LWT_SUBSCRIBE_QOS)
            if result == mqtt.MQTT_ERR_SUCCESS:
                print(f"Panel ({CLIENT_ID}) Subscribe request sent for Lamp LWT '{LAMP_LWT_TOPIC}' (QoS {LWT_SUBSCRIBE_QOS}, mid: {mid})")
    else:
        print(f"Panel ({CLIENT_ID}) Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        decoded_payload = msg.payload.decode()
        
        print(f"Panel ({CLIENT_ID}) Received message on '{topic}' (QoS {msg.qos}, Retain {msg.retain}): {decoded_payload}")

        if TEMPERATURE_TOPIC and topic == TEMPERATURE_TOPIC:
            data = json.loads(decoded_payload)
            count = data.get("count", "N/A")
            temperature = data.get("temperature")
            unit = data.get("unit", "N/A")
            if temperature is not None:
                print(f"  └── Parsed SENSOR DATA (Msg #{count}) -> Temp: {temperature}°{unit}")
            else:
                print(f"  └── 'temperature' key not found in sensor JSON.")
        
        elif LAMP_STATUS_TOPIC and topic == LAMP_STATUS_TOPIC:
            status_data = json.loads(decoded_payload)
            lamp_current_state = status_data.get("state")
            if lamp_current_state is not None:
                print(f"  └── Parsed LAMP STATUS -> Lamp is: {lamp_current_state.upper()}")
            else:
                print(f"  └── 'state' key not found in lamp status JSON.")

        elif SENSOR_LWT_TOPIC and topic == SENSOR_LWT_TOPIC:
            lwt_data = json.loads(decoded_payload)
            device_id = lwt_data.get("client_id", "Unknown Sensor")
            status = lwt_data.get("status", "unknown_status")
            print(f"  └── Parsed SENSOR LWT/STATUS -> Device: {device_id}, Status: {status.upper()}")

        elif LAMP_LWT_TOPIC and topic == LAMP_LWT_TOPIC:
            lwt_data = json.loads(decoded_payload)
            device_id = lwt_data.get("client_id", "Unknown Lamp")
            status = lwt_data.get("status", "unknown_status")
            print(f"  └── Parsed LAMP LWT/STATUS -> Device: {device_id}, Status: {status.upper()}")
        
        else:
            print(f"  └── Message on unhandled topic.")

    except json.JSONDecodeError:
        print(f"Panel ({CLIENT_ID}) Could not decode JSON payload from topic '{msg.topic}': {msg.payload.decode()}")
    except UnicodeDecodeError:
        print(f"Panel ({CLIENT_ID}) Could not decode payload as UTF-8 from topic '{msg.topic}'. Payload: {msg.payload}")
    except Exception as e:
        print(f"Panel ({CLIENT_ID}) Error processing message from topic '{msg.topic}': {e}")

def on_subscribe(client, userdata, mid, granted_qos):
    # granted_qos adalah list QoS yang disetujui oleh broker.
    print(f"Panel ({CLIENT_ID}) Subscription Confirmed by Broker (mid: {mid}). Granted QoS list: {granted_qos}")

def on_publish(client, userdata, mid):
    # Konfirmasi bahwa pesan (misalnya perintah lampu) telah diproses oleh broker
    print(f"Panel ({CLIENT_ID}) Message Published & Confirmed by Broker (mid: {mid}) for QoS {DEFAULT_QOS}")

def run_panel():
    client = mqtt.Client(client_id=CLIENT_ID)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_subscribe = on_subscribe
    client.on_publish = on_publish # Untuk konfirmasi publish perintah lampu

    try:
        print(f"Panel ({CLIENT_ID}) attempting to connect...")
        client.connect(BROKER_ADDRESS, BROKER_PORT, 60)
    except ConnectionRefusedError:
        print(f"Panel ({CLIENT_ID}) Connection refused. Check broker address/port and broker status.")
        return
    except OSError as e:
        print(f"Panel ({CLIENT_ID}) Network error during connection: {e}")
        return
    except Exception as e:
        print(f"Panel ({CLIENT_ID}) Could not connect to broker: {e}")
        return

    client.loop_start() # Gunakan loop_start untuk operasi non-blocking
    print(f"Panel ({CLIENT_ID}) running. Ready to send commands and receive updates. Press Ctrl+C to exit.")
    print("-" * 30)

    try:
        # Beri sedikit waktu agar koneksi dan subscribe awal (termasuk LWT retained) selesai diproses
        time.sleep(2) 

        if LAMP_COMMAND_TOPIC:
            print("\n--- Lamp Control Interface ---")
            while True:
                cmd_input = input("Enter lamp command (ON/OFF/EXIT): ").strip().upper()
                if cmd_input == "EXIT":
                    break
                if cmd_input in ["ON", "OFF"]:
                    print(f"Panel ({CLIENT_ID}) Sending command '{cmd_input}' to lamp...")
                    result = client.publish(LAMP_COMMAND_TOPIC, cmd_input, qos=DEFAULT_QOS)
                    if result.rc == mqtt.MQTT_ERR_SUCCESS:
                        # Konfirmasi bahwa pesan di-enqueue, konfirmasi sebenarnya dari broker ada di on_publish
                        print(f"Panel ({CLIENT_ID}) Lamp command '{cmd_input}' (mid: {result.mid}) enqueued for publishing.")
                    else:
                        print(f"Panel ({CLIENT_ID}) Failed to enqueue lamp command '{cmd_input}' (Error: {result.rc})")
                else:
                    print("Invalid command. Please use ON, OFF, or EXIT.")
        else:
            print("Panel ({CLIENT_ID}) No lamp command topic configured. Running in listen-only mode.")
            # Jaga agar tetap berjalan jika hanya mode listen
            while True:
                time.sleep(1)

    except KeyboardInterrupt:
        print(f"\nPanel ({CLIENT_ID}) Exiting due to Ctrl+C...")
    except Exception as e:
        print(f"An error occurred in the panel's main loop: {e}")
    finally:
        print("-" * 30)
        print(f"Panel ({CLIENT_ID}) Stopping network loop and disconnecting...")
        client.loop_stop()
        if client.is_connected():
            client.disconnect() # Disconnect terencana, LWT tidak terpicu
        print(f"Panel ({CLIENT_ID}) Disconnected.")

if __name__ == '__main__':
    run_panel()