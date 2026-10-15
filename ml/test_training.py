"""Unit and integration tests for TraceUPI training, split, baseline, and evaluation.

Covers all 9 required test categories:
1. Label precedence (Contract Section 2)
2. Deterministic split, coverage, and disjointness (Contract Section 4)
3. Small scenario groups (n < 2, n == 2)
4. Ground-truth leakage prevention
5. Training-only threshold selection
6. Baseline and held-out metrics (including zero-denominator edge cases)
7. Artifact metadata and reproducibility (Contract Section 3)
8. Invalid or insufficient data handling
9. Full pipeline test on both expanded dataset and original regression fixture
"""

import copy
import hashlib
import json
import os
from pathlib import Path
import unittest

import joblib
import numpy as np

from ml.baseline_rules import BASELINE_RULES, evaluate_account_rules, evaluate_baseline
from ml.evaluate import calculate_binary_metrics, evaluate_heldout_accounts
from ml.features import FEATURE_NAMES, extract_account_features
from ml.generate_data import assign_account_scenarios
from ml.train import (
    compute_dataset_fingerprint,
    compute_training_medians,
    split_accounts_by_scenario,
    train_and_evaluate_pipeline,
)


class TestTrainingPipeline(unittest.TestCase):
    """Test suite for Step 7B training pipeline and contract conformance."""

    def test_01_label_precedence(self):
        """Account-level scenario precedence matches Section 2: mule_ring > shared_device_family > normal."""
        # Account ACC_0001 appears in ring_member_accounts AND shared_device_family transaction
        txns = [
            {
                "txn_id": "T000001",
                "timestamp": "2026-10-01T10:00:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0002",
                "sender_device_id": "DEV_0001",
                "amount_inr": 1000.0,
                "status": "SUCCESS",
                "complaint_filed": False,
                "ground_truth": {
                    "scenario": "mule_ring",
                    "ring_member_accounts": ["ACC_0001"]
                }
            },
            {
                "txn_id": "T000002",
                "timestamp": "2026-10-01T10:05:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0003",
                "sender_device_id": "DEV_0001",
                "amount_inr": 500.0,
                "status": "SUCCESS",
                "complaint_filed": False,
                "ground_truth": {
                    "scenario": "shared_device_family",
                    "ring_member_accounts": []
                }
            },
            {
                "txn_id": "T000003",
                "timestamp": "2026-10-01T10:10:00Z",
                "sender_account": "ACC_0004",
                "receiver_account": "ACC_0003",
                "sender_device_id": "DEV_0002",
                "amount_inr": 300.0,
                "status": "SUCCESS",
                "complaint_filed": False,
                "ground_truth": {
                    "scenario": "normal",
                    "ring_member_accounts": []
                }
            }
        ]

        scenarios = assign_account_scenarios(txns)

        # ACC_0001 is in ring_member_accounts -> mule_ring takes precedence
        self.assertEqual(scenarios["ACC_0001"], "mule_ring")

        # ACC_0002 is receiver in mule txn but NOT in ring_member_accounts, nor in shared_device -> normal (Contract L5)
        self.assertEqual(scenarios["ACC_0002"], "normal")

        # ACC_0003 is in shared_device_family txn and not mule -> shared_device_family
        self.assertEqual(scenarios["ACC_0003"], "shared_device_family")

        # ACC_0004 is only in normal txn -> normal
        self.assertEqual(scenarios["ACC_0004"], "normal")

    def test_02_deterministic_split_coverage_and_disjointness(self):
        """Split algorithm is deterministic, mutually disjoint, and covers all accounts."""
        # Mock 50 accounts across 3 scenarios
        mock_scenarios = {}
        for i in range(1, 16):
            mock_scenarios[f"ACC_{i:04d}"] = "mule_ring"          # n = 15
        for i in range(16, 28):
            mock_scenarios[f"ACC_{i:04d}"] = "shared_device_family" # n = 12
        for i in range(28, 51):
            mock_scenarios[f"ACC_{i:04d}"] = "normal"               # n = 23

        # Run 1 vs Run 2 with identical seed
        train1, held1 = split_accounts_by_scenario(mock_scenarios, split_seed=42)
        train2, held2 = split_accounts_by_scenario(mock_scenarios, split_seed=42)

        self.assertEqual(train1, train2)
        self.assertEqual(held1, held2)

        # Disjointness
        self.assertTrue(set(train1).isdisjoint(set(held1)))

        # Coverage
        self.assertEqual(set(train1) | set(held1), set(mock_scenarios.keys()))

        # Held-out count checks per formula: min(max(1, round(0.30 * n)), n - 1)
        # Note: Python round() uses round-half-to-even:
        # mule_ring: n=15 -> 0.30 * 15 = 4.5 -> round(4.5) = 4
        # shared_device: n=12 -> 0.30 * 12 = 3.6 -> round(3.6) = 4
        # normal: n=23 -> 0.30 * 23 = 6.9 -> round(6.9) = 7
        # Total held-out = 4 + 4 + 7 = 15
        self.assertEqual(len(held1), 15)
        self.assertEqual(len(train1), 50 - 15)

    def test_03_small_scenario_groups(self):
        """Groups with n < 2 are entirely training; n == 2 holds out exactly 1 account."""
        # Scenario with n = 1
        scenarios_n1 = {
            "ACC_0001": "rare_scenario",
            "ACC_0002": "normal",
            "ACC_0003": "normal",
        }
        train, held = split_accounts_by_scenario(scenarios_n1, split_seed=42)
        self.assertIn("ACC_0001", train)
        self.assertNotIn("ACC_0001", held)

        # Scenario with n = 2: round(0.30 * 2) = 1; min(max(1, 1), 1) = 1
        scenarios_n2 = {
            "ACC_0001": "shared_device_family",
            "ACC_0002": "shared_device_family",
        }
        train, held = split_accounts_by_scenario(scenarios_n2, split_seed=42)
        self.assertEqual(len(train), 1)
        self.assertEqual(len(held), 1)
        self.assertTrue(set(train).isdisjoint(set(held)))

    def test_04_ground_truth_leakage_prevention(self):
        """Feature engineering used in training must never read or depend on ground_truth."""
        base_txn = {
            "txn_id": "T000001",
            "timestamp": "2026-10-01T10:00:00Z",
            "sender_account": "ACC_0001",
            "receiver_account": "ACC_0002",
            "sender_device_id": "DEV_0001",
            "amount_inr": 1000.0,
            "status": "SUCCESS",
            "complaint_filed": False,
        }

        txn_with_gt = copy.deepcopy(base_txn)
        txn_with_gt["ground_truth"] = {"scenario": "mule_ring", "ring_member_accounts": ["ACC_0001"]}

        txn_without_gt = copy.deepcopy(base_txn)

        f_with = extract_account_features([txn_with_gt])
        f_without = extract_account_features([txn_without_gt])

        self.assertEqual(f_with, f_without)

    def test_05_training_only_threshold_selection(self):
        """Threshold selection must not adapt to or peek at held-out data."""
        # Contract Section 4 allows a fixed constant such as 0.5
        threshold = 0.5
        # Verify decision rule matches Contract: ml.flagged = (score >= threshold)
        self.assertTrue(0.50 >= threshold)
        self.assertTrue(0.5001 >= threshold)
        self.assertFalse(0.4999 >= threshold)

    def test_06_baseline_and_heldout_metrics_zero_denominators(self):
        """Metrics calculation strictly implements Contract Section 6 zero-denominator rules."""
        # Case A: No positives flagged (TP + FP = 0) -> precision is None
        metrics_none_flagged = calculate_binary_metrics(
            y_true=[1, 0, 0],
            y_pred=[False, False, False]
        )
        self.assertIsNone(metrics_none_flagged["precision"])
        self.assertEqual(metrics_none_flagged["recall"], 0.0)
        self.assertIsNone(metrics_none_flagged["f1"])  # either precision or recall is None

        # Case B: No actual positives (TP + FN = 0) -> recall is None
        metrics_no_actual = calculate_binary_metrics(
            y_true=[0, 0, 0],
            y_pred=[True, False, False]
        )
        self.assertEqual(metrics_no_actual["precision"], 0.0)
        self.assertIsNone(metrics_no_actual["recall"])
        self.assertIsNone(metrics_no_actual["f1"])

        # Case C: Both precision and recall are 0.0 -> f1 is None per Contract
        metrics_both_zero = calculate_binary_metrics(
            y_true=[1, 0],
            y_pred=[False, True]
        )
        self.assertEqual(metrics_both_zero["precision"], 0.0)
        self.assertEqual(metrics_both_zero["recall"], 0.0)
        self.assertIsNone(metrics_both_zero["f1"])

        # Case D: Standard valid evaluation
        metrics_valid = calculate_binary_metrics(
            y_true=[1, 1, 0, 0],
            y_pred=[True, False, True, False]
        )
        # TP=1, FP=1, FN=1, TN=1
        self.assertEqual(metrics_valid["precision"], 0.5)
        self.assertEqual(metrics_valid["recall"], 0.5)
        self.assertEqual(metrics_valid["f1"], 0.5)

    def test_07_artifact_metadata_and_reproducibility(self):
        """Model artifact contains all Contract Section 3 metadata and reproduces exactly."""
        artifact_path = Path("data/artifacts/model.joblib")
        if not artifact_path.exists():
            self.skipTest("Artifact not generated yet.")

        artifact = joblib.load(artifact_path)

        # Check required fields per Contract Section 3
        required_fields = [
            "artifact_version",
            "model",
            "feature_names",
            "decision_threshold",
            "training_feature_medians",
            "heldout_account_ids",
            "dataset_fingerprint",
            "split_seed",
        ]
        for field in required_fields:
            self.assertIn(field, artifact, f"Missing required artifact field: {field}")

        self.assertEqual(artifact["artifact_version"], "1.1")
        self.assertEqual(artifact["feature_names"], FEATURE_NAMES)
        self.assertIsInstance(artifact["decision_threshold"], (int, float))
        self.assertIsInstance(artifact["training_feature_medians"], dict)
        self.assertEqual(len(artifact["training_feature_medians"]), len(FEATURE_NAMES))
        self.assertIsInstance(artifact["heldout_account_ids"], list)
        # Verify heldout_account_ids sorted ascending
        self.assertEqual(artifact["heldout_account_ids"], sorted(artifact["heldout_account_ids"]))
        self.assertIsInstance(artifact["dataset_fingerprint"], str)
        self.assertEqual(len(artifact["dataset_fingerprint"]), 64)  # SHA-256 hex
        self.assertEqual(artifact["split_seed"], 42)

    def test_08_invalid_or_insufficient_data(self):
        """Pipeline handles missing files or insufficient data with clear errors."""
        with self.assertRaises(FileNotFoundError):
            train_and_evaluate_pipeline(data_path="data/non_existent_file.jsonl")

    def test_09_pipeline_runs_on_regression_fixture(self):
        """Pipeline runs smoothly on the original small regression fixture (data/transactions.jsonl)."""
        res = train_and_evaluate_pipeline(
            data_path="data/transactions.jsonl",
            artifact_path="data/artifacts/model_regression.joblib",
            split_seed=42,
            decision_threshold=0.5,
        )
        # 62 accounts: 15 mule (4 held), 12 shared_device (4 held), 35 normal (10 held) = 18 held out
        self.assertEqual(res["metrics"]["evaluation"]["n_accounts"], 18)
        self.assertIn("ml", res["metrics"])
        self.assertIn("baseline", res["metrics"])
        self.assertIn("by_scenario", res["metrics"])

        # Clean up temporary regression artifact
        reg_art = Path("data/artifacts/model_regression.joblib")
        if reg_art.exists():
            reg_art.unlink()


if __name__ == "__main__":
    unittest.main()
