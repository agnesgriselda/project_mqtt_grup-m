# sensor/sensor_client.py
import paho.mqtt.client as mqtt # Untuk konstanta MQTT_ERR_SUCCESS dll.
import time
import json
import random
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
    # subscribe_to_topics, # Tidak selalu dibutuhkan sensor, kecuali untuk response
    disconnect_client
)
# Import Properties dan PacketTypes jika suatu saat perlu membuat properties secara manual di sini
# from mqtt_utils import Properties, PacketTypes


# --- Mengambil Konfigurasi dari GLOBAL_SETTINGS ---
topics_config = GLOBAL_SETTINGS.get("topics", {})
TEMPERATURE_TOPIC_DATA = topics_config.get("temperature")
HUMIDITY_TOPIC_DATA = topics_config.get("humidity_data") # Jika ada di config
SENSOR_LWT_TOPIC = topics_config.get("sensor_lwt")
TEMPERATURE_RESPONSE_BASE = topics_config.get("temperature_response_base") # Untuk Req/Res

DEFAULT_QOS_SENSOR = GLOBAL_SETTINGS.get("default_qos", 1)
LWT_QOS_SENSOR = GLOBAL_SETTINGS.get("lwt_qos", 1)
LWT_RETAIN_SENSOR = GLOBAL_SETTINGS.get("lwt_retain", True)

mqtt_advanced_cfg = GLOBAL_SETTINGS.get("mqtt_advanced_settings", {})
# Message Expiry untuk data sensor akan diambil dari GLOBAL_SETTINGS oleh publish_message di mqtt_utils
# jika tidak di-override secara spesifik saat memanggil publish_message.
DEFAULT_MESSAGE_EXPIRY_SENSOR_DATA = mqtt_advanced_cfg.get("default_message_expiry_interval")


CLIENT_ID_PREFIX = GLOBAL_SETTINGS.get('client_id_prefix', 'sensor_m5_') # Contoh prefix baru
CLIENT_ID = f"{CLIENT_ID_PREFIX}{str(uuid.uuid4())[:8]}"

# Validasi konfigurasi dasar topik
if not TEMPERATURE_TOPIC_DATA:
    print(f"Error ({CLIENT_ID}): temperature topic ('topics.temperature') not found in configuration. Sensor cannot publish temperature data. Exiting.")
    exit(1)
if not SENSOR_LWT_TOPIC:
    print(f"Warning ({CLIENT_ID}): Sensor LWT topic ('sensor_lwt') not found in config. LWT functionality will be disabled for {CLIENT_ID}.")

print(f"--- Sensor Client MQTTv5 ({CLIENT_ID}) ---")
# (Anda bisa menambahkan print info broker dari GLOBAL_SETTINGS.get("broker_address") jika mau)
print(f"Temperature Publish Topic: {TEMPERATURE_TOPIC_DATA}, QoS: {DEFAULT_QOS_SENSOR}")
if HUMIDITY_TOPIC_DATA: print(f"Humidity Publish Topic: {HUMIDITY_TOPIC_DATA}, QoS: {DEFAULT_QOS_SENSOR}")
if SENSOR_LWT_TOPIC:
    print(f"LWT Topic: {SENSOR_LWT_TOPIC}, QoS: {LWT_QOS_SENSOR}, Retain: {LWT_RETAIN_SENSOR}")
if TEMPERATURE_RESPONSE_BASE:
    print(f"Temperature data may be sent as REQUEST, expecting response on base: {TEMPERATURE_RESPONSE_BASE}")
if DEFAULT_MESSAGE_EXPIRY_SENSOR_DATA is not None:
    print(f"Default Message Expiry for data publishes (from settings): {DEFAULT_MESSAGE_EXPIRY_SENSOR_DATA}s")
print("-" * 30)

# Buat payload LWT di sini agar timestamp-nya update saat skrip dijalankan
SENSOR_LWT_PAYLOAD_ONLINE_str = json.dumps({"client_id": CLIENT_ID, "status": "online", "timestamp": time.time()}) if SENSOR_LWT_TOPIC else None
SENSOR_LWT_PAYLOAD_OFFLINE_UNEXPECTED_str = json.dumps({"client_id": CLIENT_ID, "status": "offline_unexpected", "timestamp": time.time()}) if SENSOR_LWT_TOPIC else None
# Template untuk offline graceful, timestamp akan diisi saat disconnect
SENSOR_LWT_PAYLOAD_OFFLINE_GRACEFUL_template = {"client_id": CLIENT_ID, "status": "offline_graceful"} if SENSOR_LWT_TOPIC else {}


