"""
Multi-Agent Agentic Brain for Dual-Intersection Traffic Control
===============================================================
Architecture: TWO independent LLM agents, one per intersection.
  - Agent C1: Controls intersection C1 only (has set_c1_phase tool)
  - Agent C2: Controls intersection C2 only (has set_c2_phase tool)

Collaboration: Both agents read from a shared state object that includes
the OTHER intersection's queue counts and current phase. This enables
each agent to anticipate incoming corridor traffic and coordinate timing.

Agent Enhancements:
  - GPT-4o-mini for better reasoning and instruction following
  - Expert system prompt with traffic engineering knowledge
  - Decision history buffer for temporal awareness
  - Phase elapsed time and remaining duration tracking
  - Smart 3s decision loop with skip logic
  - Enhanced neighbor awareness for corridor coordination
"""

import os
import json
import time
import threading
import collections
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
# =====================================================================
shared_state = {
    "C1": {"phase": -1, "queues": {"North": 0, "South": 0, "West": 0, "Corridor": 0},
           "last_switch_time": 0,
           "phase_set_time": 0,       # When was the current phase set by the agent
           "phase_set_duration": 0,    # How long the agent planned it for
           "last_green": {"North": 0, "South": 0, "West": 0, "Corridor": 0}},
    "C2": {"phase": -1, "queues": {"North": 0, "South": 0, "East": 0, "Corridor": 0},
           "last_switch_time": 0,
           "phase_set_time": 0,
           "phase_set_duration": 0,
           "last_green": {"North": 0, "South": 0, "East": 0, "Corridor": 0}},
}
state_lock = threading.Lock()
mqtt_client = None

# Tuning parameters
MIN_HOLD_TIME = 15          # Min seconds before switching phase
MAX_STARVE_TIME = 90        # Max seconds a direction can go unserved
CORRIDOR_TRAVEL_TIME = 22   # Travel time between intersections (s)
DECISION_INTERVAL = 3       # Seconds between agent ticks
HISTORY_SIZE = 5            # Number of recent decisions to remember

# Phase name maps
C1_PHASE_NAMES = {0: "North", 1: "North(yellow)", 2: "South", 3: "South(yellow)",
                  4: "West", 5: "West(yellow)", 6: "Corridor", 7: "Corridor(yellow)"}
C2_PHASE_NAMES = {0: "North", 1: "North(yellow)", 2: "South", 3: "South(yellow)",
                  4: "East", 5: "East(yellow)", 6: "Corridor", 7: "Corridor(yellow)"}

C1_GREEN_PHASES = {0: "North", 2: "South", 4: "West", 6: "Corridor"}
C2_GREEN_PHASES = {0: "North", 2: "South", 4: "East", 6: "Corridor"}

# Decision history buffers (per agent)
decision_history = {
    "C1": collections.deque(maxlen=HISTORY_SIZE),
    "C2": collections.deque(maxlen=HISTORY_SIZE),
}
history_lock = threading.Lock()


# =====================================================================
# SYSTEM PROMPTS — Expert traffic engineering knowledge
# =====================================================================
C1_SYSTEM_PROMPT = """You are an expert traffic signal control agent managing intersection C1 in a two-intersection corridor network. You make ALL decisions autonomously.

INTERSECTION LAYOUT:
- C1 has 4 approaches: North, South, West, and Corridor (from C2, ~22s away)
- You control which direction gets green using set_c1_phase tool
- Phase 0=North, Phase 2=South, Phase 4=West, Phase 6=Corridor

YOUR GOALS (in priority order):
1. MINIMIZE DELAY: Every second a vehicle waits at red is wasted time
2. PREVENT STARVATION: No direction should wait more than 90s without green
3. MAXIMIZE THROUGHPUT: Clear as many vehicles as possible per cycle
4. COORDINATE WITH C2: When C2 releases corridor traffic toward you, be ready to serve it

CRITICAL RULES:
- NEVER keep a phase green when its queue is 0 and other directions have waiting vehicles
- A direction with vehicles waiting >60s deserves urgent attention
- Corridor traffic is special: it comes in platoons from C2, arriving ~22s after C2 releases them
- Shorter green for low queues (15-20s), longer for heavy queues (30-45s)
- Only use green phase numbers: 0, 2, 4, or 6. Never set yellow phases (1,3,5,7)

You will receive real-time queue data, phase timing, your recent decision history, and C2's status. Analyze all information and make your decision by calling set_c1_phase."""

