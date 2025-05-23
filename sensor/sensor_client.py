# sensor/sensor_client.py
import time
import json
import random
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
    # subscribe_to_topics, # Sensor ini mungkin tidak subscribe, tapi bisa ditambahkan jika perlu
    disconnect_client
)
# Import Properties dan PacketTypes jika diperlukan langsung di sini
from mqtt_utils import Properties, PacketTypes


# --- Mengambil Konfigurasi dari GLOBAL_SETTINGS ---
# Konfigurasi broker, TLS, auth, dll. akan dihandle oleh create_mqtt_client()

# Topik dari config
topics_config = GLOBAL_SETTINGS.get("topics", {})
TEMPERATURE_TOPIC_DATA = topics_config.get("temperature") # Ini adalah topic data suhu dari config lama
# Jika ada topic humidity di config baru:
HUMIDITY_TOPIC_DATA = topics_config.get("humidity_data") # Dari config baru

# Topic untuk LWT Sensor
SENSOR_LWT_TOPIC = topics_config.get("sensor_lwt")

# Base topic untuk response jika sensor mengirim data sebagai request
TEMPERATURE_RESPONSE_BASE = topics_config.get("temperature_response_base") # Dari config baru

# Konfigurasi QoS dan Retain dari GLOBAL_SETTINGS
DEFAULT_QOS_SENSOR = GLOBAL_SETTINGS.get("default_qos", 1)
LWT_QOS_SENSOR = GLOBAL_SETTINGS.get("lwt_qos", 1)
LWT_RETAIN_SENSOR = GLOBAL_SETTINGS.get("lwt_retain", True)

# Konfigurasi Advanced (digunakan untuk message expiry)
mqtt_advanced_cfg = GLOBAL_SETTINGS.get("mqtt_advanced_settings", {})
DEFAULT_MESSAGE_EXPIRY_SENSOR_DATA = mqtt_advanced_cfg.get("default_message_expiry_interval")


CLIENT_ID_PREFIX = GLOBAL_SETTINGS.get('client_id_prefix', 'sensor_v5_')
CLIENT_ID = f"{CLIENT_ID_PREFIX}{str(uuid.uuid4())[:8]}"

# Validasi konfigurasi dasar topik
if not TEMPERATURE_TOPIC_DATA:
    print(f"Error ({CLIENT_ID}): temperature topic ('topics.temperature') not found in configuration. Sensor cannot publish temperature data.")
    exit(1)
if not SENSOR_LWT_TOPIC:
    print(f"Warning ({CLIENT_ID}): Sensor LWT topic ('sensor_lwt') not found in config. LWT functionality will be disabled for {CLIENT_ID}.")

print(f"--- Sensor Client MQTTv5 ({CLIENT_ID}) ---")
print(f"Temperature Publish Topic: {TEMPERATURE_TOPIC_DATA}, QoS: {DEFAULT_QOS_SENSOR}")
if HUMIDITY_TOPIC_DATA: print(f"Humidity Publish Topic: {HUMIDITY_TOPIC_DATA}, QoS: {DEFAULT_QOS_SENSOR}")
if SENSOR_LWT_TOPIC:
    print(f"LWT Topic: {SENSOR_LWT_TOPIC}, QoS: {LWT_QOS_SENSOR}, Retain: {LWT_RETAIN_SENSOR}")
if TEMPERATURE_RESPONSE_BASE:
    print(f"Temperature data will be sent as REQUEST, expecting response on base: {TEMPERATURE_RESPONSE_BASE}")
print("-" * 30)

# LWT Payloads untuk sensor ini
SENSOR_LWT_PAYLOAD_ONLINE = None
SENSOR_LWT_PAYLOAD_OFFLINE_UNEXPECTED = None # Untuk will_set
SENSOR_LWT_PAYLOAD_OFFLINE_GRACEFUL = None   # Untuk disconnect normal
if SENSOR_LWT_TOPIC:
    timestamp_now_lwt = time.time()
    SENSOR_LWT_PAYLOAD_ONLINE = json.dumps({"client_id": CLIENT_ID, "status": "online", "timestamp": timestamp_now_lwt})
    SENSOR_LWT_PAYLOAD_OFFLINE_UNEXPECTED = json.dumps({"client_id": CLIENT_ID, "status": "offline_unexpected", "timestamp": timestamp_now_lwt})
    SENSOR_LWT_PAYLOAD_OFFLINE_GRACEFUL = json.dumps({"client_id": CLIENT_ID, "status": "offline_graceful", "timestamp": timestamp_now_lwt})