active_sensor_requests = {} # {correlation_id: {details}}
is_connected_flag = False # Flag untuk menandakan koneksi sudah siap

def on_connect_sensor(client, userdata, flags, rc, properties=None):
    global is_connected_flag
    if rc == 0: # Koneksi berhasil
        is_connected_flag = True
        print(f"Sensor ({CLIENT_ID}): Custom on_connect. Connection logic activated. Ready to publish.")
    # _default_on_connect di mqtt_utils akan menghandle print detail koneksi dan publish LWT online

def on_message_sensor(client, userdata, msg):
    # Dipanggil jika sensor subscribe ke topic response dan menerima balasan
    global active_sensor_requests
    try:
        topic = msg.topic
        decoded_payload = ""
        try:
            decoded_payload = msg.payload.decode('utf-8')
        except UnicodeDecodeError:
            print(f"Sensor ({CLIENT_ID}) Warning: Could not decode response payload as UTF-8 on topic '{topic}'.")
            return

        print(f"\nSensor ({CLIENT_ID}) Received RESPONSE on '{topic}': {decoded_payload}")

        # Ambil CorrelationData dari properties pesan masuk
        correlation_id_resp = None
        if msg.properties and hasattr(msg.properties, 'CorrelationData'):
            correlation_id_resp = msg.properties.CorrelationData.decode('utf-8', errors='replace')
        
        if correlation_id_resp and correlation_id_resp in active_sensor_requests:
            request_details = active_sensor_requests.pop(correlation_id_resp) # Hapus setelah diproses
            print(f"  [RESPONSE MATCHED] For Temperature Data Request with Correlation ID: {correlation_id_resp}")
            try:
                response_data = json.loads(decoded_payload)
                print(f"  Parsed Response Data from Panel/Subscriber: {response_data}")
                # Lakukan sesuatu dengan response_data jika perlu
            except json.JSONDecodeError:
                print(f"  Response Data is not JSON (Raw): {decoded_payload}")
            
            # Unsubscribe dari topic response yang dinamis ini
            if client.is_connected(): # Pastikan masih konek sebelum unsubscribe
                client.unsubscribe(request_details['response_topic'])
                print(f"  Unsubscribed from dynamic response topic: {request_details['response_topic']}")
        else:
            print(f"  Message on topic '{topic}' was not a recognized response for this sensor or correlation ID mismatch.")

    except Exception as e:
        print(f"Sensor ({CLIENT_ID}) Error processing message from topic '{topic}': {e}")


def on_publish_sensor(client, userdata, mid, properties=None):
    # Callback ini dipanggil setelah konfirmasi dari broker (untuk QoS > 0)
    print(f"Sensor ({CLIENT_ID}) Message Published (mid: {mid}) - Confirmed by broker (for QoS > 0).")

def on_disconnect_sensor(client, userdata, rc, properties=None):
    global is_connected_flag
    is_connected_flag = False # Reset flag saat disconnect
    print(f"Sensor ({CLIENT_ID}) Disconnected from MQTT Broker (rc: {rc}).")
    # Jika rc != 0, mungkin ada masalah dan bisa coba reconnect di sini (logika lebih lanjut)

