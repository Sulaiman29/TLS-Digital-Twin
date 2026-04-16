"""
Blockchain Performance Analysis
================================
Reads blockchain_perf.csv from a simulation run and generates
publication-ready charts + statistics for thesis evaluation.

Usage:
    python blockchain/analyze_performance.py

Output:
    tartu_network/outputs/blockchain_latency_distribution.png
    tartu_network/outputs/blockchain_throughput_timeline.png
    tartu_network/outputs/blockchain_overhead_summary.png
"""

import os
import csv
import statistics
from collections import defaultdict

# Try importing matplotlib; if not available, skip chart generation
try:
    import matplotlib
    matplotlib.use("Agg")  # non-interactive backend
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    print("[Warning] matplotlib not installed — skipping chart generation.")
    print("  Install with: pip install matplotlib")


def load_csv(path):
    """Load performance CSV into list of dicts."""
    records = []
    with open(path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["timestamp"] = float(row["timestamp"])
            row["step"] = int(row["step"])
            row["latency_ms"] = float(row["latency_ms"])
            row["success"] = row["success"] == "True"
            row["data_size"] = int(row["data_size"]) if row["data_size"] else 0
            records.append(row)
    return records


def compute_stats(records):
    """Compute per-operation statistics."""
    by_op = defaultdict(list)
    for r in records:
        if r["success"]:
            by_op[r["operation"]].append(r["latency_ms"])

    stats = {}
    for op, latencies in by_op.items():
        sorted_l = sorted(latencies)
        n = len(sorted_l)
        s = {
            "count": n,
            "mean": statistics.mean(latencies),
            "median": statistics.median(latencies),
            "std": statistics.stdev(latencies) if n >= 2 else 0,
            "min": min(latencies),
            "max": max(latencies),
            "p95": sorted_l[int(n * 0.95)] if n >= 20 else max(latencies),
            "p99": sorted_l[int(n * 0.99)] if n >= 100 else max(latencies),
        }
        stats[op] = s
    return stats


def print_latex_table(stats):
    """Print a LaTeX-ready table for the thesis."""
    print("\n% --- LaTeX Table (copy into thesis) ---")
    print("\\begin{table}[h]")
    print("\\centering")
    print("\\caption{Blockchain Operation Latency (ms)}")
    print("\\label{tab:blockchain-latency}")
    print("\\begin{tabular}{lrrrrrrr}")
    print("\\hline")
    print("Operation & Count & Mean & Median & Std Dev & Min & Max & P95 \\\\")
    print("\\hline")
    for op, s in sorted(stats.items()):
        print(f"{op} & {s['count']} & {s['mean']:.2f} & {s['median']:.2f} "
              f"& {s['std']:.2f} & {s['min']:.2f} & {s['max']:.2f} & {s['p95']:.2f} \\\\")
    print("\\hline")
    print("\\end{tabular}")
    print("\\end{table}\n")


def plot_latency_distribution(records, output_dir):
    """Box plot of latency per operation type."""
    by_op = defaultdict(list)
    for r in records:
        if r["success"]:
            by_op[r["operation"]].append(r["latency_ms"])

    fig, ax = plt.subplots(figsize=(10, 5))
    ops = sorted(by_op.keys())
    data = [by_op[op] for op in ops]

    bp = ax.boxplot(data, labels=ops, patch_artist=True, showfliers=True)

    colors = ["#6c5ce7", "#00cec9", "#ff4757", "#ffa502"]
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    ax.set_ylabel("Latency (ms)", fontsize=12)
    ax.set_xlabel("Operation", fontsize=12)
    ax.set_title("Blockchain Operation Latency Distribution", fontsize=14)
    ax.grid(axis="y", alpha=0.3)

    path = os.path.join(output_dir, "blockchain_latency_distribution.png")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  ✔ Saved: {path}")


def plot_throughput_timeline(records, output_dir):
    """Throughput (tx/s) over time using 10-second windows."""
    if not records:
        return

    t0 = records[0]["timestamp"]
    window_size = 10  # seconds
    max_time = records[-1]["timestamp"] - t0

    windows = []
    counts = []
    for start in range(0, int(max_time) + 1, window_size):
        end = start + window_size
        count = sum(1 for r in records if start <= (r["timestamp"] - t0) < end)
        windows.append(start + window_size / 2)
        counts.append(count / window_size)

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(windows, counts, color="#6c5ce7", linewidth=1.5)
    ax.fill_between(windows, counts, alpha=0.15, color="#6c5ce7")
    ax.set_xlabel("Simulation Time (s)", fontsize=12)
    ax.set_ylabel("Throughput (tx/s)", fontsize=12)
    ax.set_title("Blockchain Throughput Over Time", fontsize=14)
    ax.grid(alpha=0.3)

    path = os.path.join(output_dir, "blockchain_throughput_timeline.png")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  ✔ Saved: {path}")


def plot_overhead_summary(stats, output_dir):
    """Bar chart showing mean + P95 latency per operation."""
    ops = sorted(stats.keys())
    means = [stats[op]["mean"] for op in ops]
    p95s = [stats[op]["p95"] for op in ops]

    x = range(len(ops))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    bars1 = ax.bar([i - width/2 for i in x], means, width, label="Mean",
                    color="#6c5ce7", alpha=0.8)
    bars2 = ax.bar([i + width/2 for i in x], p95s, width, label="P95",
                    color="#ff4757", alpha=0.8)

    ax.set_ylabel("Latency (ms)", fontsize=12)
    ax.set_xlabel("Operation", fontsize=12)
    ax.set_title("Blockchain Latency: Mean vs P95", fontsize=14)
    ax.set_xticks(x)
    ax.set_xticklabels(ops, fontsize=10)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    # Add value labels on bars
    for bar in bars1:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                f"{bar.get_height():.1f}", ha="center", va="bottom", fontsize=8)
    for bar in bars2:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                f"{bar.get_height():.1f}", ha="center", va="bottom", fontsize=8)

    path = os.path.join(output_dir, "blockchain_overhead_summary.png")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  ✔ Saved: {path}")


