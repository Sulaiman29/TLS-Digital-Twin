"""
Blockchain Security Layer for the Traffic Digital Twin.
Provides data integrity verification via hash-and-anchor on Ethereum (Ganache/Sepolia).
"""

from .blockchain_client import BlockchainClient
from .contract_interface import TLSDecisionContract

__all__ = ["BlockchainClient", "TLSDecisionContract"]

