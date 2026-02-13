# Walkthrough: Tartu 4-Agent Traffic Control

## Files Created

| File | Type | Description |
|---|---|---|
| [tartu_traffic_agent.py](file:///d:/MS%20Thesis%20Imp/basic/AI%20layer/tartu_traffic_agent.py) | Rule-based | Hysteresis-based phase switching for all 4 intersections |
| [tartu_agentic_brain.py](file:///d:/MS%20Thesis%20Imp/basic/AI%20layer/tartu_agentic_brain.py) | LLM-based | 4 independent GPT-4o-mini agents with shared state |

## Architecture

Both files use a **data-driven** approach (vs. the hardcoded per-intersection logic in the multi-intersection versions):

- **`INTERSECTION_CONFIG`** — dict defining directions, phases, neighbors, and corridor connections for each intersection
- **`LANE_MAP`** — list mapping SUMO lane substrings to (intersection, direction) pairs
- **`make_set_phase_tool()`** (agentic brain) — factory that creates a unique LangChain tool per intersection
- **`build_prompt()`** (agentic brain) — generic prompt builder that works for any intersection

## Lane Mapping

| Intersection | Approach Lanes | Directions |
|---|---|---|
| `TRiia_Vaba` | RiiaN_RiiaVaba, VabaW_RiiaVaba, VabaE_RiiaVaba, RiiaTuru_RiiaVaba | Riia_North, Vabaduse_West, Vabaduse_East, Corridor_South |
| `TRiia_Turu` | RiiaVaba_RiiaTuru, RiiaS_RiiaTuru, TuruW_RiiaTuru, TuruVaks_RiiaTuru | Corridor_North, Riia_South, Turu_West, Corridor_East |
| `TTuru_Vaks` | RiiaTuru_TuruVaks, VaksN_TuruVaks, VaksS_TuruVaks, TuruAlek_TuruVaks | Corridor_West, Vaksali_North, Vaksali_South, Corridor_East |
| `TTuru_Alek` | TuruVaks_TuruAlek, AlekE_TuruAlek, AlekN_TuruAlek, AlekS_TuruAlek | Corridor_West, Aleksandri_East, Aleksandri_North, Aleksandri_South |

## How To Run

**Step 1**: Start the SUMO simulation with MQTT publisher:
```
python tartu_network/scripts/realtime/realtime_publisher.py
```

**Step 2a** (Rule-based): Run the rule-based agent:
```
python "AI layer/tartu_traffic_agent.py"
```

**Step 2b** (LLM-based): Run the agentic brain (requires OPENAI_API_KEY):
```
set OPENAI_API_KEY=sk-...
python "AI layer/tartu_agentic_brain.py"
```
