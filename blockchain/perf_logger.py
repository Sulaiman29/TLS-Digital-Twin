"""
Blockchain Performance Logger
==============================
Instruments blockchain calls with timing data for thesis evaluation.

Usage:
    from blockchain.perf_logger import PerfLogger

    perf = PerfLogger()                # creates blockchain_perf.csv
    perf.log("anchor_data", latency_ms, success, step=42, extra="metrics")
    perf.summary()                     # print stats to console
"""

import os
import csv
import time
import statistics
from collections import defaultdict


class PerfLogger:
    """Records blockchain operation latencies to CSV for post-simulation analysis."""

    HEADERS = ["timestamp", "step", "operation", "latency_ms", "success", "data_size", "extra"]

    def __init__(self, output_dir=None):
        if output_dir is None:
            output_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "tartu_network", "outputs"
            )
        os.makedirs(output_dir, exist_ok=True)
        self.csv_path = os.path.join(output_dir, "blockchain_perf.csv")
        self._records = []
        self._file = open(self.csv_path, "w", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=self.HEADERS)
        self._writer.writeheader()
        self._file.flush()
        print(f"[PerfLogger] Logging to {self.csv_path}")

    def log(self, operation: str, latency_ms: float, success: bool,
            step: int = 0, data_size: int = 0, extra: str = ""):
        """Record a single blockchain operation."""
        record = {
            "timestamp": time.time(),
            "step": step,
            "operation": operation,
            "latency_ms": round(latency_ms, 3),
            "success": success,
            "data_size": data_size,
            "extra": extra,
        }
        self._records.append(record)
        self._writer.writerow(record)
        self._file.flush()

    def timed(self, operation: str, func, *args, step: int = 0,
              data_size: int = 0, extra: str = "", **kwargs):
        """Execute func(*args, **kwargs) and log its latency. Returns the result."""
        t0 = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            latency = (time.perf_counter() - t0) * 1000  # ms
            self.log(operation, latency, success=True, step=step,
                     data_size=data_size, extra=extra)
            return result
        except Exception as e:
            latency = (time.perf_counter() - t0) * 1000
            self.log(operation, latency, success=False, step=step,
                     data_size=data_size, extra=str(e))
            raise

    def summary(self):
        """Print a summary of all recorded operations."""
        if not self._records:
            print("[PerfLogger] No records to summarize.")
            return

        by_op = defaultdict(list)
        for r in self._records:
            by_op[r["operation"]].append(r)

        print("\n" + "=" * 60)
        print("  BLOCKCHAIN PERFORMANCE SUMMARY")
        print("=" * 60)

        total_txs = len(self._records)
        total_time_s = (self._records[-1]["timestamp"] - self._records[0]["timestamp"])

        for op, records in sorted(by_op.items()):
            latencies = [r["latency_ms"] for r in records]
            successes = sum(1 for r in records if r["success"])
            failures = len(records) - successes

            print(f"\n  📊 {op}")
            print(f"     Count:    {len(records)} ({successes} ok, {failures} failed)")
            print(f"     Mean:     {statistics.mean(latencies):.2f} ms")
            print(f"     Median:   {statistics.median(latencies):.2f} ms")
            if len(latencies) >= 2:
                print(f"     Std Dev:  {statistics.stdev(latencies):.2f} ms")
            print(f"     Min/Max:  {min(latencies):.2f} / {max(latencies):.2f} ms")
            if len(latencies) >= 20:
                sorted_l = sorted(latencies)
                p95 = sorted_l[int(len(sorted_l) * 0.95)]
                p99 = sorted_l[int(len(sorted_l) * 0.99)]
                print(f"     P95:      {p95:.2f} ms")
                print(f"     P99:      {p99:.2f} ms")

        if total_time_s > 0:
            throughput = total_txs / total_time_s
            print(f"\n  ⚡ Overall Throughput: {throughput:.2f} tx/s")
            print(f"     Total Transactions: {total_txs}")
            print(f"     Simulation Duration: {total_time_s:.1f}s")

        print("=" * 60 + "\n")

    def close(self):
        """Flush and close the CSV file."""
        self.summary()
        self._file.close()
        print(f"[PerfLogger] Results saved to {self.csv_path}")
