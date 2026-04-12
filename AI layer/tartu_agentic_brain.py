"""
Tartu Multi-Agent Agentic Brain for 4-Intersection Traffic Control
===================================================================
Architecture: FOUR independent LLM agents, one per intersection.
  - Agent TRiia_Kalevi : Controls Riia x Vabaduse
  - Agent TRiia_Turu : Controls Riia x Turu (Kaubamaja)
  - Agent TTuru_Soola : Controls Turu x Soola
  - Agent TTuru_Aida : Controls Turu x AidaSandri

Collaboration: All agents read from a shared state object that includes
NEIGHBOR intersections' queue counts and current phases. This enables
each agent to anticipate incoming corridor traffic and coordinate timing.

Network Topology (Inverted-T):
  TRiia_Kalevi (north) ←300m→ TRiia_Turu (center) ←300m→ TTuru_Soola ←300m→ TTuru_Aida (east)
"""

import os
import sys
import json
import time
import logging
import threading
import collections
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

import paho.mqtt.client as mqtt
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

# --- Blockchain module path ---
project_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from blockchain import BlockchainClient, TLSDecisionContract, AccessControlContract

# Blockchain toggle
BLOCKCHAIN_ENABLED = os.getenv("BLOCKCHAIN_ENABLED", "true").lower() != "false"

# Pending audit entries (tool stores, agent_loop publishes with reasoning)
pending_audit = {}

# --- CONFIGURATION ---
BROKER = os.getenv("MQTT_BROKER", "localhost")
TOPIC_VEHICLES = "simulation/tartu/vehicles/live"
TOPIC_TL = "simulation/tartu/tl/live"
TOPIC_COMMANDS = "simulation/tartu/commands"
TOPIC_AUDIT = "simulation/tartu/audit/live"

# Tuning parameters
MIN_HOLD_TIME = 15          # Min seconds before switching phase
MAX_STARVE_TIME = 90        # Max seconds a direction can go unserved
CORRIDOR_TRAVEL_TIME = 22   # Travel time between adjacent intersections (s)
DECISION_INTERVAL = 3       # Seconds between agent ticks
HISTORY_SIZE = 5            # Number of recent decisions to remember

# =====================================================================
# INTERSECTION CONFIGS — data-driven, same structure for all 4
# =====================================================================
INTERSECTION_CONFIG = {
    "TRiia_Kalevi": {
        "directions": ["Riia_North", "Vabaduse_West", "Vabaduse_East", "Corridor_South"],
        "green_phases": {0: "Riia_North", 2: "Vabaduse_West", 4: "Vabaduse_East", 6: "Corridor_South"},
        "phase_names": {
            0: "Riia_North", 1: "Riia_North(yellow)",
            2: "Vabaduse_West", 3: "Vabaduse_West(yellow)",
            4: "Vabaduse_East", 5: "Vabaduse_East(yellow)",
            6: "Corridor_South", 7: "Corridor_South(yellow)",
        },
        "neighbors": ["TRiia_Turu"],
        "corridor_from": {"TRiia_Turu": "Corridor_South"},
    },
    "TRiia_Turu": {
        "directions": ["Corridor_North", "Riia_South", "Turu_West", "Corridor_East"],
        "green_phases": {0: "Corridor_North", 2: "Riia_South", 4: "Turu_West", 6: "Corridor_East"},
        "phase_names": {
            0: "Corridor_North", 1: "Corridor_North(yellow)",
            2: "Riia_South", 3: "Riia_South(yellow)",
            4: "Turu_West", 5: "Turu_West(yellow)",
            6: "Corridor_East", 7: "Corridor_East(yellow)",
        },
        "neighbors": ["TRiia_Kalevi", "TTuru_Soola"],
        "corridor_from": {"TRiia_Kalevi": "Corridor_North", "TTuru_Soola": "Corridor_East"},
    },
    "TTuru_Soola": {
        "directions": ["Corridor_West", "Soola_North", "Soola_South", "Corridor_East"],
        "green_phases": {0: "Corridor_West", 2: "Soola_North", 4: "Soola_South", 6: "Corridor_East"},
        "phase_names": {
            0: "Corridor_West", 1: "Corridor_West(yellow)",
            2: "Soola_North", 3: "Soola_North(yellow)",
            4: "Soola_South", 5: "Soola_South(yellow)",
            6: "Corridor_East", 7: "Corridor_East(yellow)",
        },
        "neighbors": ["TRiia_Turu", "TTuru_Aida"],
        "corridor_from": {"TRiia_Turu": "Corridor_West", "TTuru_Aida": "Corridor_East"},
    },
    "TTuru_Aida": {
        "directions": ["Corridor_West", "AidaSandri_East", "AidaSandri_North", "AidaSandri_South"],
        "green_phases": {0: "Corridor_West", 2: "AidaSandri_East", 4: "AidaSandri_North", 6: "AidaSandri_South"},
        "phase_names": {
            0: "Corridor_West", 1: "Corridor_West(yellow)",
            2: "AidaSandri_East", 3: "AidaSandri_East(yellow)",
            4: "AidaSandri_North", 5: "AidaSandri_North(yellow)",
            6: "AidaSandri_South", 7: "AidaSandri_South(yellow)",
        },
        "neighbors": ["TTuru_Soola"],
        "corridor_from": {"TTuru_Soola": "Corridor_West"},
    },
}

