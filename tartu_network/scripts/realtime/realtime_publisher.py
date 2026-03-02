import os
import sys
import time
import json
import queue
import logging
import paho.mqtt.client as mqtt

# --- 1. SETUP SUMO PATHS ---
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

import traci
try:
    from geo_utils import xy_to_latlon
except ImportError:
    def xy_to_latlon(x, y): return None, None

# --- 1b. BLOCKCHAIN MODULE PATH ---
# Add project root so we can import the blockchain package
project_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from blockchain import BlockchainClient, AccessControlContract

# --- 2. CONFIGURATION ---
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
TOPIC_METRICS = "simulation/tartu/metrics/live"
TOPIC_VEHICLES = "simulation/tartu/vehicles/live"
TOPIC_TL = "simulation/tartu/tl/live"
TOPIC_COMMANDS = "simulation/tartu/commands"

# Blockchain toggle (set env BLOCKCHAIN_ENABLED=false to disable)
BLOCKCHAIN_ENABLED = os.getenv("BLOCKCHAIN_ENABLED", "true").lower() != "false"
BLOCKCHAIN_ANCHOR_INTERVAL = int(os.getenv("BLOCKCHAIN_ANCHOR_INTERVAL", "5"))  # batch vehicles every N steps

script_dir = os.path.dirname(os.path.abspath(__file__))
SUMO_CFG = os.path.join(script_dir, "../../cfg/tartu.sumocfg")
SUMO_CFG = os.path.normpath(SUMO_CFG)

CMD_QUEUE = queue.Queue()

# Tartu network traffic light IDs
TARTU_TLS_IDS = ["TRiia_Vaba", "TRiia_Turu", "TTuru_Vaks", "TTuru_Alek"]

# --- 3. MQTT CLIENT ---
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"Connected to Broker. Listening on {TOPIC_COMMANDS}")
        client.subscribe(TOPIC_COMMANDS)
    else:
        print(f"Failed to connect. Code: {rc}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        CMD_QUEUE.put(payload)
    except Exception as e:
        print(f"Error parsing command: {e}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()

# --- 4. DATA HELPERS ---
def get_aggregated_metrics(step, vehicle_ids):
    count = len(vehicle_ids)
    if count == 0: return {"time": step, "vehicle_count": 0, "avg_speed": 0, "congestion_index": 0}
    speeds = [traci.vehicle.getSpeed(vid) for vid in vehicle_ids]
    stopped = sum(1 for s in speeds if s < 0.1)
    return {
        "time": step, "vehicle_count": count,
        "avg_speed": round(sum(speeds)/count, 2),
        "stopped": stopped,
        "congestion_index": round(stopped/count, 2)
    }

def get_vehicle_states(vehicle_ids):
    result = []
    for vid in vehicle_ids:
        x, y = traci.vehicle.getPosition(vid)
        lon, lat = xy_to_latlon(x, y)
        result.append({
            "id": vid, "lane": traci.vehicle.getLaneID(vid),
            "speed": round(traci.vehicle.getSpeed(vid), 2),
            "x": round(x, 2), "y": round(y, 2), "lat": lat, "lon": lon
        })
    return result

def get_traffic_light_states():
    tl_states = []
    for tl_id in traci.trafficlight.getIDList():
        tl_states.append({
            "id": tl_id,
            "state": traci.trafficlight.getRedYellowGreenState(tl_id),
            "phase": traci.trafficlight.getPhase(tl_id),
            "program": traci.trafficlight.getProgram(tl_id)
        })
    return tl_states

# --- 5. MAIN LOOP ---
def run_simulation():
    # --- BLOCKCHAIN SETUP ---
    bc = None
    ac = None
    if BLOCKCHAIN_ENABLED:
        logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")
        bc = BlockchainClient()
        if bc.is_connected:
            print(f"[Blockchain] Connected  ✔  (block #{bc.get_block_number()})")
            # Deploy Access Control and authorize publisher
            ac = AccessControlContract.deploy(bc)
            ac.grant_role(bc.account, "PUBLISHER")
            print(f"[AccessControl] Publisher authorized  ✔  {ac.address}")
        else:
            print("[Blockchain] Not connected — anchoring disabled for this run.")
            bc = None
    else:
        print("[Blockchain] Disabled via BLOCKCHAIN_ENABLED=false")

    print(f"Starting SUMO: {SUMO_CFG}")

    # output directory for raw files
    output_dir = os.path.join(script_dir, "../../outputs/raw")
    os.makedirs(output_dir, exist_ok=True)
    tripinfo_file = os.path.join(output_dir, "tripinfo.xml")
    summary_file = os.path.join(output_dir, "summary.xml")

    sumo_cmd = [
        "sumo-gui", 
        "-c", SUMO_CFG,
        "--start",
        "--quit-on-end",
        "--tripinfo-output", tripinfo_file,
        "--summary-output", summary_file,
        "--no-warnings"
    ]

    traci.start(sumo_cmd)
    
    # Force all 4 Tartu TLS to use our static program
    for tls_id in TARTU_TLS_IDS:
        try:
            traci.trafficlight.setProgram(tls_id, "1") 
            print(f">>> SUCCESS: Forced TLS '{tls_id}' to use Program '1'")
        except Exception as e:
            print(f">>> WARNING: Could not set Program '1' for {tls_id}. Error: {e}")

    step = 0
    try:
        while step < 3600:
            traci.simulationStep()
            
            # --- ACTION: PROCESS COMMANDS ---
            while not CMD_QUEUE.empty():
                cmd = CMD_QUEUE.get()
                if cmd.get("action") == "set_phase":
                    tl_id = cmd["id"]
                    target_phase = cmd["phase"]
                    duration = cmd.get("duration", 42.0)
                    
                    try:
                        traci.trafficlight.setPhase(tl_id, target_phase)
                        traci.trafficlight.setPhaseDuration(tl_id, duration)
                        print(f"[Actuator] Set {tl_id} -> Phase {target_phase} (Duration: {duration}s)")
                    except traci.TraCIException as e:
                        print(f"Actuator Error: {e}")

            # --- OBSERVATION: PUBLISH DATA ---
            vehicle_ids = traci.vehicle.getIDList()
            
            metrics_data = get_aggregated_metrics(step, vehicle_ids)
            vehicles_data = {"time": step, "vehicles": get_vehicle_states(vehicle_ids)}
            tl_data = {"time": step, "lights": get_traffic_light_states(), "sim_speed": 1.0}

            client.publish(TOPIC_METRICS, json.dumps(metrics_data))
            client.publish(TOPIC_VEHICLES, json.dumps(vehicles_data))
            client.publish(TOPIC_TL, json.dumps(tl_data))

            # --- BLOCKCHAIN: ANCHOR DATA ---
            if bc:
                # Anchor metrics & TL state every step (low volume)
                bc.anchor_data(metrics_data)
                bc.anchor_data(tl_data)

                # Batch-anchor vehicle positions at configured interval
                if step % BLOCKCHAIN_ANCHOR_INTERVAL == 0 and vehicles_data["vehicles"]:
                    bc.anchor_batch(vehicles_data["vehicles"])
            
            if step % 50 == 0:
                bc_info = f"  |  Chain block #{bc.get_block_number()}" if bc else ""
                print(f"[Step {step}] Active Vehicles: {len(vehicle_ids)}{bc_info}")
                
            step += 1

    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        traci.close()
        client.loop_stop()

if __name__ == "__main__":
    run_simulation()
