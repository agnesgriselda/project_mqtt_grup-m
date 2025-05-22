import paho.mqtt.client as mqtt
import time
import json
import random
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

# Topik untuk data suhu
TEMPERATURE_TOPIC = config.get("topics", {}).get("temperature")

# Topik untuk LWT Sensor
SENSOR_LWT_TOPIC = config.get("topics", {}).get("sensor_lwt")

CLIENT_ID_PREFIX = config.get('client_id_prefix', 'sensor_')
CLIENT_ID = f"{CLIENT_ID_PREFIX}{str(uuid.uuid4())[:8]}" # Client ID unik & lebih pendek

DEFAULT_QOS = config.get("default_qos", 0) # Digunakan untuk publish data suhu
LWT_QOS = config.get("lwt_qos", 1)         # Digunakan untuk pesan LWT dan status online/offline
LWT_RETAIN = config.get("lwt_retain", True)  # Apakah LWT dan status online/offline di-retain

# Validasi konfigurasi dasar
if not BROKER_ADDRESS or not BROKER_PORT:
    print("Error: Missing broker_address or broker_port in configuration. Check settings.json.")
    exit()
if not TEMPERATURE_TOPIC:
    print("Error: temperature_topic not found in configuration. Sensor cannot publish temperature data.")
    exit()
# SENSOR_LWT_TOPIC adalah opsional, tapi fungsionalitas LWT tidak akan aktif jika tidak ada
if not SENSOR_LWT_TOPIC:
    print(f"Warning: Sensor LWT topic ('sensor_lwt') not found in config. LWT functionality will be disabled for {CLIENT_ID}.")

print(f"--- Sensor Client ({CLIENT_ID}) ---")
print(f"Target Broker: {BROKER_ADDRESS}:{BROKER_PORT}")
print(f"Temperature Publish Topic: {TEMPERATURE_TOPIC}, QoS: {DEFAULT_QOS}")
if SENSOR_LWT_TOPIC:
    print(f"LWT Topic: {SENSOR_LWT_TOPIC}, QoS for LWT/Online Status: {LWT_QOS}, Retain LWT/Online Status: {LWT_RETAIN}")
print("-" * 30)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Sensor ({CLIENT_ID}) Connected to MQTT Broker (rc: {rc})")
        # Jika terhubung dengan sukses dan LWT topic dikonfigurasi, publish status "online"
        if SENSOR_LWT_TOPIC:
            online_payload_dict = {"client_id": CLIENT_ID, "status": "online", "timestamp": time.time()}
            online_payload_json = json.dumps(online_payload_dict)
            try:
                # Publikasikan status "online" dengan QoS dan Retain yang sama seperti LWT
                # Ini akan menimpa LWT "offline" yang mungkin sebelumnya di-retain.
                client.publish(SENSOR_LWT_TOPIC, online_payload_json, qos=LWT_QOS, retain=LWT_RETAIN)
                print(f"Sensor ({CLIENT_ID}) Published 'online' status to '{SENSOR_LWT_TOPIC}' (Retained: {LWT_RETAIN})")
            except Exception as e:
                print(f"Sensor ({CLIENT_ID}) Failed to publish 'online' status: {e}")
    else:
        print(f"Sensor ({CLIENT_ID}) Failed to connect, return code {rc}. MQTT Connection Return Codes:")
        # (Tambahkan penjelasan kode rc jika perlu, seperti di versi panel_client sebelumnya)

def on_publish(client, userdata, mid):
    # Callback ini dipanggil setelah konfirmasi dari broker diterima (sesuai QoS)
    # Untuk data suhu, atau untuk status online/offline
    print(f"Sensor ({CLIENT_ID}) Message Published & Confirmed by Broker (mid: {mid})")

