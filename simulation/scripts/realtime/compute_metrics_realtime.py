import os
import time
import json
import traci
import paho.mqtt.client as mqtt

from geo_utils import xy_to_latlon  # still works even if returns None


MQTT_BROKER = "localhost"
TOPIC_METRICS = "simulation/metrics/live"
TOPIC_VEHICLES = "simulation/vehicles/live"

script_dir = os.path.dirname(os.path.abspath(__file__))
SUMO_CFG = os.path.join(script_dir, "../../cfg/intersection.sumocfg")
SUMO_CFG = os.path.normpath(SUMO_CFG)


# -------------------------------------
# MQTT CLIENT SETUP
# -------------------------------------
client = mqtt.Client()
client.connect(MQTT_BROKER, 1883, 60)
client.loop_start()


# -------------------------------------
# COMPUTE REAL-TIME METRICS
# -------------------------------------
def compute_live_metrics(step):
    """
    Computes:
    - number of vehicles
    - average speed
    - congestion index
    - stopped vehicle count
    """

    vehicles = traci.vehicle.getIDList()
    count = len(vehicles)

    if count == 0:
        return {
            "time": step,
            "vehicle_count": 0,
            "avg_speed": 0,
            "stopped": 0,
            "congestion_index": 0
        }

    speeds = []
    stopped = 0

    for vid in vehicles:
        speed = traci.vehicle.getSpeed(vid)
        speeds.append(speed)

        if speed < 0.1:
            stopped += 1

    avg_speed = sum(speeds) / count
    congestion_index = stopped / count   # simple % of vehicles not moving

    return {
        "time": step,
        "vehicle_count": count,
        "avg_speed": avg_speed,
        "stopped": stopped,
        "congestion_index": congestion_index
    }


# -------------------------------------
# COLLECT VEHICLE POSITIONS
# -------------------------------------
def collect_vehicle_positions():
    """
    Returns a list of:
    { id, x, y, lat, lon, speed, angle }
    """

    vehicles = traci.vehicle.getIDList()
    result = []

    for vid in vehicles:
        x, y = traci.vehicle.getPosition(vid)
        lon, lat = xy_to_latlon(x, y)   # safe, returns None if not using GIS

        result.append({
            "id": vid,
            "x": x,
            "y": y,
            "lon": lon,
            "lat": lat,
            "speed": traci.vehicle.getSpeed(vid),
            "angle": traci.vehicle.getAngle(vid)
        })

    return result


# -------------------------------------
# MAIN REAL-TIME LOOP
# -------------------------------------
def run_realtime_metrics():
    print("Starting SUMO TraCI session...")

    traci.start([
        "sumo",
        "-c", SUMO_CFG,
        "--start",
        "--quit-on-end"
    ])

    step = 0

    try:
        while step < 3600:   # 1 hour simulation
            traci.simulationStep()

            # --- compute metrics ---
            metrics = compute_live_metrics(step)
            client.publish(TOPIC_METRICS, json.dumps(metrics))

            # --- publish vehicle states ---
            vehicle_states = collect_vehicle_positions()
            client.publish(TOPIC_VEHICLES, json.dumps({
                "time": step,
                "vehicles": vehicle_states
            }))

            print(f"[Step {step}] Veh={metrics['vehicle_count']} AvgSpeed={metrics['avg_speed']:.2f}")

            time.sleep(0.1)  # optional, smoothens output
            step += 1

    except KeyboardInterrupt:
        print("Stopping simulation...")

    finally:
        traci.close()
        client.loop_stop()
        print("Done.")


# Run script
if __name__ == "__main__":
    run_realtime_metrics()
