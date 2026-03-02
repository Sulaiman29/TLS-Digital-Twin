"""
Python Interface for AccessControl Smart Contract
====================================================
Deploys and interacts with the AccessControl Solidity contract.
Provides role management, intersection registry, and validation
functions for the Digital Twin security layer.

Usage:
    from blockchain.access_control import AccessControlContract
    ac = AccessControlContract.deploy(blockchain_client)
    ac.grant_role(agent_address, "AI_AGENT")
    ac.register_intersection("TRiia_Vaba")
    assert ac.validate_command(agent_address, "TRiia_Vaba")
"""

import os
import json
import logging
from web3 import Web3

logger = logging.getLogger("blockchain.access_control")

# Path to the Hardhat-compiled ABI
ARTIFACT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "artifacts", "contracts", "AccessControl.sol", "AccessControl.json",
)

# Role name → keccak256 hash mapping (must match Solidity contract)
ROLE_HASHES = {
    "ADMIN":     Web3.keccak(text="ADMIN"),
    "AI_AGENT":  Web3.keccak(text="AI_AGENT"),
    "PUBLISHER": Web3.keccak(text="PUBLISHER"),
    "AUDITOR":   Web3.keccak(text="AUDITOR"),
}


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


def _resolve_role(role: str) -> bytes:
    """Convert a role name string to its keccak256 bytes32 hash."""
    role_upper = role.upper()
    if role_upper not in ROLE_HASHES:
        raise ValueError(f"Unknown role: {role}. Valid roles: {list(ROLE_HASHES.keys())}")
    return ROLE_HASHES[role_upper]


class AccessControlContract:
    """
    Python wrapper for the AccessControl smart contract.
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
    def deploy(cls, blockchain_client) -> "AccessControlContract":
        """Deploy a fresh AccessControl contract."""
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
            "AccessControl deployed  ✔  address=%s  block=%d",
            tx_receipt.contractAddress,
            tx_receipt.blockNumber,
        )
        return cls(w3, deployed, account)

    @classmethod
    def at_address(cls, blockchain_client, address: str) -> "AccessControlContract":
        """Connect to an already-deployed AccessControl contract."""
        w3 = blockchain_client.w3
        abi, _ = _load_artifact()
        contract = w3.eth.contract(address=address, abi=abi)
        return cls(w3, contract, blockchain_client.account)

    # ------------------------------------------------------------------
    # Role Management
    # ------------------------------------------------------------------
    def grant_role(self, account: str, role: str) -> str:
        """Grant a role to an account. Admin-only."""
        role_hash = _resolve_role(role)
        tx_hash = self.contract.functions.grantRole(role_hash, account).transact(
            {"from": self.account}
        )
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        logger.info("Role granted  ✔  %s → %s", role, account)
        return tx_hash.hex()

    def revoke_role(self, account: str, role: str) -> str:
        """Revoke a role from an account. Admin-only."""
        role_hash = _resolve_role(role)
        tx_hash = self.contract.functions.revokeRole(role_hash, account).transact(
            {"from": self.account}
        )
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        logger.info("Role revoked  ✔  %s ← %s", role, account)
        return tx_hash.hex()

    def has_role(self, account: str, role: str) -> bool:
        """Check if an account has a specific role."""
        role_hash = _resolve_role(role)
        return self.contract.functions.hasRole(role_hash, account).call()

    # ------------------------------------------------------------------
    # Intersection Registry
    # ------------------------------------------------------------------
    def register_intersection(self, intersection_id: str) -> str:
        """Register an intersection ID. Admin-only."""
        tx_hash = self.contract.functions.registerIntersection(intersection_id).transact(
            {"from": self.account}
        )
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        logger.info("Intersection registered  ✔  %s", intersection_id)
        return tx_hash.hex()

    def remove_intersection(self, intersection_id: str) -> str:
        """Remove an intersection from the registry. Admin-only."""
        tx_hash = self.contract.functions.removeIntersection(intersection_id).transact(
            {"from": self.account}
        )
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        logger.info("Intersection removed  ✔  %s", intersection_id)
        return tx_hash.hex()

    def is_registered_intersection(self, intersection_id: str) -> bool:
        """Check if an intersection is registered."""
        return self.contract.functions.isRegisteredIntersection(intersection_id).call()

    def get_intersection_count(self) -> int:
        """Return the total number of registered intersections."""
        return self.contract.functions.getIntersectionCount().call()

    # ------------------------------------------------------------------
    # Validation Functions
    # ------------------------------------------------------------------
    def validate_command(self, sender: str, intersection: str) -> bool:
        """
        Validate whether a sender can issue a TLS command to an intersection.
        Returns True if sender has AI_AGENT role AND intersection is registered.
        """
        return self.contract.functions.validateCommand(sender, intersection).call()

    def validate_publisher(self, sender: str) -> bool:
        """Validate whether a sender can publish/anchor data."""
        return self.contract.functions.validatePublisher(sender).call()

    def validate_auditor(self, sender: str) -> bool:
        """Validate whether a sender can audit decision history."""
        return self.contract.functions.validateAuditor(sender).call()

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        return f"<AccessControlContract address={self.address}>"
