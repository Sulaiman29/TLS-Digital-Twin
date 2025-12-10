# Systematic Literature Review (SLR) Plan
**Thesis Topic:**  
*A Secure and Intelligent Digital Twin Framework for Smart Cities: Integrating AI and Blockchain for Trustworthy Urban Management*

This review supports a research report describing a "Cognitive Digital Twin" integrating:  
- SUMO (traffic simulation)  
- Agentic AI (LangChain)  
- Real-time Digital Twinning (Phoenix LiveView)  
- Blockchain trust engine (Ganache + Solidity)

---

# 1. Research Problem Statement
Current digital twin frameworks for smart cities lack a unified architecture that integrates:
- **Real-time simulation** (e.g., SUMO)
- **AI reasoning via autonomous agents**
- **Blockchain-based trust and data integrity**

No existing system combines these paradigms to enable a secure, intelligent, and trustworthy urban management platform.

---

# 2. Research Questions

## Main RQs
- **RQ1:** What digital twin frameworks exist for smart cities, and what limitations do they have?
- **RQ2:** How are AI agent frameworks (e.g., LangChain, multi-agent systems, cognitive agents) used to support autonomous decision-making in digital twins?
- **RQ3:** What blockchain-based trust, security, and integrity mechanisms support digital twin ecosystems?
- **RQ4:** What architectural patterns integrate real-time urban simulations (e.g., SUMO) with digital twin platforms?

## Optional Sub-RQ Examples
- RQ2.1: What cognitive reasoning techniques are used in current AI agent systems?  
- RQ3.1: Which blockchain consensus/smart contract models suit real-time urban systems?  
- RQ4.1: What synchronization challenges arise in real-time physical-to-virtual twins?

---

# 3. Inclusion & Exclusion Criteria

## Inclusion
- Research related to **digital twins**, **IoT twins**, **urban twins**
- Studies using **AI agents**, **MAS**, **LLMs**, **cognitive models**
- Blockchain-enabled **trust**, **smart contracts**, **DLT security**
- Real-time simulation integration (SUMO, traffic twins)
- Year range: **2014–2025**
- Peer-reviewed (journals, conferences)

## Exclusion
- Digital twins only for manufacturing (unless architecture-relevant)
- Blockchain studies unrelated to IoT/smart cities
- Pure AI papers without twin/simulation relevance
- Patents, non-academic web content, magazines
- Non-English papers without translations

---

# 4. Databases Selected

### Primary
- IEEE Xplore  
- ACM Digital Library  
- Scopus  
- Web of Science  

### Supplementary
- ScienceDirect  
- Google Scholar  

---


# 5. Search Strings

## Group A: Digital Twin & Smart City
("digital twin" OR "smart city" OR "urban digital twin"
OR "cyber physical system" OR "urban simulation")

## Group B: AI Agents / Cognitive Systems
("AI agent" OR "autonomous agent" OR "multi-agent system"
OR "LLM agent" OR "cognitive agent" OR "LangChain")

## Group C: Blockchain & Trust
("blockchain" OR "distributed ledger" OR "smart contract"
OR "data integrity" OR "trust management")

## Group D: Simulation / SUMO / Real-Time Systems
("SUMO" OR "traffic simulation" OR "real-time simulation"
OR "live digital twin" OR "Phoenix LiveView")

## Example Combined Query
("digital twin" AND "smart city")
AND
("AI agent" OR "multi-agent system" OR "LLM agent")
AND
("blockchain" OR "smart contract")

## SUMO-Specific Query
("SUMO" AND "digital twin")
OR
("traffic simulation" AND "urban digital twin")


---

# 6. Search & Export Procedure

For each database:
1. Execute all search strings  
2. Export results in **CSV/BibTeX** format  
3. Remove duplicates (use Zotero/Mendeley)  
4. Maintain a **Search Log** including:  
   - Database  
   - Search date  
   - Query used  
   - Total papers retrieved  

---

# 7. Screening Process (Two Stages)

## Stage 1: Title & Abstract Screening
Reject papers if:
- Not related to smart cities/digital twins  
- Not about AI agents or blockchain trust  
- Too general or purely conceptual  

## Stage 2: Full-Text Screening
Remove papers with:
- Missing architecture details  
- Lack of validation or implementation  
- No relevance to RQs  

All screening numbers will be tracked for PRISMA.

---

# 8. Data Extraction Table (Template)

| Field | Description |
|-------|-------------|
| Author & Year | Citation |
| Domain | Digital Twin / AI Agent / Blockchain / Simulation |
| Technology | SUMO, Solidity, LangChain, LiveView, etc. |
| Architecture Type | Centralized / Decentralized / Agent-Based |
| AI Approach | LLM Agent, MAS, RL, rules |
| Blockchain Model | Smart contract, consensus, privacy model |
| Application Context | Traffic, energy, mobility, IoT |
| Key Findings | Core contributions |
| Limitations | Weaknesses |
| Relevance to RQs | Mapping to RQ1–4 |

---

# 9. Quality Assessment

Use a 0–2 score for each criterion:
- **Clarity of research problem**  
- **Methodology robustness**  
- **Relevance to digital twin ecosystem**  
- **Completeness of architecture description**  
- **Evaluation depth**  

Total score determines paper quality grade.

---

# 10. Synthesis Strategy

Organize synthesis into thematic clusters:

## Theme 1 — Digital Twin Architectures
- City-scale twins (Singapore, Helsinki)
- IoT / CPS architectures
- Gaps: lack of cognitive agents & trust layers

## Theme 2 — AI Agent Integration
- MAS frameworks  
- LLM-driven agents (emerging area)  
- Cognitive decision-making gaps

## Theme 3 — Blockchain for Trustworthy Twins
- Smart contract-based IoT coordination  
- Tamper-proof sensor data  
- Challenges: latency, scaling, cost

## Theme 4 — Real-Time Simulation & SUMO Integration
- Traffic twins using SUMO  
- Synchronization models  
- Real-time dashboards (WebSockets, LiveView)

## Theme 5 — Identified Gaps
- No unified **AI + Blockchain + SUMO + Real-time UI** framework  
- No cognitive LLM-agent digital twin architecture  
- Lack of secure real-time decision-making pipelines  
- Missing blockchain-backed urban simulations  

These gaps justify your thesis contribution.

---

# 11. PRISMA Flow Diagram Structure

Final figure will include:
1. Records identified  
2. After duplicates removed  
3. Screened (title/abstract)  
4. Full-text assessed  
5. Final included studies  

---

# 12. SLR Chapter Structure

### 1. Introduction  
Motivation + significance

### 2. Research Questions  
List of RQs

### 3. Methodology  
- Search strategy  
- Strings  
- Databases  
- Inclusion/exclusion criteria  
- Screening  
- PRISMA  
- Quality assessment  

### 4. Results  
- Tables  
- Narrative themes  
- Comparative analysis  

### 5. Discussion  
- Gaps  
- Implications  
- How SLR informs architecture design  

### 6. Conclusion  
Summary and transition to your proposed Cognitive Digital Twin framework.

---

# End of Document