def main():
    # Find CSV files
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, "..", "tartu_network", "outputs")
    csv_path = os.path.join(output_dir, "blockchain_perf.csv")

    if not os.path.exists(csv_path):
        print(f"[Error] No performance data found at: {csv_path}")
        print("  Run the simulation with blockchain enabled first.")
        return

    print(f"\n[Analyzing] {csv_path}")
    records = load_csv(csv_path)
    print(f"  Loaded {len(records)} records")

    if not records:
        print("  No records to analyze.")
        return

    # Compute stats
    stats = compute_stats(records)

    # Print console summary
    print("\n" + "=" * 60)
    print("  BLOCKCHAIN PERFORMANCE ANALYSIS")
    print("=" * 60)
    for op, s in sorted(stats.items()):
        print(f"\n  📊 {op}")
        print(f"     Count:    {s['count']}")
        print(f"     Mean:     {s['mean']:.2f} ms (σ = {s['std']:.2f})")
        print(f"     Median:   {s['median']:.2f} ms")
        print(f"     Min/Max:  {s['min']:.2f} / {s['max']:.2f} ms")
        print(f"     P95:      {s['p95']:.2f} ms")
        print(f"     P99:      {s['p99']:.2f} ms")

    total_time = records[-1]["timestamp"] - records[0]["timestamp"]
    if total_time > 0:
        print(f"\n  ⚡ Overall Throughput: {len(records) / total_time:.2f} tx/s")
    print("=" * 60)

    # LaTeX table
    print_latex_table(stats)

    # Charts
    if HAS_MPL:
        print("\n[Generating Charts]")
        plot_latency_distribution(records, output_dir)
        plot_throughput_timeline(records, output_dir)
        plot_overhead_summary(stats, output_dir)
        print("\nAll charts saved! Copy them into your thesis.\n")
    else:
        print("\n[Skipped] Install matplotlib for charts: pip install matplotlib\n")


if __name__ == "__main__":
    main()
