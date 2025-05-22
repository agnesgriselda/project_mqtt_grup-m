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

# Topik untuk perintah dan status lampu
LAMP_COMMAND_TOPIC = config.get("topics", {}).get("lamp_command")
LAMP_STATUS_TOPIC = config.get("topics", {}).get("lamp_status") # Untuk status ON/OFF reguler

# Topik untuk LWT Lampu
LAMP_LWT_TOPIC = config.get("topics", {}).get("lamp_lwt")     # Untuk status online/offline/lwt

CLIENT_ID_PREFIX = config.get('client_id_prefix', 'lamp_')
CLIENT_ID = f"{CLIENT_ID_PREFIX}{str(uuid.uuid4())[:8]}"

DEFAULT_QOS = config.get("default_qos", 0) # Digunakan untuk publish status lampu reguler & subscribe perintah
LWT_QOS = config.get("lwt_qos", 1)         # Digunakan untuk pesan LWT dan status online/offline
LWT_RETAIN = config.get("lwt_retain", True)  # Apakah LWT dan status online/offline di-retain

# Validasi konfigurasi dasar
if not all([BROKER_ADDRESS, BROKER_PORT, LAMP_COMMAND_TOPIC, LAMP_STATUS_TOPIC]):
    print("Error: Missing critical lamp configuration (broker, port, command, or status topic). Check settings.json.")
    exit()
if not LAMP_LWT_TOPIC:
    print(f"Warning: Lamp LWT topic ('lamp_lwt') not found in config. LWT functionality will be disabled for {CLIENT_ID}.")

# Status internal lampu
lamp_state_on = False # Lampu awalnya mati

print(f"--- Lamp Client ({CLIENT_ID}) ---")
print(f"Target Broker: {BROKER_ADDRESS}:{BROKER_PORT}")
print(f"Command Topic (Subscribe): {LAMP_COMMAND_TOPIC}, QoS: {DEFAULT_QOS}")
print(f"Regular Status Topic (Publish): {LAMP_STATUS_TOPIC}, QoS: {DEFAULT_QOS}, Retain: True (for regular status)")
if LAMP_LWT_TOPIC:
    print(f"LWT & Online/Offline Status Topic: {LAMP_LWT_TOPIC}, QoS: {LWT_QOS}, Retain: {LWT_RETAIN}")
print("-" * 30)


