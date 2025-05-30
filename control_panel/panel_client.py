import paho.mqtt.client as mqtt
import json
import time
import uuid
from pathlib import Path
import sys

COMMON_DIR = Path(__file__).resolve().parent.parent / 'common'
sys.path.append(str(COMMON_DIR))

from mqtt_utils import (
    GLOBAL_SETTINGS, create_mqtt_client, publish_message,
    subscribe_to_topics, disconnect_client
)

# Konfigurasi (sama seperti versi terakhir)
broker_address_cfg = GLOBAL_SETTINGS.get("broker_address")
topics_config = GLOBAL_SETTINGS.get("topics", {})
TEMPERATURE_TOPIC = topics_config.get("temperature")
LAMP_COMMAND_TOPIC = topics_config.get("lamp_command")
LAMP_STATUS_TOPIC = topics_config.get("lamp_status")
SENSOR_LWT_TOPIC = topics_config.get("sensor_lwt")
LAMP_LWT_TOPIC = topics_config.get("lamp_lwt")
PANEL_LWT_TOPIC = topics_config.get("panel_lwt")
HUMIDITY_TOPIC_DATA = topics_config.get("humidity_data")
LAMP_COMMAND_RESPONSE_BASE = topics_config.get("lamp_command_response_base")
TEMPERATURE_RESPONSE_BASE = topics_config.get("temperature_response_base")

panel_specific_cfg = GLOBAL_SETTINGS.get("panel_specific_settings", {})
PANEL_SUBSCRIBED_TOPICS_STR_LIST = panel_specific_cfg.get("subscribed_topics_list", [])

CLIENT_ID_PREFIX = GLOBAL_SETTINGS.get('client_id_prefix', 'panel_m5_')
CLIENT_ID = f"{CLIENT_ID_PREFIX}{str(uuid.uuid4())[:8]}"
DEFAULT_QOS_PANEL = GLOBAL_SETTINGS.get("default_qos", 1)
LWT_QOS_PANEL = GLOBAL_SETTINGS.get("lwt_qos", 1)
LWT_RETAIN_PANEL = GLOBAL_SETTINGS.get("lwt_retain", True)

mqtt_advanced_cfg = GLOBAL_SETTINGS.get("mqtt_advanced_settings", {})
DEFAULT_MESSAGE_EXPIRY_PANEL_CMD = mqtt_advanced_cfg.get("default_message_expiry_interval")

# Variabel untuk menyimpan status terakhir (agar tampilan lebih rapi)
last_temperature = "N/A"
last_humidity = "N/A"
last_lamp_state = "N/A"
sensor_connection_status = "UNKNOWN"
lamp_connection_status = "UNKNOWN"

print(f"--- Panel Client MQTTv5 ({CLIENT_ID}) ---")
print(f"Target Broker: {broker_address_cfg} (Port ditentukan oleh TLS setting)")
# ... (print info topik lainnya jika perlu, tapi bisa dikurangi) ...
print("-" * 30)

PANEL_LWT_PAYLOAD_ONLINE_str = json.dumps({"client_id": CLIENT_ID, "status": "online", "timestamp": time.time()}) if PANEL_LWT_TOPIC else None
PANEL_LWT_PAYLOAD_OFFLINE_UNEXPECTED_str = json.dumps({"client_id": CLIENT_ID, "status": "offline_unexpected", "timestamp": time.time()}) if PANEL_LWT_TOPIC else None
PANEL_LWT_PAYLOAD_OFFLINE_GRACEFUL_template = {"client_id": CLIENT_ID, "status": "offline_graceful"} if PANEL_LWT_TOPIC else {}

active_panel_requests = {}
is_panel_connected_flag = False

def display_dashboard():
    """Fungsi untuk menampilkan status terkini secara rapi."""
    print("\n--- MQTT DASHBOARD ---")
    print(f"  Panel Status:   {'CONNECTED' if is_panel_connected_flag else 'DISCONNECTED'}")
    print(f"  Sensor Status:  {sensor_connection_status}")
    print(f"  Lamp Status:    {lamp_connection_status}")
    print("  --------------------")
    print(f"  Temperature:    {last_temperature}")
    print(f"  Humidity:       {last_humidity}")
    print(f"  Lamp State:     {last_lamp_state}")
    print("------------------------")
    if LAMP_COMMAND_TOPIC:
        print("Enter lamp command (ON/OFF/TOGGLE/INVALID/EXIT): ", end='', flush=True)