C2_SYSTEM_PROMPT = """You are an expert traffic signal control agent managing intersection C2 in a two-intersection corridor network. You make ALL decisions autonomously.

INTERSECTION LAYOUT:
- C2 has 4 approaches: North, South, East, and Corridor (from C1, ~22s away)
- You control which direction gets green using set_c2_phase tool
- Phase 0=North, Phase 2=South, Phase 4=East, Phase 6=Corridor

YOUR GOALS (in priority order):
1. MINIMIZE DELAY: Every second a vehicle waits at red is wasted time
2. PREVENT STARVATION: No direction should wait more than 90s without green
3. MAXIMIZE THROUGHPUT: Clear as many vehicles as possible per cycle
4. COORDINATE WITH C1: When C1 releases corridor traffic toward you, be ready to serve it

CRITICAL RULES:
- NEVER keep a phase green when its queue is 0 and other directions have waiting vehicles
- A direction with vehicles waiting >60s deserves urgent attention
- Corridor traffic is special: it comes in platoons from C1, arriving ~22s after C1 releases them
- Shorter green for low queues (15-20s), longer for heavy queues (30-45s)
- Only use green phase numbers: 0, 2, 4, or 6. Never set yellow phases (1,3,5,7)

You will receive real-time queue data, phase timing, your recent decision history, and C1's status. Analyze all information and make your decision by calling set_c2_phase."""


# =====================================================================
# AGENT C1 — Tool (only controls C1)
# =====================================================================
@tool
def set_c1_phase(target_phase: int, duration: int):
    """
    Switches YOUR intersection C1's traffic light to a specific phase.
    Available GREEN phases ONLY:
      Phase 0: North green
      Phase 2: South green
      Phase 4: West green
      Phase 6: Corridor green (from C2)
    Do NOT set yellow phases (1,3,5,7).
    Duration: 15-50 seconds.
    """
    global mqtt_client
    direction = C1_GREEN_PHASES.get(target_phase, f"Unknown({target_phase})")

    with state_lock:
        elapsed = time.time() - shared_state["C1"]["last_switch_time"]
        if elapsed < MIN_HOLD_TIME:
            return f"Too soon to switch C1 (wait {MIN_HOLD_TIME - elapsed:.0f}s). Staying on current phase."
        shared_state["C1"]["last_switch_time"] = time.time()
        shared_state["C1"]["phase_set_time"] = time.time()
        shared_state["C1"]["phase_set_duration"] = duration
        if direction in shared_state["C1"]["last_green"]:
            shared_state["C1"]["last_green"][direction] = time.time()
        old_queues = shared_state["C1"]["queues"].copy()

    # Record in decision history
    with history_lock:
        decision_history["C1"].append({
            "time": time.time(),
            "action": f"Phase {target_phase} ({direction})",
            "duration": duration,
            "queues_at_decision": old_queues,
        })

    print(f"\n>>> [AGENT C1] TOOL: {direction} (Phase {target_phase}) for {duration}s")

    command = {"action": "set_phase", "id": "C1", "phase": target_phase, "duration": float(duration)}
    if mqtt_client:
        mqtt_client.publish(TOPIC_COMMANDS, json.dumps(command))
        return f"C1 switched to {direction} (Phase {target_phase}) for {duration}s."
    return "Error: MQTT not connected."


