"""
Rule-Based Traffic Agent for Tartu 4-Intersection Network
==========================================================
Controls all 4 intersections: TRiia_Kalevi, TRiia_Turu, TTuru_Soola, TTuru_Aida.
Uses a simple hysteresis-based approach: switch to the direction with the
most waiting vehicles, but only if it exceeds the current direction by >2.
"""

import json
import time
import paho.mqtt.client as mqtt

# --- CONFIGURATION ---
BROKER = "localhost"
TOPIC_VEHICLES = "simulation/tartu/vehicles/live"
TOPIC_TL = "simulation/tartu/tl/live"
TOPIC_COMMANDS = "simulation/tartu/commands"

# --- INTERSECTION DEFINITIONS ---
# Each intersection has: phase_map (direction -> phase index), and its state
INTERSECTIONS = {
    "TRiia_Kalevi": {
        "directions": ["Riia_North", "Vabaduse_West", "Vabaduse_East", "Corridor_South"],
        "phase_map": {"Riia_North": 0, "Vabaduse_West": 2, "Vabaduse_East": 4, "Corridor_South": 6},
        "phase_names": {0: "Riia_North", 2: "Vabaduse_West", 4: "Vabaduse_East", 6: "Corridor_South"},
    },
    "TRiia_Turu": {
        "directions": ["Corridor_North", "Riia_South", "Turu_West", "Corridor_East"],
        "phase_map": {"Corridor_North": 0, "Riia_South": 2, "Turu_West": 4, "Corridor_East": 6},
        "phase_names": {0: "Corridor_North", 2: "Riia_South", 4: "Turu_West", 6: "Corridor_East"},
    },
    "TTuru_Soola": {
        "directions": ["Corridor_West", "Soola_North", "Soola_South", "Corridor_East"],
        "phase_map": {"Corridor_West": 0, "Soola_North": 2, "Soola_South": 4, "Corridor_East": 6},
        "phase_names": {0: "Corridor_West", 2: "Soola_North", 4: "Soola_South", 6: "Corridor_East"},
    },
    "TTuru_Aida": {
        "directions": ["Corridor_West", "AidaSandri_East", "AidaSandri_North", "AidaSandri_South"],
        "phase_map": {"Corridor_West": 0, "AidaSandri_East": 2, "AidaSandri_North": 4, "AidaSandri_South": 6},
        "phase_names": {0: "Corridor_West", 2: "AidaSandri_East", 4: "AidaSandri_North", 6: "AidaSandri_South"},
    },
}

# --- STATE ---
tls_state = {}
for tls_id, info in INTERSECTIONS.items():
    tls_state[tls_id] = {"phase": -1, "counts": {d: 0 for d in info["directions"]}}

# --- LANE → DIRECTION MAPPING ---
# Maps lane substrings to (intersection_id, direction)
LANE_MAP = [
    # TRiia_Kalevi approaches
    ("RiiaN_RiiaKalevi",       "TRiia_Kalevi", "Riia_North"),
    ("UlikW_RiiaKalevi",       "TRiia_Kalevi", "Vabaduse_West"),
    ("KaleviE_RiiaKalevi",       "TRiia_Kalevi", "Vabaduse_East"),
    ("RiiaTuru_RiiaKalevi",    "TRiia_Kalevi", "Corridor_South"),
    # TRiia_Turu approaches
    ("RiiaKalevi_RiiaTuru",    "TRiia_Turu", "Corridor_North"),
    ("RiiaS_RiiaTuru",       "TRiia_Turu", "Riia_South"),
    ("TuruW_RiiaTuru",       "TRiia_Turu", "Turu_West"),
    ("TuruSoola_RiiaTuru",    "TRiia_Turu", "Corridor_East"),
    # TTuru_Soola approaches
    ("RiiaTuru_TuruSoola",    "TTuru_Soola", "Corridor_West"),
    ("SoolaN_TuruSoola",       "TTuru_Soola", "Soola_North"),
    ("SoolaS_TuruSoola",       "TTuru_Soola", "Soola_South"),
    ("TuruAida_TuruSoola",    "TTuru_Soola", "Corridor_East"),
    # TTuru_Aida approaches
    ("TuruSoola_TuruAida",    "TTuru_Aida", "Corridor_West"),
    ("AidaE_TuruAida",       "TTuru_Aida", "AidaSandri_East"),
    ("AidaN_TuruAida",       "TTuru_Aida", "AidaSandri_North"),
    ("AidaS_TuruAida",       "TTuru_Aida", "AidaSandri_South"),
]


def parse_lanes(vehicles):
    """Count vehicles per direction for all 4 intersections."""
    counts = {}
    for tls_id, info in INTERSECTIONS.items():
        counts[tls_id] = {d: 0 for d in info["directions"]}

    for v in vehicles:
        lane = v['lane']
        for lane_substr, tls_id, direction in LANE_MAP:
            if lane_substr in lane:
                counts[tls_id][direction] += 1
                break

    return counts


def decide_phase(client, tls_id, counts):
    """Hysteresis-based phase decision for one intersection."""
    info = INTERSECTIONS[tls_id]
    phase_map = info["phase_map"]
    phase_names = info["phase_names"]
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
    print("Tartu Traffic Controller Connected. Monitoring 4 intersections...")
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
            all_counts = parse_lanes(vehicles)

            for tls_id in INTERSECTIONS:
                tls_state[tls_id]["counts"] = all_counts[tls_id]
                decide_phase(client, tls_id, all_counts[tls_id])

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
        print("Tartu Traffic Controller shutting down.")
