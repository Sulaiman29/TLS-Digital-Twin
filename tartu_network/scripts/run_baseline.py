"""
Run Baseline (Fixed-Time) Simulations
======================================
Runs SUMO headless with no AI agent for all demand profiles and seeds.
Uses the fixed-time TLS programs defined in tartu_tls.add.xml.

Output structure:
  tartu_network/outputs/baseline/{profile}_seed{N}/
    tripinfo.xml
    summary.xml

Usage:
  python run_baseline.py              # Run all 9 scenarios
  python run_baseline.py --profile peak --seed 1   # Run one specific scenario
"""

import os
import sys
import argparse
import subprocess
import time
import xml.etree.ElementTree as ET

# --- SUMO check ---
if "SUMO_HOME" not in os.environ:
    sys.exit("ERROR: Set SUMO_HOME environment variable.")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NET_FILE = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "network", "tartu.net.xml"))
ADDITIONAL_FILES = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "network", "tartu_tls.add.xml")) + ", " + \
                   os.path.normpath(os.path.join(SCRIPT_DIR, "..", "network", "detectors.add.xml"))
ROUTES_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "routes"))
OUTPUT_BASE = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "outputs"))

PROFILES = ["off_peak", "normal", "peak"]
SEEDS = [1, 2, 3]
SIM_END = 3600


def run_one(profile, seed):
    """Run a single baseline simulation."""
    route_file = os.path.join(ROUTES_DIR, f"{profile}_seed{seed}.rou.xml")
    if not os.path.exists(route_file):
        print(f"  [SKIP] Route file not found: {os.path.basename(route_file)}")
        return None

    output_dir = os.path.join(OUTPUT_BASE, "baseline", f"{profile}_seed{seed}")
    os.makedirs(output_dir, exist_ok=True)

    tripinfo_file = os.path.join(output_dir, "tripinfo.xml")
    summary_file = os.path.join(output_dir, "summary.xml")

    # Build SUMO command (headless, no GUI)
    sumo_cmd = [
        "sumo",
        "--net-file", NET_FILE,
        "--route-files", route_file,
        "--additional-files", ADDITIONAL_FILES,
        "--begin", "0",
        "--end", str(SIM_END),
        "--step-length", "1",
        "--tripinfo-output", tripinfo_file,
        "--summary-output", summary_file,
        "--no-warnings",
        "--no-step-log",
        "--verbose", "false",
        "--seed", str(seed),
    ]

    print(f"  Running: {profile} seed={seed} ...", end=" ", flush=True)
    t0 = time.time()

    result = subprocess.run(sumo_cmd, capture_output=True, text=True)

    elapsed = time.time() - t0

    if result.returncode != 0:
        print(f"ERROR ({elapsed:.1f}s)")
        print(f"    stderr: {result.stderr[:300]}")
        return None

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
            print(f"[OK] 0 vehicles completed ({elapsed:.1f}s)")
    else:
        print(f"[OK] ({elapsed:.1f}s) -- no tripinfo generated")

    return output_dir


def main():
    parser = argparse.ArgumentParser(description="Run baseline SUMO simulations")
    parser.add_argument("--profile", choices=PROFILES, help="Run only this profile")
    parser.add_argument("--seed", type=int, choices=SEEDS, help="Run only this seed")
    args = parser.parse_args()

    profiles = [args.profile] if args.profile else PROFILES
    seeds = [args.seed] if args.seed else SEEDS

    print("=" * 60)
    print("  TARTU NETWORK — Baseline (Fixed-Time) Evaluation")
    print("=" * 60)
    print(f"  Profiles: {profiles}")
    print(f"  Seeds:    {seeds}")
    print(f"  Duration: {SIM_END}s")
    print(f"  Output:   {OUTPUT_BASE}/baseline/")
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
    print(f"  Completed {len(results)} baseline simulations.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
