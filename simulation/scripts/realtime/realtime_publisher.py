import os
import sys
import time
import json
import queue
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

# --- 2. CONFIGURATION ---
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
TOPIC_METRICS = "simulation/metrics/live"
TOPIC_VEHICLES = "simulation/vehicles/live"
TOPIC_TL = "simulation/tl/live"
TOPIC_COMMANDS = "simulation/commands"

script_dir = os.path.dirname(os.path.abspath(__file__))
SUMO_CFG = os.path.join(script_dir, "../../cfg/intersection.sumocfg")
SUMO_CFG = os.path.normpath(SUMO_CFG)

CMD_QUEUE = queue.Queue()

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
        "--tripinfo-output", tripinfo_file,  # <--- Generates tripinfo.xml
        "--summary-output", summary_file,    # <--- Generates summary.xml
        "--no-warnings"                      # Optional: Keeps logs clean
    ]

    traci.start(sumo_cmd)
    
    try:
        traci.trafficlight.setProgram("C", "1") 
        print(">>> SUCCESS: Forced TLS 'C' to use Program '1' (Simple 2-Phase)")
    except Exception as e:
        print(f">>> WARNING: Could not set Program '1'. Is the XML loaded? Error: {e}")

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
                    # Get duration or default to 42s
                    duration = cmd.get("duration", 42.0)
                    
                    try:
                        traci.trafficlight.setPhase(tl_id, target_phase)
                        traci.trafficlight.setPhaseDuration(tl_id, duration)
                        print(f"[Actuator] Set {tl_id} -> Phase {target_phase} (Duration: {duration}s)")
                    except traci.TraCIException as e:
                        print(f"Actuator Error: {e}")

            # --- OBSERVATION: PUBLISH DATA ---
            vehicle_ids = traci.vehicle.getIDList()
            
            client.publish(TOPIC_METRICS, json.dumps(get_aggregated_metrics(step, vehicle_ids)))
            client.publish(TOPIC_VEHICLES, json.dumps({"time": step, "vehicles": get_vehicle_states(vehicle_ids)}))
            client.publish(TOPIC_TL, json.dumps({"time": step, "lights": get_traffic_light_states(), "sim_speed": 1.0}))
            
            if step % 50 == 0:
                print(f"[Step {step}] Active Vehicles: {len(vehicle_ids)}")
                
            # time.sleep(0.1) # Uncomment to watch in slow motion
            step += 1

    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        traci.close()
        client.loop_stop()

if __name__ == "__main__":
    run_simulation()