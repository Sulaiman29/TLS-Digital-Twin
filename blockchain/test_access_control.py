"""
Access Control Integration Test Script
=========================================
End-to-end test for the AccessControl smart contract.
Tests role management, intersection registry, command validation,
publisher validation, and unauthorized rejection.

Prerequisites:
    1. ganache --deterministic --port 8545  (in a separate terminal)
    2. cd blockchain && npx hardhat compile  (at least once)
    3. pip install web3

Usage:
    python blockchain/test_access_control.py
"""

import sys
import os

# Add project root to path
project_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from blockchain.blockchain_client import BlockchainClient
from blockchain.access_control import AccessControlContract

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
    print("  AccessControl Smart Contract Tests")
    print("=" * 60)

    # ----------------------------------------------------------
    # 1. Deploy Contract
    # ----------------------------------------------------------
    print("\n--- 1. Deploy Contract ---")
    bc = BlockchainClient()
    test("Blockchain connected", bc.is_connected)

    if not bc.is_connected:
        print("\n⚠️  Cannot continue — Ganache is not running.")
        print("   Start it with: ganache --deterministic --port 8545")
        sys.exit(1)

    ac = AccessControlContract.deploy(bc)
    test("Contract deployed", ac.address is not None)

    # Deployer should automatically be ADMIN
    test("Deployer has ADMIN role", ac.has_role(bc.account, "ADMIN"))

    # ----------------------------------------------------------
    # 2. Role Management
    # ----------------------------------------------------------
    print("\n--- 2. Role Management ---")
    agent_addr = bc.w3.eth.accounts[1]
    publisher_addr = bc.w3.eth.accounts[2]
    auditor_addr = bc.w3.eth.accounts[3]
    unauthorized_addr = bc.w3.eth.accounts[4]

    ac.grant_role(agent_addr, "AI_AGENT")
    ac.grant_role(publisher_addr, "PUBLISHER")
    ac.grant_role(auditor_addr, "AUDITOR")

    test("Agent has AI_AGENT role", ac.has_role(agent_addr, "AI_AGENT"))
    test("Publisher has PUBLISHER role", ac.has_role(publisher_addr, "PUBLISHER"))
    test("Auditor has AUDITOR role", ac.has_role(auditor_addr, "AUDITOR"))
    test("Unauthorized has no AI_AGENT role", not ac.has_role(unauthorized_addr, "AI_AGENT"))
    test("Unauthorized has no PUBLISHER role", not ac.has_role(unauthorized_addr, "PUBLISHER"))

    # ----------------------------------------------------------
    # 3. Intersection Registry
    # ----------------------------------------------------------
    print("\n--- 3. Intersection Registry ---")
    intersections = ["TRiia_Vaba", "TRiia_Turu", "TTuru_Vaks", "TTuru_Alek"]
    for iid in intersections:
        ac.register_intersection(iid)

    test("4 intersections registered", ac.get_intersection_count() == 4)
    test("TRiia_Vaba is registered", ac.is_registered_intersection("TRiia_Vaba"))
    test("TTuru_Alek is registered", ac.is_registered_intersection("TTuru_Alek"))
    test("Unknown intersection not registered", not ac.is_registered_intersection("FakeIntersection"))

    # ----------------------------------------------------------
    # 4. Command Validation (AI Agent)
    # ----------------------------------------------------------
    print("\n--- 4. Command Validation ---")
    test(
        "Authorized agent + registered intersection → ALLOWED",
        ac.validate_command(agent_addr, "TRiia_Vaba") is True,
    )
    test(
        "Authorized agent + unregistered intersection → DENIED",
        ac.validate_command(agent_addr, "FakeIntersection") is False,
    )
    test(
        "Unauthorized address + registered intersection → DENIED",
        ac.validate_command(unauthorized_addr, "TRiia_Vaba") is False,
    )
    test(
        "Unauthorized address + unregistered intersection → DENIED",
        ac.validate_command(unauthorized_addr, "FakeIntersection") is False,
    )

    # ----------------------------------------------------------
    # 5. Publisher Validation
    # ----------------------------------------------------------
    print("\n--- 5. Publisher Validation ---")
    test("Authorized publisher → ALLOWED", ac.validate_publisher(publisher_addr) is True)
    test("Unauthorized publisher → DENIED", ac.validate_publisher(unauthorized_addr) is False)

    # ----------------------------------------------------------
    # 6. Auditor Validation
    # ----------------------------------------------------------
    print("\n--- 6. Auditor Validation ---")
    test("Authorized auditor → ALLOWED", ac.validate_auditor(auditor_addr) is True)
    test("Unauthorized auditor → DENIED", ac.validate_auditor(unauthorized_addr) is False)

    # ----------------------------------------------------------
    # 7. Role Revocation
    # ----------------------------------------------------------
    print("\n--- 7. Role Revocation ---")
    ac.revoke_role(agent_addr, "AI_AGENT")
    test("Agent role revoked", not ac.has_role(agent_addr, "AI_AGENT"))
    test(
        "Revoked agent cannot issue commands",
        ac.validate_command(agent_addr, "TRiia_Vaba") is False,
    )

    # Re-grant for clean state
    ac.grant_role(agent_addr, "AI_AGENT")
    test("Agent role re-granted", ac.has_role(agent_addr, "AI_AGENT"))

    # ----------------------------------------------------------
    # 8. Intersection Removal
    # ----------------------------------------------------------
    print("\n--- 8. Intersection Removal ---")
    ac.remove_intersection("TTuru_Alek")
    test("TTuru_Alek removed", not ac.is_registered_intersection("TTuru_Alek"))
    test(
        "Command to removed intersection → DENIED",
        ac.validate_command(agent_addr, "TTuru_Alek") is False,
    )

    # ----------------------------------------------------------
    # 9. Non-Admin Cannot Manage Roles
    # ----------------------------------------------------------
    print("\n--- 9. Admin-Only Enforcement ---")
    try:
        # Try granting a role from a non-admin account
        ac.contract.functions.grantRole(
            ac.contract.functions.ROLE_AI_AGENT().call(),
            unauthorized_addr,
        ).transact({"from": unauthorized_addr})
        test("Non-admin role grant REJECTED", False)
    except Exception:
        test("Non-admin role grant REJECTED", True)

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
        print("\n🎉 All access control tests passed!\n")


if __name__ == "__main__":
    main()
