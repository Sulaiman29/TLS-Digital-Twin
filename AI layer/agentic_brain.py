import os
import json
import time
import paho.mqtt.client as mqtt
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

# --- CONFIGURATION ---
BROKER = "localhost"
TOPIC_VEHICLES = "simulation/vehicles/live"
TOPIC_TL = "simulation/tl/live"
TOPIC_COMMANDS = "simulation/commands"
TLS_ID = "C"

# --- GLOBAL STATE ---
current_phase_index = -1
waiting_counts = {"North": 0, "East": 0, "South": 0, "West": 0}
mqtt_client = None

# --- 1. DEFINE THE TOOL ---
@tool
def set_traffic_phase(target_phase: int, duration: int):
    """
    Switches the traffic light to a specific phase for a specific duration.
    Available phases (use GREEN phases only):
      Phase 0: North green (vehicles approaching from North)
      Phase 2: East green (vehicles approaching from East)
      Phase 4: South green (vehicles approaching from South)
      Phase 6: West green (vehicles approaching from West)
    Yellow phases (1,3,5,7) are transitional - do not set directly.
    Duration should be between 15 and 45 seconds based on queue length for that direction.
    """
    global mqtt_client
    
    phase_names = {0: "North", 2: "East", 4: "South", 6: "West"}
    direction = phase_names.get(target_phase, f"Unknown({target_phase})")
    print(f"\n>>> TOOL EXECUTION: Switching to {direction} (Phase {target_phase}) for {duration}s")

    command = {
        "action": "set_phase",
        "id": TLS_ID,
        "phase": target_phase,
        "duration": float(duration)
    }
    
    if mqtt_client:
        mqtt_client.publish(TOPIC_COMMANDS, json.dumps(command))
        return f"Successfully switched to {direction} (Phase {target_phase}) for {duration} seconds."
    else:
        return "Error: MQTT Client not connected."

# --- 2. SETUP THE AGENT (Modern LangGraph) ---
def setup_agent():
    # Initialize LLM
    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)
    
    tools = [set_traffic_phase]
    
    # LangGraph's prebuilt agent handles the prompt and loop automatically.
    # It is much cleaner than the old AgentExecutor.
    agent_executor = create_react_agent(llm, tools)
    
    return agent_executor

# --- 3. MQTT LOGIC ---
def parse_lanes(vehicles):
    counts = {"North": 0, "East": 0, "South": 0, "West": 0}
    for v in vehicles:
        lane = v['lane']
        if "N_C" in lane: counts["North"] += 1
        elif "E_C" in lane: counts["East"] += 1
        elif "S_C" in lane: counts["South"] += 1
        elif "W_C" in lane: counts["West"] += 1
    return counts

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
            
    except Exception as e:
        print(f"Error processing MQTT: {e}")

# --- 4. MAIN LOOP ---
def run_agentic_loop():
    global mqtt_client
    
    # Setup MQTT
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.on_message = on_message
    mqtt_client.connect(BROKER, 1883, 60)
    mqtt_client.subscribe(TOPIC_VEHICLES)
    mqtt_client.subscribe(TOPIC_TL)
    mqtt_client.loop_start()

    print("Initializing LangGraph Agent...")
    agent_executor = setup_agent()
    print("Agent Active. Monitoring Traffic...")

    try:
        while True:
            # 1. OBSERVE - get individual direction counts
            n_count = waiting_counts["North"]
            e_count = waiting_counts["East"]
            s_count = waiting_counts["South"]
            w_count = waiting_counts["West"]
            total_count = n_count + e_count + s_count + w_count
            
            if current_phase_index == -1:
                time.sleep(1)
                continue

            # Map phase index to direction name for context
            phase_names = {0: "North", 1: "North(yellow)", 2: "East", 3: "East(yellow)",
                           4: "South", 5: "South(yellow)", 6: "West", 7: "West(yellow)"}
            current_dir = phase_names.get(current_phase_index, f"Phase {current_phase_index}")

            # Craft prompt with individual direction counts
            user_input = (
                f"Traffic Signal Control - Current green: {current_dir} (phase {current_phase_index}). "
                f"Queue lengths: North={n_count}, East={e_count}, South={s_count}, West={w_count} vehicles. "
                f"Choose the direction with the highest queue to receive green next. "
                f"Use phase 0 for North, 2 for East, 4 for South, 6 for West."
            )

            # 2. DECIDE & ACT - only run if there is traffic
            if total_count > 0:
                print(f"\n--- AI TICK ---\n{user_input}")
                
                events = agent_executor.invoke({
                    "messages": [("user", user_input)]
                })
                
                # Print AI's final reasoning
                print(f"AI Response: {events['messages'][-1].content}")
            
            # 3. SLEEP - allow time for phase to execute
            time.sleep(5)

    except KeyboardInterrupt:
        mqtt_client.loop_stop()
        print("Agent Stopped.")

if __name__ == "__main__":
    if "OPENAI_API_KEY" not in os.environ:
        print("ERROR: Please set your OPENAI_API_KEY environment variable.")
    else:
        run_agentic_loop()