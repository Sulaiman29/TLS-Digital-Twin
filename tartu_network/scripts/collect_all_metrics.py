"""
Collect All Metrics -- Unified CSV Output
=========================================
Scans all output directories (baseline, rule_based, llm_agent) and produces
a single CSV with comparable metrics for all scenarios.

Output: tartu_network/outputs/evaluation_results.csv

Usage:
  python collect_all_metrics.py
"""

import os
import csv
import xml.etree.ElementTree as ET

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_BASE = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "outputs"))
CSV_OUTPUT = os.path.join(OUTPUT_BASE, "evaluation_results.csv")

# Scenarios to scan: (directory_name, scenario_label)
# Additional scenario directories can be added here for rule-based / LLM agent results
SCENARIOS = [
    ("baseline", "Baseline (Fixed-Time)"),
    ("rule_based", "Rule-Based Agent"),
    ("llm_agent", "LLM Agent (GPT-5.4)"),
]

PROFILES = ["off_peak", "normal", "peak"]
SEEDS = [1, 2, 3]


def parse_tripinfo(tripinfo_path):
    """Extract metrics from a SUMO tripinfo.xml file."""
    if not os.path.exists(tripinfo_path):
        return None

    tree = ET.parse(tripinfo_path)
    trips = tree.getroot().findall("tripinfo")

    if len(trips) == 0:
        return {
            "vehicles_completed": 0,
            "avg_travel_time": 0,
            "avg_delay": 0,
            "avg_speed": 0,
            "total_travel_time": 0,
            "total_delay": 0,
            "max_delay": 0,
            "depart_delay": 0,
        }

    durations = [float(t.get("duration", 0)) for t in trips]
    waiting_times = [float(t.get("waitingTime", 0)) for t in trips]
    route_lengths = [float(t.get("routeLength", 0)) for t in trips]
    depart_delays = [float(t.get("departDelay", 0)) for t in trips]

    n = len(trips)
    speeds = [rl / d if d > 0 else 0 for rl, d in zip(route_lengths, durations)]

    return {
        "vehicles_completed": n,
        "avg_travel_time": round(sum(durations) / n, 2),
        "avg_delay": round(sum(waiting_times) / n, 2),
        "avg_speed": round(sum(speeds) / n, 2),
        "total_travel_time": round(sum(durations), 1),
        "total_delay": round(sum(waiting_times), 1),
        "max_delay": round(max(waiting_times), 1),
        "depart_delay": round(sum(depart_delays) / n, 2),
    }


def parse_summary(summary_path):
    """Extract peak running vehicles from summary.xml."""
    if not os.path.exists(summary_path):
        return {"peak_running": 0, "peak_time": 0}

    tree = ET.parse(summary_path)
    steps = tree.getroot().findall("step")

    if len(steps) == 0:
        return {"peak_running": 0, "peak_time": 0}

    max_running = 0
    max_time = 0
    for step in steps:
        running = int(float(step.get("running", 0)))
        if running > max_running:
            max_running = running
            max_time = float(step.get("time", 0))

    return {"peak_running": max_running, "peak_time": max_time}


def collect_all():
    """Scan all scenario directories and collect metrics."""
    rows = []

    for scenario_dir, scenario_label in SCENARIOS:
        scenario_path = os.path.join(OUTPUT_BASE, scenario_dir)
        if not os.path.exists(scenario_path):
            print(f"  [SKIP] {scenario_dir}/ directory not found")
            continue

        for profile in PROFILES:
            for seed in SEEDS:
                run_dir = os.path.join(scenario_path, f"{profile}_seed{seed}")
                tripinfo_path = os.path.join(run_dir, "tripinfo.xml")
                summary_path = os.path.join(run_dir, "summary.xml")

                if not os.path.exists(run_dir):
                    continue

                trip_metrics = parse_tripinfo(tripinfo_path)
                summary_metrics = parse_summary(summary_path)

                if trip_metrics is None:
                    continue

                row = {
                    "scenario": scenario_label,
                    "scenario_dir": scenario_dir,
                    "profile": profile,
                    "seed": seed,
                    **trip_metrics,
                    **summary_metrics,
                }
                rows.append(row)
                print(f"  [OK] {scenario_dir}/{profile}_seed{seed}: "
                      f"{trip_metrics['vehicles_completed']} veh, "
                      f"delay={trip_metrics['avg_delay']:.1f}s, "
                      f"speed={trip_metrics['avg_speed']:.2f} m/s")

    return rows


def write_csv(rows):
    """Write all collected metrics to a CSV file."""
    if not rows:
        print("\n  No data to write!")
        return

    fieldnames = [
        "scenario", "scenario_dir", "profile", "seed",
        "vehicles_completed", "avg_travel_time", "avg_delay", "avg_speed",
        "total_travel_time", "total_delay", "max_delay", "depart_delay",
        "peak_running", "peak_time",
    ]

    with open(CSV_OUTPUT, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n  CSV written to: {CSV_OUTPUT}")


def print_summary_table(rows):
    """Print a nicely formatted summary table grouped by profile."""
    if not rows:
        return

    print("\n" + "=" * 85)
    print("  EVALUATION RESULTS SUMMARY")
    print("=" * 85)
    print(f"  {'Scenario':<25} {'Profile':<10} {'Seed':>4} {'Veh':>6} {'Delay':>8} {'Travel':>8} {'Speed':>7} {'Peak':>5}")
    print("  " + "-" * 79)

    for profile in PROFILES:
        profile_rows = [r for r in rows if r["profile"] == profile]
        for r in profile_rows:
            print(f"  {r['scenario']:<25} {r['profile']:<10} {r['seed']:>4} "
                  f"{r['vehicles_completed']:>6} {r['avg_delay']:>7.1f}s "
                  f"{r['avg_travel_time']:>7.1f}s {r['avg_speed']:>6.2f} "
                  f"{r['peak_running']:>5}")

        # Print average for this profile
        if len(profile_rows) >= 2:
            avg_delay = sum(r["avg_delay"] for r in profile_rows) / len(profile_rows)
            avg_travel = sum(r["avg_travel_time"] for r in profile_rows) / len(profile_rows)
            avg_speed = sum(r["avg_speed"] for r in profile_rows) / len(profile_rows)
            avg_veh = sum(r["vehicles_completed"] for r in profile_rows) / len(profile_rows)
            print(f"  {'  +- AVERAGE':<25} {profile:<10} {'':>4} "
                  f"{avg_veh:>6.0f} {avg_delay:>7.1f}s "
                  f"{avg_travel:>7.1f}s {avg_speed:>6.2f}")
        print()

    print("=" * 85)


def main():
    print("=" * 60)
    print("  TARTU NETWORK -- Metrics Collector")
    print("=" * 60)
    print(f"  Scanning: {OUTPUT_BASE}/")
    print()

    rows = collect_all()
    write_csv(rows)
    print_summary_table(rows)


if __name__ == "__main__":
    main()
