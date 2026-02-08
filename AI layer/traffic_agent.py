import json
import time
import paho.mqtt.client as mqtt

# --- CONFIGURATION ---
BROKER = "localhost"
TOPIC_VEHICLES = "simulation/vehicles/live"
TOPIC_TL = "simulation/tl/live"
TOPIC_COMMANDS = "simulation/commands"

TLS_ID = "C"

# --- STATE MANAGEMENT ---
current_phase_index = -1
waiting_counts = {"North": 0, "East": 0, "South": 0, "West": 0}

def parse_lanes(vehicles):
    """
    Maps lane IDs to cardinal directions.
    Counts ALL incoming traffic regardless of speed to ensure we catch fast-approaching cars.
    """
    counts = {"North": 0, "East": 0, "South": 0, "West": 0}
    
    for v in vehicles:
        lane = v['lane']
        
        # Simple string matching for your edges (N_C, E_C, etc.)
        if "N_C" in lane: counts["North"] += 1
        elif "E_C" in lane: counts["East"] += 1
        elif "S_C" in lane: counts["South"] += 1
        elif "W_C" in lane: counts["West"] += 1
            
    return counts

def decide_phase(client):
    """
    Logic for 4-Phase System (N, E, S, W separate) with Dynamic Duration.
    Phases: 0=North, 2=East, 4=South, 6=West (odd phases are yellows)
    """
    global current_phase_index

    # Phase mapping: direction -> green phase index
    PHASE_MAP = {"North": 0, "East": 2, "South": 4, "West": 6}
    PHASE_NAMES = {0: "North", 2: "East", 4: "South", 6: "West"}

    # Find direction with highest queue
    max_dir = max(waiting_counts, key=waiting_counts.get)
    max_count = waiting_counts[max_dir]
    
    # Get current direction (if in a green phase)
    current_dir = PHASE_NAMES.get(current_phase_index, None)
    current_count = waiting_counts.get(current_dir, 0) if current_dir else 0

    print(f"Queue Status -> N:{waiting_counts['North']} E:{waiting_counts['East']} "
          f"S:{waiting_counts['South']} W:{waiting_counts['West']} (Active Phase: {current_phase_index})")

    # Hysteresis: Only switch if another direction has > 2 more cars than current
    if current_dir and max_count <= current_count + 2:
        return  # Stay in current phase
    
    target_phase = PHASE_MAP[max_dir]

    # If already in the correct phase, do nothing
    if current_phase_index == target_phase:
        return

    # If in Yellow transition (Phase 1, 3, 5, or 7), wait for it to finish
    if current_phase_index in [1, 3, 5, 7]:
        print(">>> AI: Light is transitioning (yellow)... Waiting.")
        return

    # Calculate dynamic duration: Base 10s + (2s per car), clamped 15-60s
    duration = 10 + (max_count * 2)
    duration = max(15, min(duration, 60))

    print(f">>> AI: Heavy Traffic on {max_dir} ({max_count} cars).")
    print(f">>> Command: Switch to Phase {target_phase} ({max_dir}) for {duration} seconds.")

    command = {
        "action": "set_phase",
        "id": TLS_ID,
        "phase": target_phase,
        "duration": float(duration)
    }
    client.publish(TOPIC_COMMANDS, json.dumps(command))

    # Cooldown to allow the command to arrive and phase to change
    time.sleep(5) 

# --- MQTT HANDLERS ---

def on_connect(client, userdata, flags, rc, properties=None):
    print("AI Agent Connected. Monitoring traffic...")
    client.subscribe(TOPIC_VEHICLES)
    client.subscribe(TOPIC_TL)

def on_message(client, userdata, msg):
    global current_phase_index, waiting_counts
    
    try:
        payload = json.loads(msg.payload.decode())

        if msg.topic == TOPIC_TL:
            lights = payload.get("lights", [])
            for tl in lights:
                if tl['id'] == TLS_ID:
                    current_phase_index = tl['phase']

        if msg.topic == TOPIC_VEHICLES:
            vehicles = payload.get("vehicles", [])
            waiting_counts = parse_lanes(vehicles)
            decide_phase(client)
            
    except Exception as e:
        print(f"AI Error: {e}")

# --- MAIN ---
if __name__ == "__main__":
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, 1883, 60)
    
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("AI Agent shutting down.")