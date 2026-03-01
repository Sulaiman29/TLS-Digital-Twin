# Blockchain for Securing the Traffic Digital Twin

> **Brainstorm Document** — How blockchain can make the Digital Twin secure, tamper-proof, and trustworthy.

---

## 1. Why Does the Digital Twin Need Security?

The Digital Twin system has several attack surfaces:

| Component | Threat | Impact |
|---|---|---|
| **MQTT Broker** | Man-in-the-middle, spoofed messages | Fake traffic data on dashboard |
| **AI Agent Decisions** | Tampered TLS commands | Malicious signal changes → accidents |
| **Sensor/Detector Data** | Falsified loop detector readings | Wrong AI decisions based on fake data |
| **Dashboard** | Unauthorized access | Privacy leaks, misinformation |
| **Simulation ↔ Real-world sync** | Data poisoning | Digital Twin diverges from reality |

**Core problem:** There is no way to *prove* that the data flowing through the system hasn't been tampered with. Anyone with MQTT access can inject fake vehicle positions, fake detector counts, or fake TLS commands.

---

## 2. What Blockchain Brings to the Table

Blockchain provides three properties that directly address Digital Twin security:

### 2.1 Immutability (Tamper-Proof Audit Trail)
Every piece of data written to the blockchain cannot be altered retroactively. This means:
- **Traffic decisions are permanently recorded** — if an AI agent made a bad TLS decision, we can trace back exactly what data it received and what it decided.
- **Detector readings are time-stamped and sealed** — no one can claim a detector showed different values after the fact.

### 2.2 Decentralized Trust (No Single Point of Failure)
- No single server controls the truth. Even if one node is compromised, the consensus mechanism protects data integrity.
- Multiple stakeholders (city, transport authority, researchers) can independently verify the data.

### 2.3 Non-Repudiation (Provable Authorship)
- Every transaction is cryptographically signed. We can prove *who* sent a particular command or data point.
- An AI agent's decisions are traceable to specific inputs.

---

## 3. Architecture: Where Blockchain Fits

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   SUMO Sim  │────▶│  Publisher   │────▶│   MQTT Broker   │
│  (Vehicles) │     │  (Python)    │     │  (Mosquitto)    │
└─────────────┘     └──────┬───────┘     └────────┬────────┘
                           │                      │
                    ┌──────▼───────┐        ┌─────▼──────────┐
                    │  Blockchain  │◀──────▶│  AI Agent      │
                    │   Layer      │        │  (LLM Brain)   │
                    │  (Logging)   │        └─────┬──────────┘
                    └──────┬───────┘              │
                           │               ┌─────▼──────────┐
                    ┌──────▼───────┐       │  Dashboard      │
                    │  Audit API   │──────▶│  (Phoenix)      │
                    └──────────────┘       └─────────────────┘
```

### The Blockchain Layer sits between components and:
1. **Logs** every data exchange (vehicle positions, detector readings, TLS commands)
2. **Validates** data integrity before it reaches consumers
3. **Provides** an audit trail accessible via API

---

## 4. Concrete Use Cases for Your System

### 4.1 🔒 Securing AI Agent TLS Decisions

**Problem:** An AI agent sends a `setPhase` command to change traffic lights. How do we know this command is legitimate and based on real data?

**Blockchain Solution:**
```
┌─────────────────────────────────────────────────────┐
│  Smart Contract: TLSDecisionLog                     │
│                                                     │
│  struct Decision {                                  │
│    bytes32   agentId;        // TRiia_Kalevi agent  │
│    uint256   timestamp;                             │
│    bytes32   inputDataHash;  // hash of traffic     │
│                              // state that prompted │
│                              // the decision        │
│    string    action;         // "setPhase(3)"       │
│    bytes32   reasoning;      // hash of LLM prompt  │
│                              // + response          │
│    bytes     signature;      // agent's private key │
│  }                                                  │
│                                                     │
│  function logDecision(Decision d) public {          │
│    require(verify(d.signature, d.agentId));          │
│    decisions.push(d);                               │
│    emit DecisionLogged(d.agentId, d.timestamp);     │
│  }                                                  │
└─────────────────────────────────────────────────────┘
```

**Flow:**
1. AI agent receives traffic state from MQTT
2. Agent hashes the input data → `inputDataHash`
3. Agent makes decision (e.g., switch to phase 3)
4. Agent signs the decision with its private key
5. Decision is logged to blockchain *before* executing
6. TLS command is sent to SUMO
7. Anyone can later verify: "Agent X decided Y based on data Z at time T"

### 4.2 🔒 Tamper-Proof Sensor Data Pipeline

**Problem:** Detector readings flow from SUMO → Publisher → MQTT → AI Agent. Any component could alter the data.

**Blockchain Solution:**
```python
# In realtime_publisher.py — after collecting detector data:
detector_data = {
    "intersection": "TRiia_Kalevi",
    "detectors": {
        "RiiaKalevi_RiiaN_0": {"count": 5, "speed": 12.3},
        "RiiaKalevi_UlikW_0": {"count": 3, "speed": 8.7},
    },
    "timestamp": 1708900000,
}