def run_sensor():
    client = mqtt.Client(client_id=CLIENT_ID)
    client.on_connect = on_connect
    client.on_publish = on_publish

    # --- Implementasi Last Will and Testament (LWT) ---
    if SENSOR_LWT_TOPIC:
        lwt_payload_dict = {"client_id": CLIENT_ID, "status": "offline_unexpected", "timestamp": time.time()}
        lwt_payload_json = json.dumps(lwt_payload_dict)
        try:
            # will_set harus dipanggil SEBELUM connect()
            client.will_set(SENSOR_LWT_TOPIC, payload=lwt_payload_json, qos=LWT_QOS, retain=LWT_RETAIN)
            print(f"Sensor ({CLIENT_ID}) Last Will and Testament SET for topic '{SENSOR_LWT_TOPIC}'")
        except ValueError as e: # Paho-MQTT bisa raise ValueError jika payload > 268435455 bytes
            print(f"Sensor ({CLIENT_ID}) Failed to set LWT due to payload size or other issue: {e}")
        except Exception as e: # Tangkap error umum lainnya
            print(f"Sensor ({CLIENT_ID}) Failed to set LWT: {e}")
    # --- Akhir Implementasi LWT ---

    try:
        print(f"Sensor ({CLIENT_ID}) attempting to connect...")
        client.connect(BROKER_ADDRESS, BROKER_PORT, 60) # 60 detik keep-alive
    except ConnectionRefusedError:
        print(f"Sensor ({CLIENT_ID}) Connection refused. Check broker address/port and broker status.")
        return
    except OSError as e:
        print(f"Sensor ({CLIENT_ID}) Network error during connection: {e}")
        return
    except Exception as e:
        print(f"Sensor ({CLIENT_ID}) Could not connect to broker: {e}")
        return

    client.loop_start() # Memulai thread network loop di background
    print(f"Sensor ({CLIENT_ID}) started. Publishing temperature data every 5 seconds. Press Ctrl+C to exit.")
    print("-" * 30)

    msg_count = 0
    try:
        while True:
            msg_count += 1
            temperature = round(random.uniform(20.0, 35.0), 2)
            # Payload data suhu
            temp_payload_dict = {"count": msg_count, "temperature": temperature, "unit": "C", "client_id": CLIENT_ID, "timestamp": time.time()}
            temp_payload_json = json.dumps(temp_payload_dict)

            # Publikasikan data suhu
            result = client.publish(TEMPERATURE_TOPIC, temp_payload_json, qos=DEFAULT_QOS) # Menggunakan DEFAULT_QOS untuk data suhu
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                # Dengan QoS > 0, ini berarti pesan berhasil di-enqueue di client library
                # Konfirmasi sebenarnya datang di on_publish
                print(f"Sensor ({CLIENT_ID}) Temperature (Msg #{msg_count}, mid: {result.mid}) enqueued for publishing (QoS {DEFAULT_QOS})")
            else:
                print(f"Sensor ({CLIENT_ID}) Failed to enqueue temperature message (Error: {result.rc})")
            
            time.sleep(5)  # Kirim data setiap 5 detik
    except KeyboardInterrupt:
        print(f"\nSensor ({CLIENT_ID}) Exiting due to Ctrl+C...")
    except Exception as e:
        print(f"An error occurred in the sensor loop: {e}")
    finally:
        print("-" * 30)
        # Saat disconnect normal (Ctrl+C), kita bisa publish status "offline_graceful"
        # Ini akan menimpa LWT "offline_unexpected" jika LWT retain=true dan topiknya sama,
        # atau menjadi satu-satunya indikasi offline jika LWT retain=false.
        if SENSOR_LWT_TOPIC and client.is_connected():
            offline_payload_dict = {"client_id": CLIENT_ID, "status": "offline_graceful", "timestamp": time.time()}
            offline_payload_json = json.dumps(offline_payload_dict)
            try:
                # Publikasikan status "offline_graceful".
                # Penting: Jika LWT di-retain, pesan ini juga harus di-retain agar status offline yang benar yang disimpan.
                # Atau, jika kamu ingin LWT "offline_unexpected" yang selalu jadi fallback, set retain=False di sini.
                # Untuk konsistensi, kita gunakan LWT_RETAIN juga untuk pesan graceful offline.
                print(f"Sensor ({CLIENT_ID}) Publishing 'offline_graceful' status to '{SENSOR_LWT_TOPIC}'...")
                client.publish(SENSOR_LWT_TOPIC, offline_payload_json, qos=LWT_QOS, retain=LWT_RETAIN)
                time.sleep(0.5) # Beri sedikit waktu agar pesan terkirim sebelum disconnect total
            except Exception as e:
                print(f"Sensor ({CLIENT_ID}) Failed to publish 'offline_graceful' status: {e}")
        
        print(f"Sensor ({CLIENT_ID}) Stopping network loop and disconnecting...")
        client.loop_stop()
        if client.is_connected():
             client.disconnect() # Ini adalah disconnect yang TERENCANA, LWT "offline_unexpected" TIDAK akan terpicu.
        print(f"Sensor ({CLIENT_ID}) Disconnected.")

if __name__ == '__main__':
    run_sensor()