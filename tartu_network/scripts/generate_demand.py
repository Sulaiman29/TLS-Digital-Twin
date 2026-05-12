"""
Generate Traffic Demand Profiles for Evaluation
================================================
Creates route files for 3 demand levels x 3 random seeds = 9 scenarios.

Demand Profiles:
  off_peak  - ~900 veh/hr  (1 vehicle every 4 seconds)  -> Late evening
  normal    - ~1800 veh/hr (1 vehicle every 2 seconds)   -> Midday
  peak      - ~3600 veh/hr (1 vehicle every 1 second)    -> Rush hour

Usage:
  python generate_demand.py
"""

import os
import sys
import subprocess

# --- SUMO tools ---
if "SUMO_HOME" in os.environ:
    SUMO_HOME = os.environ["SUMO_HOME"]
    RANDOM_TRIPS = os.path.join(SUMO_HOME, "tools", "randomTrips.py")
else:
    sys.exit("ERROR: Set SUMO_HOME environment variable.")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NET_FILE = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "network", "tartu.net.xml"))
ROUTES_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "routes"))
TRIPS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "routes", "trips_tmp"))

# Demand profiles: name -> period (seconds between departures)
# period = 3600 / desired_vehicles_per_hour
PROFILES = {
    "off_peak": 4.0,   # 3600/4 = 900 veh/hr
    "normal":   2.0,   # 3600/2 = 1800 veh/hr
    "peak":     1.0,   # 3600/1 = 3600 veh/hr
}

SEEDS = [1, 2, 3]
SIM_END = 3600  # 1 hour


def generate_trips(profile_name, period, seed):
    """Generate trips using SUMO randomTrips.py, then route them with duarouter."""
    os.makedirs(TRIPS_DIR, exist_ok=True)
    os.makedirs(ROUTES_DIR, exist_ok=True)

    trip_file = os.path.join(TRIPS_DIR, f"{profile_name}_seed{seed}.trips.xml")
    route_file = os.path.join(ROUTES_DIR, f"{profile_name}_seed{seed}.rou.xml")

    # Skip if route file already exists
    if os.path.exists(route_file):
        print(f"  [SKIP] {os.path.basename(route_file)} already exists")
        return route_file

    # Step 1: Generate random trips
    print(f"  Generating trips: {profile_name} seed={seed} period={period}s ...")
    cmd_trips = [
        sys.executable, RANDOM_TRIPS,
        "-n", NET_FILE,
        "-o", trip_file,
        "--seed", str(seed),
        "--period", str(period),
        "-b", "0",
        "-e", str(SIM_END),
        "--validate",
        "--min-distance", "200",     # Avoid very short trips
        "--fringe-factor", "5",      # Prefer trips starting/ending at network edges
    ]
    result = subprocess.run(cmd_trips, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR (randomTrips): {result.stderr[:500]}")
        return None

    # Step 2: Route the trips using duarouter
    print(f"  Routing trips -> {os.path.basename(route_file)} ...")
    cmd_route = [
        "duarouter",
        "-n", NET_FILE,
        "-t", trip_file,
        "-o", route_file,
        "--ignore-errors",
        "--no-warnings",
        "--no-step-log",
        "--begin", "0",
        "--end", str(SIM_END),
    ]
    result = subprocess.run(cmd_route, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR (duarouter): {result.stderr[:500]}")
        return None

    # Count vehicles
    with open(route_file, "r") as f:
        veh_count = f.read().count("<vehicle ")
    print(f"  [OK] {os.path.basename(route_file)}: {veh_count} vehicles")

    return route_file


def main():
    print("=" * 60)
    print("  TARTU NETWORK - Demand Profile Generator")
    print("=" * 60)
    print(f"  Network: {NET_FILE}")
    print(f"  Output:  {ROUTES_DIR}")
    print(f"  Profiles: {list(PROFILES.keys())}")
    print(f"  Seeds:   {SEEDS}")
    print(f"  Duration: {SIM_END}s")
    print()

    generated = []
    for profile_name, period in PROFILES.items():
        expected_veh = int(SIM_END / period)
        print(f"\n--- {profile_name.upper()} (period={period}s, ~{expected_veh} veh/hr) ---")
        for seed in SEEDS:
            route = generate_trips(profile_name, period, seed)
            if route:
                generated.append(route)

    print(f"\n{'=' * 60}")
    print(f"  Generated {len(generated)} route files.")
    print(f"{'=' * 60}")

    # Cleanup temp trips
    if os.path.exists(TRIPS_DIR):
        import shutil
        shutil.rmtree(TRIPS_DIR, ignore_errors=True)
        print("  Cleaned up temporary trip files.")


if __name__ == "__main__":
    main()