def on_connect_panel(client, userdata, flags, rc, properties=None):
    global is_panel_connected_flag
    if rc == 0:
        is_panel_connected_flag = True
        print(f"\nPanel ({CLIENT_ID}): Successfully connected to broker. Subscribing to topics...")
        
        topics_to_subscribe_tuples = []
        all_relevant_topics_str = set(PANEL_SUBSCRIBED_TOPICS_STR_LIST)
        if TEMPERATURE_TOPIC: all_relevant_topics_str.add(TEMPERATURE_TOPIC)
        if HUMIDITY_TOPIC_DATA: all_relevant_topics_str.add(HUMIDITY_TOPIC_DATA)
        if LAMP_STATUS_TOPIC: all_relevant_topics_str.add(LAMP_STATUS_TOPIC)
        if SENSOR_LWT_TOPIC: all_relevant_topics_str.add(SENSOR_LWT_TOPIC)
        if LAMP_LWT_TOPIC: all_relevant_topics_str.add(LAMP_LWT_TOPIC)

        for topic_name_str in all_relevant_topics_str:
            if topic_name_str:
                current_qos = LWT_QOS_PANEL if "lwt" in topic_name_str.lower() else DEFAULT_QOS_PANEL
                topics_to_subscribe_tuples.append((topic_name_str, current_qos))
        
        if topics_to_subscribe_tuples:
            subscribe_to_topics(client, topics_to_subscribe_tuples)
        display_dashboard() # Tampilkan dashboard setelah konek
    else:
        print(f"Panel ({CLIENT_ID}): Connection failed! RC: {rc}")
        is_panel_connected_flag = False
        display_dashboard()


def on_message_panel(client, userdata, msg):
    global last_temperature, last_humidity, last_lamp_state, sensor_connection_status, lamp_connection_status, active_panel_requests
    
    topic = msg.topic
    decoded_payload = ""
    try:
        decoded_payload = msg.payload.decode('utf-8')
    except UnicodeDecodeError:
        print(f"\n[ERROR] Panel ({CLIENT_ID}): Could not decode payload on '{topic}'.")
        return

    print(f"\n[MESSAGE] Panel ({CLIENT_ID}) received on '{topic}' (Retain: {msg.retain}):")
    # print(f"  Raw Payload: {decoded_payload}") # Kurangi verbosity, tampilkan jika perlu debug

    parsed_data = None
    try:
        if decoded_payload: parsed_data = json.loads(decoded_payload)
    except json.JSONDecodeError:
        # Bisa jadi LWT string sederhana atau payload lain
        pass 

    # 1. Cek apakah ini adalah respons untuk request yang dikirim panel
    correlation_id_resp = getattr(msg.properties, 'CorrelationData', b'').decode('utf-8', errors='replace') if msg.properties else None
    if correlation_id_resp and correlation_id_resp in active_panel_requests:
        request_details = active_panel_requests.pop(correlation_id_resp)
        print(f"  [RESPONSE] For command '{request_details.get('command', 'N/A')}' (CorrID: {correlation_id_resp}):")
        if parsed_data:
            print(f"    Data: {parsed_data}")
            if parsed_data.get("error_code"):
                print(f"    Status: ERROR - {parsed_data.get('message', 'No error message.')}")
            elif "new_lamp_state" in parsed_data: # Respons sukses dari lampu
                last_lamp_state = str(parsed_data.get('new_lamp_state')).upper()
                print(f"    Status: SUCCESS - Lamp is now {last_lamp_state}")
            # Tambahkan penanganan untuk response dari sensor jika perlu
        else:
            print(f"    Data (Raw): {decoded_payload}") # Jika response tidak JSON
        
        if client.is_connected(): client.unsubscribe(request_details['response_topic'])
        display_dashboard() # Update tampilan
        return

    # 2. Jika bukan response, proses sebagai pesan reguler / LWT / Status
    if parsed_data:
        device_id_from_payload = parsed_data.get("client_id", "UnknownDevice")
        status_from_payload = parsed_data.get("status", "").upper() # Untuk LWT JSON
        state_from_payload = parsed_data.get("state", "").upper()   # Untuk status lampu reguler

        if TEMPERATURE_TOPIC and topic == TEMPERATURE_TOPIC:
            temp_val = parsed_data.get("temperature")
            if temp_val is not None: 
                last_temperature = f"{temp_val}°{parsed_data.get('unit','C')}"
                print(f"  [DATA] Temperature Update: {last_temperature} from {device_id_from_payload}")
            # Logika untuk merespons request suhu dari sensor
            response_topic_req = getattr(msg.properties, 'ResponseTopic', None) if msg.properties else None
            correlation_data_req_bytes = getattr(msg.properties, 'CorrelationData', None) if msg.properties else None
            if response_topic_req:
                print(f"  [INFO] Temperature data from {device_id_from_payload} is a REQUEST. Sending ACK...")
                ack_payload = {"status": "temperature_acknowledged_by_panel", "panel_id": CLIENT_ID, "ack_timestamp": time.time()}
                publish_message(client, response_topic_req, json.dumps(ack_payload), qos=DEFAULT_QOS_PANEL, correlation_data=correlation_data_req_bytes, message_expiry_interval=60)
        
        elif HUMIDITY_TOPIC_DATA and topic == HUMIDITY_TOPIC_DATA:
            hum_val = parsed_data.get("humidity")
            if hum_val is not None:
                last_humidity = f"{hum_val}{parsed_data.get('unit','%RH')}"
                print(f"  [DATA] Humidity Update: {last_humidity} from {device_id_from_payload}")

        elif LAMP_STATUS_TOPIC and topic == LAMP_STATUS_TOPIC:
            if state_from_payload:
                last_lamp_state = state_from_payload
                print(f"  [STATUS] Lamp Regular Status Update: Lamp is {last_lamp_state} (from {device_id_from_payload})")

        elif SENSOR_LWT_TOPIC and topic == SENSOR_LWT_TOPIC:
            sensor_connection_status = status_from_payload if status_from_payload else "STATE_UNKNOWN"
            print(f"  [LWT] Sensor ({device_id_from_payload}) Connection Status: {sensor_connection_status}")

        elif LAMP_LWT_TOPIC and topic == LAMP_LWT_TOPIC:
            lamp_connection_status = status_from_payload if status_from_payload else "STATE_UNKNOWN"
            print(f"  [LWT] Lamp ({device_id_from_payload}) Connection Status: {lamp_connection_status}")
        
        # (Tambahkan penanganan untuk PANEL_LWT_TOPIC jika perlu)
        else:
            print(f"  [INFO] Received JSON on unhandled subscribed topic '{topic}': {parsed_data}")
    
    elif topic in [SENSOR_LWT_TOPIC, LAMP_LWT_TOPIC, PANEL_LWT_TOPIC] and decoded_payload: # LWT string sederhana
        # Ini fallback jika LWT dikirim sebagai string "online" / "offline"
        status_str = decoded_payload.upper()
        print(f"  [LWT-Simple] Status on '{topic}': {status_str}")
        if SENSOR_LWT_TOPIC and topic == SENSOR_LWT_TOPIC: sensor_connection_status = status_str
        elif LAMP_LWT_TOPIC and topic == LAMP_LWT_TOPIC: lamp_connection_status = status_str
    
    elif decoded_payload: # Pesan lain yang tidak JSON dan tidak LWT yang dikenal
         print(f"  [INFO] Received unhandled non-JSON message on '{topic}'")

    display_dashboard() # Update tampilan setelah memproses pesan

