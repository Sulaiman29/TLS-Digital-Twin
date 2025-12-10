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
    Use Phase 0 for North/South traffic.
    Use Phase 2 for East/West traffic.
    Duration should be between 20 and 60 seconds based on traffic density.
    """
    global mqtt_client
    
    direction = "North-South" if target_phase == 0 else "East-West"
    print(f"\n>>> TOOL EXECUTION: Switching to {direction} (Phase {target_phase}) for {duration}s")

    command = {
        "action": "set_phase",
        "id": TLS_ID,
        "phase": target_phase,
        "duration": float(duration)
    }
    
    if mqtt_client:
        mqtt_client.publish(TOPIC_COMMANDS, json.dumps(command))
        return f"Successfully sent command to switch to Phase {target_phase} for {duration} seconds."
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
            # 1. OBSERVE
            ns_count = waiting_counts["North"] + waiting_counts["South"]
            ew_count = waiting_counts["East"] + waiting_counts["West"]
            
            if current_phase_index == -1:
                time.sleep(1)
                continue

            # We craft the prompt to send to the Agent
            user_input = (
                f"Current Status: Active Phase is {current_phase_index}. "
                f"North/South Queue: {ns_count} cars. "
                f"East/West Queue: {ew_count} cars. "
                f"Decide if you need to switch phases to reduce congestion."
            )

            # 2. DECIDE & ACT
            # Only run if there is traffic to save API costs
            if ns_count > 0 or ew_count > 0:
                print(f"\n--- AI TICK ---\n{user_input}")
                
                # LangGraph uses a standard "messages" format
                events = agent_executor.invoke({
                    "messages": [("user", user_input)]
                })
                
                # Optional: Print the AI's final response if you want to see what it said
                # print(events["messages"][-1].content)
            
            # 3. SLEEP
            time.sleep(5)

    except KeyboardInterrupt:
        mqtt_client.loop_stop()
        print("Agent Stopped.")

if __name__ == "__main__":
    if "OPENAI_API_KEY" not in os.environ:
        print("ERROR: Please set your OPENAI_API_KEY environment variable.")
    else:
        run_agentic_loop()