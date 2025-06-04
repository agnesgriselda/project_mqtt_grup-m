# agnesgriselda-project_mqtt_grup-m/benchmark_req_res.py
import argparse
import json
import time
import uuid
import random
import string
import statistics
from pathlib import Path
import sys
import threading
import os

# Ensure common module can be imported
COMMON_DIR = Path(__file__).resolve().parent / 'common'
sys.path.append(str(COMMON_DIR))
CONFIG_DIR = Path(__file__).resolve().parent / 'config' # For settings.json

if not COMMON_DIR.exists():
    print(f"Error: Common directory not found at {COMMON_DIR}")
    sys.exit(1)
if not CONFIG_DIR.exists():
    print(f"Error: Config directory not found at {CONFIG_DIR}")
    sys.exit(1)

from mqtt_utils import (
    create_mqtt_client, publish_message,
    subscribe_to_topics, disconnect_client,
    GLOBAL_SETTINGS as mqtt_global_settings # Renamed to avoid conflict
)
import paho.mqtt.client as mqtt # For MQTT_ERR_SUCCESS

# --- Benchmark Configuration (Defaults) ---
DEFAULT_NUM_REQUESTS = 100
DEFAULT_REQ_PAYLOAD_SIZE = 128  # bytes
DEFAULT_RES_PAYLOAD_SIZE = 128  # bytes
DEFAULT_QOS = 1
DEFAULT_REQUEST_TOPIC = "benchmark/request"
DEFAULT_RESPONSE_TOPIC_BASE = "benchmark/response/" # Requester appends /<correlation_id>
REQUEST_TIMEOUT_SECONDS = 5 # Timeout for a single request-response
INTER_REQUEST_DELAY_S = 0.0 # Delay between sending requests (0 for as fast as possible)

# --- Global state for Requester (managed per instance) ---
class RequesterState:
    def __init__(self):
        self.active_requests = {}  # {correlation_id: {"start_time": float, "event": threading.Event(), "rtt": None}}
        self.rtt_values = []
        self.successful_requests = 0
        self.timed_out_requests = 0
        self.publish_errors = 0
        self.subscribe_errors = 0
        self.client_id = f"benchmark_requester_{str(uuid.uuid4())[:8]}"
        self.connected_event = threading.Event()

# --- Global state for Responder (managed per instance) ---
class ResponderState:
    def __init__(self):
        self.client_id = f"benchmark_responder_{str(uuid.uuid4())[:8]}"
        self.processed_requests = 0
        self.publish_errors = 0
        self.connected_event = threading.Event()