def run_sensor():
    global is_connected_flag
    is_connected_flag = False # Pastikan flag false di awal

    client = create_mqtt_client(
        client_id=CLIENT_ID,
        on_connect_custom=on_connect_sensor,
        on_message_custom=on_message_sensor, # Untuk menerima response
        on_publish_custom=on_publish_sensor,
        on_disconnect_custom=on_disconnect_sensor,
        lwt_topic=SENSOR_LWT_TOPIC,
        lwt_payload_online=SENSOR_LWT_PAYLOAD_ONLINE_str,
        lwt_payload_offline=SENSOR_LWT_PAYLOAD_OFFLINE_UNEXPECTED_str,
        lwt_qos=LWT_QOS_SENSOR,
        lwt_retain=LWT_RETAIN_SENSOR
    )
    if not client:
        print(f"Sensor ({CLIENT_ID}): Failed to create MQTT client from utils. Exiting.")
        return

    client.loop_start() # Penting untuk memproses callback dan network traffic
    print(f"Sensor ({CLIENT_ID}) started. Waiting for connection to be ready...")
    
    # Tunggu hingga koneksi benar-benar siap (flag di-set oleh on_connect_sensor)
    connection_timeout_seconds = 20 # Beri waktu lebih jika koneksi lambat
    start_wait_time = time.time()
    while not is_connected_flag and (time.time() - start_wait_time < connection_timeout_seconds):
        time.sleep(0.2) # Cek setiap 0.2 detik
    
    if not is_connected_flag:
        print(f"ERROR ({CLIENT_ID}): Failed to establish connection within {connection_timeout_seconds}s timeout. Exiting.")
        # Panggil disconnect_client dengan argumen yang benar
        disconnect_client(client, SENSOR_LWT_TOPIC, None, LWT_QOS_SENSOR, LWT_RETAIN_SENSOR, reason_string=f"Sensor {CLIENT_ID} connection timeout")
        return

    print(f"Sensor ({CLIENT_ID}) Connection ready. Publishing data...")
    print("-" * 30)
    msg_count = 0
    publish_interval = GLOBAL_SETTINGS.get("sensor_publish_interval", 5) # Ambil dari config jika ada, atau default 5 detik
    try:
        while True:
            if not is_connected_flag: # Jika koneksi putus di tengah jalan
                print(f"WARNING ({CLIENT_ID}): Connection lost. Pausing publish attempts. Paho-MQTT should be attempting to reconnect.")
                time.sleep(publish_interval) # Tunggu dan biarkan loop Paho mencoba reconnect
                continue # Coba lagi di iterasi berikutnya

            msg_count += 1
            current_timestamp = time.time()
            temperature_value = round(random.uniform(15.0, 38.0), 1) # Rentang suhu sedikit diubah
            
            # Payload data suhu
            temp_payload_dict = {"count": msg_count, "temperature": temperature_value, "unit": "C", "client_id": CLIENT_ID, "timestamp": current_timestamp}
            temp_payload_json = json.dumps(temp_payload_dict)
            
            # Properti untuk pesan suhu
            correlation_id_temp_req = None
            response_topic_temp_req = None
            user_props_temp = [("sensor_model", "VirtualThermo 2000"), ("location_grid", "A4")]
            content_type_temp = "application/json"
            # Message Expiry akan diambil dari DEFAULT_MESSAGE_EXPIRY_SENSOR_DATA oleh publish_message

            if TEMPERATURE_RESPONSE_BASE: # Jika sensor ingin mengirim data suhu sebagai request
                correlation_id_temp_req = str(uuid.uuid4())
                response_topic_temp_req = f"{TEMPERATURE_RESPONSE_BASE}{correlation_id_temp_req}"
                active_sensor_requests[correlation_id_temp_req] = {'response_topic': response_topic_temp_req, 'timestamp': current_timestamp}
                if client.is_connected():
                    (res_sub, mid_sub) = client.subscribe([(response_topic_temp_req, 1)]) # QoS untuk subscribe response
                    if res_sub == mqtt.MQTT_ERR_SUCCESS:
                         print(f"  Sensor ({CLIENT_ID}) Subscribed to '{response_topic_temp_req}' for temp response (MID: {mid_sub}).")
                    else:
                         print(f"  Sensor ({CLIENT_ID}) FAILED to subscribe to response topic '{response_topic_temp_req}' (Error: {res_sub}).")
            
            print(f"\nSensor ({CLIENT_ID}) Publishing Temperature (Msg #{msg_count}) to '{TEMPERATURE_TOPIC_DATA}'")
            result_temp = publish_message(
                client,
                topic=TEMPERATURE_TOPIC_DATA,
                payload=temp_payload_json,
                qos=DEFAULT_QOS_SENSOR,
                # retain=False, # Data sensor biasanya tidak di-retain kecuali ada kebutuhan khusus
                message_expiry_interval=DEFAULT_MESSAGE_EXPIRY_SENSOR_DATA, # Bisa juga di-override per pesan
                response_topic=response_topic_temp_req,
                correlation_data=correlation_id_temp_req.encode('utf-8') if correlation_id_temp_req else None,
                user_properties=user_props_temp,
                content_type=content_type_temp
            )
            
            if not (result_temp and result_temp.rc == mqtt.MQTT_ERR_SUCCESS):
                err_code_temp = result_temp.rc if result_temp else "N/A (Publish Failed)"
                print(f"  Failed to enqueue temperature message (Error: {err_code_temp})")
                # Cleanup jika publish request gagal
                if correlation_id_temp_req and correlation_id_temp_req in active_sensor_requests:
                    del active_sensor_requests[correlation_id_temp_req]
                    if response_topic_temp_req and client.is_connected(): client.unsubscribe(response_topic_temp_req)
            elif result_temp and correlation_id_temp_req: # Jika publish sukses dan ini adalah request
                print(f"  Temperature (mid: {result_temp.mid}) enqueued as REQUEST. Expecting response with Correlation ID: {correlation_id_temp_req}")
            elif result_temp: # Publish sukses tapi bukan request
                 print(f"  Temperature (mid: {result_temp.mid}) enqueued for publishing.")


            # Publikasi Data Kelembaban (jika topik dikonfigurasi)
            if HUMIDITY_TOPIC_DATA:
                humidity_value = round(random.uniform(30.0, 75.0), 1) # Rentang humidity
                hum_payload_dict = {"count": msg_count, "humidity": humidity_value, "unit": "%RH", "client_id": CLIENT_ID, "timestamp": current_timestamp}
                hum_payload_json = json.dumps(hum_payload_dict)
                
                print(f"Sensor ({CLIENT_ID}) Publishing Humidity (Msg #{msg_count}) to '{HUMIDITY_TOPIC_DATA}'")
                result_hum = publish_message(
                    client,
                    topic=HUMIDITY_TOPIC_DATA,
                    payload=hum_payload_json,
                    qos=DEFAULT_QOS_SENSOR,
                    message_expiry_interval=DEFAULT_MESSAGE_EXPIRY_SENSOR_DATA,
                    user_properties=[("sensor_model", "VirtualHygro 100")],
                    content_type="application/json"
                )
                if result_hum and result_hum.rc == mqtt.MQTT_ERR_SUCCESS:
                     print(f"  Humidity (mid: {result_hum.mid}) enqueued for publishing.")
                else:
                     err_code_hum = result_hum.rc if result_hum else "N/A (Publish Failed)"
                     print(f"  Failed to enqueue humidity message (Error: {err_code_hum})")

            time.sleep(publish_interval)
    except KeyboardInterrupt:
        print(f"\nSensor ({CLIENT_ID}) Exiting due to Ctrl+C...")
    except Exception as e:
        print(f"An error occurred in the sensor main loop: {e}")
    finally:
        print("-" * 30)
        # Cleanup subscriptions untuk response yang mungkin masih aktif
        if client and hasattr(client, 'is_connected') and client.is_connected():
            for corr_id, details in list(active_sensor_requests.items()): # Salin list untuk iterasi aman saat menghapus
                if client.is_connected(): # Cek lagi sebelum unsubscribe
                    print(f"  Cleaning up sensor's subscription for pending response: {details['response_topic']}")
                    client.unsubscribe(details['response_topic'])
        
        # Siapkan payload untuk LWT offline graceful
        payload_graceful_offline_final_str = None
        if SENSOR_LWT_TOPIC and SENSOR_LWT_PAYLOAD_OFFLINE_GRACEFUL_template: # Pastikan template ada
            temp_payload_offline = dict(SENSOR_LWT_PAYLOAD_OFFLINE_GRACEFUL_template) # Buat salinan
            temp_payload_offline["timestamp"] = time.time() # Update timestamp
            payload_graceful_offline_final_str = json.dumps(temp_payload_offline)
        
        disconnect_client(
            client,
            lwt_topic=SENSOR_LWT_TOPIC,
            lwt_payload_offline_graceful=payload_graceful_offline_final_str,
            lwt_qos=LWT_QOS_SENSOR,
            lwt_retain=LWT_RETAIN_SENSOR,
            reason_string=f"Sensor {CLIENT_ID} normal shutdown"
        )
        print(f"Sensor ({CLIENT_ID}) Disconnected by mqtt_utils.")

if __name__ == '__main__':
    run_sensor()