# Lane substrings → (intersection_id, direction)
LANE_MAP = [
    ("RiiaN_RiiaKalevi",       "TRiia_Kalevi", "Riia_North"),
    ("UlikW_RiiaKalevi",       "TRiia_Kalevi", "Vabaduse_West"),
    ("KaleviE_RiiaKalevi",       "TRiia_Kalevi", "Vabaduse_East"),
    ("RiiaTuru_RiiaKalevi",    "TRiia_Kalevi", "Corridor_South"),
    ("RiiaKalevi_RiiaTuru",    "TRiia_Turu", "Corridor_North"),
    ("RiiaS_RiiaTuru",       "TRiia_Turu", "Riia_South"),
    ("TuruW_RiiaTuru",       "TRiia_Turu", "Turu_West"),
    ("TuruSoola_RiiaTuru",    "TRiia_Turu", "Corridor_East"),
    ("RiiaTuru_TuruSoola",    "TTuru_Soola", "Corridor_West"),
    ("SoolaN_TuruSoola",       "TTuru_Soola", "Soola_North"),
    ("SoolaS_TuruSoola",       "TTuru_Soola", "Soola_South"),
    ("TuruAida_TuruSoola",    "TTuru_Soola", "Corridor_East"),
    ("TuruSoola_TuruAida",    "TTuru_Aida", "Corridor_West"),
    ("AidaE_TuruAida",       "TTuru_Aida", "AidaSandri_East"),
    ("AidaN_TuruAida",       "TTuru_Aida", "AidaSandri_North"),
    ("AidaS_TuruAida",       "TTuru_Aida", "AidaSandri_South"),
]

# =====================================================================
# SHARED STATE — all agents read, MQTT callbacks write
# =====================================================================
shared_state = {}
for tls_id, cfg in INTERSECTION_CONFIG.items():
    shared_state[tls_id] = {
        "phase": -1,
        "queues": {d: 0 for d in cfg["directions"]},
        "last_switch_time": 0,
        "phase_set_time": 0,
        "phase_set_duration": 0,
        "last_green": {d: 0 for d in cfg["directions"]},
    }
state_lock = threading.Lock()
mqtt_client = None
tls_contract = None  # TLSDecisionContract instance (set in main)
access_control = None  # AccessControlContract instance (set in main)

# Decision history buffers (per agent)
decision_history = {tls_id: collections.deque(maxlen=HISTORY_SIZE) for tls_id in INTERSECTION_CONFIG}
history_lock = threading.Lock()


