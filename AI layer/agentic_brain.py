import os
import json
import time
import paho.mqtt.client as mqtt
from langchain_openai import ChatOpenAI
from langchain.agents import tool, AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# --- CONFIGURATION ---
BROKER = "localhost"
TOPIC_VEHICLES = "simulation/vehicles/live"
TOPIC_TL = "simulation/tl/live"
TOPIC_COMMANDS = "simulation/commands"
TLS_ID = "C"

# --- GLOBAL STATE (The Agent's "Short Term Memory") ---
current_phase_index = -1
waiting_counts = {"North": 0, "East": 0, "South": 0, "West": 0}
mqtt_client = None  # Will be set in main

# --- 1. DEFINE THE TOOL (The "Act" part) ---
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

# --- 2. SETUP THE AGENT (The "Reasoning" part) ---
def setup_agent():
    # Initialize LLM (GPT-3.5 is fast/cheap, GPT-4 is smarter)
    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)
    
    tools = [set_traffic_phase]
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an intelligent Traffic Control Assistant responsible for a busy intersection.
        
        YOUR GOAL: Minimize congestion and prevent long queues.
        
        SYSTEM RULES:
        1. The intersection has two main phases:
           - Phase 0: Green for North & South.
           - Phase 2: Green for East & West.
        2. You receive the current queue lengths and the currently active phase.
        3. Logic:
           - If the active phase matches the busiest direction, DO NOTHING (let traffic flow).
           - If the inactive direction is building up a huge queue, switch to it.
           - Never switch phases too frequently (flickering).
        
        Wait implies doing nothing and letting the current phase run.
        """),
        ("user", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_openai_tools_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
    return agent_executor

# --- 3. MQTT LOGIC (The "Observation" part) ---
def parse_lanes(vehicles):
    """Updates global waiting counts based on vehicle positions."""
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

    print("Initializing Agentic Brain...")
    agent_executor = setup_agent()
    print("Agent Active. Thinking...")

    try:
        while True:
            # 1. OBSERVE
            # We aggregate data for simple prompting
            ns_count = waiting_counts["North"] + waiting_counts["South"]
            ew_count = waiting_counts["East"] + waiting_counts["West"]
            
            # Skip if simulation hasn't started
            if current_phase_index == -1:
                time.sleep(1)
                continue

            observation_text = (
                f"OBSERVATION:\n"
                f"- Active Phase: {current_phase_index}\n"
                f"- North+South Queue: {ns_count} cars\n"
                f"- East+West Queue: {ew_count} cars\n"
            )

            # 2. DECIDE (Run the ReAct Chain)
            # We only query the LLM if there is actually traffic to manage
            # to save tokens/money.
            if ns_count > 0 or ew_count > 0:
                print(f"\n--- AI TICK ---\n{observation_text}")
                
                result = agent_executor.invoke({
                    "input": observation_text
                })
                
                # The 'verbose=True' in the agent will show you the "Thought" process in the terminal
            
            # 3. SLEEP
            # LLMs are slow and expensive. We don't need to think every 0.1s.
            # Thinking every 5-10 seconds is realistic for traffic control.
            time.sleep(5)

    except KeyboardInterrupt:
        mqtt_client.loop_stop()
        print("Agent Stopped.")

if __name__ == "__main__":
    # Ensure you set this in your terminal: export OPENAI_API_KEY="sk-..."
    if "OPENAI_API_KEY" not in os.environ:
        print("ERROR: Please set your OPENAI_API_KEY environment variable.")
    else:
        run_agentic_loop()