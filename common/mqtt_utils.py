# common/mqtt_utils.py
import paho.mqtt.client as mqtt
import ssl
import json
import time # Untuk LWT payload timestamp
from pathlib import Path
import os # Untuk path absolut sertifikat

from paho.mqtt.properties import Properties
from paho.mqtt.packettypes import PacketTypes

PROJECT_ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE_PATH_GLOBAL = PROJECT_ROOT_DIR / 'config' / 'settings.json'

def load_settings():
    try:
        with open(CONFIG_FILE_PATH_GLOBAL, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"FATAL ERROR (mqtt_utils): Configuration file {CONFIG_FILE_PATH_GLOBAL} not found.")
        exit(1)
    except json.JSONDecodeError as e:
        print(f"FATAL ERROR (mqtt_utils): Could not decode JSON from {CONFIG_FILE_PATH_GLOBAL}. Error: {e}")
        exit(1)
    except Exception as e:
        print(f"FATAL ERROR (mqtt_utils): An unexpected error occurred while loading config: {e}")
        exit(1)

GLOBAL_SETTINGS = load_settings()

def create_mqtt_client(client_id,
                       on_connect_custom=None,
                       on_message_custom=None,
                       on_disconnect_custom=None,
                       on_subscribe_custom=None,
                       on_publish_custom=None,
                       userdata=None,
                       lwt_topic=None,
                       lwt_payload_online=None,
                       lwt_payload_offline=None,
                       lwt_qos=None,
                       lwt_retain=None):
    if not GLOBAL_SETTINGS:
        print("ERROR (mqtt_utils): Global settings not loaded.")
        return None

    print(f"INFO (mqtt_utils): Creating MQTT client: {client_id} with MQTTv5 protocol.")
    try:
        client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv5, userdata=userdata)
    except TypeError: # Fallback untuk Paho-MQTT versi lama yang mungkin tidak punya 'protocol'
        print("INFO (mqtt_utils): Falling back to default MQTT protocol (likely v3.1.1) for client creation.")
        client = mqtt.Client(client_id=client_id, userdata=userdata)


    mqtt_adv_cfg = GLOBAL_SETTINGS.get("mqtt_advanced_settings", {})
    broker_address = GLOBAL_SETTINGS.get("broker_address", "localhost")
    default_port = GLOBAL_SETTINGS.get("broker_port", 1883)
    tls_port = mqtt_adv_cfg.get("port_tls", 8883)
    use_tls = mqtt_adv_cfg.get("use_tls", False)
    ca_cert_rel_path = mqtt_adv_cfg.get("ca_cert_path")
    client_cert_rel_path = mqtt_adv_cfg.get("client_cert_path")
    client_key_rel_path = mqtt_adv_cfg.get("client_key_path")
    use_auth = mqtt_adv_cfg.get("use_auth", False)
    username = mqtt_adv_cfg.get("username")
    password = mqtt_adv_cfg.get("password")
    keepalive = mqtt_adv_cfg.get("keepalive", 60)
    receive_maximum = mqtt_adv_cfg.get("v5_receive_maximum", 10) # Untuk MQTTv5

    actual_lwt_qos = lwt_qos if lwt_qos is not None else GLOBAL_SETTINGS.get("lwt_qos", 1)
    actual_lwt_retain = lwt_retain if lwt_retain is not None else GLOBAL_SETTINGS.get("lwt_retain", True)

    if lwt_topic and lwt_payload_offline:
        print(f"INFO (mqtt_utils): Setting LWT for {client_id}: Topic='{lwt_topic}', QoS={actual_lwt_qos}, Retain={actual_lwt_retain}")
        client.will_set(lwt_topic, lwt_payload_offline, qos=actual_lwt_qos, retain=actual_lwt_retain)

    def _default_on_connect(client_obj, user_data_obj, flags_dict, rc_int, props_obj=None): # Nama argumen lebih deskriptif
        client_id_str = getattr(client_obj, '_client_id', 'UnknownClient')
        client_id_str = client_id_str.decode() if isinstance(client_id_str, bytes) else str(client_id_str)

        if rc_int == 0 or rc_int == mqtt.CONNACK_ACCEPTED: # mqtt.CONNACK_ACCEPTED adalah 0
            print(f"INFO (mqtt_utils:{client_id_str}): Connected successfully (RC: Success / {rc_int})")
            if props_obj: print(f"  Broker CONNECT Properties: {vars(props_obj)}")
            if lwt_topic and lwt_payload_online:
                 publish_message(client_obj, lwt_topic, lwt_payload_online, qos=actual_lwt_qos, retain=actual_lwt_retain)
        else:
            print(f"ERROR (mqtt_utils:{client_id_str}): Connection failed (RC: {rc_int})")
            # Tambahkan detail error berdasarkan RC
            if rc_int == 1: print("  Connection refused - incorrect protocol version")
            elif rc_int == 2: print("  Connection refused - invalid client identifier")
            elif rc_int == 3: print("  Connection refused - server unavailable")
            elif rc_int == 4: print("  Connection refused - bad username or password")
            elif rc_int == 5: print("  Connection refused - not authorised")
            else: print(f"  Connection refused - (Unknown RC: {rc_int})")

        if on_connect_custom:
            on_connect_custom(client_obj, user_data_obj, flags_dict, rc_int, props_obj)

    client.on_connect = _default_on_connect
    if on_message_custom: client.on_message = on_message_custom
    if on_disconnect_custom: client.on_disconnect = on_disconnect_custom
    if on_subscribe_custom: client.on_subscribe = on_subscribe_custom
    if on_publish_custom: client.on_publish = on_publish_custom
    
    current_broker_port = default_port
    if use_tls:
        print(f"INFO (mqtt_utils): Configuring TLS for {client_id}...")
        ca_cert_abs_path = None
        if ca_cert_rel_path:
            ca_cert_abs_path_obj = PROJECT_ROOT_DIR / ca_cert_rel_path
            if ca_cert_abs_path_obj.exists():
                ca_cert_abs_path = str(ca_cert_abs_path_obj)
                print(f"  Using CA certificate: {ca_cert_abs_path}")
            else:
                print(f"  WARNING: CA certificate '{ca_cert_abs_path_obj}' not found. TLS may fail or use system CAs.")
        else:
            print(f"  CA certificate path not specified. TLS will use system CAs or fail if server cert is self-signed.")

        client_cert_abs_obj = PROJECT_ROOT_DIR / client_cert_rel_path if client_cert_rel_path else None
        client_key_abs_obj = PROJECT_ROOT_DIR / client_key_rel_path if client_key_rel_path else None
        mTLS_enabled = client_cert_abs_obj and client_key_abs_obj and client_cert_abs_obj.exists() and client_key_abs_obj.exists()

        try:
            client.tls_set(
                ca_certs=ca_cert_abs_path,
                certfile=str(client_cert_abs_obj) if mTLS_enabled else None,
                keyfile=str(client_key_abs_obj) if mTLS_enabled else None,
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
                ciphers=None
            )
            client.tls_insecure_set(False)  # Disable insecure mode
            current_broker_port = tls_port
            print(f"  TLS configured. Target port: {current_broker_port}.")
            if mTLS_enabled: print("  mTLS (Client Certificate Authentication) is configured.")
        except Exception as e_tls:
            print(f"  ERROR setting up TLS: {e_tls}. Connection will likely fail if target port is TLS only.")

    if use_auth:
        if username and password and username not in ["YOUR_MQTT_USERNAME", ""]:
            print(f"INFO (mqtt_utils): Setting MQTT username: {username} for {client_id}")
            client.username_pw_set(username, password)
        else:
            print(f"  WARNING (mqtt_utils): 'use_auth' is true, but username/password are placeholders or not set for {client_id}. Autentikasi mungkin gagal.")

    print(f"INFO (mqtt_utils): {client_id} attempting to connect to {broker_address}:{current_broker_port}...")
    try:
        connect_props = None
        if hasattr(client, '_protocol') and client._protocol == mqtt.MQTTv5:
            connect_props = Properties(PacketTypes.CONNECT)
            if receive_maximum is not None:
                 connect_props.ReceiveMaximum = receive_maximum
        
        client.connect(broker_address, current_broker_port, keepalive, properties=connect_props)
        return client
    except ConnectionRefusedError as e_conn: # Lebih spesifik
        print(f"ERROR (mqtt_utils): Connection refused for {client_id} to {broker_address}:{current_broker_port}. Broker might not be running or port is wrong. Error: {e_conn}")
    except OSError as e_conn: # Untuk error jaringan lain seperti host tidak ditemukan
        print(f"ERROR (mqtt_utils): Network error for {client_id} connecting to {broker_address}:{current_broker_port}. Error: {e_conn}")
    except Exception as e_conn:
        print(f"ERROR (mqtt_utils): Could not connect {client_id} to broker ({broker_address}:{current_broker_port}): {e_conn}")
    return None # Eksplisit kembalikan None jika gagal

