"""
Run LLM Agent Evaluation (Self-Contained)
==========================================
Runs SUMO headless with GPT-5.4 controlling all 4 intersections
directly via TraCI + OpenAI API. No MQTT, no blockchain needed.

Usage:
  python run_llm_agent.py                           # Run all 9 scenarios
  python run_llm_agent.py --profile normal --seed 1  # Run one scenario
"""

import os
import sys
import json
import argparse
import time
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"))

if "SUMO_HOME" not in os.environ:
    sys.exit("ERROR: Set SUMO_HOME environment variable.")
sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))
import traci

from openai import OpenAI

# --- PATHS ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NET_FILE = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "network", "tartu.net.xml"))
ADDITIONAL_TLS = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "network", "tartu_tls.add.xml"))
ADDITIONAL_DET = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "network", "detectors.add.xml"))
ROUTES_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "routes"))
OUTPUT_BASE = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "outputs"))

PROFILES = ["off_peak", "normal", "peak"]
SEEDS = [1, 2, 3]
SIM_END = 3600
TARTU_TLS_IDS = ["TRiia_Kalevi", "TRiia_Turu", "TTuru_Soola", "TTuru_Aida"]

# --- LLM CONFIG ---
MODEL = "gpt-5.4"
DECISION_INTERVAL = 5       # steps between LLM calls
MIN_HOLD_TIME = 15          # minimum seconds before phase switch
CHANGE_THRESHOLD = 3        # min queue change to trigger new LLM call

# --- PHASE MAPPINGS (matching tartu_tls.add.xml) ---
INTERSECTIONS = {
    "TRiia_Kalevi": {
        "phases": {0: "Kalevi/Ulikooli (EW)", 2: "Riia/Corridor (NS)"},
        "n_phases": 4,
    },
    "TRiia_Turu": {
        "phases": {0: "Corridor_North", 2: "Riia_South", 4: "Corridor_East", 6: "Turu_West"},
        "n_phases": 8,
    },
    "TTuru_Soola": {
        "phases": {0: "Soola (NS)", 2: "Corridor (EW)"},
        "n_phases": 5,
    },
    "TTuru_Aida": {
        "phases": {0: "Aida (NS)", 2: "Corridor (EW)"},
        "n_phases": 4,
    },
}

# Lane -> (intersection, direction group)
LANE_MAP = [
    ("RiiaN_RiiaKalevi",    "TRiia_Kalevi", "Riia/Corridor (NS)"),
    ("UlikW_RiiaKalevi",    "TRiia_Kalevi", "Kalevi/Ulikooli (EW)"),
    ("KaleviE_RiiaKalevi",  "TRiia_Kalevi", "Kalevi/Ulikooli (EW)"),
    ("RiiaTuru_RiiaKalevi", "TRiia_Kalevi", "Riia/Corridor (NS)"),
    ("RiiaKalevi_RiiaTuru", "TRiia_Turu",   "Corridor_North"),
    ("RiiaS_RiiaTuru",      "TRiia_Turu",   "Riia_South"),
    ("TuruW_RiiaTuru",      "TRiia_Turu",   "Turu_West"),
    ("TuruSoola_RiiaTuru",  "TRiia_Turu",   "Corridor_East"),
    ("RiiaTuru_TuruSoola",  "TTuru_Soola",  "Corridor (EW)"),
    ("SoolaN_TuruSoola",    "TTuru_Soola",  "Soola (NS)"),
    ("SoolaS_TuruSoola",    "TTuru_Soola",  "Soola (NS)"),
    ("TuruAida_TuruSoola",  "TTuru_Soola",  "Corridor (EW)"),
    ("TuruSoola_TuruAida",  "TTuru_Aida",   "Corridor (EW)"),
    ("AidaE_TuruAida",      "TTuru_Aida",   "Corridor (EW)"),
    ("AidaN_TuruAida",      "TTuru_Aida",   "Aida (NS)"),
    ("AidaS_TuruAida",      "TTuru_Aida",   "Aida (NS)"),
]

# --- STATE ---
last_switch = {}
last_queues = {}
llm_call_count = 0

# --- OPENAI CLIENT ---
client = None

SYSTEM_PROMPT = """You are a traffic signal controller for a 4-intersection corridor in Tartu, Estonia.
Your goal: MINIMIZE average vehicle delay across all intersections.

Key rules:
- Only switch when a different direction has significantly more waiting vehicles
- Maintain a phase for at least 15 seconds before switching
- Corridor traffic flows in platoons; coordinate by keeping corridor phases green when platoons are expected
- Shorter green (15-25s) for low queues, longer (30-50s) for heavy queues
- When queues are balanced, prefer keeping the current phase to avoid switching losses

Respond with ONLY valid JSON, no extra text:
{"decisions": [{"intersection": "TRiia_Kalevi", "phase": 0, "duration": 25}, ...]}

Only include intersections that NEED a change. If an intersection is fine, omit it.
If no changes needed, respond: {"decisions": []}"""