# =====================================================================
# SYSTEM PROMPTS — one per intersection
# =====================================================================
def build_system_prompt(tls_id):
    cfg = INTERSECTION_CONFIG[tls_id]
    directions = cfg["directions"]
    green_phases = cfg["green_phases"]
    neighbors = cfg["neighbors"]

    phase_desc = ", ".join(f"Phase {p}={d}" for p, d in green_phases.items())
    neighbor_desc = ", ".join(neighbors)
    corridor_desc = "\n".join(
        f"  - Traffic from {nb} arrives on your {corr_dir} approach (~{CORRIDOR_TRAVEL_TIME}s travel time)"
        for nb, corr_dir in cfg["corridor_from"].items()
    )

    return f"""You are an expert traffic signal control agent managing intersection {tls_id} in the Tartu city center road network (Estonia). You make ALL decisions autonomously.

INTERSECTION LAYOUT:
- {tls_id} has 4 approaches: {', '.join(directions)}
- You control which direction gets green using your set_{tls_id}_phase tool
- {phase_desc}

NETWORK CONTEXT:
- You are part of a 4-intersection corridor: TRiia_Kalevi ↔ TRiia_Turu ↔ TTuru_Soola ↔ TTuru_Aida
- Your direct neighbors: {neighbor_desc}
- Corridor connections:
{corridor_desc}

YOUR GOALS (in priority order):
1. MINIMIZE DELAY: Every second a vehicle waits at red is wasted time
2. PREVENT STARVATION: No direction should wait more than 90s without green
3. MAXIMIZE THROUGHPUT: Clear as many vehicles as possible per cycle
4. COORDINATE: When a neighbor releases corridor traffic toward you, be ready

CRITICAL RULES:
- NEVER keep a phase green when its queue is 0 and other directions have waiting vehicles
- A direction with vehicles waiting >60s deserves urgent attention
- Corridor traffic comes in platoons, arriving ~{CORRIDOR_TRAVEL_TIME}s after the neighbor releases them
- Shorter green for low queues (15-20s), longer for heavy queues (30-45s)
- Only use green phase numbers: 0, 2, 4, or 6. Never set yellow phases (1,3,5,7)

You will receive real-time queue data, phase timing, your recent decisions, and neighbor status. Analyze all information and call set_{tls_id}_phase."""


# =====================================================================
# TOOL FACTORY — creates a set_phase tool for a specific intersection
# =====================================================================
def make_set_phase_tool(tls_id):
    cfg = INTERSECTION_CONFIG[tls_id]
    green_phases = cfg["green_phases"]
    phase_doc = "\n".join(f"      Phase {p}: {d} green" for p, d in green_phases.items())

    @tool
    def set_phase(target_phase: int, duration: int):
        """Switches this intersection's traffic light to a specific green phase (0, 2, 4, or 6). Do NOT set yellow phases (1,3,5,7). Duration: 15-50 seconds."""
        global mqtt_client
        direction = green_phases.get(target_phase, f"Unknown({target_phase})")

        with state_lock:
            elapsed = time.time() - shared_state[tls_id]["last_switch_time"]
            if elapsed < MIN_HOLD_TIME:
                return f"Too soon to switch {tls_id} (wait {MIN_HOLD_TIME - elapsed:.0f}s). Staying on current phase."
            shared_state[tls_id]["last_switch_time"] = time.time()
            shared_state[tls_id]["phase_set_time"] = time.time()
            shared_state[tls_id]["phase_set_duration"] = duration
            if direction in shared_state[tls_id]["last_green"]:
                shared_state[tls_id]["last_green"][direction] = time.time()
            old_queues = shared_state[tls_id]["queues"].copy()

        with history_lock:
            decision_history[tls_id].append({
                "time": time.time(),
                "action": f"Phase {target_phase} ({direction})",
                "duration": duration,
                "queues_at_decision": old_queues,
            })

        # --- BLOCKCHAIN: Validate command via access control ---
        if access_control:
            try:
                allowed = access_control.validate_command(access_control.account, tls_id)
                if not allowed:
                    return f"Access denied: agent not authorized for {tls_id}"
            except Exception as ac_err:
                print(f"    [AccessControl] Validation error: {ac_err}")

        # --- BLOCKCHAIN: Log decision on-chain ---
        if tls_contract:
            try:
                input_hash = BlockchainClient.hash_data(old_queues)
                action_str = f"Phase {target_phase} ({direction}) for {duration}s"
                tx_hash = tls_contract.log_decision(tls_id, action_str, input_hash)
                print(f"    [Blockchain] Decision logged on-chain  ✔")

                # Store audit entry for agent_loop to publish with reasoning
                if mqtt_client:
                    import datetime
                    pending_audit[tls_id] = {
                        "intersection": tls_id,
                        "action": action_str,
                        "input_hash": input_hash,
                        "tx_hash": tx_hash if tx_hash else None,
                        "timestamp": datetime.datetime.utcnow().strftime("%H:%M:%S"),
                        "queues": old_queues,
                        "phase": target_phase,
                        "duration": duration,
                        "direction": direction,
                    }
            except Exception as bc_err:
                print(f"    [Blockchain] Log failed: {bc_err}")

        print(f"\n>>> [AGENT {tls_id}] TOOL: {direction} (Phase {target_phase}) for {duration}s")

        command = {"action": "set_phase", "id": tls_id, "phase": target_phase, "duration": float(duration)}
        if mqtt_client:
            mqtt_client.publish(TOPIC_COMMANDS, json.dumps(command))
            return f"{tls_id} switched to {direction} (Phase {target_phase}) for {duration}s."
        return "Error: MQTT not connected."

    # Rename tool so the LLM sees a unique name
    set_phase.name = f"set_{tls_id}_phase"
    set_phase.description = (
        f"Switches intersection {tls_id}'s traffic light to a specific phase.\n"
        f"Available GREEN phases ONLY:\n{phase_doc}\n"
        f"Do NOT set yellow phases (1,3,5,7). Duration: 15-50 seconds."
    )
    return set_phase


