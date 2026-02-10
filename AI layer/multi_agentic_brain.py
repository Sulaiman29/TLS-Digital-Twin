import os
import json
import time
import paho.mqtt.client as mqtt
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

# --- CONFIGURATION ---
BROKER = "localhost"
TOPIC_VEHICLES = "simulation/multi/vehicles/live"
TOPIC_TL = "simulation/multi/tl/live"
TOPIC_COMMANDS = "simulation/multi/commands"

# --- GLOBAL STATE ---
tls_state = {
    "C1": {"phase": -1},
    "C2": {"phase": -1},
}
waiting_counts = {
    "C1": {"North": 0, "South": 0, "West": 0, "Corridor": 0},
    "C2": {"North": 0, "South": 0, "East": 0, "Corridor": 0},
}
mqtt_client = None

# --- 1. DEFINE TOOLS ---
@tool
def set_c1_phase(target_phase: int, duration: int):
    """
    Switches Intersection C1's traffic light to a specific phase.
    Available phases (GREEN only):
      Phase 0: North green (vehicles from N1 approach)
      Phase 2: South green (vehicles from S1 approach)
      Phase 4: West green (vehicles from W approach)
      Phase 6: Corridor green (vehicles arriving from C2)
    Yellow phases (1,3,5,7) are transitional - do not set directly.
    Duration should be between 15 and 45 seconds based on queue length.
    """
    global mqtt_client
    phase_names = {0: "North", 2: "South", 4: "West", 6: "Corridor"}
    direction = phase_names.get(target_phase, f"Unknown({target_phase})")
    print(f"\n>>> TOOL: C1 -> {direction} (Phase {target_phase}) for {duration}s")

    command = {"action": "set_phase", "id": "C1", "phase": target_phase, "duration": float(duration)}
    if mqtt_client:
        mqtt_client.publish(TOPIC_COMMANDS, json.dumps(command))
        return f"C1 switched to {direction} (Phase {target_phase}) for {duration}s."
    return "Error: MQTT not connected."

@tool
def set_c2_phase(target_phase: int, duration: int):
    """
    Switches Intersection C2's traffic light to a specific phase.
    Available phases (GREEN only):
      Phase 0: North green (vehicles from N2 approach)
      Phase 2: South green (vehicles from S2 approach)
      Phase 4: East green (vehicles from E approach)
      Phase 6: Corridor green (vehicles arriving from C1)
    Yellow phases (1,3,5,7) are transitional - do not set directly.
    Duration should be between 15 and 45 seconds based on queue length.
    """
    global mqtt_client
    phase_names = {0: "North", 2: "South", 4: "East", 6: "Corridor"}
    direction = phase_names.get(target_phase, f"Unknown({target_phase})")
    print(f"\n>>> TOOL: C2 -> {direction} (Phase {target_phase}) for {duration}s")

    command = {"action": "set_phase", "id": "C2", "phase": target_phase, "duration": float(duration)}
    if mqtt_client:
        mqtt_client.publish(TOPIC_COMMANDS, json.dumps(command))
        return f"C2 switched to {direction} (Phase {target_phase}) for {duration}s."
    return "Error: MQTT not connected."

# --- 2. SETUP AGENT ---
def setup_agent():
    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)
    tools = [set_c1_phase, set_c2_phase]
    agent_executor = create_react_agent(llm, tools)
    return agent_executor

# --- 3. MQTT LOGIC ---
def parse_lanes(vehicles):
    c1 = {"North": 0, "South": 0, "West": 0, "Corridor": 0}
    c2 = {"North": 0, "South": 0, "East": 0, "Corridor": 0}
    for v in vehicles:
        lane = v['lane']
        if "N1_C1" in lane: c1["North"] += 1
        elif "S1_C1" in lane: c1["South"] += 1
        elif "W_C1" in lane: c1["West"] += 1
        elif "C2_C1" in lane: c1["Corridor"] += 1
        elif "N2_C2" in lane: c2["North"] += 1
        elif "S2_C2" in lane: c2["South"] += 1
        elif "E_C2" in lane: c2["East"] += 1
        elif "C1_C2" in lane: c2["Corridor"] += 1
    return c1, c2

