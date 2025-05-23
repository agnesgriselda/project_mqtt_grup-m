# common/mqtt_utils.py
import paho.mqtt.client as mqtt
import ssl
import json
import time # Untuk LWT payload timestamp
from pathlib import Path
import os # Untuk path absolut sertifikat

# Import properties untuk MQTT v5
from paho.mqtt.properties import Properties
from paho.mqtt.packettypes import PacketTypes

# Path konfigurasi global (bisa diakses oleh semua modul yang mengimpor utils)
PROJECT_ROOT_DIR = Path(__file__).resolve().parent.parent # common -> project_root
CONFIG_FILE_PATH_GLOBAL = PROJECT_ROOT_DIR / 'config' / 'settings.json'

def load_settings():
    """Memuat pengaturan dari file settings.json global."""
    try:
        with open(CONFIG_FILE_PATH_GLOBAL, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"FATAL ERROR (mqtt_utils): Configuration file {CONFIG_FILE_PATH_GLOBAL} not found.")
        exit(1)
    except json.JSONDecodeError:
        print(f"FATAL ERROR (mqtt_utils): Could not decode JSON from {CONFIG_FILE_PATH_GLOBAL}.")
        exit(1)
    except Exception as e:
        print(f"FATAL ERROR (mqtt_utils): An unexpected error occurred while loading config: {e}")
        exit(1)

# Muat settings sekali saat modul diimpor
GLOBAL_SETTINGS = load_settings()

