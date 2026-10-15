"""TraceUPI Counterfactual Engine Unit Tests.

Validates Contract v1.2 §10:
  - Error rejection: empty interventions, unknown edge IDs, non-transfer edges.
  - Transfer edge removal intervention.
  - Device sharing suppression toggle.
  - Complaint suppression toggle.
  - Signed score delta definition (counterfactual_score - original_score).
  - Hypothesis labeling and causation disclaimer.
  - Sandbox isolation and input immutability.
  - Determinism across repeated executions.
"""

import copy
import json
import unittest

from ml.counterfactual import CounterfactualError, recompute_counterfactual
from ml.pipeline import run_analysis


class TestCounterfactualEngine(unittest.TestCase):
    """Test suite for Counterfactual What-If Sandbox."""

    @classmethod
    def setUpClass(cls):
        # Load sample transactions from regression fixture
        with open("data/transactions.jsonl", "r", encoding="utf-8") as f:
            cls.transactions = [json.loads(line) for line in f]

        # Run analysis to obtain a valid alert with rich evidence
        cls.analysis_result = run_analysis(cls.transactions)
        # Find an alert with transfer edges and rules triggered (e.g. ACC_0101 or ACC_0102)
        cls.test_alert = next(
            (a for a in cls.analysis_result["alerts"] if a["evidence"]["edges"]),
            cls.analysis_result["alerts"][0],
        )

    def test_empty_counterfactual_request_rejection(self):
        """Reject request when all interventions are empty or false (§10.1)."""
        with self.assertRaises(CounterfactualError) as ctx:
            recompute_counterfactual(
                alert=self.test_alert,
                transactions=self.transactions,
                remove_edge_ids=[],
                suppress_device_sharing=False,
                suppress_complaints=False,
            )
        self.assertEqual(ctx.exception.detail, "empty_counterfactual_request")
        self.assertEqual(ctx.exception.to_dict(), {"detail": "empty_counterfactual_request"})

        # Also when remove_edge_ids is None
        with self.assertRaises(CounterfactualError) as ctx2:
            recompute_counterfactual(
                alert=self.test_alert,
                transactions=self.transactions,
                remove_edge_ids=None,
                suppress_device_sharing=False,
                suppress_complaints=False,
            )
        self.assertEqual(ctx2.exception.detail, "empty_counterfactual_request")

    def test_unknown_edge_id_rejection(self):
        """Reject intervention containing unknown edge ID (§10.1)."""
        with self.assertRaises(CounterfactualError) as ctx:
            recompute_counterfactual(
                alert=self.test_alert,
                transactions=self.transactions,
                remove_edge_ids=["E_NON_EXISTENT_9999"],
            )
        self.assertEqual(ctx.exception.detail, "invalid_counterfactual_intervention")
        self.assertEqual(ctx.exception.error, "unknown_or_unsupported_edge_id")
        self.assertEqual(
            ctx.exception.to_dict(),
            {
                "detail": "invalid_counterfactual_intervention",
                "error": "unknown_or_unsupported_edge_id",
            },
        )

    def test_non_transfer_edge_removal_rejection(self):
        """Reject attempt to remove structural non-transfer edges (e.g. merchant_profile, uses_device)."""
        # Find an alert that contains a non-transfer edge
        non_transfer_edge = None
        target_alert = None
        for a in self.analysis_result["alerts"]:
            for e in a["evidence"]["edges"]:
                if e["type"] in ("uses_device", "merchant_profile", "has_complaint"):
                    non_transfer_edge = e
                    target_alert = a
                    break
            if non_transfer_edge:
                break

        if non_transfer_edge is not None and target_alert is not None:
            with self.assertRaises(CounterfactualError) as ctx:
                recompute_counterfactual(
                    alert=target_alert,
                    transactions=self.transactions,
                    remove_edge_ids=[non_transfer_edge["id"]],
                )
            self.assertEqual(ctx.exception.detail, "invalid_counterfactual_intervention")
            self.assertEqual(ctx.exception.error, "unknown_or_unsupported_edge_id")

    def test_remove_transfer_edge_intervention(self):
        """Successfully recompute score and delta when removing valid transfer edge (§10.1)."""
        # Find a transfer edge touching the alert account
        transfer_edge = next(
            (e for e in self.test_alert["evidence"]["edges"] if e["type"] == "transfer"),
            None,
        )
        self.assertIsNotNone(transfer_edge)

        res = recompute_counterfactual(
            alert=self.test_alert,
            transactions=self.transactions,
            remove_edge_ids=[transfer_edge["id"]],
        )

        self.assertEqual(res["alert_id"], self.test_alert["alert_id"])
        self.assertEqual(res["account_id"], self.test_alert["account_id"])
        self.assertEqual(res["original_score"], self.test_alert["ml"]["score"])
        self.assertIsInstance(res["counterfactual_score"], float)
        self.assertIsInstance(res["score_delta"], float)
        # Mathematical equality: delta == counterfactual - original
        self.assertAlmostEqual(
            res["score_delta"],
            round(res["counterfactual_score"] - res["original_score"], 4),
            places=4,
        )
        self.assertTrue(res["plausible_benign_alternative"].startswith("Hypothesis:"))

        # Recomputed graph evidence excludes the removed transfer transaction
        self.assertIn("evidence", res)
        cf_txn_ids = {e.get("txn_id") for e in res["evidence"]["edges"] if e.get("txn_id")}
        self.assertNotIn(transfer_edge["txn_id"], cf_txn_ids)

    def test_suppress_device_sharing_toggle(self):
        """Toggle suppress_device_sharing modifies underlying features and recomputes score."""
        # Find an alert with shared_device_detected == True
        shared_dev_alert = next(
            (a for a in self.analysis_result["alerts"] if a["context_flags"]["shared_device_detected"]),
            None,
        )

        if shared_dev_alert is not None:
            res = recompute_counterfactual(
                alert=shared_dev_alert,
                transactions=self.transactions,
                suppress_device_sharing=True,
            )
            self.assertIn("device sharing", res["plausible_benign_alternative"])
            self.assertAlmostEqual(
                res["score_delta"],
                round(res["counterfactual_score"] - res["original_score"], 4),
                places=4,
            )

    def test_suppress_complaints_toggle(self):
        """Toggle suppress_complaints suppresses counterparty complaints and removes related rules."""
        # Find an alert with complaint rules or complaints
        complaint_alert = next(
            (a for a in self.analysis_result["alerts"] if "HIGH_COMPLAINT_RATE" in a["baseline"]["rules_triggered"]),
            self.test_alert,
        )

        res = recompute_counterfactual(
            alert=complaint_alert,
            transactions=self.transactions,
            suppress_complaints=True,
        )

        if "HIGH_COMPLAINT_RATE" in complaint_alert["baseline"]["rules_triggered"]:
            self.assertIn("HIGH_COMPLAINT_RATE", res["rules_removed"])
        self.assertIn("fraud complaints are suppressed", res["plausible_benign_alternative"])
        self.assertAlmostEqual(
            res["score_delta"],
            round(res["counterfactual_score"] - res["original_score"], 4),
            places=4,
        )

    def test_hypothesis_labeling_and_disclaimer(self):
        """Plausible benign alternative must begin with 'Hypothesis:' and contain disclaimer."""
        transfer_edge = next(
            (e for e in self.test_alert["evidence"]["edges"] if e["type"] == "transfer"),
            None,
        )
        res = recompute_counterfactual(
            alert=self.test_alert,
            transactions=self.transactions,
            remove_edge_ids=[transfer_edge["id"]] if transfer_edge else [],
            suppress_complaints=True,
        )
        hypo = res["plausible_benign_alternative"]
        self.assertTrue(hypo.startswith("Hypothesis:"))
        self.assertIn("does not constitute legal proof", hypo)

    def test_sandbox_isolation_and_input_immutability(self):
        """Counterfactual recomputation never mutates input alert or transaction records."""
        alert_copy = copy.deepcopy(self.test_alert)
        alert_json_before = json.dumps(alert_copy, sort_keys=True)

        txns_copy = copy.deepcopy(self.transactions)
        txns_json_before = json.dumps(txns_copy, sort_keys=True)

        transfer_edge = next(
            (e for e in alert_copy["evidence"]["edges"] if e["type"] == "transfer"),
            None,
        )
        _ = recompute_counterfactual(
            alert=alert_copy,
            transactions=txns_copy,
            remove_edge_ids=[transfer_edge["id"]] if transfer_edge else [],
            suppress_device_sharing=True,
            suppress_complaints=True,
        )

        alert_json_after = json.dumps(alert_copy, sort_keys=True)
        txns_json_after = json.dumps(txns_copy, sort_keys=True)

        self.assertEqual(alert_json_before, alert_json_after)
        self.assertEqual(txns_json_before, txns_json_after)

    def test_counterfactual_determinism(self):
        """Repeated counterfactual executions on identical inputs yield bitwise identical outputs."""
        transfer_edge = next(
            (e for e in self.test_alert["evidence"]["edges"] if e["type"] == "transfer"),
            None,
        )
        res1 = recompute_counterfactual(
            alert=self.test_alert,
            transactions=self.transactions,
            remove_edge_ids=[transfer_edge["id"]] if transfer_edge else [],
            suppress_device_sharing=True,
        )
        res2 = recompute_counterfactual(
            alert=self.test_alert,
            transactions=self.transactions,
            remove_edge_ids=[transfer_edge["id"]] if transfer_edge else [],
            suppress_device_sharing=True,
        )
        self.assertEqual(res1, res2)


if __name__ == "__main__":
    unittest.main()