def publish_message(client, topic, payload, qos=None, retain=False,
                    message_expiry_interval=None,
                    response_topic=None, correlation_data=None,
                    user_properties=None, content_type=None):
    if not client:
        print(f"ERROR (mqtt_utils): Client object is None. Cannot publish to '{topic}'.")
        return None
    if not hasattr(client, 'is_connected') or not client.is_connected():
        print(f"ERROR (mqtt_utils): Client not connected. Cannot publish to '{topic}'.")
        return None

    actual_qos = qos if qos is not None else GLOBAL_SETTINGS.get("default_qos", 1)
    
    publish_props = None
    has_props = False

    if hasattr(client, '_protocol') and client._protocol == mqtt.MQTTv5:
        publish_props = Properties(PacketTypes.PUBLISH)
        actual_expiry_val_from_arg = message_expiry_interval
        
        final_expiry_interval = None
        if actual_expiry_val_from_arg is not None: # Prioritas argumen fungsi
            final_expiry_interval = actual_expiry_val_from_arg
        else: # Fallback ke global settings
            adv_settings = GLOBAL_SETTINGS.get("mqtt_advanced_settings", {})
            final_expiry_interval = adv_settings.get("default_message_expiry_interval")
        
        if final_expiry_interval is not None:
            try:
                expiry_int = int(final_expiry_interval)
                if expiry_int >= 0: # 0 berarti tidak kadaluarsa
                    publish_props.MessageExpiryInterval = expiry_int
                    has_props = True
            except ValueError:
                print(f"WARNING (mqtt_utils): Invalid value for message_expiry_interval: {final_expiry_interval}")
        
        if response_topic:
            publish_props.ResponseTopic = str(response_topic)
            has_props = True
        if correlation_data:
            if isinstance(correlation_data, str):
                correlation_data = correlation_data.encode('utf-8')
            publish_props.CorrelationData = correlation_data
            has_props = True
        if user_properties and isinstance(user_properties, list): # Pastikan list of tuples
            publish_props.UserProperty = user_properties
            has_props = True
        if content_type:
            publish_props.ContentType = str(content_type)
            has_props = True
        
        props_to_send = publish_props if has_props else None
    else:
        props_to_send = None
        if any([message_expiry_interval, response_topic, correlation_data, user_properties, content_type]):
             print(f"WARNING (mqtt_utils): Client is not MQTTv5. Properties for publish to '{topic}' will be ignored.")
    try:
        return client.publish(topic, payload, qos=actual_qos, retain=retain, properties=props_to_send)
    except Exception as e_pub:
        print(f"ERROR (mqtt_utils): Exception during publish to '{topic}': {e_pub}")
        return None