# Untuk melacak request yang dikirim oleh sensor dan menunggu response
active_sensor_requests = {} # key: correlation_id, value: {'response_topic': str, 'timestamp': float}

# --- Callback MQTT Spesifik untuk Sensor ---
def on_connect_sensor(client, userdata, flags, rc, properties=None):
    # Fungsi _default_on_connect di mqtt_utils akan menangani print dasar dan publish LWT online
    if rc == 0:
        print(f"Sensor ({CLIENT_ID}): Connected logic specific to sensor.")
        # Sensor ini mungkin tidak perlu subscribe ke apapun secara default,
        # kecuali jika ia mengharapkan response pada topic yang tetap.
        # Jika response topic dibuat dinamis, subscribe dilakukan saat publish request.
    # else case sudah dihandle oleh _default_on_connect di mqtt_utils

def on_message_sensor(client, userdata, msg):
    # Sensor ini akan menerima pesan jika ia subscribe ke topic response
    try:
        topic = msg.topic
        decoded_payload = msg.payload.decode()
        print(f"\nSensor ({CLIENT_ID}) Received message on '{topic}': {decoded_payload}")

        if msg.properties:
            print("  Message Properties:")
            props_dict = vars(msg.properties)
            for prop_name, prop_value in props_dict.items():
                if prop_value is not None and prop_name != "names":
                    if prop_name == "CorrelationData" and isinstance(prop_value, bytes):
                        print(f"    {prop_name}: {prop_value.decode('utf-8', errors='ignore')}")
                    # ... (print properti lain jika perlu) ...

        correlation_id_resp = None
        if msg.properties and hasattr(msg.properties, 'CorrelationData'):
            correlation_id_resp = msg.properties.CorrelationData.decode('utf-8', errors='ignore')
        
        if correlation_id_resp and correlation_id_resp in active_sensor_requests:
            request_details = active_sensor_requests.pop(correlation_id_resp) # Hapus setelah diproses
            print(f"  [RESPONSE MATCHED] For Temperature Data Request with Correlation ID: {correlation_id_resp}")
            try:
                response_data = json.loads(decoded_payload)
                print(f"  Parsed Response Data: {response_data}")
            except json.JSONDecodeError:
                print(f"  Response Data (Raw): {decoded_payload}")
            
            # Unsubscribe dari topic response yang spesifik ini
            client.unsubscribe(request_details['response_topic'])
            print(f"  Unsubscribed from response topic: {request_details['response_topic']}")
        else:
            print(f"  Message on topic '{topic}' was not a recognized response for this sensor.")

    except Exception as e:
        print(f"Sensor ({CLIENT_ID}) Error processing message from topic '{msg.topic}': {e}")


def on_publish_sensor(client, userdata, mid, properties=None): # Tambah properties
    print(f"Sensor ({CLIENT_ID}) Message Published (mid: {mid})")

def on_disconnect_sensor(client, userdata, rc, properties=None): # Tambah properties
    print(f"Sensor ({CLIENT_ID}) Disconnected from MQTT Broker (rc: {rc}).")
    if properties:
        print(f"  Broker DISCONNECT Properties: {vars(properties)}")