# =====================================================================
# MQTT — Shared data ingestion
# =====================================================================
def parse_lanes(vehicles):
    counts = {}
    for tls_id, cfg in INTERSECTION_CONFIG.items():
        counts[tls_id] = {d: 0 for d in cfg["directions"]}

    for v in vehicles:
        lane = v['lane']
        for lane_substr, tls_id, direction in LANE_MAP:
            if lane_substr in lane:
                counts[tls_id][direction] += 1
                break
    return counts


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        with state_lock:
            if msg.topic == TOPIC_TL:
                for tl in payload.get("lights", []):
                    if tl['id'] in shared_state:
                        shared_state[tl['id']]["phase"] = tl['phase']
            if msg.topic == TOPIC_VEHICLES:
                all_counts = parse_lanes(payload.get("vehicles", []))
                for tls_id in INTERSECTION_CONFIG:
                    shared_state[tls_id]["queues"] = all_counts[tls_id]
    except Exception as e:
        print(f"MQTT Error: {e}")


# =====================================================================
# PROMPT BUILDER — Generic for any intersection
# =====================================================================
def format_history(agent_id):
    with history_lock:
        history = list(decision_history[agent_id])
    if not history:
        return "No previous decisions yet (this is your first decision)."

    now = time.time()
    lines = []
    for h in history:
        ago = now - h["time"]
        queues_str = ", ".join(f"{k}={v}" for k, v in h["queues_at_decision"].items())
        lines.append(f"  [{ago:.0f}s ago] {h['action']} for {h['duration']}s (queues were: {queues_str})")
    return "\n".join(lines)


