"""Unit tests for ml/features.py.

Covers all 10 required test categories:
1. Sender-only, receiver-only, and mixed-role accounts
2. Successful and failed transactions
3. Amount sums, averages, and maximums
4. Unique counterparties and graph topology
5. Shared-device statistics (sender-side only per Limitation L7)
6. Empty and malformed input validation
7. Deterministic output
8. Input immutability
9. Ground-truth leakage resistance
10. Zero NaN or infinite feature values
"""

import copy
import math
import unittest
from typing import Any, Dict, List

from ml.features import (
    FEATURE_NAMES,
    FEATURE_DEFINITIONS,
    extract_account_features,
    extract_feature_matrix,
    validate_feature_input,
)


def make_txn(
    txn_id: str = "T000001",
    timestamp: str = "2026-10-01T10:00:00Z",
    sender: str = "ACC_0001",
    receiver: str = "ACC_0002",
    device: str = "DEV_0001",
    amount: float = 1000.0,
    status: str = "SUCCESS",
    complaint: bool = False,
    ground_truth: Any = None,
) -> Dict[str, Any]:
    """Helper to create a valid transaction dictionary."""
    txn = {
        "txn_id": txn_id,
        "timestamp": timestamp,
        "sender_account": sender,
        "receiver_account": receiver,
        "sender_device_id": device,
        "amount_inr": amount,
        "status": status,
        "complaint_filed": complaint,
    }
    if ground_truth is not None:
        txn["ground_truth"] = ground_truth
    return txn