# =====================================================================
# AGENT C2 — Tool (only controls C2)
# =====================================================================
@tool
def set_c2_phase(target_phase: int, duration: int):
    """
    Switches YOUR intersection C2's traffic light to a specific phase.
    Available GREEN phases ONLY:
      Phase 0: North green
      Phase 2: South green
      Phase 4: East green
      Phase 6: Corridor green (from C1)
    Do NOT set yellow phases (1,3,5,7).
    Duration: 15-50 seconds.
    """
    global mqtt_client
    direction = C2_GREEN_PHASES.get(target_phase, f"Unknown({target_phase})")

    with state_lock:
        elapsed = time.time() - shared_state["C2"]["last_switch_time"]
        if elapsed < MIN_HOLD_TIME:
            return f"Too soon to switch C2 (wait {MIN_HOLD_TIME - elapsed:.0f}s). Staying on current phase."
        shared_state["C2"]["last_switch_time"] = time.time()
        shared_state["C2"]["phase_set_time"] = time.time()
        shared_state["C2"]["phase_set_duration"] = duration
        if direction in shared_state["C2"]["last_green"]:
            shared_state["C2"]["last_green"][direction] = time.time()
        old_queues = shared_state["C2"]["queues"].copy()

    # Record in decision history
    with history_lock:
        decision_history["C2"].append({
            "time": time.time(),
            "action": f"Phase {target_phase} ({direction})",
            "duration": duration,
            "queues_at_decision": old_queues,
        })

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
# PROMPT BUILDERS — Rich context for autonomous LLM decisions
# =====================================================================
def format_history(agent_id):
    """Format recent decision history for the prompt."""
    with history_lock:
        history = list(decision_history[agent_id])
    if not history:
        return "No previous decisions yet (this is your first decision)."

    now = time.time()
    lines = []
    for i, h in enumerate(history):
        ago = now - h["time"]
        queues_str = ", ".join(f"{k}={v}" for k, v in h["queues_at_decision"].items())
        lines.append(f"  [{ago:.0f}s ago] {h['action']} for {h['duration']}s (queues were: {queues_str})")
    return "\n".join(lines)


def build_c1_prompt():
    """Build rich context prompt for Agent C1."""
    now = time.time()
    with state_lock:
        c1 = shared_state["C1"]["queues"].copy()
        c2 = shared_state["C2"]["queues"].copy()
        c1_phase = shared_state["C1"]["phase"]
        c2_phase = shared_state["C2"]["phase"]
        last_green = shared_state["C1"]["last_green"].copy()
        phase_set_time = shared_state["C1"]["phase_set_time"]
        phase_set_duration = shared_state["C1"]["phase_set_duration"]
        c2_phase_set_time = shared_state["C2"]["phase_set_time"]
        c2_phase_set_duration = shared_state["C2"]["phase_set_duration"]

    c1_dir = C1_PHASE_NAMES.get(c1_phase, f"Phase {c1_phase}")
    c2_dir = C2_PHASE_NAMES.get(c2_phase, f"Phase {c2_phase}")

    # Phase timing info
    if phase_set_time > 0:
        phase_elapsed = now - phase_set_time
        phase_remaining = max(0, phase_set_duration - phase_elapsed)
        timing_str = f"Current phase: {c1_dir} — running for {phase_elapsed:.0f}s, {phase_remaining:.0f}s remaining of planned {phase_set_duration}s."
        if phase_remaining <= 0:
            timing_str += " EXPIRED — you should switch to the next best direction now."
    else:
        timing_str = f"Current phase: {c1_dir} (phase {c1_phase}) — timing unknown (not set by you yet)."

    # Starvation info
    starvation_lines = []
    for direction, last_t in last_green.items():
        if last_t == 0:
            wait = "never served"
            if c1[direction] > 0:
                starvation_lines.append(f"  ⚠ {direction}: NEVER SERVED — {c1[direction]} vehicles waiting!")
            else:
                starvation_lines.append(f"  {direction}: never served (0 vehicles)")
        else:
            wait_s = now - last_t
            if wait_s > MAX_STARVE_TIME and c1[direction] > 0:
                starvation_lines.append(f"  ⚠ {direction}: STARVED {wait_s:.0f}s — {c1[direction]} vehicles waiting!")
            elif wait_s > 60 and c1[direction] > 0:
                starvation_lines.append(f"  ⚡ {direction}: waiting {wait_s:.0f}s — {c1[direction]} vehicles (getting urgent)")
            else:
                starvation_lines.append(f"  {direction}: last green {wait_s:.0f}s ago — {c1[direction]} vehicles")

    # Neighbor info
    c2_elapsed = now - c2_phase_set_time if c2_phase_set_time > 0 else 0
    c2_remaining = max(0, c2_phase_set_duration - c2_elapsed) if c2_phase_set_time > 0 else 0
    neighbor_str = (f"C2 status: {c2_dir} (running {c2_elapsed:.0f}s, ~{c2_remaining:.0f}s remaining). "
                    f"C2 corridor queue (heading to you): {c2.get('Corridor', 0)} vehicles.")

    # Drain detection
    current_green_dir = C1_GREEN_PHASES.get(c1_phase, None)
    drain_alert = ""
    if current_green_dir and c1.get(current_green_dir, 0) == 0:
        other_waiting = sum(v for k, v in c1.items() if k != current_green_dir and v > 0)
        if other_waiting > 0:
            drain_alert = f"\n🚨 DRAIN: Current green direction ({current_green_dir}) has 0 vehicles but {other_waiting} vehicles wait on other approaches. Switch NOW."

    # Decision history
    history_str = format_history("C1")

    total_waiting = sum(c1.values())

    return (
        f"=== INTERSECTION C1 STATUS UPDATE ===\n\n"
        f"QUEUES: North={c1['North']}, South={c1['South']}, West={c1['West']}, Corridor={c1['Corridor']} "
        f"(Total: {total_waiting} vehicles)\n\n"
        f"TIMING: {timing_str}\n\n"
        f"WAIT TIMES PER DIRECTION:\n" + "\n".join(starvation_lines) + "\n\n"
        f"NEIGHBOR: {neighbor_str}\n"
        f"{drain_alert}\n\n"
        f"YOUR RECENT DECISIONS:\n{history_str}\n\n"
        f"Analyze the situation and call set_c1_phase with your chosen phase and duration."
    ), c1, c1_phase