def build_prompt(tls_id):
    """Build rich context prompt for any intersection agent."""
    cfg = INTERSECTION_CONFIG[tls_id]
    now = time.time()

    with state_lock:
        my_queues = shared_state[tls_id]["queues"].copy()
        my_phase = shared_state[tls_id]["phase"]
        last_green = shared_state[tls_id]["last_green"].copy()
        phase_set_time = shared_state[tls_id]["phase_set_time"]
        phase_set_duration = shared_state[tls_id]["phase_set_duration"]

        # Gather neighbor info
        neighbor_info = {}
        for nb_id in cfg["neighbors"]:
            nb_cfg = INTERSECTION_CONFIG[nb_id]
            neighbor_info[nb_id] = {
                "phase": shared_state[nb_id]["phase"],
                "queues": shared_state[nb_id]["queues"].copy(),
                "phase_set_time": shared_state[nb_id]["phase_set_time"],
                "phase_set_duration": shared_state[nb_id]["phase_set_duration"],
            }

    my_dir = cfg["phase_names"].get(my_phase, f"Phase {my_phase}")

    # Phase timing
    if phase_set_time > 0:
        phase_elapsed = now - phase_set_time
        phase_remaining = max(0, phase_set_duration - phase_elapsed)
        timing_str = (f"Current phase: {my_dir} — running for {phase_elapsed:.0f}s, "
                      f"{phase_remaining:.0f}s remaining of planned {phase_set_duration}s.")
        if phase_remaining <= 0:
            timing_str += " EXPIRED — you should switch to the next best direction now."
    else:
        timing_str = f"Current phase: {my_dir} (phase {my_phase}) — timing unknown (not set by you yet)."

    # Starvation
    starvation_lines = []
    for direction, last_t in last_green.items():
        q = my_queues.get(direction, 0)
        if last_t == 0:
            if q > 0:
                starvation_lines.append(f"  ⚠ {direction}: NEVER SERVED — {q} vehicles waiting!")
            else:
                starvation_lines.append(f"  {direction}: never served (0 vehicles)")
        else:
            wait_s = now - last_t
            if wait_s > MAX_STARVE_TIME and q > 0:
                starvation_lines.append(f"  ⚠ {direction}: STARVED {wait_s:.0f}s — {q} vehicles waiting!")
            elif wait_s > 60 and q > 0:
                starvation_lines.append(f"  ⚡ {direction}: waiting {wait_s:.0f}s — {q} vehicles (getting urgent)")
            else:
                starvation_lines.append(f"  {direction}: last green {wait_s:.0f}s ago — {q} vehicles")

    # Neighbor info
    neighbor_lines = []
    for nb_id, nb in neighbor_info.items():
        nb_cfg = INTERSECTION_CONFIG[nb_id]
        nb_dir = nb_cfg["phase_names"].get(nb["phase"], f"Phase {nb['phase']}")
        nb_elapsed = now - nb["phase_set_time"] if nb["phase_set_time"] > 0 else 0
        nb_remaining = max(0, nb["phase_set_duration"] - nb_elapsed) if nb["phase_set_time"] > 0 else 0
        # What corridor queue is heading toward us from this neighbor?
        corr_dir = cfg["corridor_from"].get(nb_id, None)
        corr_q = my_queues.get(corr_dir, 0) if corr_dir else 0
        neighbor_lines.append(
            f"  {nb_id}: {nb_dir} (running {nb_elapsed:.0f}s, ~{nb_remaining:.0f}s remaining). "
            f"Corridor queue heading to you: {corr_q} vehicles."
        )

    # Drain detection
    current_green_dir = cfg["green_phases"].get(my_phase, None)
    drain_alert = ""
    if current_green_dir and my_queues.get(current_green_dir, 0) == 0:
        other_waiting = sum(v for k, v in my_queues.items() if k != current_green_dir and v > 0)
        if other_waiting > 0:
            drain_alert = (f"\n🚨 DRAIN: Current green direction ({current_green_dir}) has 0 vehicles "
                          f"but {other_waiting} vehicles wait on other approaches. Switch NOW.")

    # Build queue string
    queue_parts = ", ".join(f"{d}={my_queues[d]}" for d in cfg["directions"])
    total_waiting = sum(my_queues.values())
    history_str = format_history(tls_id)

    return (
        f"=== INTERSECTION {tls_id} STATUS UPDATE ===\n\n"
        f"QUEUES: {queue_parts} (Total: {total_waiting} vehicles)\n\n"
        f"TIMING: {timing_str}\n\n"
        f"WAIT TIMES PER DIRECTION:\n" + "\n".join(starvation_lines) + "\n\n"
        f"NEIGHBORS:\n" + "\n".join(neighbor_lines) + "\n"
        f"{drain_alert}\n\n"
        f"YOUR RECENT DECISIONS:\n{history_str}\n\n"
        f"Analyze the situation and call set_{tls_id}_phase with your chosen phase and duration."
    ), my_queues, my_phase


# =====================================================================
# AGENT LOOP — Each agent runs its own thread
# =====================================================================
def should_call_llm(agent_id, queues, phase):
    now = time.time()
    with state_lock:
        phase_set_time = shared_state[agent_id]["phase_set_time"]
        phase_set_duration = shared_state[agent_id]["phase_set_duration"]

    green_phases = INTERSECTION_CONFIG[agent_id]["green_phases"]
    current_dir = green_phases.get(phase, None)

    if phase_set_time == 0:
        return True

    phase_elapsed = now - phase_set_time
    phase_remaining = phase_set_duration - phase_elapsed

    if phase_remaining <= 0:
        return True

    if current_dir and queues.get(current_dir, 0) == 0:
        other_waiting = sum(v for k, v in queues.items() if k != current_dir)
        if other_waiting > 0:
            return True

    if current_dir and queues.get(current_dir, 0) > 0 and phase_remaining > 5:
        return False

    return True


