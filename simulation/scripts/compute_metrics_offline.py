import os
import pandas as pd
import xml.etree.ElementTree as ET

OUTPUT_DIR = "outputs/raw"   # folder where SUMO output files are saved

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
        
        # Compute average speed (m/s)
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

    print("\n=== BASELINE METRICS ===")

    print(f"Total vehicles simulated: {len(tripinfo)}")
    print(f"Average travel time: {tripinfo['duration'].mean():.2f} seconds")
    print(f"Average delay: {tripinfo['waitingTime'].mean():.2f} seconds")
    print(f"Average speed: {tripinfo['avgSpeed'].mean():.2f} m/s")

    total_flow = 0
    for lane, df in detector_results.items():
        lane_flow = df["flow"].mean()
        total_flow += lane_flow
        print(f"{lane} average flow: {lane_flow:.2f} veh/hour")

    print(f"\nTotal intersection throughput: {total_flow:.2f} veh/hour")

    print("\nOccupancy stats:")
    for lane, df in detector_results.items():
        print(f"{lane}: avg occupancy {df['occupancy'].mean():.2f}")