def build_c2_prompt():
    """Build rich context prompt for Agent C2."""
    now = time.time()
    with state_lock:
        c1 = shared_state["C1"]["queues"].copy()
        c2 = shared_state["C2"]["queues"].copy()
        c1_phase = shared_state["C1"]["phase"]
        c2_phase = shared_state["C2"]["phase"]
        last_green = shared_state["C2"]["last_green"].copy()
        phase_set_time = shared_state["C2"]["phase_set_time"]
        phase_set_duration = shared_state["C2"]["phase_set_duration"]
        c1_phase_set_time = shared_state["C1"]["phase_set_time"]
        c1_phase_set_duration = shared_state["C1"]["phase_set_duration"]

    c1_dir = C1_PHASE_NAMES.get(c1_phase, f"Phase {c1_phase}")
    c2_dir = C2_PHASE_NAMES.get(c2_phase, f"Phase {c2_phase}")

    # Phase timing info
    if phase_set_time > 0:
        phase_elapsed = now - phase_set_time
        phase_remaining = max(0, phase_set_duration - phase_elapsed)
        timing_str = f"Current phase: {c2_dir} — running for {phase_elapsed:.0f}s, {phase_remaining:.0f}s remaining of planned {phase_set_duration}s."
        if phase_remaining <= 0:
            timing_str += " EXPIRED — you should switch to the next best direction now."
    else:
        timing_str = f"Current phase: {c2_dir} (phase {c2_phase}) — timing unknown (not set by you yet)."

    # Starvation info
    starvation_lines = []
    for direction, last_t in last_green.items():
        if last_t == 0:
            if c2[direction] > 0:
                starvation_lines.append(f"  ⚠ {direction}: NEVER SERVED — {c2[direction]} vehicles waiting!")
            else:
                starvation_lines.append(f"  {direction}: never served (0 vehicles)")
        else:
            wait_s = now - last_t
            if wait_s > MAX_STARVE_TIME and c2[direction] > 0:
                starvation_lines.append(f"  ⚠ {direction}: STARVED {wait_s:.0f}s — {c2[direction]} vehicles waiting!")
            elif wait_s > 60 and c2[direction] > 0:
                starvation_lines.append(f"  ⚡ {direction}: waiting {wait_s:.0f}s — {c2[direction]} vehicles (getting urgent)")
            else:
                starvation_lines.append(f"  {direction}: last green {wait_s:.0f}s ago — {c2[direction]} vehicles")

    # Neighbor info
    c1_elapsed = now - c1_phase_set_time if c1_phase_set_time > 0 else 0
    c1_remaining = max(0, c1_phase_set_duration - c1_elapsed) if c1_phase_set_time > 0 else 0
    neighbor_str = (f"C1 status: {c1_dir} (running {c1_elapsed:.0f}s, ~{c1_remaining:.0f}s remaining). "
                    f"C1 corridor queue (heading to you): {c1.get('Corridor', 0)} vehicles.")

    # Drain detection
    current_green_dir = C2_GREEN_PHASES.get(c2_phase, None)
    drain_alert = ""
    if current_green_dir and c2.get(current_green_dir, 0) == 0:
        other_waiting = sum(v for k, v in c2.items() if k != current_green_dir and v > 0)
        if other_waiting > 0:
            drain_alert = f"\n🚨 DRAIN: Current green direction ({current_green_dir}) has 0 vehicles but {other_waiting} vehicles wait on other approaches. Switch NOW."

    # Decision history
    history_str = format_history("C2")

    total_waiting = sum(c2.values())

    return (
        f"=== INTERSECTION C2 STATUS UPDATE ===\n\n"
        f"QUEUES: North={c2['North']}, South={c2['South']}, East={c2['East']}, Corridor={c2['Corridor']} "
        f"(Total: {total_waiting} vehicles)\n\n"
        f"TIMING: {timing_str}\n\n"
        f"WAIT TIMES PER DIRECTION:\n" + "\n".join(starvation_lines) + "\n\n"
        f"NEIGHBOR: {neighbor_str}\n"
        f"{drain_alert}\n\n"
        f"YOUR RECENT DECISIONS:\n{history_str}\n\n"
        f"Analyze the situation and call set_c2_phase with your chosen phase and duration."
    ), c2, c2_phase


