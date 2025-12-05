import os
import sys
import time
import json
import traci
import paho.mqtt.client as mqtt
from geo_utils import xy_to_latlon

# ---  SETUP SUMO PATHS ---
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("please declare environment variable 'SUMO_HOME'")

# ---  CONFIG & TOPICS ---
MQTT_BROKER = "localhost"
# Topic design: "simulation/{entity}/{type}"
TOPIC_METRICS = "simulation/metrics/live"      # For Dashboard Graphs
TOPIC_VEHICLES = "simulation/vehicles/live"    # For Map Visualization
TOPIC_TL = "simulation/tl/live"                # For AI Agent Observations

# Dynamic path resolution
script_dir = os.path.dirname(os.path.abspath(__file__))
SUMO_CFG = os.path.join(script_dir, "../../cfg/intersection.sumocfg")
SUMO_CFG = os.path.normpath(SUMO_CFG)

# ---  MQTT SETUP ---
client = mqtt.Client()
client.connect(MQTT_BROKER, 1883, 60)
client.loop_start()

# ---  DATA COLLECTION FUNCTIONS ---

def get_aggregated_metrics(step, vehicle_ids):
    """Calculates system-level stats (Congestion, Avg Speed)"""
    count = len(vehicle_ids)
    if count == 0:
        return {
            "time": step, "vehicle_count": 0, "avg_speed": 0, 
            "stopped": 0, "congestion_index": 0
        }

    speeds = []
    stopped = 0
    for vid in vehicle_ids:
        speed = traci.vehicle.getSpeed(vid)
        speeds.append(speed)
        if speed < 0.1: stopped += 1

    avg_speed = sum(speeds) / count
    congestion_index = stopped / count

    return {
        "time": step,
        "vehicle_count": count,
        "avg_speed": round(avg_speed, 2),
        "stopped": stopped,
        "congestion_index": round(congestion_index, 2)
    }

def get_vehicle_states(vehicle_ids):
    """Detailed state for every single car (for the Map & AI)"""
    result = []
    for vid in vehicle_ids:
        x, y = traci.vehicle.getPosition(vid)
        lon, lat = xy_to_latlon(x, y)
        
        result.append({
            "id": vid,
            "lane": traci.vehicle.getLaneID(vid), # Crucial for AI (Knows which lane has queue)
            "x": round(x, 2), "y": round(y, 2),
            "lat": lat, "lon": lon,
            "speed": round(traci.vehicle.getSpeed(vid), 2)
        })
    return result

def get_traffic_light_states():
    """Current colors of the signals (Crucial for AI to know 'Is it Red?')"""
    tl_states = []
    for tl_id in traci.trafficlight.getIDList():
        # returns string like "GrGr"
        state = traci.trafficlight.getRedYellowGreenState(tl_id) 
        tl_states.append({
            "id": tl_id,
            "state": state,
            "program": traci.trafficlight.getProgram(tl_id),
            "phase": traci.trafficlight.getPhase(tl_id)
        })
    return tl_states

# ---  MAIN LOOP ---
def run_simulation():
    print(f"Starting SUMO using config: {SUMO_CFG}")
    
    # Start TraCI
    traci.start(["sumo", "-c", SUMO_CFG, "--start", "--quit-on-end"])
    
    step = 0
    try:
        while step < 3600:
            traci.simulationStep()
            
            # Get list of vehicles once to save performance
            vehicle_ids = traci.vehicle.getIDList()

            # 1. Publish Metrics (For Dashboard Charts)
            metrics = get_aggregated_metrics(step, vehicle_ids)
            client.publish(TOPIC_METRICS, json.dumps(metrics))

            # 2. Publish Vehicle Positions (For Dashboard Map)
            veh_states = get_vehicle_states(vehicle_ids)
            client.publish(TOPIC_VEHICLES, json.dumps({"time": step, "vehicles": veh_states}))

            # 3. Publish Traffic Light State (For AI Agent)
            tl_states = get_traffic_light_states()
            client.publish(TOPIC_TL, json.dumps({"time": step, "lights": tl_states}))

            # Logging
            if step % 10 == 0: # Print only every 10 steps to reduce noise
                print(f"[Step {step}] C={metrics['vehicle_count']} Congestion={metrics['congestion_index']}")

            # time.sleep(0.1) # Uncomment if you want to watch it in real-time speed
            step += 1

    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        traci.close()
        client.loop_stop()

if __name__ == "__main__":
    run_simulation()