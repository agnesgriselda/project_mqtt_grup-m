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
import ssl
import logging
from typing import Dict, Any, Optional, Tuple

# Ensure common module can be imported
COMMON_DIR = Path(__file__).resolve().parent / 'common'
sys.path.append(str(COMMON_DIR))
CONFIG_DIR = Path(__file__).resolve().parent / 'config'

try:
    from mqtt_utils import (
        create_mqtt_client as original_create_mqtt_client,
        publish_message,
        subscribe_to_topics,
        disconnect_client as mqtt_utils_disconnect_client,  # Renamed to avoid collision
        GLOBAL_SETTINGS as mqtt_global_settings
    )
    import paho.mqtt.client as mqtt
    from paho.mqtt.properties import Properties
    from paho.mqtt.packettypes import PacketTypes 
except ImportError as e:
    print(f"Failed to import from mqtt_utils or paho.mqtt: {e}")
    sys.exit(1)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Benchmark Configuration (Defaults) ---
DEFAULT_NUM_REQUESTS = 100
DEFAULT_REQ_PAYLOAD_SIZE = 128  # bytes
DEFAULT_RES_PAYLOAD_SIZE = 128  # bytes
DEFAULT_QOS = 1
DEFAULT_REQUEST_TOPIC = "benchmark/request"
DEFAULT_RESPONSE_TOPIC_BASE = "benchmark/response/" 
REQUEST_TIMEOUT_SECONDS = 50 
INTER_REQUEST_DELAY_S = 0.0 
SUBSCRIPTION_TIMEOUT = 10  # seconds to wait for SUBACK

class RequesterState:
    def __init__(self):
        self.active_requests: Dict[str, Dict[str, Any]] = {}
        self.rtt_values = []
        self.successful_requests = 0
        self.timed_out_requests = 0
        self.publish_errors = 0
        self.subscribe_errors = 0
        self.client_id = f"benchmark_requester_{str(uuid.uuid4())[:8]}"
        self.connected_event = threading.Event()
        self.disconnected_event = threading.Event()
        self.lock = threading.RLock()  # Use RLock for nested locking

class ResponderState:
    def __init__(self):
        self.client_id = f"benchmark_responder_{str(uuid.uuid4())[:8]}"
        self.processed_requests = 0
        self.publish_errors = 0
        self.connected_event = threading.Event()
        self.disconnected_event = threading.Event()