class TestAccountFeatures(unittest.TestCase):
    """Test suite for feature extraction and validation."""

    def test_feature_names_and_definitions_consistency(self):
        """All features in FEATURE_NAMES must be documented in FEATURE_DEFINITIONS."""
        self.assertEqual(len(FEATURE_NAMES), 25)
        self.assertEqual(len(FEATURE_DEFINITIONS), 25)
        for fname in FEATURE_NAMES:
            self.assertIn(fname, FEATURE_DEFINITIONS)
            self.assertTrue(len(FEATURE_DEFINITIONS[fname]) > 0)

    def test_sender_only_account(self):
        """Account that only sends transactions."""
        txns = [
            make_txn("T000001", sender="ACC_0001", receiver="ACC_0002", amount=500.0, device="DEV_0001"),
            make_txn("T000002", sender="ACC_0001", receiver="ACC_0003", amount=1500.0, device="DEV_0001"),
        ]
        feats = extract_account_features(txns)
        acc1 = feats["ACC_0001"]

        self.assertEqual(acc1["txn_count_sent"], 2.0)
        self.assertEqual(acc1["txn_count_received"], 0.0)
        self.assertEqual(acc1["txn_count_total"], 2.0)
        self.assertEqual(acc1["amount_sent_total"], 2000.0)
        self.assertEqual(acc1["amount_received_total"], 0.0)
        self.assertEqual(acc1["net_flow_amount"], -2000.0)
        self.assertEqual(acc1["amount_sent_avg"], 1000.0)
        self.assertEqual(acc1["amount_received_avg"], 0.0)
        self.assertEqual(acc1["amount_sent_max"], 1500.0)
        self.assertEqual(acc1["amount_received_max"], 0.0)
        self.assertEqual(acc1["amount_max_overall"], 1500.0)
        self.assertEqual(acc1["fan_in_count"], 0.0)
        self.assertEqual(acc1["fan_out_count"], 2.0)
        self.assertEqual(acc1["counterparty_count_total"], 2.0)
        self.assertEqual(acc1["fan_ratio"], 0.0)  # 0 / (2 + 1)
        self.assertEqual(acc1["devices_used_count"], 1.0)
        self.assertEqual(acc1["max_senders_on_used_devices"], 1.0)
        self.assertEqual(acc1["shared_device_user_flag"], 0.0)

    def test_receiver_only_account(self):
        """Account that only receives transactions (tests Limitation L7)."""
        txns = [
            make_txn("T000001", sender="ACC_0001", receiver="ACC_0002", amount=500.0, device="DEV_0001"),
            make_txn("T000002", sender="ACC_0003", receiver="ACC_0002", amount=1500.0, device="DEV_0002", complaint=True),
        ]
        feats = extract_account_features(txns)
        acc2 = feats["ACC_0002"]

        self.assertEqual(acc2["txn_count_sent"], 0.0)
        self.assertEqual(acc2["txn_count_received"], 2.0)
        self.assertEqual(acc2["txn_count_total"], 2.0)
        self.assertEqual(acc2["amount_sent_total"], 0.0)
        self.assertEqual(acc2["amount_received_total"], 2000.0)
        self.assertEqual(acc2["net_flow_amount"], 2000.0)
        self.assertEqual(acc2["amount_sent_avg"], 0.0)
        self.assertEqual(acc2["amount_received_avg"], 1000.0)
        self.assertEqual(acc2["amount_sent_max"], 0.0)
        self.assertEqual(acc2["amount_received_max"], 1500.0)
        self.assertEqual(acc2["amount_max_overall"], 1500.0)
        self.assertEqual(acc2["fan_in_count"], 2.0)
        self.assertEqual(acc2["fan_out_count"], 0.0)
        self.assertEqual(acc2["counterparty_count_total"], 2.0)
        self.assertEqual(acc2["fan_ratio"], 2.0)  # 2 / (0 + 1)
        self.assertEqual(acc2["complaint_count_as_receiver"], 1.0)
        self.assertEqual(acc2["complaint_count_as_sender"], 0.0)

        # Limitation L7: Device is strictly sender-side. Receiver has NO device attributed.
        self.assertEqual(acc2["devices_used_count"], 0.0)
        self.assertEqual(acc2["max_senders_on_used_devices"], 0.0)
        self.assertEqual(acc2["shared_device_user_flag"], 0.0)

    def test_mixed_role_account(self):
        """Account that both sends and receives."""
        txns = [
            make_txn("T000001", sender="ACC_0001", receiver="ACC_0002", amount=1000.0, device="DEV_0001"),
            make_txn("T000002", sender="ACC_0002", receiver="ACC_0003", amount=800.0, device="DEV_0002"),
        ]
        feats = extract_account_features(txns)
        acc2 = feats["ACC_0002"]

        self.assertEqual(acc2["txn_count_sent"], 1.0)
        self.assertEqual(acc2["txn_count_received"], 1.0)
        self.assertEqual(acc2["txn_count_total"], 2.0)
        self.assertEqual(acc2["amount_sent_total"], 800.0)
        self.assertEqual(acc2["amount_received_total"], 1000.0)
        self.assertEqual(acc2["net_flow_amount"], 200.0)
        self.assertEqual(acc2["amount_max_overall"], 1000.0)
        self.assertEqual(acc2["fan_in_count"], 1.0)
        self.assertEqual(acc2["fan_out_count"], 1.0)
        self.assertEqual(acc2["counterparty_count_total"], 2.0)
        self.assertEqual(acc2["fan_ratio"], 0.5)  # 1 / (1 + 1) = 0.5
        self.assertEqual(acc2["devices_used_count"], 1.0)  # only DEV_0002 (sent), not DEV_0001 (received)

    def test_successful_and_failed_transactions(self):
        """Verifies successful and failed transaction splits and failure rates."""
        txns = [
            make_txn("T000001", sender="ACC_0001", receiver="ACC_0002", status="SUCCESS"),
            make_txn("T000002", sender="ACC_0001", receiver="ACC_0003", status="FAILED"),
            make_txn("T000003", sender="ACC_0001", receiver="ACC_0004", status="FAILED"),
            make_txn("T000004", sender="ACC_0005", receiver="ACC_0001", status="FAILED"),
            make_txn("T000005", sender="ACC_0006", receiver="ACC_0001", status="SUCCESS"),
        ]
        feats = extract_account_features(txns)
        acc1 = feats["ACC_0001"]

        self.assertEqual(acc1["txn_success_sent"], 1.0)
        self.assertEqual(acc1["txn_failed_sent"], 2.0)
        self.assertEqual(acc1["txn_success_received"], 1.0)
        self.assertEqual(acc1["txn_failed_received"], 1.0)
        self.assertAlmostEqual(acc1["failure_rate_sent"], 2.0 / 3.0, places=4)

    def test_amount_aggregates(self):
        """Sums, averages, maximums, and rounding behavior."""
        txns = [
            make_txn("T000001", sender="ACC_0001", receiver="ACC_0002", amount=123.456),
            make_txn("T000002", sender="ACC_0001", receiver="ACC_0003", amount=876.543),
        ]
        feats = extract_account_features(txns)
        acc1 = feats["ACC_0001"]

        self.assertEqual(acc1["amount_sent_total"], 999.999)
        self.assertEqual(acc1["amount_sent_avg"], 499.9995)
        self.assertEqual(acc1["amount_sent_max"], 876.543)
        self.assertEqual(acc1["amount_max_overall"], 876.543)

    def test_unique_counterparties(self):
        """Overlap between senders and receivers is deduplicated in counterparty_count_total."""
        txns = [
            make_txn("T000001", sender="ACC_0002", receiver="ACC_0001"),  # in from 0002
            make_txn("T000002", sender="ACC_0003", receiver="ACC_0001"),  # in from 0003
            make_txn("T000003", sender="ACC_0001", receiver="ACC_0003"),  # out to 0003 (overlap)
            make_txn("T000004", sender="ACC_0001", receiver="ACC_0004"),  # out to 0004
        ]
        feats = extract_account_features(txns)
        acc1 = feats["ACC_0001"]

        self.assertEqual(acc1["fan_in_count"], 2.0)   # ACC_0002, ACC_0003
        self.assertEqual(acc1["fan_out_count"], 2.0)  # ACC_0003, ACC_0004
        # Total distinct counterparties: {ACC_0002, ACC_0003, ACC_0004} = 3
        self.assertEqual(acc1["counterparty_count_total"], 3.0)
        self.assertAlmostEqual(acc1["fan_ratio"], 2.0 / (2.0 + 1.0), places=4)

    def test_shared_device_statistics(self):
        """Multiple senders on the same device trigger device-sharing flags."""
        txns = [
            make_txn("T000001", sender="ACC_0001", receiver="ACC_0099", device="DEV_0010"),
            make_txn("T000002", sender="ACC_0002", receiver="ACC_0099", device="DEV_0010"),
            make_txn("T000003", sender="ACC_0003", receiver="ACC_0099", device="DEV_0010"),
            make_txn("T000004", sender="ACC_0004", receiver="ACC_0099", device="DEV_0020"),  # sole user
        ]
        feats = extract_account_features(txns)

        # ACC_0001 used DEV_0010, which was used by ACC_0001, ACC_0002, ACC_0003 (3 senders)
        self.assertEqual(feats["ACC_0001"]["devices_used_count"], 1.0)
        self.assertEqual(feats["ACC_0001"]["max_senders_on_used_devices"], 3.0)
        self.assertEqual(feats["ACC_0001"]["shared_device_user_flag"], 1.0)

        # ACC_0004 used DEV_0020, which has only 1 sender
        self.assertEqual(feats["ACC_0004"]["devices_used_count"], 1.0)
        self.assertEqual(feats["ACC_0004"]["max_senders_on_used_devices"], 1.0)
        self.assertEqual(feats["ACC_0004"]["shared_device_user_flag"], 0.0)

        # ACC_0099 is receiver only, receives transactions from DEV_0010 and DEV_0020
        # Limitation L7: NEVER infer receiver device
        self.assertEqual(feats["ACC_0099"]["devices_used_count"], 0.0)
        self.assertEqual(feats["ACC_0099"]["max_senders_on_used_devices"], 0.0)
        self.assertEqual(feats["ACC_0099"]["shared_device_user_flag"], 0.0)

    def test_empty_and_inactive_accounts(self):
        """Empty input and explicit inactive accounts return clean zeroed structures."""
        self.assertEqual(extract_account_features([]), {})

        acc_ids, matrix = extract_feature_matrix([], account_ids=["ACC_0001", "ACC_0002"])
        self.assertEqual(acc_ids, ["ACC_0001", "ACC_0002"])
        self.assertEqual(len(matrix), 2)
        self.assertEqual(matrix[0], [0.0] * 25)
        self.assertEqual(matrix[1], [0.0] * 25)

        # Inactive account requested alongside active transactions
        txns = [make_txn("T000001", sender="ACC_0001", receiver="ACC_0002")]
        acc_ids, matrix = extract_feature_matrix(txns, account_ids=["ACC_0001", "ACC_0999"])
        self.assertEqual(acc_ids, ["ACC_0001", "ACC_0999"])
        self.assertNotEqual(matrix[0], [0.0] * 25)
        self.assertEqual(matrix[1], [0.0] * 25)

    def test_malformed_input_rejection(self):
        """Comprehensive input validation rejection."""
        # Non-list
        with self.assertRaises(TypeError):
            validate_feature_input("not-a-list")

        # Non-dict item
        with self.assertRaises(TypeError):
            validate_feature_input(["not-a-dict"])

        # Missing required key
        bad_txn = make_txn()
        del bad_txn["amount_inr"]
        with self.assertRaises(ValueError):
            validate_feature_input([bad_txn])

        # Bad txn_id format
        with self.assertRaises(ValueError):
            validate_feature_input([make_txn(txn_id="TX_12345")])

        # Duplicate txn_id
        with self.assertRaises(ValueError):
            validate_feature_input([make_txn(txn_id="T000001"), make_txn(txn_id="T000001")])

        # Bad timestamp format
        with self.assertRaises(ValueError):
            validate_feature_input([make_txn(timestamp="2026/10/01 10:00:00")])

        # Bad account ID format
        with self.assertRaises(ValueError):
            validate_feature_input([make_txn(sender="ACC1234")])
        with self.assertRaises(ValueError):
            validate_feature_input([make_txn(receiver="ACCOUNT_1")])

        # Sender equals receiver
        with self.assertRaises(ValueError):
            validate_feature_input([make_txn(sender="ACC_0001", receiver="ACC_0001")])

        # Bad device ID format
        with self.assertRaises(ValueError):
            validate_feature_input([make_txn(device="DEVICE_1")])

        # Boolean as amount (Python isinstance(True, int) is True, must be rejected!)
        with self.assertRaises(ValueError):
            validate_feature_input([make_txn(amount=True)])

        # Zero or negative amount
        with self.assertRaises(ValueError):
            validate_feature_input([make_txn(amount=0.0)])
        with self.assertRaises(ValueError):
            validate_feature_input([make_txn(amount=-100.0)])

        # NaN or inf amount
        with self.assertRaises(ValueError):
            validate_feature_input([make_txn(amount=float("nan"))])
        with self.assertRaises(ValueError):
            validate_feature_input([make_txn(amount=float("inf"))])

        # Invalid status
        with self.assertRaises(ValueError):
            validate_feature_input([make_txn(status="PENDING")])

        # Non-bool complaint_filed
        with self.assertRaises(ValueError):
            validate_feature_input([make_txn(complaint="yes")])

    def test_deterministic_output(self):
        """Identical transactions produce identical feature values regardless of extraction calls."""
        txns = [
            make_txn("T000001", sender="ACC_0001", receiver="ACC_0002", amount=100.0),
            make_txn("T000002", sender="ACC_0003", receiver="ACC_0001", amount=200.0),
            make_txn("T000003", sender="ACC_0002", receiver="ACC_0003", amount=300.0),
        ]
        feats1 = extract_account_features(txns)
        feats2 = extract_account_features(txns)
        self.assertEqual(feats1, feats2)

        # Keys in feats must be sorted ascending
        self.assertEqual(list(feats1.keys()), sorted(feats1.keys()))

    def test_input_immutability(self):
        """Input list and transaction dictionaries must never be mutated."""
        txns = [
            make_txn("T000001", sender="ACC_0001", receiver="ACC_0002", amount=500.0),
            make_txn("T000002", sender="ACC_0002", receiver="ACC_0003", amount=750.0),
        ]
        original = copy.deepcopy(txns)

        extract_account_features(txns)
        self.assertEqual(txns, original)

        extract_feature_matrix(txns)
        self.assertEqual(txns, original)

    def test_ground_truth_leakage_resistance(self):
        """Features must be identical whether ground_truth is present, altered, or stripped."""
        txns_with_gt = [
            make_txn(
                "T000001",
                sender="ACC_0001",
                receiver="ACC_0002",
                amount=500.0,
                ground_truth={"scenario": "mule_ring", "ring_member_accounts": ["ACC_0001", "ACC_0002"]},
            ),
            make_txn(
                "T000002",
                sender="ACC_0002",
                receiver="ACC_0003",
                amount=1000.0,
                ground_truth={"scenario": "normal", "ring_member_accounts": []},
            ),
        ]

        txns_without_gt = [
            make_txn("T000001", sender="ACC_0001", receiver="ACC_0002", amount=500.0),
            make_txn("T000002", sender="ACC_0002", receiver="ACC_0003", amount=1000.0),
        ]

        txns_with_bogus_gt = [
            make_txn("T000001", sender="ACC_0001", receiver="ACC_0002", amount=500.0, ground_truth="BOGUS_SCENARIO"),
            make_txn("T000002", sender="ACC_0002", receiver="ACC_0003", amount=1000.0, ground_truth=12345),
        ]

        feats_gt = extract_account_features(txns_with_gt)
        feats_nogt = extract_account_features(txns_without_gt)
        feats_bogus = extract_account_features(txns_with_bogus_gt)

        self.assertEqual(feats_gt, feats_nogt)
        self.assertEqual(feats_gt, feats_bogus)

    def test_zero_nan_or_infinite_values(self):
        """Verify no NaN, inf, or None exists in any feature across edge cases."""
        # Edge cases: 0 sent, 0 received, 0 failed, 0 success
        txns = [
            make_txn("T000001", sender="ACC_0001", receiver="ACC_0002", amount=1.0),
            make_txn("T000002", sender="ACC_0002", receiver="ACC_0003", amount=2.0),
        ]
        feats = extract_account_features(txns)

        for acc, acc_feats in feats.items():
            for fname in FEATURE_NAMES:
                val = acc_feats[fname]
                self.assertIsInstance(val, float, f"{acc}:{fname} is not float")
                self.assertFalse(math.isnan(val), f"{acc}:{fname} is NaN")
                self.assertFalse(math.isinf(val), f"{acc}:{fname} is Inf")

        _, matrix = extract_feature_matrix(txns, account_ids=["ACC_0001", "ACC_9999"])
        for row in matrix:
            for val in row:
                self.assertIsInstance(val, float)
                self.assertFalse(math.isnan(val))
                self.assertFalse(math.isinf(val))

    def test_nullable_and_omitted_device_ids(self):
        """Transactions with sender_device_id None or omitted must evaluate to 0.0 for device features."""
        txns = [
            {
                "txn_id": "T000001",
                "timestamp": "2026-10-01T10:00:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0002",
                "sender_device_id": None,
                "amount_inr": 1000.0,
                "status": "SUCCESS",
            },
            {
                "txn_id": "T000002",
                "timestamp": "2026-10-01T11:00:00Z",
                "sender_account": "ACC_0002",
                "receiver_account": "ACC_0003",
                "amount_inr": 500.0,
                "status": "SUCCESS",
            },
            {
                "txn_id": "T000003",
                "timestamp": "2026-10-01T12:00:00Z",
                "sender_account": "ACC_0003",
                "receiver_account": "ACC_0004",
                "sender_device_id": "DEV_0001",
                "amount_inr": 700.0,
                "status": "SUCCESS",
            },
        ]
        validate_feature_input(txns)
        feats = extract_account_features(txns)

        # ACC_0001: sent txn with sender_device_id=None -> no device observation
        self.assertEqual(feats["ACC_0001"]["devices_used_count"], 0.0)
        self.assertEqual(feats["ACC_0001"]["max_senders_on_used_devices"], 0.0)
        self.assertEqual(feats["ACC_0001"]["shared_device_user_flag"], 0.0)
        self.assertEqual(feats["ACC_0001"]["txn_count_sent"], 1.0)
        self.assertEqual(feats["ACC_0001"]["amount_sent_total"], 1000.0)

        # ACC_0002: sent txn with omitted sender_device_id -> no device observation
        self.assertEqual(feats["ACC_0002"]["devices_used_count"], 0.0)
        self.assertEqual(feats["ACC_0002"]["max_senders_on_used_devices"], 0.0)
        self.assertEqual(feats["ACC_0002"]["shared_device_user_flag"], 0.0)

        # ACC_0003: sent txn with explicit DEV_0001 -> 1 device, 1 sender on that device
        self.assertEqual(feats["ACC_0003"]["devices_used_count"], 1.0)
        self.assertEqual(feats["ACC_0003"]["max_senders_on_used_devices"], 1.0)
        self.assertEqual(feats["ACC_0003"]["shared_device_user_flag"], 0.0)

        # ACC_0004: receiver only -> 0.0 device features per L7
        self.assertEqual(feats["ACC_0004"]["devices_used_count"], 0.0)
        self.assertEqual(feats["ACC_0004"]["max_senders_on_used_devices"], 0.0)
        self.assertEqual(feats["ACC_0004"]["shared_device_user_flag"], 0.0)

    def test_device_features_dedicated_vs_unobserved_distinction(self):
        """Contract §5.2 distinction: dedicated private device (1, 1, 0) vs unobserved device (0, 0, 0)."""
        txns = [
            # ACC_0001 has verified private device DEV_0001
            make_txn("T000001", sender="ACC_0001", receiver="ACC_0002", device="DEV_0001"),
            # ACC_0002 has unobserved device (None)
            make_txn("T000002", sender="ACC_0002", receiver="ACC_0003", device=None),
        ]
        feats = extract_account_features(txns)

        # Dedicated private device
        self.assertEqual(feats["ACC_0001"]["devices_used_count"], 1.0)
        self.assertEqual(feats["ACC_0001"]["max_senders_on_used_devices"], 1.0)
        self.assertEqual(feats["ACC_0001"]["shared_device_user_flag"], 0.0)

        # Unobserved device
        self.assertEqual(feats["ACC_0002"]["devices_used_count"], 0.0)
        self.assertEqual(feats["ACC_0002"]["max_senders_on_used_devices"], 0.0)
        self.assertEqual(feats["ACC_0002"]["shared_device_user_flag"], 0.0)

    def test_structured_complaint_and_legacy_fallback(self):
        """Structured complaint object and legacy boolean fallback support."""
        txns = [
            # Structured complaint
            {
                "txn_id": "T000001",
                "timestamp": "2026-10-01T10:00:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0002",
                "amount_inr": 1000.0,
                "status": "SUCCESS",
                "complaint": {
                    "complaint_id": "CMP_0001",
                    "filed_at": "2026-10-01T10:30:00Z",
                    "ingested_at": "2026-10-01T10:35:00Z",
                    "category": "PHISHING_SCAM",
                },
            },
            # Legacy boolean fallback (complaint_filed=True, complaint omitted)
            {
                "txn_id": "T000002",
                "timestamp": "2026-10-01T11:00:00Z",
                "sender_account": "ACC_0003",
                "receiver_account": "ACC_0002",
                "amount_inr": 2000.0,
                "status": "SUCCESS",
                "complaint_filed": True,
            },
            # Clean transaction (complaint_filed=False, complaint omitted)
            {
                "txn_id": "T000003",
                "timestamp": "2026-10-01T12:00:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0004",
                "amount_inr": 500.0,
                "status": "SUCCESS",
                "complaint_filed": False,
            },
        ]
        validate_feature_input(txns)
        feats = extract_account_features(txns)

        # ACC_0002 received T000001 (structured) and T000002 (legacy fallback) -> count = 2.0
        self.assertEqual(feats["ACC_0002"]["complaint_count_as_receiver"], 2.0)
        self.assertEqual(feats["ACC_0002"]["complaint_count_as_sender"], 0.0)

        # ACC_0001 sent T000001 (structured) and T000003 (clean) -> count = 1.0
        self.assertEqual(feats["ACC_0001"]["complaint_count_as_sender"], 1.0)
        self.assertEqual(feats["ACC_0001"]["complaint_count_as_receiver"], 0.0)

        # ACC_0003 sent T000002 (legacy fallback) -> count = 1.0
        self.assertEqual(feats["ACC_0003"]["complaint_count_as_sender"], 1.0)

        # ACC_0004 received T000003 (clean) -> count = 0.0
        self.assertEqual(feats["ACC_0004"]["complaint_count_as_receiver"], 0.0)

    def test_conflicting_complaint_telemetry_rejection(self):
        """Reject transaction when complaint dict is present but complaint_filed is False."""
        txns = [
            {
                "txn_id": "T000001",
                "timestamp": "2026-10-01T10:00:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0002",
                "amount_inr": 1000.0,
                "status": "SUCCESS",
                "complaint_filed": False,
                "complaint": {
                    "complaint_id": "CMP_0001",
                    "filed_at": "2026-10-01T10:30:00Z",
                    "category": "UNAUTHORIZED_TRANSACTION",
                },
            }
        ]
        with self.assertRaises(ValueError) as ctx:
            validate_feature_input(txns)
        self.assertIn("conflicting complaint telemetry", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            extract_account_features(txns)
        self.assertIn("conflicting complaint telemetry", str(ctx.exception))

    def test_complaint_validation_rules(self):
        """Validate complaint fields: ID format, timestamps sequencing, category enum, dict type."""
        base_txn = {
            "txn_id": "T000001",
            "timestamp": "2026-10-01T10:00:00Z",
            "sender_account": "ACC_0001",
            "receiver_account": "ACC_0002",
            "amount_inr": 1000.0,
            "status": "SUCCESS",
        }

        # Non-dict complaint
        bad_type = dict(base_txn, complaint="CMP_0001")
        with self.assertRaises(ValueError):
            validate_feature_input([bad_type])

        # Malformed complaint_id
        bad_cid = dict(base_txn, complaint={"complaint_id": "COMPLAINT_1", "filed_at": "2026-10-01T10:30:00Z"})
        with self.assertRaises(ValueError):
            validate_feature_input([bad_cid])

        # filed_at before txn timestamp
        early_filed = dict(
            base_txn,
            complaint={"complaint_id": "CMP_0001", "filed_at": "2026-10-01T09:00:00Z"},
        )
        with self.assertRaises(ValueError):
            validate_feature_input([early_filed])

        # ingested_at before filed_at
        early_ingested = dict(
            base_txn,
            complaint={
                "complaint_id": "CMP_0001",
                "filed_at": "2026-10-01T10:30:00Z",
                "ingested_at": "2026-10-01T10:20:00Z",
            },
        )
        with self.assertRaises(ValueError):
            validate_feature_input([early_ingested])

        # Invalid category enum
        bad_cat = dict(
            base_txn,
            complaint={
                "complaint_id": "CMP_0001",
                "filed_at": "2026-10-01T10:30:00Z",
                "category": "INVALID_CATEGORY",
            },
        )
        with self.assertRaises(ValueError):
            validate_feature_input([bad_cat])

        # Valid complaint with all categories
        for valid_cat in ["UNAUTHORIZED_TRANSACTION", "PHISHING_SCAM", "NON_DELIVERY_GOODS", "UNSPECIFIED"]:
            ok_txn = dict(
                base_txn,
                complaint={
                    "complaint_id": "CMP_0001",
                    "filed_at": "2026-10-01T10:30:00Z",
                    "ingested_at": "2026-10-01T10:35:00Z",
                    "category": valid_cat,
                },
            )
            validate_feature_input([ok_txn])

    def test_nullable_device_and_complaint_determinism_and_immutability(self):
        """Mixed telemetry must be strictly deterministic and preserve input immutability."""
        txns = [
            {
                "txn_id": "T000001",
                "timestamp": "2026-10-01T10:00:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0002",
                "sender_device_id": None,
                "amount_inr": 1500.0,
                "status": "SUCCESS",
                "complaint": {
                    "complaint_id": "CMP_0001",
                    "filed_at": "2026-10-01T10:15:00Z",
                    "category": "PHISHING_SCAM",
                },
            },
            {
                "txn_id": "T000002",
                "timestamp": "2026-10-01T11:00:00Z",
                "sender_account": "ACC_0002",
                "receiver_account": "ACC_0003",
                "amount_inr": 2500.0,
                "status": "SUCCESS",
                "complaint_filed": True,
            },
            {
                "txn_id": "T000003",
                "timestamp": "2026-10-01T12:00:00Z",
                "sender_account": "ACC_0003",
                "receiver_account": "ACC_0001",
                "sender_device_id": "DEV_0001",
                "amount_inr": 500.0,
                "status": "FAILED",
            },
        ]
        original = copy.deepcopy(txns)

        # Immutability
        res1 = extract_account_features(txns)
        self.assertEqual(txns, original)

        # Determinism
        res2 = extract_account_features(txns)
        self.assertEqual(res1, res2)

        # Feature matrix determinism
        accs1, mat1 = extract_feature_matrix(txns)
        accs2, mat2 = extract_feature_matrix(txns)
        self.assertEqual(accs1, accs2)
        self.assertEqual(mat1, mat2)


if __name__ == "__main__":
    unittest.main()
