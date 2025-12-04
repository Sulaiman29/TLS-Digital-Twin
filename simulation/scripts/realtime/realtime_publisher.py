import json
import time
import paho.mqtt.client as mqtt
import traci
from geo_utils import xy_to_latlon

MQTT_BROKER = "localhost"
MQTT_TOPIC = "dt/traffic/state"

SUMO_BINARY = "sumo"   # or sumo-gui
SUMOCFG = "../../cfg/intersection.sumocfg"


def build_state():
    data = {
        "time": traci.simulation.getTime(),
        "vehicles": [],
        "traffic_lights": []
    }

    # VEHICLES
    for vid in traci.vehicle.getIDList():
        x, y = traci.vehicle.getPosition(vid)
        lat, lon = xy_to_latlon(x, y)

        data["vehicles"].append({
            "id": vid,
            "lane": traci.vehicle.getLaneID(vid),
            "speed": traci.vehicle.getSpeed(vid),
            "pos_xy": {"x": x, "y": y},
            "pos_geo": {"lat": lat, "lon": lon}
        })

    # TRAFFIC LIGHT STATES
    for tl in traci.trafficlight.getIDList():
        data["traffic_lights"].append({
            "id": tl,
            "state": traci.trafficlight.getRedYellowGreenState(tl)
        })

    return data


def main():
    print("Connecting to MQTT broker...")
    client = mqtt.Client()
    client.connect(MQTT_BROKER)

    print("Starting SUMO TRACI...")
    traci.start([SUMO_BINARY, "-c", SUMOCFG])

    while traci.simulation.getTime() < 3600:
        traci.simulationStep()

        state = build_state()
        client.publish(MQTT_TOPIC, json.dumps(state))

        time.sleep(0.1)  # 10 Hz update

    traci.close()


if __name__ == "__main__":
    main()