# Hash the data and write to blockchain
data_hash = sha256(json.dumps(detector_data, sort_keys=True))
blockchain.submit_transaction({
    "type": "DETECTOR_READING",
    "hash": data_hash,
    "source": "publisher_node_1",
    "timestamp": detector_data["timestamp"],
})

# The AI agent can later verify:
received_hash = sha256(json.dumps(received_data, sort_keys=True))
assert blockchain.verify_hash(received_hash, timestamp)  # Data not tampered!
```

### 4.3 🔒 Vehicle Position Integrity

**Problem:** Vehicle positions on the dashboard could be spoofed.

**Blockchain Solution:**
- Each simulation step's vehicle positions are hashed and anchored to the blockchain.
- The dashboard can verify that the positions it displays match the blockchain record.
- Lightweight approach: batch-hash every N seconds rather than every vehicle update.

### 4.4 🔒 Multi-Stakeholder Access Control

**Problem:** Who should be able to send TLS override commands? Who can view raw data?

**Blockchain Solution:**
```
Smart Contract: AccessControl

Roles:
  ADMIN        → can add/remove agents, change policies
  AI_AGENT     → can submit TLS decisions (verified by signature)
  OBSERVER     → can read data, cannot send commands
  AUDITOR      → can access full decision history

function setPhase(intersection, phase) {
    require(hasRole(msg.sender, AI_AGENT));
    require(isRegisteredIntersection(intersection));
    // Execute only if caller is authorized
}
```

---

## 5. Blockchain Platform Options

| Platform | Type | Pros | Cons | Best For |
|---|---|---|---|---|
| **Hyperledger Fabric** | Private/Permissioned | Fast, no gas fees, fine-grained access control | Complex setup, needs infrastructure | Production deployment with known participants |
| **Ethereum (Sepolia testnet)** | Public | Large ecosystem, smart contracts, well-documented | Gas fees (mainnet), slower | PoC / Research / Thesis demo |
| **Polygon** | L2 Public | Low fees, Ethereum-compatible, fast | Still public | Cost-effective production |
| **IOTA** | DAG-based | Feeless, IoT-focused, lightweight | Smaller ecosystem | IoT/sensor data logging |
| **Ganache (local)** | Local Ethereum | Zero cost, instant, perfect for dev | Not production-ready | Thesis development & testing |

### 🎯 Recommended for MS Thesis:
**Ganache (local) → Sepolia testnet → Hyperledger Fabric**
1. Develop with Ganache locally (instant, free)
2. Demo on Sepolia testnet (proves public chain viability)
3. Discuss Hyperledger Fabric as the production-grade solution

---

## 6. Implementation Approach (Thesis-Friendly)

### Phase 1: Hash-and-Anchor (Simplest, High Impact)
```
Publisher → hash(data) → store hash on blockchain → send data via MQTT
Consumer → receive data → compute hash → verify against blockchain
```
- **Effort:** Low (add ~50 lines of Python)
- **Impact:** Proves data integrity end-to-end
- **Tech:** Web3.py + Ganache

### Phase 2: Smart Contract for TLS Decisions
```
AI Agent → log(decision, input_hash, action) → smart contract
Auditor → query contract → full decision trail
```
- **Effort:** Medium (Solidity contract + Python integration)
- **Impact:** Proves AI accountability and traceability
- **Tech:** Solidity + Hardhat + Web3.py

### Phase 3: Access Control & Role-Based Permissions
```
Smart Contract enforces who can:
  - Submit TLS commands (only registered AI agents)
  - Read traffic data (only authorized observers)
  - Modify agent parameters (only admins)
```
- **Effort:** Medium-High
- **Impact:** Complete security model

### Phase 4: Dashboard Verification UI
```
Dashboard shows:
  ✅ "Data verified on blockchain (block #12345)"
  ✅ "AI decision auditable (tx: 0xabc...)"
  ❌ "Warning: Data integrity check failed!"
