// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title TLSDecisionLog
 * @notice Immutable on-chain log of AI agent traffic light decisions.
 *         Each decision records the agent, intersection, action taken,
 *         a hash of the input data that prompted the decision, and the
 *         block timestamp.
 *
 * @dev   For the MS Thesis "Blockchain-Secured Digital Twin".
 *        Deployed on Ganache (dev) / Sepolia (demo).
 */
contract TLSDecisionLog {

    // ----------------------------------------------------------------
    // Data Structures
    // ----------------------------------------------------------------
    struct Decision {
        address agent;            // Ethereum address of the AI agent
        string  intersection;     // e.g. "TRiia_Vaba"
        string  action;           // e.g. "Phase 2 (Vabaduse_West) for 30s"
        bytes32 inputDataHash;    // SHA-256 hash of the traffic state
        uint256 timestamp;        // block.timestamp when logged
    }

    // ----------------------------------------------------------------
    // State
    // ----------------------------------------------------------------
    Decision[] public decisions;
    mapping(address => bool) public authorizedAgents;
    address public admin;

    // ----------------------------------------------------------------
    // Events
    // ----------------------------------------------------------------
    event DecisionLogged(
        uint256 indexed index,
        address indexed agent,
        string  intersection,
        string  action,
        uint256 timestamp
    );

    event AgentRegistered(address indexed agent);
    event AgentRemoved(address indexed agent);

    // ----------------------------------------------------------------
    // Modifiers
    // ----------------------------------------------------------------
    modifier onlyAdmin() {
        require(msg.sender == admin, "Only admin");
        _;
    }

    modifier onlyAgent() {
        require(authorizedAgents[msg.sender], "Not an authorized agent");
        _;
    }

    // ----------------------------------------------------------------
    // Constructor
    // ----------------------------------------------------------------
    constructor() {
        admin = msg.sender;
    }

    // ----------------------------------------------------------------
    // Admin Functions
    // ----------------------------------------------------------------
    function registerAgent(address agent) external onlyAdmin {
        authorizedAgents[agent] = true;
        emit AgentRegistered(agent);
    }

    function removeAgent(address agent) external onlyAdmin {
        authorizedAgents[agent] = false;
        emit AgentRemoved(agent);
    }

    // ----------------------------------------------------------------
    // Core: Log a TLS Decision
    // ----------------------------------------------------------------
    function logDecision(
        string memory intersection,
        string memory action,
        bytes32 inputDataHash
    ) external onlyAgent {
        uint256 idx = decisions.length;
        decisions.push(Decision(
            msg.sender,
            intersection,
            action,
            inputDataHash,
            block.timestamp
        ));
        emit DecisionLogged(idx, msg.sender, intersection, action, block.timestamp);
    }

    // ----------------------------------------------------------------
    // Query Functions
    // ----------------------------------------------------------------
    function getDecisionCount() external view returns (uint256) {
        return decisions.length;
    }

    function getDecision(uint256 index) external view returns (Decision memory) {
        require(index < decisions.length, "Index out of bounds");
        return decisions[index];
    }

    function getLatestDecisions(uint256 count) external view returns (Decision[] memory) {
        uint256 total = decisions.length;
        if (count > total) count = total;

        Decision[] memory result = new Decision[](count);
        for (uint256 i = 0; i < count; i++) {
            result[i] = decisions[total - count + i];
        }
        return result;
    }
}
