"""
Multi-Agent Agentic Brain for Dual-Intersection Traffic Control
===============================================================
Architecture: TWO independent LLM agents, one per intersection.
  - Agent C1: Controls intersection C1 only (has set_c1_phase tool)
  - Agent C2: Controls intersection C2 only (has set_c2_phase tool)

Collaboration: Both agents read from a shared state object that includes
the OTHER intersection's queue counts and current phase. This enables
each agent to anticipate incoming corridor traffic and coordinate timing.
"""

import os
import json
import time
import threading
import paho.mqtt.client as mqtt
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

# --- CONFIGURATION ---
BROKER = "localhost"
TOPIC_VEHICLES = "simulation/multi/vehicles/live"
TOPIC_TL = "simulation/multi/tl/live"
TOPIC_COMMANDS = "simulation/multi/commands"

# =====================================================================
# SHARED STATE — both agents read from this, MQTT callbacks write to it
# This is the collaboration mechanism: each agent sees the other's state
# =====================================================================
shared_state = {
    "C1": {"phase": -1, "queues": {"North": 0, "South": 0, "West": 0, "Corridor": 0}},
    "C2": {"phase": -1, "queues": {"North": 0, "South": 0, "East": 0, "Corridor": 0}},
}
state_lock = threading.Lock()  # Thread-safe access
mqtt_client = None

# Phase name maps
C1_PHASE_NAMES = {0: "North", 1: "North(yellow)", 2: "South", 3: "South(yellow)",
                  4: "West", 5: "West(yellow)", 6: "Corridor", 7: "Corridor(yellow)"}
C2_PHASE_NAMES = {0: "North", 1: "North(yellow)", 2: "South", 3: "South(yellow)",
                  4: "East", 5: "East(yellow)", 6: "Corridor", 7: "Corridor(yellow)"}


# =====================================================================
# AGENT C1 — Tool + Prompt (only controls C1)
# =====================================================================
@tool
def set_c1_phase(target_phase: int, duration: int):
    """
    Switches YOUR intersection C1's traffic light to a specific phase.
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
    print(f"\n>>> [AGENT C1] TOOL: {direction} (Phase {target_phase}) for {duration}s")

    command = {"action": "set_phase", "id": "C1", "phase": target_phase, "duration": float(duration)}
    if mqtt_client:
        mqtt_client.publish(TOPIC_COMMANDS, json.dumps(command))
        return f"C1 switched to {direction} (Phase {target_phase}) for {duration}s."
    return "Error: MQTT not connected."


# =====================================================================
# AGENT C2 — Tool + Prompt (only controls C2)
# =====================================================================
@tool
def set_c2_phase(target_phase: int, duration: int):
    """
    Switches YOUR intersection C2's traffic light to a specific phase.
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
    print(f"\n>>> [AGENT C2] TOOL: {direction} (Phase {target_phase}) for {duration}s")

    command = {"action": "set_phase", "id": "C2", "phase": target_phase, "duration": float(duration)}
    if mqtt_client:
        mqtt_client.publish(TOPIC_COMMANDS, json.dumps(command))
        return f"C2 switched to {direction} (Phase {target_phase}) for {duration}s."
    return "Error: MQTT not connected."


# =====================================================================
# MQTT — Shared data ingestion
# =====================================================================
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
    try:
        payload = json.loads(msg.payload.decode())
        with state_lock:
            if msg.topic == TOPIC_TL:
                for tl in payload.get("lights", []):
                    if tl['id'] in shared_state:
                        shared_state[tl['id']]["phase"] = tl['phase']
            if msg.topic == TOPIC_VEHICLES:
                c1_counts, c2_counts = parse_lanes(payload.get("vehicles", []))
                shared_state["C1"]["queues"] = c1_counts
                shared_state["C2"]["queues"] = c2_counts
    except Exception as e:
        print(f"MQTT Error: {e}")


# =====================================================================
# AGENT LOOP — Each agent runs in its own thread
# =====================================================================
def build_c1_prompt():
    """Build prompt for Agent C1, including C2's state for collaboration."""
    with state_lock:
        c1 = shared_state["C1"]["queues"].copy()
        c2 = shared_state["C2"]["queues"].copy()
        c1_phase = shared_state["C1"]["phase"]
        c2_phase = shared_state["C2"]["phase"]

    c1_dir = C1_PHASE_NAMES.get(c1_phase, f"Phase {c1_phase}")
    c2_dir = C2_PHASE_NAMES.get(c2_phase, f"Phase {c2_phase}")

    return (
        f"You are Agent C1. You control ONLY intersection C1.\n"
        f"C1 is connected to intersection C2 via an east-west corridor.\n\n"
        f"YOUR INTERSECTION (C1) - Current green: {c1_dir} (phase {c1_phase})\n"
        f"  Your Queues: North={c1['North']}, South={c1['South']}, "
        f"West={c1['West']}, Corridor(from C2)={c1['Corridor']}\n\n"
        f"NEIGHBOR (C2) - Current green: {c2_dir} (phase {c2_phase})\n"
        f"  C2 Queues: North={c2['North']}, South={c2['South']}, "
        f"East={c2['East']}, Corridor(from C1)={c2['Corridor']}\n\n"
        f"COLLABORATION INFO:\n"
        f"- If C2 is releasing corridor traffic toward you (C2 phase=6), "
        f"prepare YOUR corridor green (phase 6) soon.\n"
        f"- If you give green to West/North/South, some cars will enter "
        f"the C1->C2 corridor. C2's corridor queue will grow.\n"
        f"- Prioritize the direction with the highest queue at YOUR intersection.\n"
        f"Use set_c1_phase to adjust your traffic light."
    ), c1, c1_phase


