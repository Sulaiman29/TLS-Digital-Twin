# Digital Twin for Smart Traffic Signal

This repository contains a traffic simulation project for Tartu, Estonia, implementing various traffic control strategies using SUMO (Simulation of Urban MObility) and Python. The project explores rule-based and LLM-driven agentic approaches to optimize traffic flow, with a real-time Digital Twin dashboard built using Elixir/Phoenix LiveView. Blockchain will now be added as an additional layer for security purposes of the twin.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  SUMO Simulation (Python)                                        │
│  realtime_publisher.py → publishes vehicle, TL, metrics via MQTT │
└──────────────┬───────────────────────────────────────────────────┘
               │ MQTT (JSON)
               ▼
┌──────────────────────────────────────────┐
│  AI Layer (Python)                       │
│  tartu_traffic_agent.py  (rule-based)    │
│  tartu_agentic_brain.py  (GPT-4o-mini)   │
│  Subscribes + publishes phase commands   │
└──────┬───────────────────────────────────┘
       │ MQTT (JSON)
       ▼
┌──────────────────────────────────────────┐      ┌─────────────────────┐
│  Digital Twin Dashboard (Elixir/Phoenix) │      │  Blockchain (Ganache)│
│  Tortoise MQTT → GenServer → PubSub      │◄────►│  TLSDecisionLog.sol  │
│  LiveView → LeafletJS (browser)          │      │  AccessControl.sol   │
│  Blockchain Security Panel               │      │  Data anchoring (tx) │
│  http://localhost:4000                   │      │  http://127.0.0.1:8545│
└──────────────────────────────────────────┘      └─────────────────────┘
```

## Project Structure

- **`AI layer/`** — Traffic control agents (Python)
  - `tartu_agentic_brain.py` — LLM-based agent (4× GPT-4o-mini) for the Tartu network
  - `tartu_traffic_agent.py` — Rule-based agent for the Tartu network
  - `multi_agentic_brain.py` / `multi_traffic_agent.py` — Agents for multi-intersection scenarios
  - `agentic_brain.py` / `traffic_agent.py` — Single-intersection agent logic

- **`digital_twin/`** — Real-time dashboard (Elixir/Phoenix LiveView)
  - `lib/digital_twin/traffic_state.ex` — GenServer holding live city state in memory
  - `lib/digital_twin/mqtt_handler.ex` — Tortoise MQTT handler for SUMO data ingestion
  - `lib/digital_twin_web/live/dashboard_live.ex` — LiveView page with metrics and TL sidebar
  - `assets/js/hooks/traffic_map.js` — LeafletJS map hook with vehicle markers

- **`tartu_network/`** — SUMO network files for the 4-intersection Tartu corridor
  - `cfg/` — Simulation configuration (`.sumocfg`)
  - `network/` — Network topology, traffic lights, detectors, labels
  - `scripts/` — Realtime publisher, offline metrics computation

- **`blockchain/`** — Blockchain security layer
  - `contracts/TLSDecisionLog.sol` — Solidity smart contract for immutable AI decision logging
  - `contracts/AccessControl.sol` — RBAC (Admin, AI Agent, Publisher, Auditor)
  - `blockchain_client.py` — Hash-and-anchor data integrity via Ganache
  - `contract_interface.py` — Python wrapper for TLSDecisionLog contract
  - `access_control.py` — Python wrapper for AccessControl contract
  - `test_blockchain.py` / `test_contract.py` / `test_access_control.py` — 61 tests total

- **`multi_intersection/`** — Two-intersection corridor scenarios

- **`single_intersection/`** — Baseline single-intersection scenarios

- **`docs/`** — Documentation and design docs

- **`SLR/`** — Systematic Literature Review documents

## Requirements

### Python (Simulation + AI Agents)
- Python 3.x
- SUMO with `SUMO_HOME` environment variable set
- `traci`, `sumolib`
- `paho-mqtt` — MQTT client
- `langchain`, `langchain-openai`, `langgraph` — for LLM agents
- `openai` API key (for LLM agents only)

### Elixir (Digital Twin Dashboard)
- Erlang/OTP 27+
- Elixir 1.17+
- Phoenix 1.8+

### Infrastructure
- Mosquitto MQTT broker (or any MQTT broker on `localhost:1883`)

### Blockchain (optional, for security layer)
- Node.js 18+ (for Hardhat and Ganache)
- Ganache (`npm install -g ganache`) — local Ethereum blockchain
- `web3` (Python) — Ethereum interaction

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/Sulaiman29/TLS-Digital-Twin.git
cd TLS-Digital-Twin

# 2. Python dependencies
pip install traci sumolib paho-mqtt langchain langchain-openai langgraph

# 3. Elixir/Phoenix dependencies
cd digital_twin
mix deps.get
mix compile
cd ..

# 4. Blockchain dependencies (optional)
cd blockchain
npm install
npx hardhat compile
cd ..
```

## Usage

### 1. Start MQTT Broker
```bash
mosquitto
```

### 1b. Start Ganache (optional, enables blockchain security)
```bash
ganache --deterministic --port 8545
```

### 2. Run SUMO Simulation with MQTT Publisher
```bash
python tartu_network/scripts/realtime/realtime_publisher.py
```

### 3a. Run Rule-Based Agent
```bash
python "AI layer/tartu_traffic_agent.py"
```

### 3b. Run LLM-Based Agent (requires OpenAI API key)
```bash
set OPENAI_API_KEY=sk-...
python "AI layer/tartu_agentic_brain.py"
```

### 4. Start Digital Twin Dashboard
```bash
cd digital_twin
mix phx.server
```

Open **http://localhost:4000** to see the live dashboard with:
- 🗺️ LeafletJS map with real-time vehicle markers on Tartu streets
- 📊 Live metrics (vehicle count, speed, congestion index)
- 🚦 Traffic light state visualization for all 4 intersections
- 🔗 Blockchain security panel (data integrity, decision audit, access control)

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Required for LLM agents |
| `BLOCKCHAIN_ENABLED` | `true` | Set to `false` to disable blockchain |
| `BLOCKCHAIN_RPC_URL` | `http://127.0.0.1:8545` | Ganache/Ethereum RPC endpoint |
| `BLOCKCHAIN_ANCHOR_INTERVAL` | `5` | Batch-anchor vehicles every N steps |
| `MQTT_BROKER` | `localhost` | MQTT broker hostname (Python scripts) |
| `SUMO_MODE` | `gui` | `gui` for SUMO-GUI, `headless` for Docker |

## Docker (Alternative)

Run everything with a single command — no need to open 5 terminals:

```bash
# 1. Copy and fill in your .env
cp .env.example .env
# Edit .env and set OPENAI_API_KEY

# 2. Build and start all services
docker compose up --build

# 3. Open the dashboard
# http://localhost:4000
```

To stop: `docker compose down`

> **Note:** Docker runs SUMO in headless mode (no GUI window). The Phoenix dashboard at `localhost:4000` provides full real-time visualization.

## Contributing
Personal thesis implementation.