# =====================================================================
# AGENT LOOP — Each agent runs in its own thread
# =====================================================================
def should_call_llm(agent_id, queues, phase):
    """
    Smart skip logic: decide whether to call the LLM this tick.
    Skip if current phase still has traffic and hasn't expired yet.
    Always call if: drain detected, phase expired, or first decision.
    """
    now = time.time()
    with state_lock:
        phase_set_time = shared_state[agent_id]["phase_set_time"]
        phase_set_duration = shared_state[agent_id]["phase_set_duration"]

    green_phases = C1_GREEN_PHASES if agent_id == "C1" else C2_GREEN_PHASES
    current_dir = green_phases.get(phase, None)

    # Always call if we haven't made a decision yet
    if phase_set_time == 0:
        return True

    phase_elapsed = now - phase_set_time
    phase_remaining = phase_set_duration - phase_elapsed

    # Always call if phase expired
    if phase_remaining <= 0:
        return True

    # Always call if current direction has drain (0 vehicles) and others are waiting
    if current_dir and queues.get(current_dir, 0) == 0:
        other_waiting = sum(v for k, v in queues.items() if k != current_dir)
        if other_waiting > 0:
            return True

    # Skip if current phase still has traffic and time remaining
    if current_dir and queues.get(current_dir, 0) > 0 and phase_remaining > 5:
        return False

    return True


def agent_loop(agent_name, agent_id, agent_executor, prompt_builder, system_prompt):
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
            if total > 0 and should_call_llm(agent_id, queues, phase):
                print(f"\n--- [{agent_name}] AI TICK ---")
                print(f"[{agent_name}] Queues: {queues} | Phase: {phase}")

                events = agent_executor.invoke({
                    "messages": [
                        ("system", system_prompt),
                        ("user", prompt),
                    ]
                })

                response = events['messages'][-1].content
                print(f"[{agent_name}] Decision: {response}")
            else:
                if total == 0:
                    pass  # No vehicles, nothing to do
                else:
                    print(f"[{agent_name}] Skipping LLM call — current phase active with traffic.")

            time.sleep(DECISION_INTERVAL)

        except Exception as e:
            print(f"[{agent_name}] Error: {e}")
            time.sleep(DECISION_INTERVAL)


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
    print("  MULTI-AGENT TRAFFIC CONTROL — Autonomous AI Agents")
    print("  Model: GPT-4o-mini | Decision interval: 3s")
    print("  Features: System prompt, Decision history, Phase timing")
    print("=" * 60)

    # --- Create TWO separate LLM agents with GPT-4o-mini ---
    print("\nInitializing Agent C1 (GPT-4o-mini)...")
    llm_c1 = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    agent_c1 = create_react_agent(llm_c1, [set_c1_phase])

    print("Initializing Agent C2 (GPT-4o-mini)...")
    llm_c2 = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    agent_c2 = create_react_agent(llm_c2, [set_c2_phase])

    # --- Launch each agent in its own thread ---
    thread_c1 = threading.Thread(
        target=agent_loop,
        args=("Agent-C1", "C1", agent_c1, build_c1_prompt, C1_SYSTEM_PROMPT),
        daemon=True
    )
    thread_c2 = threading.Thread(
        target=agent_loop,
        args=("Agent-C2", "C2", agent_c2, build_c2_prompt, C2_SYSTEM_PROMPT),
        daemon=True
    )

    thread_c1.start()
    thread_c2.start()

    print("\nBoth agents are running autonomously. Press Ctrl+C to stop.\n")

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