def create_mqtt_client(client_id, 
                       on_connect_custom=None, 
                       on_message_custom=None, 
                       on_disconnect_custom=None,
                       on_subscribe_custom=None,
                       on_publish_custom=None,
                       userdata=None,
                       lwt_topic=None, 
                       lwt_payload_online=None, # Payload untuk dipublish manual saat konek
                       lwt_payload_offline=None, # Payload untuk will_set
                       lwt_qos=1, 
                       lwt_retain=True):
    """
    Membuat, mengkonfigurasi, dan menghubungkan instance MQTT client dengan fitur MQTTv5.
    Mengembalikan client instance atau None jika gagal.
    """
    if not GLOBAL_SETTINGS:
        print("ERROR (mqtt_utils): Global settings not loaded, client cannot be created.")
        return None

    print(f"INFO (mqtt_utils): Creating MQTT client: {client_id} with MQTTv5 protocol.")
    try:
        client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv5, userdata=userdata)
    except TypeError as e:
        print(f"ERROR (mqtt_utils): Error creating MQTT client (check paho-mqtt version for MQTTv5 support): {e}")
        print("INFO (mqtt_utils): Falling back to default MQTT protocol.")
        client = mqtt.Client(client_id=client_id, userdata=userdata) # Fallback

    # --- Konfigurasi Advanced dari settings ---
    mqtt_adv_cfg = GLOBAL_SETTINGS.get("mqtt_advanced_settings", {})
    broker_address = GLOBAL_SETTINGS.get("broker_address", "localhost")
    default_port = GLOBAL_SETTINGS.get("broker_port", 1883)
    tls_port = mqtt_adv_cfg.get("port_tls", 8883)
    use_tls = mqtt_adv_cfg.get("use_tls", False)
    ca_cert_rel_path = mqtt_adv_cfg.get("ca_cert_path")
    client_cert_rel_path = mqtt_adv_cfg.get("client_cert_path") # Untuk mTLS
    client_key_rel_path = mqtt_adv_cfg.get("client_key_path")   # Untuk mTLS
    use_auth = mqtt_adv_cfg.get("use_auth", False)
    username = mqtt_adv_cfg.get("username")
    password = mqtt_adv_cfg.get("password")
    keepalive = mqtt_adv_cfg.get("keepalive", 60)
    receive_maximum = mqtt_adv_cfg.get("v5_receive_maximum", 10)

    # --- Set LWT (Will) ---
    if lwt_topic and lwt_payload_offline:
        print(f"INFO (mqtt_utils): Setting LWT for {client_id}: Topic='{lwt_topic}', QoS={lwt_qos}, Retain={lwt_retain}")
        client.will_set(lwt_topic, lwt_payload_offline, qos=lwt_qos, retain=lwt_retain)

    # --- Callback ---
    # Default callbacks (bisa di-override)
    def _default_on_connect(client_obj, user_data, flags, rc, properties=None):
        client_id_str = client_obj._client_id.decode() if isinstance(client_obj._client_id, bytes) else client_obj._client_id
        if rc == 0:
            print(f"INFO (mqtt_utils:{client_id_str}): Connected successfully (RC: {rc})")
            if properties: print(f"  Broker CONNECT Properties: {vars(properties)}")
            # Publish online status for LWT if provided
            if lwt_topic and lwt_payload_online:
                 publish_message(client_obj, lwt_topic, lwt_payload_online, qos=lwt_qos, retain=lwt_retain)
        else:
            print(f"ERROR (mqtt_utils:{client_id_str}): Connection failed (RC: {rc})")
            if rc == 3: print("  Server unavailable")
            elif rc == 4: print("  Bad username or password")
            elif rc == 5: print("  Not authorised")
        if on_connect_custom:
            on_connect_custom(client_obj, user_data, flags, rc, properties)

    client.on_connect = _default_on_connect
    if on_message_custom: client.on_message = on_message_custom
    if on_disconnect_custom: client.on_disconnect = on_disconnect_custom
    if on_subscribe_custom: client.on_subscribe = on_subscribe_custom
    if on_publish_custom: client.on_publish = on_publish_custom
    
    # --- Konfigurasi TLS ---
    current_broker_port = default_port
    if use_tls:
        print(f"INFO (mqtt_utils): Configuring TLS for {client_id}...")
        ca_cert_abs_path = None
        if ca_cert_rel_path:
            # Path sertifikat dibuat absolut dari root proyek
            ca_cert_abs_path_obj = PROJECT_ROOT_DIR / ca_cert_rel_path
            if ca_cert_abs_path_obj.exists():
                ca_cert_abs_path = str(ca_cert_abs_path_obj)
                print(f"  Using CA certificate: {ca_cert_abs_path}")
            else:
                print(f"  WARNING: CA certificate '{ca_cert_abs_path_obj}' not found. Will try system CAs.")
        else:
            print(f"  CA certificate path not specified. Will try system CAs.")

        client_cert_abs = PROJECT_ROOT_DIR / client_cert_rel_path if client_cert_rel_path else None
        client_key_abs = PROJECT_ROOT_DIR / client_key_rel_path if client_key_rel_path else None
        mTLS_enabled = client_cert_abs and client_key_abs and client_cert_abs.exists() and client_key_abs.exists()

        try:
            client.tls_set(
                ca_certs=ca_cert_abs_path, # Bisa None
                certfile=str(client_cert_abs) if mTLS_enabled else None,
                keyfile=str(client_key_abs) if mTLS_enabled else None,
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLS_CLIENT
            )
            current_broker_port = tls_port
            print(f"  TLS configured. Target port: {current_broker_port}.")
            if mTLS_enabled: print("  mTLS (Client Certificate Authentication) is configured.")
        except Exception as e_tls:
            print(f"  ERROR setting up TLS: {e_tls}. Connection might fail or use non-TLS.")
            # Fallback ke port non-TLS jika setup TLS gagal total? Atau biarkan gagal?
            # Untuk sekarang, biarkan current_broker_port tetap tls_port dan biarkan connect() gagal.

    # --- Konfigurasi Autentikasi ---
    if use_auth:
        if username and password and username != "YOUR_MQTT_USERNAME": # Cek placeholder
            print(f"INFO (mqtt_utils): Setting MQTT username: {username} for {client_id}")
            client.username_pw_set(username, password)
        else:
            print(f"  WARNING (mqtt_utils): 'use_auth' is true, but username/password are placeholders or not set for {client_id}.")

    # --- Koneksi ke Broker ---
    print(f"INFO (mqtt_utils): {client_id} attempting to connect to {broker_address}:{current_broker_port}...")
    try:
        connect_props = Properties(PacketTypes.CONNECT)
        connect_props.ReceiveMaximum = receive_maximum
        # connect_props.SessionExpiryInterval = 300 # Opsional
        client.connect(broker_address, current_broker_port, keepalive, properties=connect_props)
        return client # Kembalikan client jika connect() tidak raise exception
    except Exception as e_conn:
        print(f"ERROR (mqtt_utils): Could not connect {client_id} to broker: {e_conn}")
        return None # Kembalikan None jika koneksi gagal

