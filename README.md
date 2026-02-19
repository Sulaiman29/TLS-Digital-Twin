# Digital Twin for smart Traffic Signal

This repository contains a traffic simulation project for Tartu, Estonia, implementing various traffic control strategies using SUMO (Simulation of Urban MObility) and Python. The project explores rule-based and LLM-driven agentic approaches to optimize traffic flow. Will add now Elixir Dashboard and Blockchain layer.

## Project Structure

The repository is organized as follows:

- **`AI layer/`**: Contains the Python implementation of traffic control agents.
  - `tartu_agentic_brain.py`: LLM-based agent for the full Tartu network.
  - `tartu_traffic_agent.py`: Rule-based agent for the full Tartu network.
  - `multi_agentic_brain.py` / `multi_traffic_agent.py`: Agents for multi-intersection scenarios.
  - `agentic_brain.py` / `traffic_agent.py`: Core or single-intersection agent logic.

- **`tartu_network/`**: SUMO configuration and network files for the specific Tartu city simulation.
  - `cfg/`: Contains `.sumocfg` configuration files.
  - `network/`: Network topology (`.net.xml`), connections, and edge data.

- **`multi_intersection/`**: Scenarios involving multiple interconnected intersections.
  - `cfg/`: Simulation configurations.
  - `routes/`, `network/`: Route and network definitions.

- **`single_intersection/`**: Baseline scenarios for a single intersection.

- **`SLR/`**: System Literature Review and related documents.

## Requirements

To run the simulations, you need:

1.  **SUMO**: Install SUMO and ensure `SUMO_HOME` environment variable is set.
2.  **Python 3.x**: Recommended to use a virtual environment.
3.  **Python Libraries**:
    - `traci`
    - `sumolib`
    - `openai` (for LLM-based agents)
    - `python-dotenv` (recommended for API key management)

## Installation

1.  Clone the repository.
2.  Install dependencies:
    ```bash
    pip install traci sumolib openai python-dotenv
    ```
3.  Ensure SUMO is installed and accessible in your system path.

## Usage

Each simulation scenario is controlled by scripts in the `AI layer`.

### Running Rule-Based Agents
To run a standard rule-based stimulation (e.g., for Tartu):
```bash
python "AI layer/tartu_traffic_agent.py"
```

### Running LLM-Based Agents
To run the agentic (LLM-driven) simulation (ensure your OpenAI API key is configured):
```bash
python "AI layer/tartu_agentic_brain.py"
```

*Note: You may need to adjust the paths within the python scripts to point to the correct `.sumocfg` file if running from the root directory.*

## Contributing
Personal thesis implementation.