def on_message(client, userdata, msg):
    global waiting_counts
    try:
        payload = json.loads(msg.payload.decode())
        if msg.topic == TOPIC_TL:
            for tl in payload.get("lights", []):
                if tl['id'] in tls_state:
                    tls_state[tl['id']]["phase"] = tl['phase']
        if msg.topic == TOPIC_VEHICLES:
            c1_counts, c2_counts = parse_lanes(payload.get("vehicles", []))
            waiting_counts["C1"] = c1_counts
            waiting_counts["C2"] = c2_counts
    except Exception as e:
        print(f"MQTT Error: {e}")

# --- 4. PHASE NAME HELPERS ---
C1_PHASE_NAMES = {0: "North", 1: "North(yellow)", 2: "South", 3: "South(yellow)",
                  4: "West", 5: "West(yellow)", 6: "Corridor", 7: "Corridor(yellow)"}
C2_PHASE_NAMES = {0: "North", 1: "North(yellow)", 2: "South", 3: "South(yellow)",
                  4: "East", 5: "East(yellow)", 6: "Corridor", 7: "Corridor(yellow)"}

# --- 5. MAIN LOOP ---
def run_agentic_loop():
    global mqtt_client

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.on_message = on_message
    mqtt_client.connect(BROKER, 1883, 60)
    mqtt_client.subscribe(TOPIC_VEHICLES)
    mqtt_client.subscribe(TOPIC_TL)
    mqtt_client.loop_start()

    print("Initializing Multi-Agent LangGraph Brain...")
    agent_executor = setup_agent()
    print("Agent Active. Monitoring BOTH intersections...")

    try:
        while True:
            c1 = waiting_counts["C1"]
            c2 = waiting_counts["C2"]
            c1_phase = tls_state["C1"]["phase"]
            c2_phase = tls_state["C2"]["phase"]
            total = sum(c1.values()) + sum(c2.values())

            if c1_phase == -1 or c2_phase == -1:
                time.sleep(1)
                continue

            c1_dir = C1_PHASE_NAMES.get(c1_phase, f"Phase {c1_phase}")
            c2_dir = C2_PHASE_NAMES.get(c2_phase, f"Phase {c2_phase}")

            # KEY: Each agent gets context about BOTH intersections
            user_input = (
                f"You control TWO connected intersections (C1 and C2) linked by a corridor. "
                f"Vehicles leaving C1 eastbound arrive at C2, and vice versa.\n\n"
                f"INTERSECTION C1 - Current green: {c1_dir} (phase {c1_phase})\n"
                f"  Queues: North={c1['North']}, South={c1['South']}, "
                f"West={c1['West']}, Corridor(from C2)={c1['Corridor']}\n\n"
                f"INTERSECTION C2 - Current green: {c2_dir} (phase {c2_phase})\n"
                f"  Queues: North={c2['North']}, South={c2['South']}, "
                f"East={c2['East']}, Corridor(from C1)={c2['Corridor']}\n\n"
                f"COORDINATION RULES:\n"
                f"- If C1 gives green to its West/South/North, those cars may head to C2 via corridor.\n"
                f"- If many cars are in the C1->C2 corridor, C2 should prepare corridor green (phase 6).\n"
                f"- Avoid both intersections being in corridor-green simultaneously (wastes capacity).\n"
                f"- Prioritize the direction with the highest queue at each intersection.\n"
                f"Set phases for whichever intersection(s) need adjustment."
            )

            if total > 0:
                print(f"\n--- MULTI-AGENT AI TICK ---")
                print(f"C1: {c1} (phase {c1_phase})  |  C2: {c2} (phase {c2_phase})")

                events = agent_executor.invoke({
                    "messages": [("user", user_input)]
                })

                print(f"AI Response: {events['messages'][-1].content}")

            time.sleep(5)

    except KeyboardInterrupt:
        mqtt_client.loop_stop()
        print("Multi-Agent Brain Stopped.")

if __name__ == "__main__":
    if "OPENAI_API_KEY" not in os.environ:
        print("ERROR: Please set your OPENAI_API_KEY environment variable.")
    else:
        run_agentic_loop()
