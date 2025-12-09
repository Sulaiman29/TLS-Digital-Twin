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
    Logic for 2-Phase System (NS vs EW) with Dynamic Duration.
    """
    global current_phase_index

    # 1. GROUP THE TEAMS
    # Phase 0 serves both North and South
    ns_score = waiting_counts["North"] + waiting_counts["South"]
    
    # Phase 2 serves both East and West
    ew_score = waiting_counts["East"] + waiting_counts["West"]

    print(f"Queue Status -> NS: {ns_score} | EW: {ew_score} (Active Phase: {current_phase_index})")

    # 2. DECIDE WINNER
    target_phase = -1
    winning_count = 0

    # Hysteresis: Only switch if the other side has > 2 more cars
    if ns_score > ew_score + 2:
        target_phase = 0  # North-South Green
        winning_count = ns_score
    elif ew_score > ns_score + 2:
        target_phase = 2  # East-West Green
        winning_count = ew_score

    # 3. EXECUTE SWITCH
    if target_phase != -1:
        # If already in the correct phase, do nothing
        if current_phase_index == target_phase:
            return 
        
        # If in Yellow transition (Phase 1 or 3), wait for it to finish
        if current_phase_index in [1, 3]:
             print(">>> AI: Light is transitioning... Waiting.")
             return 

        # 4. CALCULATE DYNAMIC DURATION
        # Base 10s + (2s per car). Clamped between 15s and 60s.
        duration = 10 + (winning_count * 2)
        duration = max(15, min(duration, 60))

        direction_name = "North-South" if target_phase == 0 else "East-West"
        print(f">>> AI: Heavy Traffic on {direction_name} ({winning_count} cars).")
        print(f">>> Command: Switch to Phase {target_phase} for {duration} seconds.")
        
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