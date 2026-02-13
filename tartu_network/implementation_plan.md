# Tartu Network AI Agents — Implementation Plan

Add rule-based and LLM-based AI traffic control agents for all 4 Tartu intersections, following the same architecture as `multi_agentic_brain.py`.

## Network Topology Reference

| Intersection | Approaches | Phase Mapping |
|---|---|---|
| `TRiia_Vaba` | RiiaN (N), VabaW (W), VabaE (E), Corridor-S (from TRiia_Turu) | 0=N, 2=W, 4=E, 6=Corridor |
| `TRiia_Turu` | Corridor-N (from TRiia_Vaba), RiiaS (S), TuruW (W), Corridor-E (from TTuru_Vaks) | 0=CorrN, 2=S, 4=W, 6=CorrE |
| `TTuru_Vaks` | Corridor-W (from TRiia_Turu), VaksN (N), VaksS (S), Corridor-E (from TTuru_Alek) | 0=CorrW, 2=N, 4=S, 6=CorrE |
| `TTuru_Alek` | Corridor-W (from TTuru_Vaks), AlekE (E), AlekN (N), AlekS (S) | 0=CorrW, 2=E, 4=N, 6=S |

## Lane-to-Intersection Mapping

```
TRiia_Vaba: RiiaN_RiiaVaba→N, VabaW_RiiaVaba→W, VabaE_RiiaVaba→E, RiiaTuru_RiiaVaba→Corridor
TRiia_Turu: RiiaVaba_RiiaTuru→CorrN, RiiaS_RiiaTuru→S, TuruW_RiiaTuru→W, TuruVaks_RiiaTuru→CorrE
TTuru_Vaks: RiiaTuru_TuruVaks→CorrW, VaksN_TuruVaks→N, VaksS_TuruVaks→S, TuruAlek_TuruVaks→CorrE
TTuru_Alek: TuruVaks_TuruAlek→CorrW, AlekE_TuruAlek→E, AlekN_TuruAlek→N, AlekS_TuruAlek→S
```

## Proposed Changes

### [NEW] [tartu_traffic_agent.py](file:///d:/MS%20Thesis%20Imp/basic/AI%20layer/tartu_traffic_agent.py)
Rule-based agent (no LLM). Adapts `multi_traffic_agent.py` to 4 intersections with hysteresis-based phase switching.

### [NEW] [tartu_agentic_brain.py](file:///d:/MS%20Thesis%20Imp/basic/AI%20layer/tartu_agentic_brain.py)
LLM-based multi-agent brain. 4 independent GPT-4o-mini agents, one per intersection, each with:
- Own tool (`set_TRiia_Vaba_phase`, etc.)
- Own system prompt describing its intersection layout and neighbors
- Decision history, starvation detection, drain alerts
- Shared state for neighbor awareness (corridor coordination)
- Corridor travel times (~22s between adjacent intersections)

## Verification
- Run `realtime_publisher.py`, then `tartu_traffic_agent.py` → verify phase commands are published
- Run `tartu_agentic_brain.py` → verify LLM agents make decisions autonomously