def subscribe_to_topics(client, topics_with_qos_list, sub_properties=None):
    if not client or not hasattr(client, 'is_connected') or not client.is_connected():
        print("ERROR (mqtt_utils): Client not connected. Cannot subscribe.")
        return None
    if not topics_with_qos_list:
        print("INFO (mqtt_utils): No topics to subscribe to.")
        return None
    
    props_to_send = sub_properties if hasattr(client, '_protocol') and client._protocol == mqtt.MQTTv5 else None
    try:
        return client.subscribe(topics_with_qos_list, properties=props_to_send)
    except Exception as e_sub:
        print(f"ERROR (mqtt_utils): Exception during subscribe: {e_sub}")
        return None

def disconnect_client(client,
                      lwt_topic=None,
                      lwt_payload_offline_graceful=None,
                      lwt_qos=None,
                      lwt_retain=None,
                      reason_code=0, # MQTTv5: 0 = Normal disconnection
                      reason_string="Client shutting down normally",
                      session_expiry_interval=0):
    if client:
        client_id_str = getattr(client, '_client_id', 'UnknownClient')
        client_id_str = client_id_str.decode() if isinstance(client_id_str, bytes) else str(client_id_str)
        
        print(f"INFO (mqtt_utils): Disconnecting client '{client_id_str}'...")

        if lwt_payload_offline_graceful and hasattr(client, 'is_connected') and client.is_connected():
            actual_lwt_topic = lwt_topic
            if not actual_lwt_topic: # Coba tebak dari client_id jika tidak diberikan
                prefix_to_remove = GLOBAL_SETTINGS.get('client_id_prefix', '').split('_v5_')[0]
                device_name = client_id_str.replace(prefix_to_remove, '').split('_')[0].lower()
                if device_name:
                    actual_lwt_topic = GLOBAL_SETTINGS.get("topics", {}).get(f"{device_name}_lwt")

            actual_lwt_qos = lwt_qos if lwt_qos is not None else GLOBAL_SETTINGS.get("lwt_qos", 1)
            actual_lwt_retain = lwt_retain if lwt_retain is not None else GLOBAL_SETTINGS.get("lwt_retain", True)

            if actual_lwt_topic:
                print(f"INFO (mqtt_utils): Publishing 'offline_graceful' LWT to '{actual_lwt_topic}' for '{client_id_str}'")
                publish_message(
                    client, topic=actual_lwt_topic, payload=lwt_payload_offline_graceful,
                    qos=actual_lwt_qos, retain=actual_lwt_retain
                )
                time.sleep(0.5) # Beri waktu pesan terkirim
            else:
                print(f"WARNING (mqtt_utils): Cannot publish 'offline_graceful' for '{client_id_str}', LWT topic not determined.")
        
        if hasattr(client, 'loop_stop') and callable(client.loop_stop): client.loop_stop()# Hentikan loop Paho v1.x
        # Untuk Paho v2.x, loop_stop() mungkin tidak ada atau berbeda, disconnect menangani loop.

        if hasattr(client, 'is_connected') and client.is_connected():
            disconnect_props = None
            is_v5_client = hasattr(client, '_protocol') and client._protocol == mqtt.MQTTv5
            
            if is_v5_client:
                disconnect_props = Properties(PacketTypes.DISCONNECT)
                disconnect_props.SessionExpiryInterval = session_expiry_interval
                if reason_string:
                    disconnect_props.ReasonString = reason_string
            
            try:
                print(f"INFO (mqtt_utils): Initiating disconnect for '{client_id_str}' (RC={reason_code}, Props={vars(disconnect_props) if disconnect_props else 'None'})")
                if is_v5_client:
                    client.disconnect(reasoncode=reason_code, properties=disconnect_props)
                else: # MQTTv3.1.1
                    client.disconnect()
                print(f"INFO (mqtt_utils): Client '{client_id_str}' disconnect command sent.")
            except Exception as e_disc:
                print(f"ERROR (mqtt_utils): Exception during client.disconnect() for '{client_id_str}': {e_disc}")
        else:
            print(f"INFO (mqtt_utils): Client '{client_id_str}' was already disconnected or not fully connected.")