def generate_payload(size: int) -> str:
    """Generate random payload of specified size."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=size))

def safe_disconnect_client(client: Optional[mqtt.Client], reason_string: str = "Client shutting down normally") -> None:
    """Safely disconnect MQTT client with proper error handling."""
    if not client:
        return
        
    try:
        # Check if client is connected before attempting operations
        if hasattr(client, '_sock') and client._sock is not None:
            if hasattr(client, 'loop_stop'):
                client.loop_stop()
                
            # Create disconnect properties for MQTTv5
            try:
                disconnect_props = Properties(PacketTypes.DISCONNECT)
                disconnect_props.ReasonString = reason_string
                client.disconnect(properties=disconnect_props)
            except Exception as props_error:
                # Fallback to simple disconnect for MQTTv3.1.1 compatibility
                logger.warning(f"Properties disconnect failed, using simple disconnect: {props_error}")
                client.disconnect()
        else:
            logger.debug("Client already disconnected")
            
    except Exception as e:
        logger.warning(f"Error during disconnect: {e}")

def create_benchmark_mqtt_client(
    client_id: str, 
    on_connect_custom: Optional[callable], 
    on_message_custom: Optional[callable], 
    on_disconnect_custom: Optional[callable], 
    userdata: Dict[str, Any], 
    benchmark_args: argparse.Namespace
) -> Optional[mqtt.Client]:
    """Creates an MQTT client specifically for benchmark with proper error handling."""
    
    logger.info(f"Creating MQTT client: {client_id} with MQTTv5 protocol for benchmark")
    
    try:
        # Try new callback API first
        try:
            client = mqtt.Client(
                client_id=client_id, 
                protocol=mqtt.MQTTv5, 
                userdata=userdata, 
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2
            )
        except (TypeError, AttributeError):
            # Fallback with consistent protocol
            logger.warning("New callback API not available, using legacy API with MQTTv5")
            client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv5, userdata=userdata)
    except Exception as e:
        logger.error(f"Failed to create MQTT client: {e}")
        return None

    # Set up connection callback with error handling
    def _benchmark_on_connect(client_obj, user_data_obj, flags_dict, rc_int, props_obj=None):
        if rc_int == 0:
            logger.info(f"Client {client_id}: Connected successfully (RC: {rc_int})")
        else:
            logger.error(f"Client {client_id}: Connection failed (RC: {rc_int})")
        
        if on_connect_custom:
            try:
                on_connect_custom(client_obj, user_data_obj, flags_dict, rc_int, props_obj)
            except Exception as e:
                logger.error(f"Error in custom on_connect callback: {e}")

    # Set up callbacks
    client.on_connect = _benchmark_on_connect
    if on_message_custom: 
        client.on_message = on_message_custom
    if on_disconnect_custom: 
        client.on_disconnect = on_disconnect_custom

    # Configure connection parameters
    broker_address = benchmark_args.bench_broker_host
    current_broker_port = benchmark_args.bench_broker_port
    keepalive = mqtt_global_settings.get("mqtt_advanced_settings", {}).get("keepalive", 60)
    receive_maximum = mqtt_global_settings.get("mqtt_advanced_settings", {}).get("v5_receive_maximum", 10)

    # Configure TLS if needed
    if benchmark_args.bench_use_tls:
        logger.info("Configuring TLS for benchmark")
        ca_cert_path_for_bench = (
            benchmark_args.bench_ca_cert or 
            mqtt_global_settings.get("mqtt_advanced_settings", {}).get("ca_cert_path")
        )
        
        ca_cert_abs_path = None
        if ca_cert_path_for_bench:
            ca_cert_abs_path_obj = Path(ca_cert_path_for_bench)
            if not ca_cert_abs_path_obj.is_absolute():
                ca_cert_abs_path_obj = COMMON_DIR.parent / ca_cert_path_for_bench

            if ca_cert_abs_path_obj.exists():
                ca_cert_abs_path = str(ca_cert_abs_path_obj)
                logger.info(f"Using CA certificate: {ca_cert_abs_path}")
            else:
                logger.warning(f"CA certificate not found: {ca_cert_abs_path_obj}")
        
        try:
            # Try different SSL versions for compatibility
            ssl_version = getattr(ssl, 'PROTOCOL_TLS_CLIENT', ssl.PROTOCOL_TLS)
            client.tls_set(
                ca_certs=ca_cert_abs_path, 
                cert_reqs=ssl.CERT_REQUIRED, 
                tls_version=ssl_version
            )
        except Exception as e_tls:
            logger.error(f"TLS setup failed: {e_tls}")
            return None
    else:
        logger.info("TLS disabled for benchmark")

    # Set authentication
    if benchmark_args.bench_username and benchmark_args.bench_password:
        logger.info(f"Setting authentication for client {client_id}")
        client.username_pw_set(benchmark_args.bench_username, benchmark_args.bench_password)

    # Connect to broker
    logger.info(f"Client {client_id} connecting to {broker_address}:{current_broker_port}")
    try:
        # Create connection properties
        connect_props = Properties(PacketTypes.CONNECT)
        if receive_maximum is not None:
            connect_props.ReceiveMaximum = receive_maximum
        
        client.connect(broker_address, current_broker_port, keepalive, properties=connect_props)
        client.loop_start()
        return client
        
    except Exception as e_conn:
        logger.error(f"Connection failed for {client_id}: {e_conn}")
        return None

def on_disconnect_benchmark(client, userdata, flags, rc, properties=None):
    """Handle benchmark client disconnection."""
    state = userdata['state']
    logger.info(f"Client {state.client_id}: Disconnected (RC: {rc})")
    
    if properties and hasattr(properties, 'ReasonString') and properties.ReasonString:
        logger.info(f"Disconnect reason: {properties.ReasonString}")
    
    state.disconnected_event.set()

def on_connect_responder(client, userdata, flags, rc, properties=None):
    """Handle responder connection."""
    state = userdata['state']
    args = userdata['args']
    
    if rc == 0:
        logger.info(f"Responder {state.client_id}: Connected, subscribing to {args.request_topic}")
        
        try:
            res, mid = subscribe_to_topics(client, [(args.request_topic, args.qos)])
            if res == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Responder {state.client_id}: Subscribed successfully")
            else:
                logger.error(f"Responder {state.client_id}: Subscription failed (code: {res})")
        except Exception as e:
            logger.error(f"Responder {state.client_id}: Subscription error: {e}")
            
        state.connected_event.set()
    else:
        logger.error(f"Responder {state.client_id}: Connection failed (RC: {rc})")

def on_message_responder(client, userdata, msg):
    """Handle incoming requests for responder."""
    state = userdata['state']
    args = userdata['args']
    state.processed_requests += 1
    
    logger.info(f"Responder {state.client_id}: Processing request #{state.processed_requests}")
    logger.debug(f"Topic: {msg.topic}, QoS: {msg.qos}, Payload: {len(msg.payload)} bytes")
    
    # Safely extract properties
    if not msg.properties:
        logger.warning(f"Responder {state.client_id}: No properties in message")
        return
        
    response_topic_prop = getattr(msg.properties, 'ResponseTopic', None)
    correlation_data_prop_bytes = getattr(msg.properties, 'CorrelationData', None)
    
    if not response_topic_prop:
        logger.warning(f"Responder {state.client_id}: No ResponseTopic in properties")
        return
        
    if not correlation_data_prop_bytes:
        logger.warning(f"Responder {state.client_id}: No CorrelationData in properties")
        return
        
    try:
        correlation_id = correlation_data_prop_bytes.decode('utf-8', errors='strict')
    except UnicodeDecodeError as e:
        logger.error(f"Responder {state.client_id}: Invalid correlation data encoding: {e}")
        return
    
    logger.debug(f"Responder {state.client_id}: Correlation ID: {correlation_id}")
    
    # Generate response
    response_payload_str = generate_payload(args.res_payload_size)
    
    # Publish response
    try:
        pub_res = publish_message(
            client, 
            topic=response_topic_prop, 
            payload=response_payload_str,
            qos=args.qos, 
            correlation_data=correlation_data_prop_bytes,
            content_type="text/plain"
        )
        
        if pub_res and pub_res.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.debug(f"Responder {state.client_id}: Response sent for {correlation_id}")
        else:
            logger.error(f"Responder {state.client_id}: Failed to send response")
            state.publish_errors += 1
            
    except Exception as e:
        logger.error(f"Responder {state.client_id}: Error sending response: {e}")
        state.publish_errors += 1

def wait_for_subscription(client: mqtt.Client, timeout: float = SUBSCRIPTION_TIMEOUT) -> bool:
    """Wait for subscription to be confirmed."""
    # This is a simplified version - in production you'd want to track SUBACK messages
    time.sleep(0.1)  # Small delay to allow subscription to process
    return True

def cleanup_request(state: RequesterState, correlation_id: str, client: mqtt.Client, response_topic: str) -> None:
    """Clean up request resources safely."""
    try:
        # Remove from active requests
        with state.lock:
            if correlation_id in state.active_requests:
                del state.active_requests[correlation_id]
        
        # Unsubscribe from response topic
        if client and hasattr(client, 'unsubscribe'):
            try:
                client.unsubscribe(response_topic)
                logger.debug(f"Unsubscribed from {response_topic}")
            except Exception as e:
                logger.warning(f"Failed to unsubscribe from {response_topic}: {e}")
                
    except Exception as e:
        logger.error(f"Error during request cleanup: {e}")

def on_connect_requester(client, userdata, flags, rc, properties=None):
    """Handle requester connection."""
    state = userdata['state']
    if rc == 0:
        state.connected_event.set()
    else:
        logger.error(f"Requester {state.client_id}: Connection failed (RC: {rc})")

def on_message_requester(client, userdata, msg):
    """Handle response messages for requester."""
    state = userdata['state']
    
    # Safely extract correlation data
    if not msg.properties:
        logger.warning(f"Requester {state.client_id}: Response without properties")
        return
        
    correlation_id_resp_bytes = getattr(msg.properties, 'CorrelationData', None)
    if not correlation_id_resp_bytes:
        logger.warning(f"Requester {state.client_id}: Response without CorrelationData")
        return
        
    try:
        correlation_id_resp = correlation_id_resp_bytes.decode('utf-8', errors='strict')
    except UnicodeDecodeError as e:
        logger.error(f"Requester {state.client_id}: Invalid correlation data: {e}")
        return
    
    logger.debug(f"Requester {state.client_id}: Response received for {correlation_id_resp}")
    
    # Record RTT safely
    with state.lock:
        if correlation_id_resp in state.active_requests:
            request_data = state.active_requests[correlation_id_resp]
            if not request_data.get("rtt_recorded", False):
                end_time = time.perf_counter()
                rtt = end_time - request_data['start_time']
                request_data['rtt'] = rtt
                request_data['rtt_recorded'] = True
                request_data['event'].set()
                logger.debug(f"RTT recorded: {rtt*1000:.3f}ms for {correlation_id_resp}")
        else:
            logger.warning(f"Requester {state.client_id}: Unknown correlation ID: {correlation_id_resp}")

def run_responder(args):
    """Run the responder component of the benchmark."""
    state = ResponderState()
    logger.info(f"Starting Responder {state.client_id}")
    logger.info(f"Request Topic: {args.request_topic}")
    logger.info(f"Response Topic Base: {args.response_topic_base}")
    logger.info(f"QoS: {args.qos}")
    logger.info(f"Broker: {args.bench_broker_host}:{args.bench_broker_port}")

    responder_client = create_benchmark_mqtt_client(
        client_id=state.client_id,
        on_connect_custom=on_connect_responder,
        on_message_custom=on_message_responder,
        on_disconnect_custom=on_disconnect_benchmark,
        userdata={'state': state, 'args': args},
        benchmark_args=args
    )

    if not responder_client:
        logger.error(f"Responder {state.client_id}: Failed to create client")
        return

    if not state.connected_event.wait(timeout=15):
        logger.error(f"Responder {state.client_id}: Connection timeout")
        safe_disconnect_client(responder_client)
        return
    
    logger.info(f"Responder {state.client_id}: Ready for requests")
    
    try:
        while not state.disconnected_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info(f"Responder {state.client_id}: Shutting down...")
    finally:
        safe_disconnect_client(responder_client, "Responder normal shutdown")
        logger.info(f"Responder {state.client_id}: Final stats - Processed: {state.processed_requests}, Errors: {state.publish_errors}")

def run_requester(args):
    """Run the requester component of the benchmark."""
    state = RequesterState()
    logger.info(f"Starting Requester {state.client_id}")
    logger.info(f"Requests: {args.num_requests}, Payload: {args.req_payload_size} bytes")

    requester_client = create_benchmark_mqtt_client(
        client_id=state.client_id,
        on_connect_custom=on_connect_requester,
        on_message_custom=on_message_requester,
        on_disconnect_custom=on_disconnect_benchmark,
        userdata={'state': state, 'args': args},
        benchmark_args=args
    )

    if not requester_client:
        logger.error(f"Requester {state.client_id}: Failed to create client")
        return

    if not state.connected_event.wait(timeout=15):
        logger.error(f"Requester {state.client_id}: Connection timeout")
        safe_disconnect_client(requester_client)
        return
        
    logger.info(f"Requester {state.client_id}: Starting benchmark...")
    
    total_benchmark_start_time = time.perf_counter()
    
    for i in range(args.num_requests):
        if state.disconnected_event.is_set():
            logger.warning(f"Requester {state.client_id}: Disconnected during benchmark")
            break
            
        correlation_id = str(uuid.uuid4())
        dynamic_response_topic = f"{args.response_topic_base.rstrip('/')}/{correlation_id}"
        request_event = threading.Event()
        
        logger.debug(f"Request {i+1}/{args.num_requests}: {correlation_id}")
        
        # Initialize request tracking
        with state.lock:
            state.active_requests[correlation_id] = {
                'start_time': 0, 
                'event': request_event, 
                'rtt': None, 
                'rtt_recorded': False
            }
        
        try:
            # Subscribe to response topic
            sub_res, mid_sub = subscribe_to_topics(requester_client, [(dynamic_response_topic, args.qos)])
            if sub_res != mqtt.MQTT_ERR_SUCCESS:
                logger.error(f"Subscription failed for {dynamic_response_topic}")
                state.subscribe_errors += 1
                continue
                
            # Wait for subscription to be active
            if not wait_for_subscription(requester_client):
                logger.error(f"Subscription timeout for {dynamic_response_topic}")
                state.subscribe_errors += 1
                continue
            
            # Generate request payload
            request_payload_str = generate_payload(args.req_payload_size)
            
            # Record start time
            with state.lock:
                state.active_requests[correlation_id]['start_time'] = time.perf_counter()
            
            # Publish request
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
                logger.error(f"Publish failed for request {i+1}")
                state.publish_errors += 1
                continue
            
            # Wait for response
            if request_event.wait(timeout=REQUEST_TIMEOUT_SECONDS):
                with state.lock:
                    rtt_val = state.active_requests[correlation_id].get('rtt')
                if rtt_val is not None:
                    state.rtt_values.append(rtt_val)
                    state.successful_requests += 1
                    logger.debug(f"Request {i+1} successful: {rtt_val*1000:.3f}ms")
                else:
                    state.timed_out_requests += 1
                    logger.warning(f"Request {i+1} response received but RTT not recorded")
            else:
                state.timed_out_requests += 1
                logger.warning(f"Request {i+1} timed out after {REQUEST_TIMEOUT_SECONDS}s")
                
        except Exception as e:
            logger.error(f"Error processing request {i+1}: {e}")
            state.publish_errors += 1
            
        finally:
            # Always clean up request resources
            cleanup_request(state, correlation_id, requester_client, dynamic_response_topic)
            
            # Inter-request delay
            if args.inter_request_delay_s > 0 and i < args.num_requests - 1:
                time.sleep(args.inter_request_delay_s)
    
    total_benchmark_end_time = time.perf_counter()
    total_duration = total_benchmark_end_time - total_benchmark_start_time

    # Print Results
    print("\n" + "="*50)
    print("BENCHMARK RESULTS")
    print("="*50)
    print(f"Total requests attempted: {args.num_requests}")
    print(f"Successful requests: {state.successful_requests}")
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
            
        # Calculate percentiles
        sorted_rtts = sorted([rtt * 1000 for rtt in state.rtt_values])
        p50 = sorted_rtts[len(sorted_rtts) // 2]
        p95 = sorted_rtts[int(len(sorted_rtts) * 0.95)]
        p99 = sorted_rtts[int(len(sorted_rtts) * 0.99)]
        print(f"50th percentile: {p50:.3f} ms")
        print(f"95th percentile: {p95:.3f} ms")
        print(f"99th percentile: {p99:.3f} ms")
    else:
        print("No successful RTT measurements to report.")
    
    print(f"Total benchmark duration: {total_duration:.3f} seconds")
    if total_duration > 0 and state.successful_requests > 0:
        rps = state.successful_requests / total_duration
        print(f"Throughput: {rps:.2f} requests/second")
    
    success_rate = (state.successful_requests / args.num_requests) * 100 if args.num_requests > 0 else 0
    print(f"Success rate: {success_rate:.1f}%")
    print("="*50)

    safe_disconnect_client(requester_client, "Requester benchmark finished")
    logger.info(f"Requester {state.client_id}: Benchmark completed")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MQTT Request-Response Benchmark Tool")
    parser.add_argument("role", choices=["requester", "responder"], help="Role to play")
    
    # Benchmark parameters
    parser.add_argument("--num_requests", type=int, default=DEFAULT_NUM_REQUESTS, 
                       help=f"Number of requests to send (default: {DEFAULT_NUM_REQUESTS})")
    parser.add_argument("--req_payload_size", type=int, default=DEFAULT_REQ_PAYLOAD_SIZE,
                       help=f"Request payload size in bytes (default: {DEFAULT_REQ_PAYLOAD_SIZE})")
    parser.add_argument("--res_payload_size", type=int, default=DEFAULT_RES_PAYLOAD_SIZE,
                       help=f"Response payload size in bytes (default: {DEFAULT_RES_PAYLOAD_SIZE})")
    parser.add_argument("--qos", type=int, choices=[0, 1, 2], default=DEFAULT_QOS,
                       help=f"MQTT QoS level (default: {DEFAULT_QOS})")
    parser.add_argument("--request_topic", type=str, default=DEFAULT_REQUEST_TOPIC,
                       help=f"Request topic (default: {DEFAULT_REQUEST_TOPIC})")
    parser.add_argument("--response_topic_base", type=str, default=DEFAULT_RESPONSE_TOPIC_BASE,
                       help=f"Response topic base (default: {DEFAULT_RESPONSE_TOPIC_BASE})")
    parser.add_argument("--delay", type=float, default=INTER_REQUEST_DELAY_S, dest="inter_request_delay_s",
                       help=f"Delay between requests in seconds (default: {INTER_REQUEST_DELAY_S})")

    # Benchmark broker connection parameters
    parser.add_argument("--bench_broker_host", type=str, default="localhost", 
                       help="Benchmark broker hostname (default: localhost)")
    parser.add_argument("--bench_broker_port", type=int, default=1884, 
                       help="Benchmark broker port (default: 1884)")
    parser.add_argument("--bench_use_tls", action="store_true", 
                       help="Use TLS for benchmark broker connection")
    parser.add_argument("--bench_ca_cert", type=str, default=None, 
                       help="Path to CA certificate for TLS")
    parser.add_argument("--bench_username", type=str, default=None, 
                       help="Username for broker authentication")
    parser.add_argument("--bench_password", type=str, default=None, 
                       help="Password for broker authentication")
    
    # Logging options
    parser.add_argument("--verbose", "-v", action="store_true", 
                       help="Enable verbose logging")
    parser.add_argument("--debug", action="store_true", 
                       help="Enable debug logging")
    
    args = parser.parse_args()

    # Configure logging based on arguments
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    else:
        logging.getLogger().setLevel(logging.WARNING)

    # Validate arguments
    if args.num_requests <= 0:
        print("Error: num_requests must be positive")
        sys.exit(1)
        
    if args.req_payload_size <= 0 or args.res_payload_size <= 0:
        print("Error: payload sizes must be positive")
        sys.exit(1)
        
    if args.inter_request_delay_s < 0:
        print("Error: delay cannot be negative")
        sys.exit(1)

    # Print configuration
    logger.info(f"Benchmark Target: {args.bench_broker_host}:{args.bench_broker_port}")
    logger.info(f"TLS Enabled: {args.bench_use_tls}")
    logger.info(f"Authentication: {'Yes' if args.bench_username else 'No'}")

    try:
        if args.role == "responder":
            run_responder(args)
        elif args.role == "requester":
            run_requester(args)
    except KeyboardInterrupt:
        logger.info("Benchmark interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        sys.exit(1)