def publish_regular_lamp_status(client):
    """Mempublikasikan status ON/OFF reguler lampu dengan retain=True."""
    global lamp_state_on
    status_payload_dict = {"client_id": CLIENT_ID, "state": "ON" if lamp_state_on else "OFF", "timestamp": time.time()}
    payload_json = json.dumps(status_payload_dict)
    
    # Status reguler DI-RETAIN agar klien baru langsung tahu state ON/OFF
    result = client.publish(LAMP_STATUS_TOPIC, payload_json, qos=DEFAULT_QOS, retain=True)
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print(f"Lamp ({CLIENT_ID}) Regular Status Published (mid: {result.mid}, RETAINED): {payload_json} to '{LAMP_STATUS_TOPIC}'")
    else:
        print(f"Lamp ({CLIENT_ID}) Failed to enqueue regular status for publishing (Error: {result.rc})")

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Lamp ({CLIENT_ID}) Connected to MQTT Broker (rc: {rc})")
        # Subscribe ke topik perintah lampu
        (result_subscribe, mid_subscribe) = client.subscribe(LAMP_COMMAND_TOPIC, qos=DEFAULT_QOS)
        if result_subscribe == mqtt.MQTT_ERR_SUCCESS:
            print(f"Lamp ({CLIENT_ID}) Subscribe request sent for '{LAMP_COMMAND_TOPIC}' (mid: {mid_subscribe})")
        
        # Publikasikan status awal reguler (misalnya "OFF") dengan retain=True
        publish_regular_lamp_status(client)

        # Jika terhubung dengan sukses dan LWT topic dikonfigurasi, publish status "online"
        if LAMP_LWT_TOPIC:
            online_payload_dict = {"client_id": CLIENT_ID, "status": "online", "timestamp": time.time()}
            online_payload_json = json.dumps(online_payload_dict)
            try:
                client.publish(LAMP_LWT_TOPIC, online_payload_json, qos=LWT_QOS, retain=LWT_RETAIN)
                print(f"Lamp ({CLIENT_ID}) Published 'online' LWT/status to '{LAMP_LWT_TOPIC}' (Retained: {LWT_RETAIN})")
            except Exception as e:
                print(f"Lamp ({CLIENT_ID}) Failed to publish 'online' LWT/status: {e}")
    else:
        print(f"Lamp ({CLIENT_ID}) Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    global lamp_state_on
    command_payload_str = msg.payload.decode()
    print(f"Lamp ({CLIENT_ID}) Received command on '{msg.topic}' (QoS {msg.qos}): '{command_payload_str}'")

    new_state_on = lamp_state_on
    
    if command_payload_str.upper() == "ON":
        new_state_on = True
        print(f"Lamp ({CLIENT_ID}) Processing command: Turning ON")
    elif command_payload_str.upper() == "OFF":
        new_state_on = False
        print(f"Lamp ({CLIENT_ID}) Processing command: Turning OFF")
    else:
        print(f"Lamp ({CLIENT_ID}) Unknown command received: '{command_payload_str}'")
        return # Jangan ubah status jika perintah tidak dikenal

    if new_state_on != lamp_state_on:
        lamp_state_on = new_state_on
        # Publikasikan status reguler baru setelah diubah (dengan retain=True)
        publish_regular_lamp_status(client)
    else:
        print(f"Lamp ({CLIENT_ID}) State unchanged ({'ON' if lamp_state_on else 'OFF'}), no regular status update needed.")

def on_publish(client, userdata, mid):
    # Callback ini untuk konfirmasi publish status reguler, status online, atau status offline graceful
    print(f"Lamp ({CLIENT_ID}) Message Published & Confirmed by Broker (mid: {mid})")

def on_subscribe(client, userdata, mid, granted_qos):
    print(f"Lamp ({CLIENT_ID}) Subscription Confirmed by Broker for '{LAMP_COMMAND_TOPIC}' (mid: {mid}). Granted QoS: {granted_qos}")

def run_lamp():
    client = mqtt.Client(client_id=CLIENT_ID)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_publish = on_publish
    client.on_subscribe = on_subscribe

    # --- Implementasi Last Will and Testament (LWT) ---
    if LAMP_LWT_TOPIC:
        lwt_payload_dict = {"client_id": CLIENT_ID, "status": "offline_unexpected", "timestamp": time.time()}
        lwt_payload_json = json.dumps(lwt_payload_dict)
        try:
            client.will_set(LAMP_LWT_TOPIC, payload=lwt_payload_json, qos=LWT_QOS, retain=LWT_RETAIN)
            print(f"Lamp ({CLIENT_ID}) Last Will and Testament SET for topic '{LAMP_LWT_TOPIC}'")
        except ValueError as e:
            print(f"Lamp ({CLIENT_ID}) Failed to set LWT due to payload size or other issue: {e}")
        except Exception as e:
            print(f"Lamp ({CLIENT_ID}) Failed to set LWT: {e}")
    # --- Akhir Implementasi LWT ---

    try:
        print(f"Lamp ({CLIENT_ID}) attempting to connect...")
        client.connect(BROKER_ADDRESS, BROKER_PORT, 60)
    except ConnectionRefusedError:
        print(f"Lamp ({CLIENT_ID}) Connection refused. Check broker address/port and broker status.")
        return
    except OSError as e:
        print(f"Lamp ({CLIENT_ID}) Network error during connection: {e}")
        return
    except Exception as e:
        print(f"Lamp ({CLIENT_ID}) Could not connect to broker: {e}")
        return

    # Menggunakan loop_forever karena tugas utama lampu adalah menunggu perintah
    print(f"Lamp ({CLIENT_ID}) running, waiting for commands on '{LAMP_COMMAND_TOPIC}'. Press Ctrl+C to exit.")
    print("-" * 30)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print(f"\nLamp ({CLIENT_ID}) Exiting due to Ctrl+C...")
    except Exception as e:
        print(f"An error occurred in the lamp loop: {e}")
    finally:
        print("-" * 30)
        # Saat disconnect normal (Ctrl+C), publish status "offline_graceful"
        if LAMP_LWT_TOPIC and client.is_connected():
            offline_payload_dict = {"client_id": CLIENT_ID, "status": "offline_graceful", "timestamp": time.time()}
            offline_payload_json = json.dumps(offline_payload_dict)
            try:
                print(f"Lamp ({CLIENT_ID}) Publishing 'offline_graceful' LWT/status to '{LAMP_LWT_TOPIC}'...")
                # Penting: Paho-MQTT v1.x.x loop_forever() memblokir, jadi publish ini mungkin tidak terkirim
                # sebelum koneksi ditutup oleh finally. Solusi lebih baik adalah menggunakan loop_start()
                # dan loop manual jika perlu aksi sebelum disconnect, atau pastikan broker cepat.
                # Untuk Paho-MQTT v2.x.x, client.loop_stop() perlu dipanggil sebelum disconnect.
                # Demi kesederhanaan, kita coba publish langsung di sini.
                # Jika menggunakan loop_forever, pesan ini idealnya dikirim dari thread lain atau sebelum loop_forever.
                # Namun, Paho-MQTT biasanya cukup cepat untuk mengirim pesan singkat sebelum disconnect.
                client.publish(LAMP_LWT_TOPIC, offline_payload_json, qos=LWT_QOS, retain=LWT_RETAIN)
                time.sleep(0.5) # Beri sedikit waktu
            except Exception as e:
                print(f"Lamp ({CLIENT_ID}) Failed to publish 'offline_graceful' LWT/status: {e}")

        print(f"Lamp ({CLIENT_ID}) Disconnecting...")
        # Jika menggunakan loop_forever, client.disconnect() sudah cukup.
        # Jika menggunakan loop_start(), maka client.loop_stop() diperlukan.
        # Paho MQTT v1.x.x: client.disconnect() akan menghentikan loop_forever() secara implisit.
        if client.is_connected():
            client.disconnect() # Disconnect TERENCANA, LWT "offline_unexpected" TIDAK akan terpicu.
        print(f"Lamp ({CLIENT_ID}) Disconnected.")

if __name__ == '__main__':
    run_lamp()