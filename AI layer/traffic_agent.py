import json
import time
import paho.mqtt.client as mqtt

# --- CONFIGURATION ---
BROKER = "localhost"
TOPIC_VEHICLES = "simulation/vehicles/live"
TOPIC_TL = "simulation/tl/live"
TOPIC_COMMANDS = "simulation/commands"

# YOUR SPECIFIC IDS
TLS_ID = "C"  # From intersection_tls.add.xml

# STATE
current_phase_index = 0
waiting_counts = {
    "North": 0, 
    "East": 0, 
    "South": 0, 
    "West": 0
}

def parse_lanes(vehicles):
    """
    Maps specific lane IDs (N_C_0, E_C_1) to cardinal directions.
    """
    counts = {"North": 0, "East": 0, "South": 0, "West": 0}
    
    for v in vehicles:
        lane = v['lane']  # e.g., "N_C_0"
        speed = v['speed']
        
        # Only count cars that are stopped or moving very slowly (< 1.0 m/s)
        if speed < 1.0:
            if "N_C" in lane:    # Matches N_C_0, N_C_1
                counts["North"] += 1
            elif "E_C" in lane:  # Matches E_C_0, E_C_1
                counts["East"] += 1
            elif "S_C" in lane:  # Matches S_C_0, S_C_1
                counts["South"] += 1
            elif "W_C" in lane:  # Matches W_C_0, W_C_1
                counts["West"] += 1
                
    return counts

def on_message(client, userdata, msg):
    global current_phase_index, waiting_counts

    payload = json.loads(msg.payload.decode())

    # 1. Update Traffic Light State
    if msg.topic == TOPIC_TL:
        lights = payload.get("lights", [])
        for tl in lights:
            if tl['id'] == TLS_ID:
                current_phase_index = tl['phase']

    # 2. Update Vehicle Counts & Make Decision
    if msg.topic == TOPIC_VEHICLES:
        vehicles = payload.get("vehicles", [])
        waiting_counts = parse_lanes(vehicles)
        decide_phase(client)

def decide_phase(client):
    """
    Greedy Logic: Always try to switch to the direction with the MOST waiting cars.
    """
    # 1. Find the direction with the max queue
    busiest_direction = max(waiting_counts, key=waiting_counts.get)
    max_queue = waiting_counts[busiest_direction]
    
    print(f"Queues: N={waiting_counts['North']} E={waiting_counts['East']} "
          f"S={waiting_counts['South']} W={waiting_counts['West']} | "
          f"Active Phase: {current_phase_index}")

    # If traffic is light everywhere, don't intervene
    if max_queue < 2:
        return

    # 2. Map Direction to Phase ID (Based on your XML)
    # Phase 0 = North Green
    # Phase 2 = East Green
    # Phase 4 = South Green
    # Phase 6 = West Green
    target_phase = -1
    
    if busiest_direction == "North": target_phase = 0
    elif busiest_direction == "East": target_phase = 2
    elif busiest_direction == "South": target_phase = 4
    elif busiest_direction == "West": target_phase = 6

    # 3. Send Command if we aren't already in that phase
    # Note: We allow slight mismatch (e.g., if phase is 1 (North Yellow), we don't force 0 immediately)
    if target_phase != -1 and current_phase_index != target_phase:
        
        # Logic: Only switch if the new queue is significantly larger than others
        # This prevents rapid flickering
        print(f">>> AI Decision: Switching to {busiest_direction} (Phase {target_phase})")
        
        command = {
            "action": "set_phase",
            "id": TLS_ID,
            "phase": target_phase
        }
        client.publish(TOPIC_COMMANDS, json.dumps(command))
        
        # Artificial sleep to prevent spamming commands every millisecond
        time.sleep(5) 

# --- RUN AGENT ---
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(BROKER)
client.subscribe(TOPIC_VEHICLES)
client.subscribe(TOPIC_TL)
client.on_message = on_message

print(f"AI Agent Active. Controlling TLS: {TLS_ID}")
client.loop_forever()