def on_subscribe_panel(client, userdata, mid, granted_qos, properties=None):
    print(f"\n[INFO] Panel ({CLIENT_ID}) Subscription Confirmed (mid: {mid}). Granted QoS: {granted_qos}")
    display_dashboard()

def on_publish_panel(client, userdata, mid, properties=None):
    print(f"\n[INFO] Panel ({CLIENT_ID}) Message/Command Published (mid: {mid}). Waiting for broker confirmation...")
    # Tidak update dashboard di sini, tunggu response atau status update

def on_disconnect_panel(client, userdata, rc, properties=None):
    global is_panel_connected_flag, sensor_connection_status, lamp_connection_status
    is_panel_connected_flag = False
    sensor_connection_status = "DISCONNECTED (Panel Offline)" # Asumsi jika panel offline
    lamp_connection_status = "DISCONNECTED (Panel Offline)"
    print(f"\n[CRITICAL] Panel ({CLIENT_ID}) Disconnected from MQTT Broker (rc: {rc}).")
    display_dashboard()

def run_panel():
    global is_panel_connected_flag; is_panel_connected_flag = False
    # (Definisi payload LWT panel sama seperti sebelumnya)
    PANEL_LWT_PAYLOAD_ONLINE_str = json.dumps({"client_id": CLIENT_ID, "status": "online", "timestamp": time.time()}) if PANEL_LWT_TOPIC else None
    PANEL_LWT_PAYLOAD_OFFLINE_UNEXPECTED_str = json.dumps({"client_id": CLIENT_ID, "status": "offline_unexpected", "timestamp": time.time()}) if PANEL_LWT_TOPIC else None
    PANEL_LWT_PAYLOAD_OFFLINE_GRACEFUL_template = {"client_id": CLIENT_ID, "status": "offline_graceful"} if PANEL_LWT_TOPIC else {}


    client = create_mqtt_client(CLIENT_ID, on_connect_panel, on_message_panel, on_disconnect_panel, on_subscribe_custom=on_subscribe_panel, on_publish_custom=on_publish_panel, lwt_topic=PANEL_LWT_TOPIC, lwt_payload_online=PANEL_LWT_PAYLOAD_ONLINE_str, lwt_payload_offline=PANEL_LWT_PAYLOAD_OFFLINE_UNEXPECTED_str, lwt_qos=LWT_QOS_PANEL, lwt_retain=LWT_RETAIN_PANEL)
    if not client: return

    client.loop_start()
    print(f"Panel ({CLIENT_ID}) attempting to connect. Waiting for connection status...")
    
    connection_timeout_seconds = 15; start_wait_time = time.time()
    while not is_panel_connected_flag and (time.time() - start_wait_time < connection_timeout_seconds): time.sleep(0.1)
    
    if not is_panel_connected_flag:
        print(f"ERROR ({CLIENT_ID}): Panel connection timeout. Exiting.")
        disconnect_client(client, PANEL_LWT_TOPIC, None, LWT_QOS_PANEL, LWT_RETAIN_PANEL, reason_string=f"Panel {CLIENT_ID} connection timeout")
        return
    # display_dashboard() sudah dipanggil di on_connect jika berhasil

    try:
        if LAMP_COMMAND_TOPIC:
            while True: # Loop input perintah
                # Prompt sudah ditampilkan oleh display_dashboard()
                cmd_input = input().strip().upper() # Hanya baca input
                if cmd_input == "EXIT": break
                if cmd_input in ["ON", "OFF", "TOGGLE", "INVALIDCMD"]: # Tambah INVALIDCMD untuk tes error
                    print(f"\n[COMMAND] Panel ({CLIENT_ID}) Sending '{cmd_input}' to lamp...")
                    correlation_id_lamp, response_topic_for_lamp_cmd = None, None
                    if LAMP_COMMAND_RESPONSE_BASE:
                        correlation_id_lamp = str(uuid.uuid4())
                        response_topic_for_lamp_cmd = f"{LAMP_COMMAND_RESPONSE_BASE}{correlation_id_lamp}"
                        active_panel_requests[correlation_id_lamp] = {'response_topic': response_topic_for_lamp_cmd, 'command': cmd_input}
                        if client.is_connected(): subscribe_to_topics(client, [(response_topic_for_lamp_cmd, 1)])
                    
                    result = publish_message(client, LAMP_COMMAND_TOPIC, cmd_input, qos=DEFAULT_QOS_PANEL, message_expiry_interval=DEFAULT_MESSAGE_EXPIRY_PANEL_CMD, response_topic=response_topic_for_lamp_cmd, correlation_data=correlation_id_lamp.encode('utf-8') if correlation_id_lamp else None, user_properties=[("command_source", CLIENT_ID)], content_type="text/plain")
                    
                    if not (result and result.rc == mqtt.MQTT_ERR_SUCCESS):
                        print(f"  [ERROR] Failed to send command '{cmd_input}'.")
                        if correlation_id_lamp and correlation_id_lamp in active_panel_requests: del active_panel_requests[correlation_id_lamp]
                        if response_topic_for_lamp_cmd and client.is_connected(): client.unsubscribe(response_topic_for_lamp_cmd)
                    elif correlation_id_lamp:
                         print(f"  Command '{cmd_input}' sent as REQUEST. Expecting response (CorrID: {correlation_id_lamp[:8]}...).")
                    display_dashboard() # Update tampilan setelah kirim perintah
                elif cmd_input: # Jika input tidak kosong tapi bukan exit atau perintah valid
                    print(f"  [ERROR] Invalid command: '{cmd_input}'. Options: ON, OFF, TOGGLE, INVALIDCMD, EXIT.")
                    display_dashboard()
        else:
            print("Panel ({CLIENT_ID}) No lamp command topic. Running in listen-only mode.")
            while True: time.sleep(60); display_dashboard() # Refresh dashboard berkala
    except KeyboardInterrupt: print(f"\nPanel ({CLIENT_ID}) Exiting...")
    except Exception as e: print(f"Panel main loop error: {e}")
    finally:
        print("-" * 30)
        # ... (Cleanup active_panel_requests sama seperti sebelumnya) ...
        payload_graceful_offline_final_str = None
        if PANEL_LWT_TOPIC and PANEL_LWT_PAYLOAD_OFFLINE_GRACEFUL_template:
            # ... (buat payload graceful offline sama seperti sebelumnya) ...
            pass # Placeholder untuk brevity

        disconnect_client(client, lwt_topic=PANEL_LWT_TOPIC, lwt_payload_offline_graceful=payload_graceful_offline_final_str, lwt_qos=LWT_QOS_PANEL, lwt_retain=LWT_RETAIN_PANEL, reason_string=f"Panel {CLIENT_ID} normal shutdown")
        print(f"Panel ({CLIENT_ID}) Disconnected.")

if __name__ == '__main__': run_panel()