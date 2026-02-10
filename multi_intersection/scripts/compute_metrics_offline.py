import os
import pandas as pd
import xml.etree.ElementTree as ET

# Get absolute path relative to this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "outputs", "raw")
OUTPUT_DIR = os.path.normpath(OUTPUT_DIR)

# --------------------------
# Parse tripinfo.xml
# --------------------------
def parse_tripinfo():
    tree = ET.parse(os.path.join(OUTPUT_DIR, "tripinfo.xml"))
    root = tree.getroot()

    trips = []
    for trip in root.findall("tripinfo"):
        route_length = float(trip.get("routeLength", 0)) 
        duration = float(trip.get("duration", 0))
        waiting_time = float(trip.get("waitingTime", 0))
        depart_delay = float(trip.get("departDelay", 0))
        arrival_speed = float(trip.get("arrivalSpeed", 0))
        depart_speed = float(trip.get("departSpeed", 0))
        
        avg_speed = route_length / duration if duration > 0 else 0

        trips.append({
            "id": trip.get("id"),
            "duration": duration,
            "waitingTime": waiting_time,
            "departDelay": depart_delay,
            "routeLength": route_length,
            "avgSpeed": avg_speed,
            "arrivalSpeed": arrival_speed,
            "departSpeed": depart_speed
        })

    df = pd.DataFrame(trips)
    return df


# --------------------------
# Parse summary.xml
# --------------------------
def parse_summary():
    tree = ET.parse(os.path.join(OUTPUT_DIR, "summary.xml"))
    root = tree.getroot()

    summaries = []
    for step in root.findall("step"):
        summaries.append({
            "time": float(step.get("time")),
            "loaded": float(step.get("loaded")),
            "running": float(step.get("running")),
            "waiting": float(step.get("waiting")),
        })

    return pd.DataFrame(summaries)


# --------------------------
# Parse detector loop files
# --------------------------
def parse_loop(detector_file):
    tree = ET.parse(detector_file)
    root = tree.getroot()

    entries = []
    for interval in root.findall("interval"):
        entries.append({
            "begin": float(interval.get("begin")),
            "end": float(interval.get("end")),
            "nVehContrib": float(interval.get("nVehContrib")),
            "flow": float(interval.get("flow")),     # veh/hour
            "occupancy": float(interval.get("occupancy")),
            "speed": float(interval.get("speed"))
        })

    return pd.DataFrame(entries)


# --------------------------
# MAIN
# --------------------------
if __name__ == "__main__":
    print("Parsing tripinfo.xml...")
    tripinfo = parse_tripinfo()
    print(tripinfo.head())

    print("\nParsing summary.xml...")
    summary = parse_summary()
    print(summary.head())

    print("\nParsing detector loops...")
    detector_results = {}

    for file in os.listdir(OUTPUT_DIR):
        if file.startswith("loop_") and file.endswith(".xml"):
            loop_name = file.replace(".xml", "")
            detector_results[loop_name] = parse_loop(os.path.join(OUTPUT_DIR, file))

    # -----------------------------
    # Compute baseline metrics
    # -----------------------------

    print("\n=== CORRIDOR METRICS ===")

    print(f"Total vehicles simulated: {len(tripinfo)}")
    print(f"Average travel time: {tripinfo['duration'].mean():.2f} seconds")
    print(f"Average delay: {tripinfo['waitingTime'].mean():.2f} seconds")
    print(f"Average speed: {tripinfo['avgSpeed'].mean():.2f} m/s")

    # Group detectors by intersection
    print("\n--- Intersection C1 ---")
    c1_flow = 0
    for lane, df in sorted(detector_results.items()):
        if "C1" in lane:
            lane_flow = df["flow"].mean()
            c1_flow += lane_flow
            print(f"{lane} average flow: {lane_flow:.2f} veh/hour")
    print(f"C1 throughput: {c1_flow:.2f} veh/hour")

    print("\n--- Intersection C2 ---")
    c2_flow = 0
    for lane, df in sorted(detector_results.items()):
        if "C2" in lane:
            lane_flow = df["flow"].mean()
            c2_flow += lane_flow
            print(f"{lane} average flow: {lane_flow:.2f} veh/hour")
    print(f"C2 throughput: {c2_flow:.2f} veh/hour")

    print(f"\nTotal network throughput: {c1_flow + c2_flow:.2f} veh/hour")

    print("\nOccupancy stats:")
    for lane, df in sorted(detector_results.items()):
        print(f"{lane}: avg occupancy {df['occupancy'].mean():.2f}")