def run_sensor():
    # Membuat client menggunakan mqtt_utils
    client = create_mqtt_client(
        client_id=CLIENT_ID,
        on_connect_custom=on_connect_sensor,
        on_message_custom=on_message_sensor, # Dibutuhkan jika sensor mengharapkan response
        on_publish_custom=on_publish_sensor,
        on_disconnect_custom=on_disconnect_sensor,
        lwt_topic=SENSOR_LWT_TOPIC,
        lwt_payload_online=SENSOR_LWT_PAYLOAD_ONLINE,
        lwt_payload_offline=SENSOR_LWT_PAYLOAD_OFFLINE_UNEXPECTED,
        lwt_qos=LWT_QOS_SENSOR,
        lwt_retain=LWT_RETAIN_SENSOR
    )

    if not client:
        print(f"Sensor ({CLIENT_ID}): Failed to create or connect MQTT client. Exiting.")
        return

    client.loop_start() # Memulai thread network loop di background
    print(f"Sensor ({CLIENT_ID}) started. Publishing data. Press Ctrl+C to exit.")
    print("-" * 30)

    msg_count = 0
    publish_interval = 5 # Detik
    try:
        while True:
            msg_count += 1
            current_timestamp = time.time()
            temperature_value = round(random.uniform(20.0, 35.0), 2)
            
            # Payload data suhu
            temp_payload_dict = {
                "count": msg_count, 
                "temperature": temperature_value, 
                "unit": "C", 
                "client_id": CLIENT_ID, 
                "timestamp": current_timestamp
            }
            temp_payload_json = json.dumps(temp_payload_dict)

            # --- Properti untuk publish data suhu ---
            temp_pub_props = Properties(PacketTypes.PUBLISH)
            temp_pub_props.ContentType = "application/json"
            temp_pub_props.UserProperty = [("sensor_type", "DHT22_simulated"), ("location", "lab_A")]
            
            # Message Expiry untuk data sensor
            if DEFAULT_MESSAGE_EXPIRY_SENSOR_DATA is not None and int(DEFAULT_MESSAGE_EXPIRY_SENSOR_DATA) > 0:
                temp_pub_props.MessageExpiryInterval = int(DEFAULT_MESSAGE_EXPIRY_SENSOR_DATA)

            # --- Pola Request/Response untuk data suhu ---
            correlation_id_temp = None
            response_topic_for_temp = None
            if TEMPERATURE_RESPONSE_BASE: # Jika sensor ingin mengirim data suhu sebagai request
                correlation_id_temp = str(uuid.uuid4())
                response_topic_for_temp = f"{TEMPERATURE_RESPONSE_BASE}{correlation_id_temp}"
                
                temp_pub_props.ResponseTopic = response_topic_for_temp
                temp_pub_props.CorrelationData = correlation_id_temp.encode('utf-8')
                
                # Simpan detail request
                active_sensor_requests[correlation_id_temp] = {
                    'response_topic': response_topic_for_temp,
                    'timestamp': current_timestamp
                }
                # Subscribe ke topic response yang baru dibuat (QoS untuk response bisa 0 atau 1)
                # Gunakan mqtt_utils.subscribe_to_topics jika perlu properties saat subscribe
                # Untuk sederhana, client.subscribe langsung
                (res_sub, mid_sub) = client.subscribe([(response_topic_for_temp, 1)])
                if res_sub == mqtt.MQTT_ERR_SUCCESS:
                     print(f"  Sensor ({CLIENT_ID}) Subscribed to '{response_topic_for_temp}' for temperature response (MID: {mid_sub}).")
                else:
                     print(f"  Sensor ({CLIENT_ID}) FAILED to subscribe to response topic '{response_topic_for_temp}' (Error: {res_sub}).")


            print(f"\nSensor ({CLIENT_ID}) Publishing Temperature (Msg #{msg_count}) to '{TEMPERATURE_TOPIC_DATA}'")
            result_temp = publish_message(
                client,
                TEMPERATURE_TOPIC_DATA,
                temp_payload_json,
                qos=DEFAULT_QOS_SENSOR,
                # retain=False, # Data sensor biasanya tidak di-retain
                message_expiry_interval=temp_pub_props.MessageExpiryInterval,
                response_topic=temp_pub_props.ResponseTopic,
                correlation_data=temp_pub_props.CorrelationData,
                user_properties=temp_pub_props.UserProperty,
                content_type=temp_pub_props.ContentType
            )
            
            if result_temp and result_temp.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"  Temperature (mid: {result_temp.mid}) enqueued for publishing.")
                if correlation_id_temp:
                    print(f"  Expecting response with Correlation ID: {correlation_id_temp}")
            else:
                err_code_temp = result_temp.rc if result_temp else "N/A (Publish failed)"
                print(f"  Failed to enqueue temperature message (Error: {err_code_temp})")
                # Cleanup jika publish request gagal
                if correlation_id_temp and correlation_id_temp in active_sensor_requests:
                    del active_sensor_requests[correlation_id_temp]
                    if response_topic_for_temp: client.unsubscribe(response_topic_for_temp)
            
            # --- Publikasi Data Kelembaban (jika ada) ---
            if HUMIDITY_TOPIC_DATA:
                humidity_value = round(random.uniform(40.0, 70.0), 1)
                hum_payload_dict = {
                    "count": msg_count, 
                    "humidity": humidity_value, 
                    "unit": "%RH", 
                    "client_id": CLIENT_ID, 
                    "timestamp": current_timestamp
                }
                hum_payload_json = json.dumps(hum_payload_dict)
                
                # Properti untuk publish data kelembaban (bisa sama atau beda dengan suhu)
                hum_pub_props = Properties(PacketTypes.PUBLISH)
                hum_pub_props.ContentType = "application/json"
                # hum_pub_props.UserProperty = [("sensor_type", "AM2302_simulated")]
                if DEFAULT_MESSAGE_EXPIRY_SENSOR_DATA is not None and int(DEFAULT_MESSAGE_EXPIRY_SENSOR_DATA) > 0:
                    hum_pub_props.MessageExpiryInterval = int(DEFAULT_MESSAGE_EXPIRY_SENSOR_DATA)

                print(f"Sensor ({CLIENT_ID}) Publishing Humidity (Msg #{msg_count}) to '{HUMIDITY_TOPIC_DATA}'")
                result_hum = publish_message(
                    client,
                    HUMIDITY_TOPIC_DATA,
                    hum_payload_json,
                    qos=DEFAULT_QOS_SENSOR,
                    message_expiry_interval=hum_pub_props.MessageExpiryInterval,
                    # Tidak ada request/response untuk humidity di contoh ini
                    user_properties=hum_pub_props.UserProperty,
                    content_type=hum_pub_props.ContentType
                )
                if result_hum and result_hum.rc == mqtt.MQTT_ERR_SUCCESS:
                     print(f"  Humidity (mid: {result_hum.mid}) enqueued for publishing.")
                else:
                     err_code_hum = result_hum.rc if result_hum else "N/A (Publish failed)"
                     print(f"  Failed to enqueue humidity message (Error: {err_code_hum})")

            time.sleep(publish_interval)
    except KeyboardInterrupt:
        print(f"\nSensor ({CLIENT_ID}) Exiting due to Ctrl+C...")
    except Exception as e:
        print(f"An error occurred in the sensor main loop: {e}")
    finally:
        print("-" * 30)
        # Cleanup subscriptions untuk response yang mungkin masih aktif
        if client and client.is_connected(): # Pastikan client ada dan terhubung
            for corr_id, details in list(active_sensor_requests.items()):
                print(f"  Cleaning up subscription for pending response: {details['response_topic']}")
                client.unsubscribe(details['response_topic'])

        # Saat disconnect normal (Ctrl+C), publish status "offline_graceful"
        if SENSOR_LWT_TOPIC and client and client.is_connected() and SENSOR_LWT_PAYLOAD_OFFLINE_GRACEFUL:
            print(f"Sensor ({CLIENT_ID}) Publishing 'offline_graceful' status to '{SENSOR_LWT_TOPIC}'...")
            # Update timestamp untuk payload graceful offline
            payload_graceful_offline_updated = json.loads(SENSOR_LWT_PAYLOAD_OFFLINE_GRACEFUL)
            payload_graceful_offline_updated["timestamp"] = time.time()
            
            publish_message(
                client,
                SENSOR_LWT_TOPIC,
                json.dumps(payload_graceful_offline_updated),
                qos=LWT_QOS_SENSOR,
                retain=LWT_RETAIN_SENSOR
            )
            time.sleep(0.5) # Beri sedikit waktu agar pesan terkirim

        # Menggunakan disconnect_client dari mqtt_utils
        disconnect_client(client, reason_string=f"Sensor {CLIENT_ID} normal shutdown")
        print(f"Sensor ({CLIENT_ID}) Disconnected by mqtt_utils.")

if __name__ == '__main__':
    run_sensor()