def agent_loop(agent_name, agent_id, agent_executor, system_prompt):
    print(f"[{agent_name}] Agent thread started.")

    while True:
        try:
            prompt, queues, phase = build_prompt(agent_id)

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

                # Publish pending audit entries with LLM reasoning
                if agent_id in pending_audit and mqtt_client:
                    entry = pending_audit.pop(agent_id)
                    entry["reasoning"] = response
                    entry["context"] = prompt[:500]  # first 500 chars of context
                    mqtt_client.publish(TOPIC_AUDIT, json.dumps(entry))
            else:
                if total > 0:
                    print(f"[{agent_name}] Skipping LLM call — current phase active with traffic.")

            time.sleep(DECISION_INTERVAL)

        except Exception as e:
            print(f"[{agent_name}] Error: {e}")
            time.sleep(DECISION_INTERVAL)


# =====================================================================
# MAIN — Start MQTT + four agent threads
# =====================================================================
def main():
    global mqtt_client, tls_contract, access_control

    # --- MQTT Setup ---
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.on_message = on_message
    mqtt_client.connect(BROKER, 1883, 60)
    mqtt_client.subscribe(TOPIC_VEHICLES)
    mqtt_client.subscribe(TOPIC_TL)
    mqtt_client.loop_start()

    # --- Blockchain Setup ---
    if BLOCKCHAIN_ENABLED:
        logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")
        bc = BlockchainClient()
        if bc.is_connected:
            # Deploy TLS Decision Logger
            tls_contract = TLSDecisionContract.deploy(bc)
            tls_contract.register_agent(bc.account)
            print(f"[Blockchain] TLSDecisionLog deployed  ✔  {tls_contract.address}")

            # Deploy Access Control
            access_control = AccessControlContract.deploy(bc)
            access_control.grant_role(bc.account, "AI_AGENT")
            for tls_id in INTERSECTION_CONFIG:
                access_control.register_intersection(tls_id)
            print(f"[Blockchain] AccessControl deployed  ✔  {access_control.address}")
            print(f"[Blockchain] Registered {len(INTERSECTION_CONFIG)} intersections, agent authorized")
        else:
            print("[Blockchain] Not connected — decision logging disabled.")
    else:
        print("[Blockchain] Disabled via BLOCKCHAIN_ENABLED=false")

    print("=" * 65)
    print("  TARTU 4-AGENT TRAFFIC CONTROL — Autonomous AI Agents")
    print("  Intersections: TRiia_Kalevi | TRiia_Turu | TTuru_Soola | TTuru_Aida")
    print("  Model: GPT-4o-mini | Decision interval: 3s")
    print("  Features: System prompt, Decision history, Phase timing")
    print("  Blockchain: " + (f"ON — {tls_contract.address}" if tls_contract else "OFF"))
    print("=" * 65)

    # --- Create 4 separate LLM agents ---
    agents = {}
    tools_map = {}
    for tls_id in INTERSECTION_CONFIG:
        print(f"\nInitializing Agent {tls_id} (GPT-4o-mini)...")
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        phase_tool = make_set_phase_tool(tls_id)
        tools_map[tls_id] = phase_tool
        agents[tls_id] = create_react_agent(llm, [phase_tool])

    # --- Launch each agent in its own thread ---
    threads = []
    for tls_id in INTERSECTION_CONFIG:
        system_prompt = build_system_prompt(tls_id)
        t = threading.Thread(
            target=agent_loop,
            args=(f"Agent-{tls_id}", tls_id, agents[tls_id], system_prompt),
            daemon=True
        )
        threads.append(t)
        t.start()

    print(f"\nAll {len(threads)} agents are running autonomously. Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down all agents...")
        mqtt_client.loop_stop()
        print("Tartu Multi-Agent Brain Stopped.")


if __name__ == "__main__":
    if "OPENAI_API_KEY" not in os.environ:
        print("ERROR: Please set your OPENAI_API_KEY environment variable.")
    else:
        main()
