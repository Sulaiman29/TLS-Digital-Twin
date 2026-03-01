"""
Blockchain Client for Digital Twin Data Integrity
==================================================
Connects to a local Ganache (or Sepolia) Ethereum node and provides:
  - anchor_data()  : Hash & store data on-chain
  - verify_data()  : Verify data against on-chain record
  - anchor_batch() : Batch-hash multiple data items

Usage:
    from blockchain import BlockchainClient
    bc = BlockchainClient()
    tx = bc.anchor_data({"speed": 12.3, "count": 5})
    assert bc.verify_data({"speed": 12.3, "count": 5}, tx)
"""

import os
import json
import hashlib
import logging
from web3 import Web3

logger = logging.getLogger("blockchain")

# ---------------------------------------------------------------------------
# Configuration (overridable via environment variables)
# ---------------------------------------------------------------------------
DEFAULT_RPC_URL = "http://127.0.0.1:8545"
DEFAULT_GAS_OVERHEAD_PER_BYTE = 68       # Ethereum non-zero byte cost
DEFAULT_BASE_GAS = 21_000                # Intrinsic tx cost


class BlockchainClient:
    """Thin wrapper around Web3.py for hash-and-anchor operations."""

    def __init__(self, rpc_url: str | None = None, account_index: int = 0):
        """
        Connect to an Ethereum-compatible node.

        Args:
            rpc_url:       HTTP endpoint (default: env BLOCKCHAIN_RPC_URL or localhost:8545)
            account_index: Which Ganache account to use (default: 0 / first deterministic account)
        """
        self.rpc_url = rpc_url or os.getenv("BLOCKCHAIN_RPC_URL", DEFAULT_RPC_URL)
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        self._connected = False
        self.account = None

        if self.w3.is_connected():
            accounts = self.w3.eth.accounts
            if accounts:
                self.account = accounts[account_index]
                self._connected = True
                logger.info(
                    "Blockchain connected  ✔  RPC=%s  Account=%s",
                    self.rpc_url,
                    self.account,
                )
            else:
                logger.warning("Blockchain node has no accounts.")
        else:
            logger.warning(
                "Could not connect to blockchain at %s. "
                "Data will NOT be anchored.",
                self.rpc_url,
            )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    @property
    def is_connected(self) -> bool:
        """Return True if we have a live connection + usable account."""
        return self._connected

    @staticmethod
    def hash_data(data: dict) -> str:
        """
        Deterministically hash a dict with SHA-256.

        Sorts keys so that equivalent dicts always produce the same hash
        regardless of insertion order.
        """
        data_json = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(data_json.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Core: Anchor & Verify
    # ------------------------------------------------------------------
    def anchor_data(self, data: dict) -> str | None:
        """
        Hash *data* and write the hash on-chain in a self-transaction.

        Returns the transaction hash (hex string) or None on failure.
        """
        if not self.is_connected:
            logger.debug("Skipping anchor — not connected.")
            return None

        try:
            data_hash = self.hash_data(data)
            data_bytes = bytes.fromhex(data_hash)

            tx = {
                "from": self.account,
                "to": self.account,           # self-tx → data anchoring
                "value": 0,
                "data": data_bytes,
                "gas": DEFAULT_BASE_GAS + len(data_bytes) * DEFAULT_GAS_OVERHEAD_PER_BYTE,
            }
            tx_hash = self.w3.eth.send_transaction(tx)
            tx_hex = tx_hash.hex()
            logger.debug("Anchored  ✔  hash=%s  tx=%s", data_hash[:16], tx_hex[:16])
            return tx_hex
        except Exception as exc:
            logger.error("anchor_data failed: %s", exc)
            return None

    def verify_data(self, data: dict, tx_hash: str) -> bool:
        """
        Re-hash *data* and compare against the hash stored on-chain in *tx_hash*.

        Returns True if the hashes match (data is untampered).
        """
        if not self.is_connected:
            logger.debug("Skipping verify — not connected.")
            return False

        try:
            expected_hash = self.hash_data(data)
            tx = self.w3.eth.get_transaction(tx_hash)
            # input field contains the 0x-prefixed hex of the stored hash
            stored_hash = tx["input"].hex()
            # Strip 0x prefix if present
            if stored_hash.startswith("0x"):
                stored_hash = stored_hash[2:]
            return stored_hash == expected_hash
        except Exception as exc:
            logger.error("verify_data failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Batch anchoring (for high-frequency data like vehicle positions)
    # ------------------------------------------------------------------
    def anchor_batch(self, data_list: list[dict]) -> str | None:
        """
        Combine multiple data dicts into one Merkle-like hash and anchor it.

        Each item is individually hashed, then the hashes are concatenated
        and hashed again to produce a single root hash.

        Returns the transaction hash (hex string) or None on failure.
        """
        if not self.is_connected:
            return None

        try:
            individual_hashes = [self.hash_data(d) for d in data_list]
            combined = "".join(individual_hashes)
            root_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()

            data_bytes = bytes.fromhex(root_hash)
            tx = {
                "from": self.account,
                "to": self.account,
                "value": 0,
                "data": data_bytes,
                "gas": DEFAULT_BASE_GAS + len(data_bytes) * DEFAULT_GAS_OVERHEAD_PER_BYTE,
            }
            tx_hash = self.w3.eth.send_transaction(tx)
            tx_hex = tx_hash.hex()
            logger.debug(
                "Batch anchored  ✔  items=%d  root=%s  tx=%s",
                len(data_list), root_hash[:16], tx_hex[:16],
            )
            return tx_hex
        except Exception as exc:
            logger.error("anchor_batch failed: %s", exc)
            return None

    def verify_batch(self, data_list: list[dict], tx_hash: str) -> bool:
        """
        Verify a batch of data against an on-chain batch anchor.
        """
        if not self.is_connected:
            return False

        try:
            individual_hashes = [self.hash_data(d) for d in data_list]
            combined = "".join(individual_hashes)
            expected_root = hashlib.sha256(combined.encode("utf-8")).hexdigest()

            tx = self.w3.eth.get_transaction(tx_hash)
            stored_hash = tx["input"].hex()
            if stored_hash.startswith("0x"):
                stored_hash = stored_hash[2:]
            return stored_hash == expected_root
        except Exception as exc:
            logger.error("verify_batch failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------
    def get_block_number(self) -> int | None:
        """Return the latest block number, or None if not connected."""
        if not self.is_connected:
            return None
        return self.w3.eth.block_number

    def __repr__(self) -> str:
        status = "connected" if self.is_connected else "disconnected"
        return f"<BlockchainClient rpc={self.rpc_url} status={status}>"