def build_c2_prompt():
    """Build prompt for Agent C2, including C1's state for collaboration."""
    with state_lock:
        c1 = shared_state["C1"]["queues"].copy()
        c2 = shared_state["C2"]["queues"].copy()
        c1_phase = shared_state["C1"]["phase"]
        c2_phase = shared_state["C2"]["phase"]

    c1_dir = C1_PHASE_NAMES.get(c1_phase, f"Phase {c1_phase}")
    c2_dir = C2_PHASE_NAMES.get(c2_phase, f"Phase {c2_phase}")

    return (
        f"You are Agent C2. You control ONLY intersection C2.\n"
        f"C2 is connected to intersection C1 via an east-west corridor.\n\n"
        f"YOUR INTERSECTION (C2) - Current green: {c2_dir} (phase {c2_phase})\n"
        f"  Your Queues: North={c2['North']}, South={c2['South']}, "
        f"East={c2['East']}, Corridor(from C1)={c2['Corridor']}\n\n"
        f"NEIGHBOR (C1) - Current green: {c1_dir} (phase {c1_phase})\n"
        f"  C1 Queues: North={c1['North']}, South={c1['South']}, "
        f"West={c1['West']}, Corridor(from C2)={c1['Corridor']}\n\n"
        f"COLLABORATION INFO:\n"
        f"- If C1 is releasing corridor traffic toward you (C1 giving green to "
        f"non-corridor directions), cars will soon arrive at YOUR corridor.\n"
        f"- If you give green to East/North/South, some cars will enter "
        f"the C2->C1 corridor. C1's corridor queue will grow.\n"
        f"- Prioritize the direction with the highest queue at YOUR intersection.\n"
        f"Use set_c2_phase to adjust your traffic light."
    ), c2, c2_phase


def agent_loop(agent_name, agent_executor, prompt_builder):
    """
    Independent decision loop for one agent.
    Each agent runs in its own thread with its own LLM instance.
    """
    print(f"[{agent_name}] Agent thread started.")

    while True:
        try:
            prompt, queues, phase = prompt_builder()

            if phase == -1:
                time.sleep(1)
                continue

            total = sum(queues.values())
            if total > 0:
                print(f"\n--- [{agent_name}] AI TICK ---")
                print(f"[{agent_name}] Queues: {queues} | Phase: {phase}")

                events = agent_executor.invoke({
                    "messages": [("user", prompt)]
                })

                response = events['messages'][-1].content
                print(f"[{agent_name}] Decision: {response}")

            time.sleep(5)

        except Exception as e:
            print(f"[{agent_name}] Error: {e}")
            time.sleep(5)


# =====================================================================
# MAIN — Start MQTT + two agent threads
# =====================================================================
def main():
    global mqtt_client

    # --- MQTT Setup ---
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.on_message = on_message
    mqtt_client.connect(BROKER, 1883, 60)
    mqtt_client.subscribe(TOPIC_VEHICLES)
    mqtt_client.subscribe(TOPIC_TL)
    mqtt_client.loop_start()

    print("=" * 60)
    print("  MULTI-AGENT TRAFFIC CONTROL — Two Independent AI Agents")
    print("=" * 60)

    # --- Create TWO separate LLM agents ---
    print("\nInitializing Agent C1 (own LLM instance)...")
    llm_c1 = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)
    agent_c1 = create_react_agent(llm_c1, [set_c1_phase])  # Only C1 tool

    print("Initializing Agent C2 (own LLM instance)...")
    llm_c2 = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)
    agent_c2 = create_react_agent(llm_c2, [set_c2_phase])  # Only C2 tool

    # --- Launch each agent in its own thread ---
    thread_c1 = threading.Thread(
        target=agent_loop,
        args=("Agent-C1", agent_c1, build_c1_prompt),
        daemon=True
    )
    thread_c2 = threading.Thread(
        target=agent_loop,
        args=("Agent-C2", agent_c2, build_c2_prompt),
        daemon=True
    )

    thread_c1.start()
    thread_c2.start()

    print("\nBoth agents are running. Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down both agents...")
        mqtt_client.loop_stop()
        print("Multi-Agent Brain Stopped.")


if __name__ == "__main__":
    if "OPENAI_API_KEY" not in os.environ:
        print("ERROR: Please set your OPENAI_API_KEY environment variable.")
    else:
        main()