# --- Helper Functions ---
def generate_payload(size):
    """Generates a random string payload of a given size."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=size))

# --- Responder Callbacks ---
def on_connect_responder(client, userdata, flags, rc, properties=None):
    state = userdata['state']
    if rc == 0:
        print(f"Responder ({state.client_id}): Connected to broker.")
        args = userdata['args']
        res, mid = subscribe_to_topics(client, [(args.request_topic, args.qos)])
        if res == mqtt.MQTT_ERR_SUCCESS:
            print(f"Responder ({state.client_id}): Subscribed to '{args.request_topic}' (QoS {args.qos})")
        else:
            print(f"Responder ({state.client_id}): Failed to subscribe to '{args.request_topic}'. Error code: {res}")
        state.connected_event.set()
    else:
        print(f"Responder ({state.client_id}): Connection failed. RC: {rc}")

def on_message_responder(client, userdata, msg):
    state = userdata['state']
    args = userdata['args']
    state.processed_requests += 1
    
    # print(f"Responder ({state.client_id}): Received request on '{msg.topic}'")

    response_topic_prop = getattr(msg.properties, 'ResponseTopic', None)
    correlation_data_prop_bytes = getattr(msg.properties, 'CorrelationData', None)

    if not response_topic_prop or not correlation_data_prop_bytes:
        # print(f"Responder ({state.client_id}): Missing ResponseTopic or CorrelationData. Ignoring.")
        return

    response_payload_str = generate_payload(args.res_payload_size)
    
    # Simulate some processing delay if needed
    # time.sleep(0.001) # 1ms

    pub_res = publish_message(
        client,
        topic=response_topic_prop,
        payload=response_payload_str,
        qos=args.qos,
        correlation_data=correlation_data_prop_bytes,
        content_type="text/plain" # Or application/octet-stream
    )
    if not (pub_res and pub_res.rc == mqtt.MQTT_ERR_SUCCESS):
        state.publish_errors +=1
        # print(f"Responder ({state.client_id}): Failed to publish response. MID: {pub_res.mid if pub_res else 'N/A'}")
    # else:
        # print(f"Responder ({state.client_id}): Sent response to '{response_topic_prop}' (CorrID: {correlation_data_prop_bytes.decode()[:8]})")


def run_responder(args):
    """Runs the responder client."""
    state = ResponderState()
    print(f"--- Responder Client ({state.client_id}) ---")
    print(f"Listening for requests on: {args.request_topic} (QoS {args.qos})")
    print(f"Response payload size: {args.res_payload_size} bytes")

    max_retries = 3
    retry_count = 0
    retry_delay = 2  # seconds

    while retry_count < max_retries:
        responder_client = create_mqtt_client(
            client_id=state.client_id,
            on_connect_custom=on_connect_responder,
            on_message_custom=on_message_responder,
            userdata={'state': state, 'args': args}
        )

        if not responder_client:
            print(f"Responder ({state.client_id}): Failed to create MQTT client. Retrying...")
            retry_count += 1
            time.sleep(retry_delay)
            continue

        state.connected_event.wait(timeout=10)
        if not responder_client.is_connected():
            print(f"Responder ({state.client_id}): Failed to connect to broker. Retrying...")
            disconnect_client(responder_client)
            retry_count += 1
            time.sleep(retry_delay)
            continue

        # Reset retry count on successful connection
        retry_count = 0

        try:
            while True:
                time.sleep(1)
                if not responder_client.is_connected():
                    print(f"Responder ({state.client_id}): Connection lost. Attempting to reconnect...")
                    break
        except KeyboardInterrupt:
            print(f"\nResponder ({state.client_id}): Shutting down...")
            break
        finally:
            disconnect_client(responder_client, reason_string="Responder normal shutdown")
            print(f"Responder ({state.client_id}): Disconnected. Processed {state.processed_requests} requests. Publish errors: {state.publish_errors}")

    if retry_count >= max_retries:
        print(f"Responder ({state.client_id}): Failed to connect after {max_retries} attempts. Exiting.")

# --- Requester Callbacks ---
def on_connect_requester(client, userdata, flags, rc, properties=None):
    state = userdata['state']
    if rc == 0:
        print(f"Requester ({state.client_id}): Connected to broker.")
        state.connected_event.set()
    else:
        print(f"Requester ({state.client_id}): Connection failed. RC: {rc}")

def on_message_requester(client, userdata, msg):
    state = userdata['state']
    # print(f"Requester ({state.client_id}): Received message on '{msg.topic}'")

    correlation_id_resp_bytes = getattr(msg.properties, 'CorrelationData', None)
    if not correlation_id_resp_bytes:
        return 

    correlation_id_resp = correlation_id_resp_bytes.decode('utf-8', errors='ignore')

    with threading.Lock(): # Protect access to shared active_requests
        if correlation_id_resp in state.active_requests:
            end_time = time.perf_counter()
            request_data = state.active_requests[correlation_id_resp]
            
            if not request_data.get("rtt_recorded", False): # Ensure RTT is recorded only once
                rtt = end_time - request_data['start_time']
                request_data['rtt'] = rtt
                request_data['rtt_recorded'] = True
                request_data['event'].set() # Signal the waiting thread
                # print(f"Requester ({state.client_id}): Response for {correlation_id_resp[:8]} received. RTT: {rtt*1000:.2f} ms")
        # else:
            # print(f"Requester ({state.client_id}): Received response for unknown/timed-out CorrelationID: {correlation_id_resp[:8]}")

def run_requester(args):
    """Runs the requester client and collects benchmark data."""
    state = RequesterState()
    print(f"--- Requester Client ({state.client_id}) ---")
    print(f"Sending {args.num_requests} requests to: {args.request_topic} (QoS {args.qos})")
    print(f"Expecting responses on base: {args.response_topic_base}")
    print(f"Request payload size: {args.req_payload_size} bytes")
    print(f"Response payload size: {args.res_payload_size} bytes (for responder config)")
    print(f"Inter-request delay: {args.inter_request_delay_s * 1000:.1f} ms")
    print(f"Timeout per request: {REQUEST_TIMEOUT_SECONDS}s")

    requester_client = create_mqtt_client(
        client_id=state.client_id,
        on_connect_custom=on_connect_requester,
        on_message_custom=on_message_requester, # This will handle all messages
        userdata={'state': state, 'args': args}
    )

    if not requester_client:
        print(f"Requester ({state.client_id}): Failed to create MQTT client. Exiting.")
        return

    state.connected_event.wait(timeout=10)
    if not requester_client.is_connected():
        print(f"Requester ({state.client_id}): Failed to connect to broker. Exiting.")
        disconnect_client(requester_client)
        return

    print(f"Requester ({state.client_id}): Starting benchmark...")
    total_benchmark_start_time = time.perf_counter()

    for i in range(args.num_requests):
        correlation_id = str(uuid.uuid4())
        dynamic_response_topic = f"{args.response_topic_base.rstrip('/')}/{correlation_id}"
        
        request_event = threading.Event()
        
        with threading.Lock():
            state.active_requests[correlation_id] = {
                'start_time': 0, # Will be set just before publish
                'event': request_event,
                'rtt': None,
                'rtt_recorded': False
            }

        # Subscribe to the unique response topic for this request
        sub_res, mid_sub = subscribe_to_topics(requester_client, [(dynamic_response_topic, args.qos)])
        if sub_res != mqtt.MQTT_ERR_SUCCESS:
            print(f"Requester ({state.client_id}): Failed to subscribe to {dynamic_response_topic}. Error: {sub_res}")
            with threading.Lock():
                del state.active_requests[correlation_id]
            state.subscribe_errors += 1
            if args.inter_request_delay_s > 0: time.sleep(args.inter_request_delay_s)
            continue # Skip this request

        request_payload_str = generate_payload(args.req_payload_size)
        
        with threading.Lock():
            state.active_requests[correlation_id]['start_time'] = time.perf_counter()

        pub_res = publish_message(
            requester_client,
            topic=args.request_topic,
            payload=request_payload_str,
            qos=args.qos,
            response_topic=dynamic_response_topic,
            correlation_data=correlation_id.encode('utf-8'),
            user_properties=[("benchmark_req_num", str(i+1))],
            content_type="text/plain"
        )

        if not (pub_res and pub_res.rc == mqtt.MQTT_ERR_SUCCESS):
            print(f"Requester ({state.client_id}): Failed to publish request {i+1}. MID: {pub_res.mid if pub_res else 'N/A'}")
            with threading.Lock():
                del state.active_requests[correlation_id]
            state.publish_errors += 1
            requester_client.unsubscribe(dynamic_response_topic)
            if args.inter_request_delay_s > 0: time.sleep(args.inter_request_delay_s)
            continue

        # Wait for the response or timeout
        if request_event.wait(timeout=REQUEST_TIMEOUT_SECONDS):
            with threading.Lock():
                rtt_val = state.active_requests[correlation_id].get('rtt')
            if rtt_val is not None:
                state.rtt_values.append(rtt_val)
                state.successful_requests += 1
            else: # Should not happen if event was set correctly
                # print(f"Requester ({state.client_id}): Event set for {correlation_id[:8]} but RTT not found.")
                state.timed_out_requests +=1 # Treat as timeout
        else:
            # print(f"Requester ({state.client_id}): Request {i+1} (CorrID: {correlation_id[:8]}) timed out.")
            state.timed_out_requests += 1
        
        requester_client.unsubscribe(dynamic_response_topic) # Clean up subscription
        with threading.Lock():
            if correlation_id in state.active_requests:
                del state.active_requests[correlation_id]
        
        if args.inter_request_delay_s > 0 and i < args.num_requests - 1 :
            time.sleep(args.inter_request_delay_s)
        
        if (i + 1) % 10 == 0 or (i + 1) == args.num_requests:
            print(f"Requester ({state.client_id}): Sent {i+1}/{args.num_requests} requests...")


    total_benchmark_end_time = time.perf_counter()
    total_duration = total_benchmark_end_time - total_benchmark_start_time

    # --- Print Results ---
    print("\n--- Benchmark Results ---")
    print(f"Total requests attempted: {args.num_requests}")
    print(f"Successful requests (response received): {state.successful_requests}")
    print(f"Timed-out requests: {state.timed_out_requests}")
    print(f"Publish errors: {state.publish_errors}")
    print(f"Subscribe errors: {state.subscribe_errors}")
    
    if state.rtt_values:
        min_rtt_ms = min(state.rtt_values) * 1000
        max_rtt_ms = max(state.rtt_values) * 1000
        avg_rtt_ms = statistics.mean(state.rtt_values) * 1000
        
        print(f"Minimum RTT: {min_rtt_ms:.3f} ms")
        print(f"Maximum RTT: {max_rtt_ms:.3f} ms")
        print(f"Average RTT: {avg_rtt_ms:.3f} ms")
        if len(state.rtt_values) > 1:
            stdev_rtt_ms = statistics.stdev(state.rtt_values) * 1000
            print(f"StdDev RTT: {stdev_rtt_ms:.3f} ms")
    else:
        print("No successful RTT measurements to report.")

    print(f"Total benchmark duration: {total_duration:.3f} seconds")
    if total_duration > 0 and state.successful_requests > 0:
        rps = state.successful_requests / total_duration
        print(f"Throughput (successful requests/sec): {rps:.2f} RPS")

    disconnect_client(requester_client, reason_string="Requester benchmark finished")
    print(f"Requester ({state.client_id}): Disconnected.")


# --- Main Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MQTT Request-Response Benchmark Tool. Uses settings from config/settings.json for broker connection.")
    parser.add_argument("role", choices=["requester", "responder"], help="Role to play: requester or responder.")
    parser.add_argument("--num_requests", type=int, default=DEFAULT_NUM_REQUESTS, help="Number of requests to send (requester only).")
    parser.add_argument("--req_payload_size", type=int, default=DEFAULT_REQ_PAYLOAD_SIZE, help="Size of request payload in bytes.")
    parser.add_argument("--res_payload_size", type=int, default=DEFAULT_RES_PAYLOAD_SIZE, help="Size of response payload in bytes.")
    parser.add_argument("--qos", type=int, choices=[0, 1, 2], default=DEFAULT_QOS, help="MQTT Quality of Service level for requests and responses.")
    parser.add_argument("--request_topic", type=str, default=DEFAULT_REQUEST_TOPIC, help="Topic to send requests on.")
    parser.add_argument("--response_topic_base", type=str, default=DEFAULT_RESPONSE_TOPIC_BASE, help="Base topic for responses. Requester appends /<correlation_id>.")
    parser.add_argument("--delay", type=float, default=INTER_REQUEST_DELAY_S, dest="inter_request_delay_s", help="Delay in seconds between sending requests (requester only). Default 0.")
    
    args = parser.parse_args()

    # Use global MQTT settings from mqtt_utils (which loads from config/settings.json)
    # No need to explicitly load settings.json here if mqtt_utils does it.
    # Check if settings were loaded
    if not mqtt_global_settings.get("broker_address"):
        print("FATAL ERROR: MQTT settings (e.g., broker_address) not loaded from config/settings.json via mqtt_utils.")
        print("Please ensure 'config/settings.json' is present and correct, and mqtt_utils.py loads it.")
        sys.exit(1)

    print(f"Using MQTT Broker: {mqtt_global_settings.get('broker_address')}:{mqtt_global_settings.get('mqtt_advanced_settings', {}).get('port_tls') if mqtt_global_settings.get('mqtt_advanced_settings', {}).get('use_tls') else mqtt_global_settings.get('broker_port', 1883)}")
    print(f"Using TLS: {mqtt_global_settings.get('mqtt_advanced_settings', {}).get('use_tls', False)}")
    print(f"Using Auth: {mqtt_global_settings.get('mqtt_advanced_settings', {}).get('use_auth', False)}")


    if args.role == "responder":
        run_responder(args)
    elif args.role == "requester":
        run_requester(args)
    else:
        parser.print_help()