"""
Smart Contract Integration Test Script
=========================================
End-to-end test for the TLSDecisionLog smart contract.
Deploys the contract, registers agents, logs decisions,
and verifies on-chain data.

Prerequisites:
    1. ganache --deterministic --port 8545  (in a separate terminal)
    2. cd blockchain && npx hardhat compile  (at least once)
    3. pip install web3

Usage:
    python blockchain/test_contract.py
"""

import sys
import os

# Add project root to path
project_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from blockchain.blockchain_client import BlockchainClient
from blockchain.contract_interface import TLSDecisionContract

# ------------------------------------------------------------------
# Test helpers
# ------------------------------------------------------------------
passed = 0
failed = 0


def test(name: str, condition: bool):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ PASS: {name}")
    else:
        failed += 1
        print(f"  ❌ FAIL: {name}")


# ==================================================================
# TEST SUITE
# ==================================================================
def main():
    global passed, failed
    print("=" * 60)
    print("  TLSDecisionLog Smart Contract Tests")
    print("=" * 60)

    # ----------------------------------------------------------
    # 1. Deploy contract
    # ----------------------------------------------------------
    print("\n--- 1. Deploy Contract ---")
    bc = BlockchainClient()
    test("Blockchain connected", bc.is_connected)

    if not bc.is_connected:
        print("\n⚠️  Cannot continue — Ganache is not running.")
        print("   Start it with: ganache --deterministic --port 8545")
        sys.exit(1)

    contract = TLSDecisionContract.deploy(bc)
    test("Contract deployed", contract.address is not None)
    test("Contract has an address", contract.address.startswith("0x"))
    test("Initial decision count is 0", contract.get_decision_count() == 0)

    # ----------------------------------------------------------
    # 2. Agent Registration
    # ----------------------------------------------------------
    print("\n--- 2. Agent Registration ---")
    agent_address = bc.w3.eth.accounts[0]
    agent2_address = bc.w3.eth.accounts[1]

    contract.register_agent(agent_address)
    test("Agent registered", contract.is_authorized(agent_address))
    test("Unregistered agent is not authorized", not contract.is_authorized(agent2_address))

    # ----------------------------------------------------------
    # 3. Log Decisions
    # ----------------------------------------------------------
    print("\n--- 3. Log Decisions ---")
    decisions_to_log = [
        {
            "intersection": "TRiia_Vaba",
            "action": "Phase 2 (Vabaduse_West) for 30s",
            "queues": {"Riia_North": 5, "Vabaduse_West": 12, "Vabaduse_East": 0, "Corridor_South": 3},
        },
        {
            "intersection": "TRiia_Turu",
            "action": "Phase 0 (Corridor_North) for 25s",
            "queues": {"Corridor_North": 8, "Riia_South": 2, "Turu_West": 4, "Corridor_East": 1},
        },
        {
            "intersection": "TRiia_Vaba",
            "action": "Phase 4 (Vabaduse_East) for 20s",
            "queues": {"Riia_North": 2, "Vabaduse_West": 0, "Vabaduse_East": 7, "Corridor_South": 1},
        },
    ]

    tx_hashes = []
    for d in decisions_to_log:
        input_hash = BlockchainClient.hash_data(d["queues"])
        tx = contract.log_decision(d["intersection"], d["action"], input_hash)
        tx_hashes.append(tx)
        test(f"Decision logged: {d['intersection']} → {d['action'][:30]}...", tx is not None)

    test("Decision count is 3", contract.get_decision_count() == 3)

    # ----------------------------------------------------------
    # 4. Query & Verify Decisions
    # ----------------------------------------------------------
    print("\n--- 4. Query & Verify ---")
    d0 = contract.get_decision(0)
    test("Decision 0 agent matches", d0["agent"] == agent_address)
    test("Decision 0 intersection is TRiia_Vaba", d0["intersection"] == "TRiia_Vaba")
    test("Decision 0 action correct", "Vabaduse_West" in d0["action"])

    # Verify input hash
    expected_hash = BlockchainClient.hash_data(decisions_to_log[0]["queues"])
    stored_hash = d0["inputDataHash"]
    test("Decision 0 input hash matches queue data", stored_hash == expected_hash)

    # Query latest decisions
    latest = contract.get_latest_decisions(2)
    test("get_latest_decisions returns 2", len(latest) == 2)
    test("Latest decision is the 3rd logged", "Vabaduse_East" in latest[1]["action"])

    # ----------------------------------------------------------
    # 5. Unauthorized Agent Rejection
    # ----------------------------------------------------------
    print("\n--- 5. Unauthorized Agent ---")
    try:
        contract.log_decision(
            "TTuru_Vaks", "Phase 0 (Corridor_West) for 15s",
            BlockchainClient.hash_data({"test": 1}),
            from_account=agent2_address,
        )
        test("Unauthorized agent REJECTED", False)  # Should not reach here
    except Exception:
        test("Unauthorized agent REJECTED", True)

    # ----------------------------------------------------------
    # 6. Agent Removal
    # ----------------------------------------------------------
    print("\n--- 6. Agent Removal ---")
    contract.remove_agent(agent_address)
    test("Agent removed", not contract.is_authorized(agent_address))

    # Re-register for further tests
    contract.register_agent(agent_address)
    test("Agent re-registered", contract.is_authorized(agent_address))

    # ----------------------------------------------------------
    # 7. Full Audit Trail
    # ----------------------------------------------------------
    print("\n--- 7. Audit Trail ---")
    all_decisions = contract.get_all_decisions()
    test("All 3 decisions retrieved", len(all_decisions) == 3)

    print("\n  📋 Full Audit Trail:")
    for i, d in enumerate(all_decisions):
        print(f"     [{i}] {d['intersection']}: {d['action']} (by {d['agent'][:10]}...)")

    # ----------------------------------------------------------
    # Summary
    # ----------------------------------------------------------
    total = passed + failed
    print("\n" + "=" * 60)
    print(f"  Results: {passed}/{total} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
    else:
        print("\n🎉 All contract tests passed! TLS decision logging works.\n")


if __name__ == "__main__":
    main()