```
- **Effort:** Medium (Phoenix LiveView + Web3 API)
- **Impact:** Visual proof of security for thesis demo

---

## 7. What to Write in the Thesis

### Chapter: Blockchain-Secured Digital Twin

1. **Motivation** — Why traffic Digital Twins need security guarantees
2. **Threat Model** — MQTT injection, data poisoning, unauthorized commands
3. **Proposed Architecture** — Where blockchain sits in the pipeline
4. **Smart Contract Design** — Decision logging, data anchoring, access control
5. **Implementation** — Ganache/Sepolia, Web3.py integration, Solidity contracts
6. **Evaluation** — Latency overhead, throughput impact, security guarantees proven
7. **Discussion** — Trade-offs (latency vs. security), scalability, Hyperledger for production

### Key Metrics to Measure:
| Metric | Without Blockchain | With Blockchain |
|---|---|---|
| Data integrity guarantee | ❌ None | ✅ Cryptographic proof |
| Decision traceability | ❌ Logs only (deletable) | ✅ Immutable on-chain |
| TLS command latency | ~5ms | ~5ms + 50-200ms (chain write) |
| Throughput impact | Baseline | Measure overhead |
| Access control | MQTT ACLs only | Smart contract enforced |

---

## 8. Quick-Start Code Skeleton

### Install Dependencies
```bash
pip install web3 py-solc-x
npm install -g ganache
```

### Start Local Blockchain
```bash
ganache --deterministic --port 8545
```

### Python Integration (publisher side)
```python
from web3 import Web3
import hashlib, json

w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
account = w3.eth.accounts[0]

def anchor_data(data: dict) -> str:
    """Hash data and store on blockchain, return tx hash."""
    data_json = json.dumps(data, sort_keys=True)
    data_hash = hashlib.sha256(data_json.encode()).hexdigest()

    tx = {
        "from": account,
        "to": account,  # self-transaction (data anchoring)
        "value": 0,
        "data": w3.to_bytes(hexstr=data_hash),
        "gas": 21000 + len(data_hash) * 68,
    }
    tx_hash = w3.eth.send_transaction(tx)
    return tx_hash.hex()

def verify_data(data: dict, tx_hash: str) -> bool:
    """Verify data matches what was anchored on-chain."""
    data_json = json.dumps(data, sort_keys=True)
    expected_hash = hashlib.sha256(data_json.encode()).hexdigest()

    tx = w3.eth.get_transaction(tx_hash)
    stored_hash = tx["input"].hex()[2:]  # strip 0x prefix
    return stored_hash == expected_hash
```

### Solidity Smart Contract (TLS Decision Logger)
```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract TLSDecisionLog {
    struct Decision {
        address agent;
        string  intersection;
        string  action;
        bytes32 inputDataHash;
        uint256 timestamp;
    }

    Decision[] public decisions;
    mapping(address => bool) public authorizedAgents;
    address public admin;

    modifier onlyAdmin()  { require(msg.sender == admin); _; }
    modifier onlyAgent()  { require(authorizedAgents[msg.sender]); _; }

    constructor() { admin = msg.sender; }

    function registerAgent(address agent) external onlyAdmin {
        authorizedAgents[agent] = true;
    }

    function logDecision(
        string memory intersection,
        string memory action,
        bytes32 inputDataHash
    ) external onlyAgent {
        decisions.push(Decision(
            msg.sender, intersection, action,
            inputDataHash, block.timestamp
        ));
    }

    function getDecisionCount() external view returns (uint256) {
        return decisions.length;
    }

    function getDecision(uint256 index) external view returns (Decision memory) {
        return decisions[index];
    }
}
```

---

## 9. Summary: The Pitch

> **"By integrating blockchain into the Digital Twin pipeline, every traffic signal decision, every sensor reading, and every vehicle position update becomes cryptographically verifiable and permanently recorded. This transforms the Digital Twin from a monitoring tool into a trustworthy, auditable, and tamper-proof system — critical for real-world deployment where traffic safety depends on data integrity."**

---

## 10. Next Steps

- [x] Set up Ganache locally
- [x] Write `TLSDecisionLog.sol` smart contract
- [x] Add `anchor_data()` to `realtime_publisher.py`
- [ ] Add `verify_data()` to `tartu_agentic_brain.py`
- [ ] Add blockchain verification badge to Phoenix dashboard
- [ ] Measure latency overhead
- [ ] Write thesis chapter
