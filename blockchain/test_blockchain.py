"""
Blockchain Integration Test Script
====================================
Standalone test that verifies the BlockchainClient works correctly
against a running Ganache instance.

Prerequisites:
    1. npm install -g ganache
    2. ganache --deterministic --port 8545   (in a separate terminal)
    3. pip install web3

Usage:
    python blockchain/test_blockchain.py
"""

import sys
import os

# Add project root to path
project_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from blockchain.blockchain_client import BlockchainClient

# ------------------------------------------------------------------
# Test helpers
# ------------------------------------------------------------------
passed = 0
failed = 0


def test(name: str, condition: bool):
    """Simple test assertion with colored output."""
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
    print("  Blockchain Integration Tests")
    print("=" * 60)

    # ----------------------------------------------------------
    # 1. Connection
    # ----------------------------------------------------------
    print("\n--- 1. Connection ---")
    bc = BlockchainClient()
    test("Client connects to Ganache", bc.is_connected)
    test("Block number is >= 0", bc.get_block_number() is not None and bc.get_block_number() >= 0)

    if not bc.is_connected:
        print("\n⚠️  Cannot continue — Ganache is not running.")
        print("   Start it with: ganache --deterministic --port 8545")
        sys.exit(1)

    # ----------------------------------------------------------
    # 2. Hashing determinism
    # ----------------------------------------------------------
    print("\n--- 2. Hashing ---")
    data_a = {"count": 5, "speed": 12.3, "intersection": "TRiia_Kalevi"}
    data_b = {"intersection": "TRiia_Kalevi", "speed": 12.3, "count": 5}  # same data, different order
    data_c = {"count": 5, "speed": 12.4, "intersection": "TRiia_Kalevi"}  # different data

    hash_a = BlockchainClient.hash_data(data_a)
    hash_b = BlockchainClient.hash_data(data_b)
    hash_c = BlockchainClient.hash_data(data_c)

    test("Same data, different key order → same hash", hash_a == hash_b)
    test("Different data → different hash", hash_a != hash_c)
    test("Hash is 64 hex chars (SHA-256)", len(hash_a) == 64)

    # ----------------------------------------------------------
    # 3. Anchor & Verify (single data point)
    # ----------------------------------------------------------
    print("\n--- 3. Anchor & Verify ---")
    detector_reading = {
        "intersection": "TRiia_Vaba",
        "detectors": {
            "RiiaKalevi_RiiaN_0": {"count": 5, "speed": 12.3},
            "RiiaKalevi_UlikW_0": {"count": 3, "speed": 8.7},
        },
        "timestamp": 1708900000,
    }

    tx_hash = bc.anchor_data(detector_reading)
    test("anchor_data returns a tx hash", tx_hash is not None)
    test("tx hash is a hex string", tx_hash is not None and len(tx_hash) > 0)

    verified = bc.verify_data(detector_reading, tx_hash)
    test("verify_data confirms untampered data", verified is True)

    # ----------------------------------------------------------
    # 4. Tamper Detection
    # ----------------------------------------------------------
    print("\n--- 4. Tamper Detection ---")
    tampered = detector_reading.copy()
    tampered["detectors"] = {
        "RiiaKalevi_RiiaN_0": {"count": 99, "speed": 0.0},  # TAMPERED!
        "RiiaKalevi_UlikW_0": {"count": 3, "speed": 8.7},
    }

    tamper_check = bc.verify_data(tampered, tx_hash)
    test("Tampered data is REJECTED by verify_data", tamper_check is False)

    # ----------------------------------------------------------
    # 5. TLS Decision anchoring
    # ----------------------------------------------------------
    print("\n--- 5. TLS Decision ---")
    tls_decision = {
        "agent": "TRiia_Vaba",
        "action": "setPhase(3)",
        "input_data_hash": BlockchainClient.hash_data({"queue_north": 8, "queue_south": 2}),
        "reasoning": "North approach has 4x more vehicles",
        "timestamp": 1708900042,
    }

    tls_tx = bc.anchor_data(tls_decision)
    test("TLS decision anchored", tls_tx is not None)
    test("TLS decision verified", bc.verify_data(tls_decision, tls_tx))

    # ----------------------------------------------------------
    # 6. Batch Anchoring (vehicle positions)
    # ----------------------------------------------------------
    print("\n--- 6. Batch Anchoring ---")
    vehicles = [
        {"id": "veh_0", "x": 100.0, "y": 200.0, "speed": 13.5, "lane": "edge1_0"},
        {"id": "veh_1", "x": 150.0, "y": 220.0, "speed": 10.2, "lane": "edge2_1"},
        {"id": "veh_2", "x": 80.0,  "y": 190.0, "speed": 0.0,  "lane": "edge1_0"},
    ]

    batch_tx = bc.anchor_batch(vehicles)
    test("Batch anchor returns tx hash", batch_tx is not None)
    test("Batch verify: original data passes", bc.verify_batch(vehicles, batch_tx))

    # Tamper one vehicle
    tampered_vehicles = [v.copy() for v in vehicles]
    tampered_vehicles[1]["speed"] = 999.0  # TAMPERED!
    test("Batch verify: tampered data fails", bc.verify_batch(tampered_vehicles, batch_tx) is False)

    # ----------------------------------------------------------
    # 7. Graceful handling of bad tx hash
    # ----------------------------------------------------------
    print("\n--- 7. Edge Cases ---")
    bad_verify = bc.verify_data(detector_reading, "0x" + "00" * 32)
    test("Bad tx hash returns False (not crash)", bad_verify is False)

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
        print("\n🎉 All tests passed! Blockchain integration is working.\n")


if __name__ == "__main__":
    main()
