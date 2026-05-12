"""
Run Rule-Based Agent Evaluation (Self-Contained)
==================================================
Runs SUMO headless with the rule-based hysteresis agent controlling
all 4 intersections directly via TraCI. No MQTT, no blockchain.

This embeds the rule-based logic from tartu_traffic_agent.py directly
into the simulation loop for reproducible, headless evaluation.

Usage:
  python run_rule_based.py              # Run all 9 scenarios
  python run_rule_based.py --profile peak --seed 1
"""

import os
import sys
import argparse
import time
import xml.etree.ElementTree as ET

if "SUMO_HOME" not in os.environ:
    sys.exit("ERROR: Set SUMO_HOME environment variable.")
sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))
import traci

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

# =====================================================================
# RULE-BASED AGENT LOGIC (adapted from tartu_traffic_agent.py)
# Phase indices MUST match the actual tartu_tls.add.xml programs:
#   TRiia_Kalevi: 4 phases — 0(green:EW), 1(yellow), 2(green:NS), 3(yellow)
#   TRiia_Turu:   8 phases — 0(green:N), 1(y), 2(green:S), 3(y), 4(green:E), 5(y), 6(green:W), 7(y)
#   TTuru_Soola:  5 phases — 0(green:NS), 1(yellow), 2(green:EW), 3(yellow), 4(all-red)
#   TTuru_Aida:   4 phases — 0(green:NS), 1(yellow), 2(green:EW), 3(yellow)
# =====================================================================
INTERSECTIONS = {
    "TRiia_Kalevi": {
        # Phase 0: Kalevi/Ulikooli (EW) green  |  Phase 2: Riia/Corridor (NS) green
        "directions": ["EastWest", "NorthSouth"],
        "phase_map": {"EastWest": 0, "NorthSouth": 2},
        "phase_names": {0: "EastWest", 2: "NorthSouth"},
    },
    "TRiia_Turu": {
        # Phase 0: Corridor_North  |  Phase 2: Riia_South  |  Phase 4: Corridor_East  |  Phase 6: Turu_West
        "directions": ["Corridor_North", "Riia_South", "Corridor_East", "Turu_West"],
        "phase_map": {"Corridor_North": 0, "Riia_South": 2, "Corridor_East": 4, "Turu_West": 6},
        "phase_names": {0: "Corridor_North", 2: "Riia_South", 4: "Corridor_East", 6: "Turu_West"},
    },
    "TTuru_Soola": {
        # Phase 0: Soola NS green  |  Phase 2: Corridor EW green
        "directions": ["Soola_NS", "Corridor_EW"],
        "phase_map": {"Soola_NS": 0, "Corridor_EW": 2},
        "phase_names": {0: "Soola_NS", 2: "Corridor_EW"},
    },
    "TTuru_Aida": {
        # Phase 0: Aida NS green  |  Phase 2: Corridor EW green
        "directions": ["Aida_NS", "Corridor_EW"],
        "phase_map": {"Aida_NS": 0, "Corridor_EW": 2},
        "phase_names": {0: "Aida_NS", 2: "Corridor_EW"},
    },
}

LANE_MAP = [
    # TRiia_Kalevi: EastWest = Kalevi + Ulikooli, NorthSouth = Riia + Corridor
    ("RiiaN_RiiaKalevi",    "TRiia_Kalevi", "NorthSouth"),
    ("UlikW_RiiaKalevi",    "TRiia_Kalevi", "EastWest"),
    ("KaleviE_RiiaKalevi",  "TRiia_Kalevi", "EastWest"),
    ("RiiaTuru_RiiaKalevi", "TRiia_Kalevi", "NorthSouth"),
    # TRiia_Turu: 4 independent directions
    ("RiiaKalevi_RiiaTuru", "TRiia_Turu",   "Corridor_North"),
    ("RiiaS_RiiaTuru",      "TRiia_Turu",   "Riia_South"),
    ("TuruW_RiiaTuru",      "TRiia_Turu",   "Turu_West"),
    ("TuruSoola_RiiaTuru",  "TRiia_Turu",   "Corridor_East"),
    # TTuru_Soola: NS = Soola, EW = Corridor
    ("RiiaTuru_TuruSoola",  "TTuru_Soola",  "Corridor_EW"),
    ("SoolaN_TuruSoola",    "TTuru_Soola",  "Soola_NS"),
    ("SoolaS_TuruSoola",    "TTuru_Soola",  "Soola_NS"),
    ("TuruAida_TuruSoola",  "TTuru_Soola",  "Corridor_EW"),
    # TTuru_Aida: NS = Aida, EW = Corridor
    ("TuruSoola_TuruAida",  "TTuru_Aida",   "Corridor_EW"),
    ("AidaE_TuruAida",      "TTuru_Aida",   "Corridor_EW"),
    ("AidaN_TuruAida",      "TTuru_Aida",   "Aida_NS"),
    ("AidaS_TuruAida",      "TTuru_Aida",   "Aida_NS"),
]

