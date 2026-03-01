"""
Python Interface for TLSDecisionLog Smart Contract
====================================================
Deploys and interacts with the TLSDecisionLog Solidity contract.
Provides a clean Python API for logging and querying AI agent
traffic light decisions on the blockchain.

Usage:
    from blockchain.contract_interface import TLSDecisionContract
    contract = TLSDecisionContract.deploy(blockchain_client)
    contract.register_agent(agent_address)
    contract.log_decision("TRiia_Vaba", "Phase 2 (Vabaduse_West) for 30s", input_hash)
"""

import os
import json
import logging
from web3 import Web3

logger = logging.getLogger("blockchain.contract")

# Path to the Hardhat-compiled ABI
ARTIFACT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "artifacts", "contracts", "TLSDecisionLog.sol", "TLSDecisionLog.json",
)


def _load_artifact():
    """Load the compiled contract ABI and bytecode from Hardhat artifacts."""
    if not os.path.exists(ARTIFACT_PATH):
        raise FileNotFoundError(
            f"Contract artifact not found at {ARTIFACT_PATH}. "
            "Run 'npx hardhat compile' in the blockchain/ directory first."
        )
    with open(ARTIFACT_PATH, "r") as f:
        artifact = json.load(f)
    return artifact["abi"], artifact["bytecode"]


class TLSDecisionContract:
    """
    Python wrapper for the TLSDecisionLog smart contract.

    Attributes:
        w3:       Web3 instance
        contract: Web3 contract instance
        address:  Deployed contract address
        account:  Default account for transactions
    """

    def __init__(self, w3: Web3, contract, account: str):
        self.w3 = w3
        self.contract = contract
        self.address = contract.address
        self.account = account

    # ------------------------------------------------------------------
    # Deployment
    # ------------------------------------------------------------------
    @classmethod
    def deploy(cls, blockchain_client) -> "TLSDecisionContract":
        """
        Deploy a fresh TLSDecisionLog contract to the connected chain.

        Args:
            blockchain_client: A connected BlockchainClient instance.

        Returns:
            TLSDecisionContract instance pointing at the new deployment.
        """
        if not blockchain_client.is_connected:
            raise ConnectionError("BlockchainClient is not connected.")

        w3 = blockchain_client.w3
        account = blockchain_client.account
        abi, bytecode = _load_artifact()

        Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
        tx_hash = Contract.constructor().transact({"from": account})
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        deployed = w3.eth.contract(address=tx_receipt.contractAddress, abi=abi)
        logger.info(
            "TLSDecisionLog deployed  ✔  address=%s  block=%d",
            tx_receipt.contractAddress,
            tx_receipt.blockNumber,
        )
        return cls(w3, deployed, account)

    @classmethod
    def at_address(cls, blockchain_client, address: str) -> "TLSDecisionContract":
        """
        Connect to an already-deployed TLSDecisionLog contract.

        Args:
            blockchain_client: A connected BlockchainClient instance.
            address:           Ethereum address of the deployed contract.
        """
        w3 = blockchain_client.w3
        abi, _ = _load_artifact()
        contract = w3.eth.contract(address=address, abi=abi)
        return cls(w3, contract, blockchain_client.account)

    # ------------------------------------------------------------------
    # Admin Functions
    # ------------------------------------------------------------------
    def register_agent(self, agent_address: str) -> str:
        """Register an Ethereum address as an authorized AI agent."""
        tx_hash = self.contract.functions.registerAgent(agent_address).transact(
            {"from": self.account}
        )
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        logger.info("Agent registered  ✔  %s", agent_address)
        return tx_hash.hex()

    def remove_agent(self, agent_address: str) -> str:
        """Remove an agent's authorization."""
        tx_hash = self.contract.functions.removeAgent(agent_address).transact(
            {"from": self.account}
        )
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        logger.info("Agent removed  ✔  %s", agent_address)
        return tx_hash.hex()

    def is_authorized(self, agent_address: str) -> bool:
        """Check if an address is an authorized agent."""
        return self.contract.functions.authorizedAgents(agent_address).call()

    # ------------------------------------------------------------------
    # Core: Log Decisions
    # ------------------------------------------------------------------
    def log_decision(
        self,
        intersection: str,
        action: str,
        input_data_hash: str,
        from_account: str | None = None,
    ) -> str:
        """
        Log a TLS decision on-chain.

        Args:
            intersection:    Intersection ID (e.g. "TRiia_Vaba")
            action:          Human-readable action (e.g. "Phase 2 (Vabaduse_West) for 30s")
            input_data_hash: 64-char hex SHA-256 hash of the traffic state
            from_account:    Optional sender address (defaults to self.account)

        Returns:
            Transaction hash (hex string).
        """
        sender = from_account or self.account
        # Convert hex string to bytes32
        hash_bytes = bytes.fromhex(input_data_hash)

        tx_hash = self.contract.functions.logDecision(
            intersection, action, hash_bytes
        ).transact({"from": sender})

        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        logger.debug(
            "Decision logged  ✔  %s → %s  (block %d)",
            intersection, action, receipt.blockNumber,
        )
        return tx_hash.hex()

    # ------------------------------------------------------------------
    # Query Functions
    # ------------------------------------------------------------------
    def get_decision_count(self) -> int:
        """Return the total number of decisions logged."""
        return self.contract.functions.getDecisionCount().call()

    def get_decision(self, index: int) -> dict:
        """
        Fetch a single decision by index.

        Returns dict with: agent, intersection, action, inputDataHash, timestamp.
        """
        d = self.contract.functions.getDecision(index).call()
        return {
            "agent": d[0],
            "intersection": d[1],
            "action": d[2],
            "inputDataHash": d[3].hex(),
            "timestamp": d[4],
        }

    def get_latest_decisions(self, count: int = 10) -> list[dict]:
        """Fetch the most recent N decisions."""
        raw = self.contract.functions.getLatestDecisions(count).call()
        return [
            {
                "agent": d[0],
                "intersection": d[1],
                "action": d[2],
                "inputDataHash": d[3].hex(),
                "timestamp": d[4],
            }
            for d in raw
        ]

    def get_all_decisions(self) -> list[dict]:
        """Fetch all decisions (use sparingly on large datasets)."""
        count = self.get_decision_count()
        return [self.get_decision(i) for i in range(count)]

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        return f"<TLSDecisionContract address={self.address}>"