def count_queues():
    """Count vehicles per direction for all intersections."""
    counts = {}
    for tls_id in TARTU_TLS_IDS:
        counts[tls_id] = {}
        for _, direction in INTERSECTIONS[tls_id]["phases"].items():
            counts[tls_id][direction] = 0

    for vid in traci.vehicle.getIDList():
        lane = traci.vehicle.getLaneID(vid)
        speed = traci.vehicle.getSpeed(vid)
        # Count slow/stopped vehicles (queue)
        if speed < 2.0:
            for lane_substr, tls_id, direction in LANE_MAP:
                if lane_substr in lane:
                    counts[tls_id][direction] += 1
                    break

    return counts


def queues_changed_significantly(new_queues):
    """Check if queues changed enough to warrant a new LLM call."""
    global last_queues
    if not last_queues:
        return True

    total_change = 0
    for tls_id in TARTU_TLS_IDS:
        for direction in new_queues.get(tls_id, {}):
            old = last_queues.get(tls_id, {}).get(direction, 0)
            new = new_queues[tls_id][direction]
            total_change += abs(new - old)

    return total_change >= CHANGE_THRESHOLD


def build_prompt(step, queues):
    """Build the user prompt with current state."""
    lines = [f"Simulation step: {step}/{SIM_END}"]
    lines.append(f"Total vehicles in network: {len(traci.vehicle.getIDList())}")
    lines.append("")

    for tls_id in TARTU_TLS_IDS:
        current_phase = traci.trafficlight.getPhase(tls_id)
        info = INTERSECTIONS[tls_id]
        current_dir = info["phases"].get(current_phase, f"yellow/transition({current_phase})")
        elapsed = step - last_switch.get(tls_id, 0)

        lines.append(f"--- {tls_id} ---")
        lines.append(f"  Current phase: {current_phase} ({current_dir}), held for {elapsed}s")
        lines.append(f"  Valid green phases: {json.dumps({str(k): v for k, v in info['phases'].items()})}")
        lines.append(f"  Queued vehicles (slow/stopped):")
        for direction, count in queues.get(tls_id, {}).items():
            lines.append(f"    {direction}: {count} vehicles")
        lines.append("")

    return "\n".join(lines)


def call_llm(step, queues):
    """Call GPT-5.4 for traffic decisions."""
    global llm_call_count

    prompt = build_prompt(step, queues)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_completion_tokens=300,
        )

        llm_call_count += 1
        content = response.choices[0].message.content.strip()

        # Parse JSON response
        # Handle markdown code blocks if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        result = json.loads(content)
        return result.get("decisions", [])

    except json.JSONDecodeError as e:
        return []
    except Exception as e:
        print(f"    [LLM Error] {e}")
        return []


def apply_decisions(step, decisions):
    """Apply LLM decisions via TraCI."""
    for decision in decisions:
        tls_id = decision.get("intersection")
        target_phase = decision.get("phase")
        duration = decision.get("duration", 30)

        if tls_id not in TARTU_TLS_IDS:
            continue

        info = INTERSECTIONS[tls_id]

        # Validate phase
        if target_phase not in info["phases"]:
            continue

        # Check minimum hold time
        elapsed = step - last_switch.get(tls_id, 0)
        if elapsed < MIN_HOLD_TIME:
            continue

        # Check if already in this phase
        current_phase = traci.trafficlight.getPhase(tls_id)
        if current_phase == target_phase:
            continue

        # Skip if in yellow
        if current_phase % 2 == 1:
            continue

        # Clamp duration
        duration = max(15, min(duration, 60))

        try:
            traci.trafficlight.setPhase(tls_id, target_phase)
            traci.trafficlight.setPhaseDuration(tls_id, duration)
            last_switch[tls_id] = step
        except Exception as e:
            print(f"    [TraCI Error] {tls_id}: {e}")