def publish_message(client, topic, payload, qos=None, retain=False, 
                    message_expiry_interval=None, 
                    response_topic=None, correlation_data=None,
                    user_properties=None, content_type=None):
    """
    Mempublikasikan pesan dengan properti MQTTv5 opsional.
    user_properties: list of tuples, e.g., [('key1','value1')]
    """
    if not client or not client.is_connected(): # Perlu cek is_connected()
        print(f"ERROR (mqtt_utils): Client not connected. Cannot publish to '{topic}'.")
        return None

    actual_qos = qos if qos is not None else GLOBAL_SETTINGS.get("default_qos", 1)
    
    publish_props = Properties(PacketTypes.PUBLISH)
    has_props = False

    # Message Expiry
    actual_expiry = message_expiry_interval
    if actual_expiry is None: # Jika tidak di-override, gunakan default dari settings
        actual_expiry = GLOBAL_SETTINGS.get("mqtt_advanced_settings", {}).get("default_message_expiry_interval")
    
    if actual_expiry is not None and int(actual_expiry) > 0:
        publish_props.MessageExpiryInterval = int(actual_expiry)
        has_props = True

    # Request/Response
    if response_topic:
        publish_props.ResponseTopic = str(response_topic)
        has_props = True
    if correlation_data:
        if isinstance(correlation_data, str):
            correlation_data = correlation_data.encode('utf-8')
        publish_props.CorrelationData = correlation_data
        has_props = True
    
    if user_properties: # Harusnya list of tuples
        publish_props.UserProperty = user_properties
        has_props = True
    
    if content_type:
        publish_props.ContentType = str(content_type)
        has_props = True
    
    props_to_send = publish_props if has_props else None
    # print(f"DEBUG (mqtt_utils): Publishing to '{topic}' with QoS {actual_qos}, Retain {retain}, Props: {vars(props_to_send) if props_to_send else 'None'}")
    return client.publish(topic, payload, qos=actual_qos, retain=retain, properties=props_to_send)


def subscribe_to_topics(client, topics_with_qos_list, sub_properties=None):
    """
    Melakukan subscribe ke daftar topic.
    topics_with_qos_list: list of tuples, e.g., [("topic1", 1), ("topic2", 0)]
    sub_properties: Paho MQTT Properties object untuk SUBSCRIBE (opsional)
    """
    if not client or not client.is_connected():
        print("ERROR (mqtt_utils): Client not connected. Cannot subscribe.")
        return None
    if not topics_with_qos_list:
        print("INFO (mqtt_utils): No topics to subscribe to.")
        return None

    # print(f"DEBUG (mqtt_utils): Subscribing to: {topics_with_qos_list}")
    results = client.subscribe(topics_with_qos_list, properties=sub_properties)
    
    # Penanganan hasil subscribe di callback on_subscribe_custom lebih baik
    # Tapi bisa juga di-log di sini untuk debug cepat
    # if isinstance(results, list): ... (logging seperti di panel_client)
    return results

def disconnect_client(client, reason_string="Client shutting down normally", session_expiry_interval=0):
    """Menghentikan loop dan memutuskan koneksi client dengan properti DISCONNECT MQTTv5."""
    if client:
        client_id_str = client._client_id.decode() if hasattr(client, '_client_id') and isinstance(client._client_id, bytes) else str(getattr(client, '_client_id', 'UnknownClient'))
        print(f"INFO (mqtt_utils): Disconnecting client '{client_id_str}'...")
        client.loop_stop() # Hentikan loop network client
        if client.is_connected():
            disconnect_props = Properties(PacketTypes.DISCONNECT)
            disconnect_props.SessionExpiryInterval = session_expiry_interval
            if reason_string:
                disconnect_props.ReasonString = reason_string
            client.disconnect(properties=disconnect_props)
            print(f"INFO (mqtt_utils): Client '{client_id_str}' disconnect initiated.")
        else:
            print(f"INFO (mqtt_utils): Client '{client_id_str}' was already disconnected or not fully connected.")