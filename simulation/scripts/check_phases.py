import os
import sys
import traci

# --- SETUP PATHS ---
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("please declare environment variable 'SUMO_HOME'")

# POINT THIS TO YOUR CONFIG FILE
script_dir = os.path.dirname(os.path.abspath(__file__))
# Adjust this relative path if necessary!
SUMO_CFG = os.path.join(script_dir, "../cfg/intersection.sumocfg") 
SUMO_CFG = os.path.normpath(SUMO_CFG)

def analyze_tls():
    print(f"Loading SUMO with: {SUMO_CFG}")
    traci.start(["sumo", "-c", SUMO_CFG])
    
    tl_id = "C" # Your Intersection ID
    
    try:
        # Get the full logic definition
        logic = traci.trafficlight.getCompleteRedYellowGreenDefinition(tl_id)[0]
        
        print(f"\n=== TRAFFIC LIGHT DIAGNOSTIC FOR '{tl_id}' ===")
        print(f"Total Phases Found: {len(logic.phases)}")
        
        for i, phase in enumerate(logic.phases):
            print(f"Phase {i}: Duration={phase.duration}s | State={phase.state}")
            
        print("==============================================\n")
        
        # ANALYSIS
        state_0 = logic.phases[0].state.lower()
        
        # Check first half (North) vs Middle (South)
        # Assuming 16 links: 0-3 are North, 8-11 are South
        north_green = 'g' in state_0[0:4]
        south_green = 'g' in state_0[8:12]
        
        if north_green and south_green:
            print("CONCLUSION: This is a 2-PHASE System (North & South go Green together).")
        elif north_green and not south_green:
            print("CONCLUSION: This is a 4-PHASE System (North goes, then someone else).")
            
    except Exception as e:
        print(f"Error: {e}")
    
    traci.close()

if __name__ == "__main__":
    analyze_tls()