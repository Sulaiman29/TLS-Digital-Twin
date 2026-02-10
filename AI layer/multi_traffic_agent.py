import json
import time
import paho.mqtt.client as mqtt

# --- CONFIGURATION ---
BROKER = "localhost"
TOPIC_VEHICLES = "simulation/multi/vehicles/live"
TOPIC_TL = "simulation/multi/tl/live"
TOPIC_COMMANDS = "simulation/multi/commands"

# --- STATE MANAGEMENT ---
# Per-intersection state
tls_state = {
    "C1": {"phase": -1, "counts": {"North": 0, "South": 0, "West": 0, "Corridor": 0}},
    "C2": {"phase": -1, "counts": {"North": 0, "South": 0, "East": 0, "Corridor": 0}},
}

# Phase mapping for both intersections
# C1: North=N1_C1, South=S1_C1, West=W_C1, Corridor=C2_C1
# C2: North=N2_C2, South=S2_C2, East=E_C2, Corridor=C1_C2
PHASE_MAP_C1 = {"North": 0, "South": 2, "West": 4, "Corridor": 6}
PHASE_MAP_C2 = {"North": 0, "South": 2, "East": 4, "Corridor": 6}
PHASE_NAMES_C1 = {0: "North", 2: "South", 4: "West", 6: "Corridor"}
PHASE_NAMES_C2 = {0: "North", 2: "South", 4: "East", 6: "Corridor"}

def parse_lanes(vehicles):
    """Counts vehicles per direction for BOTH intersections."""
    c1 = {"North": 0, "South": 0, "West": 0, "Corridor": 0}
    c2 = {"North": 0, "South": 0, "East": 0, "Corridor": 0}

    for v in vehicles:
        lane = v['lane']
        # C1 approaches
        if "N1_C1" in lane: c1["North"] += 1
        elif "S1_C1" in lane: c1["South"] += 1
        elif "W_C1" in lane: c1["West"] += 1
        elif "C2_C1" in lane: c1["Corridor"] += 1
        # C2 approaches
        elif "N2_C2" in lane: c2["North"] += 1
        elif "S2_C2" in lane: c2["South"] += 1
        elif "E_C2" in lane: c2["East"] += 1
        elif "C1_C2" in lane: c2["Corridor"] += 1

    return c1, c2


def decide_phase(client, tls_id, counts, phase_map, phase_names):
    """
    4-Phase decision logic for one intersection (rule-based, no inter-agent info).
    """
    current_phase = tls_state[tls_id]["phase"]

    # Find direction with highest queue
    max_dir = max(counts, key=counts.get)
    max_count = counts[max_dir]

    # Current direction (if in green phase)
    current_dir = phase_names.get(current_phase, None)
    current_count = counts.get(current_dir, 0) if current_dir else 0

    counts_str = " ".join(f"{k}:{v}" for k, v in counts.items())
    print(f"[{tls_id}] Queue -> {counts_str} (Phase: {current_phase})")

    # Hysteresis: only switch if another direction has > 2 more cars
    if current_dir and max_count <= current_count + 2:
        return

    target_phase = phase_map[max_dir]

    # Already in correct phase
    if current_phase == target_phase:
        return

    # In yellow transition
    if current_phase in [1, 3, 5, 7]:
        print(f"[{tls_id}] Transitioning (yellow)... Waiting.")
        return

    # Dynamic duration: 10 + 2*cars, clamped 15-60s
    duration = max(15, min(10 + max_count * 2, 60))

    print(f">>> [{tls_id}] Heavy Traffic on {max_dir} ({max_count} cars).")
    print(f">>> [{tls_id}] Switch to Phase {target_phase} ({max_dir}) for {duration}s.")

    command = {
        "action": "set_phase",
        "id": tls_id,
        "phase": target_phase,
        "duration": float(duration)
    }
    client.publish(TOPIC_COMMANDS, json.dumps(command))
    time.sleep(3)


# --- MQTT HANDLERS ---
def on_connect(client, userdata, flags, rc, properties=None):
    print("Multi-Agent Traffic Controller Connected. Monitoring both intersections...")
    client.subscribe(TOPIC_VEHICLES)
    client.subscribe(TOPIC_TL)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())

        if msg.topic == TOPIC_TL:
            lights = payload.get("lights", [])
            for tl in lights:
                tl_id = tl['id']
                if tl_id in tls_state:
                    tls_state[tl_id]["phase"] = tl['phase']

        if msg.topic == TOPIC_VEHICLES:
            vehicles = payload.get("vehicles", [])
            c1_counts, c2_counts = parse_lanes(vehicles)
            tls_state["C1"]["counts"] = c1_counts
            tls_state["C2"]["counts"] = c2_counts

            # Independent decisions — no collaboration (baseline)
            decide_phase(client, "C1", c1_counts, PHASE_MAP_C1, PHASE_NAMES_C1)
            decide_phase(client, "C2", c2_counts, PHASE_MAP_C2, PHASE_NAMES_C2)

    except Exception as e:
        print(f"Error: {e}")

# --- MAIN ---
if __name__ == "__main__":
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, 1883, 60)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("Multi-Agent Traffic Controller shutting down.")