def run_one(profile, seed):
    """Run a single LLM agent simulation."""
    global last_switch, last_queues, llm_call_count

    route_file = os.path.join(ROUTES_DIR, f"{profile}_seed{seed}.rou.xml")
    if not os.path.exists(route_file):
        print(f"  [SKIP] Route file not found: {os.path.basename(route_file)}")
        return None

    output_dir = os.path.join(OUTPUT_BASE, "llm_agent", f"{profile}_seed{seed}")
    os.makedirs(output_dir, exist_ok=True)

    tripinfo_file = os.path.join(output_dir, "tripinfo.xml")
    summary_file = os.path.join(output_dir, "summary.xml")

    # Reset state
    last_switch = {tls_id: 0 for tls_id in TARTU_TLS_IDS}
    last_queues = {}
    llm_call_count = 0

    sumo_cmd = [
        "sumo",
        "--net-file", NET_FILE,
        "--route-files", route_file,
        "--additional-files", f"{ADDITIONAL_TLS}, {ADDITIONAL_DET}",
        "--begin", "0",
        "--end", str(SIM_END),
        "--step-length", "1",
        "--tripinfo-output", tripinfo_file,
        "--summary-output", summary_file,
        "--no-warnings",
        "--no-step-log",
        "--seed", str(seed),
    ]

    print(f"  Running: {profile} seed={seed} ...", flush=True)
    t0 = time.time()

    traci.start(sumo_cmd)

    # Force TLS programs
    for tls_id in TARTU_TLS_IDS:
        try:
            traci.trafficlight.setProgram(tls_id, "1")
        except Exception:
            pass

    # Main simulation loop
    step = 0
    while step < SIM_END:
        traci.simulationStep()

        # LLM decision at intervals
        if step % DECISION_INTERVAL == 0 and step > 0:
            queues = count_queues()

            # Only call LLM if traffic situation changed meaningfully
            if queues_changed_significantly(queues):
                decisions = call_llm(step, queues)
                if decisions:
                    apply_decisions(step, decisions)
                last_queues = queues

        # Progress log every 300 steps
        if step % 300 == 0 and step > 0:
            n_veh = len(traci.vehicle.getIDList())
            elapsed = time.time() - t0
            print(f"    [Step {step}] Vehicles: {n_veh}, LLM calls: {llm_call_count} ({elapsed:.0f}s)")

        step += 1

    traci.close()
    elapsed = time.time() - t0

    # Metric extraction
    if os.path.exists(tripinfo_file):
        tree = ET.parse(tripinfo_file)
        trips = tree.getroot().findall("tripinfo")
        n_veh = len(trips)
        if n_veh > 0:
            avg_delay = sum(float(t.get("waitingTime", 0)) for t in trips) / n_veh
            avg_duration = sum(float(t.get("duration", 0)) for t in trips) / n_veh
            print(f"  [OK] {n_veh} veh, delay={avg_delay:.1f}s, travel={avg_duration:.1f}s, "
                  f"LLM calls={llm_call_count} ({elapsed:.1f}s)")
        else:
            print(f"  [OK] 0 vehicles ({elapsed:.1f}s)")
    else:
        print(f"  [OK] ({elapsed:.1f}s)")

    return output_dir


def main():
    global client

    parser = argparse.ArgumentParser(description="Run LLM agent SUMO simulations")
    parser.add_argument("--profile", choices=PROFILES, help="Run only this profile")
    parser.add_argument("--seed", type=int, choices=SEEDS, help="Run only this seed")
    args = parser.parse_args()

    # Check API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        sys.exit("ERROR: Set OPENAI_API_KEY in your .env file")

    client = OpenAI(api_key=api_key)

    # Quick model test
    print(f"  Testing {MODEL} API connection...", end=" ", flush=True)
    try:
        test = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Say OK"}],
            max_completion_tokens=5,
        )
        print(f"OK ({test.choices[0].message.content.strip()})")
    except Exception as e:
        sys.exit(f"FAILED: {e}")

    profiles = [args.profile] if args.profile else PROFILES
    seeds = [args.seed] if args.seed else SEEDS

    print("=" * 60)
    print(f"  TARTU NETWORK - LLM Agent Evaluation ({MODEL})")
    print("=" * 60)
    print(f"  Model: {MODEL} | Decision interval: {DECISION_INTERVAL} steps")
    print(f"  Profiles: {profiles}")
    print(f"  Seeds:    {seeds}")
    print()

    results = []
    for profile in profiles:
        expected = {"off_peak": "~900", "normal": "~1800", "peak": "~3600"}
        print(f"\n--- {profile.upper()} ({expected.get(profile, '')} veh/hr) ---")
        for seed in seeds:
            out = run_one(profile, seed)
            if out:
                results.append((profile, seed, out))

    print(f"\n{'=' * 60}")
    print(f"  Completed {len(results)} LLM agent simulations.")
    print(f"  Total LLM API calls: {llm_call_count}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