# Track last switch time per intersection to enforce minimum hold
last_switch = {tls_id: 0 for tls_id in TARTU_TLS_IDS}
MIN_HOLD = 10  # seconds minimum before switching


def parse_lanes_traci():
    """Count vehicles per direction for all 4 intersections using TraCI."""
    counts = {}
    for tls_id, info in INTERSECTIONS.items():
        counts[tls_id] = {d: 0 for d in info["directions"]}

    for vid in traci.vehicle.getIDList():
        lane = traci.vehicle.getLaneID(vid)
        for lane_substr, tls_id, direction in LANE_MAP:
            if lane_substr in lane:
                counts[tls_id][direction] += 1
                break

    return counts


def decide_and_act(step, tls_id, counts):
    """Hysteresis-based phase decision for one intersection, applied via TraCI."""
    info = INTERSECTIONS[tls_id]
    phase_map = info["phase_map"]
    phase_names = info["phase_names"]

    current_phase = traci.trafficlight.getPhase(tls_id)

    # Find direction with highest queue
    max_dir = max(counts, key=counts.get)
    max_count = counts[max_dir]

    # Current direction (if in green phase)
    current_dir = phase_names.get(current_phase, None)
    current_count = counts.get(current_dir, 0) if current_dir else 0

    # In yellow transition - skip
    if current_phase in [1, 3, 5, 7]:
        return

    # Enforce minimum hold time
    if step - last_switch[tls_id] < MIN_HOLD:
        return

    # Hysteresis: only switch if another direction has > 2 more cars
    if current_dir and max_count <= current_count + 2:
        return

    target_phase = phase_map[max_dir]

    # Already in correct phase
    if current_phase == target_phase:
        return

    # No traffic anywhere - skip
    if max_count == 0:
        return

    # Dynamic duration: 10 + 2*cars, clamped 15-60s
    duration = max(15, min(10 + max_count * 2, 60))

    traci.trafficlight.setPhase(tls_id, target_phase)
    traci.trafficlight.setPhaseDuration(tls_id, duration)
    last_switch[tls_id] = step


def run_one(profile, seed):
    """Run a single rule-based agent simulation."""
    route_file = os.path.join(ROUTES_DIR, f"{profile}_seed{seed}.rou.xml")
    if not os.path.exists(route_file):
        print(f"  [SKIP] Route file not found: {os.path.basename(route_file)}")
        return None

    output_dir = os.path.join(OUTPUT_BASE, "rule_based", f"{profile}_seed{seed}")
    os.makedirs(output_dir, exist_ok=True)

    tripinfo_file = os.path.join(output_dir, "tripinfo.xml")
    summary_file = os.path.join(output_dir, "summary.xml")

    # Reset agent state
    for tls_id in TARTU_TLS_IDS:
        last_switch[tls_id] = 0

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

    print(f"  Running: {profile} seed={seed} ...", end=" ", flush=True)
    t0 = time.time()

    traci.start(sumo_cmd)

    # Force all TLS to use our static program
    for tls_id in TARTU_TLS_IDS:
        try:
            traci.trafficlight.setProgram(tls_id, "1")
        except Exception:
            pass

    # Main simulation loop with agent control
    step = 0
    while step < SIM_END:
        traci.simulationStep()

        # Agent logic: every 3 steps (reduce overhead)
        if step % 3 == 0:
            all_counts = parse_lanes_traci()
            for tls_id in TARTU_TLS_IDS:
                decide_and_act(step, tls_id, all_counts[tls_id])

        step += 1

    traci.close()
    elapsed = time.time() - t0

    # Quick metric extraction
    if os.path.exists(tripinfo_file):
        tree = ET.parse(tripinfo_file)
        trips = tree.getroot().findall("tripinfo")
        n_veh = len(trips)
        if n_veh > 0:
            avg_delay = sum(float(t.get("waitingTime", 0)) for t in trips) / n_veh
            avg_duration = sum(float(t.get("duration", 0)) for t in trips) / n_veh
            print(f"[OK] {n_veh} veh, delay={avg_delay:.1f}s, travel={avg_duration:.1f}s ({elapsed:.1f}s)")
        else:
            print(f"[OK] 0 vehicles ({elapsed:.1f}s)")
    else:
        print(f"[OK] ({elapsed:.1f}s)")

    return output_dir


def main():
    parser = argparse.ArgumentParser(description="Run rule-based agent SUMO simulations")
    parser.add_argument("--profile", choices=PROFILES, help="Run only this profile")
    parser.add_argument("--seed", type=int, choices=SEEDS, help="Run only this seed")
    args = parser.parse_args()

    profiles = [args.profile] if args.profile else PROFILES
    seeds = [args.seed] if args.seed else SEEDS

    print("=" * 60)
    print("  TARTU NETWORK - Rule-Based Agent Evaluation")
    print("=" * 60)
    print(f"  Agent: Hysteresis-based (threshold=2, hold=10s)")
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
    print(f"  Completed {len(results)} rule-based simulations.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
