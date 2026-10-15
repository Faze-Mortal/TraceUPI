import hashlib
import unittest

from pydantic import ValidationError

from backend.schemas import (
    Alert,
    AlertSummary,
    AlertsResponse,
    CounterfactualResponse,
    Evidence,
    MetricsResponse,
    PipelineRunRequest,
    ReviewQueueState,
    ReviewState,
    TransactionEvent,
)


def _sha256_hex() -> str:
    return hashlib.sha256(b"fixture").hexdigest()


def _alert_core_kwargs() -> dict:
    return {
        "alert_id": "ALT_0001",
        "alert_fingerprint": _sha256_hex(),
        "account_id": "ACC_0917",
        "created_at": "2026-10-15T16:00:00Z",
        "status": "OPEN",
        "priority": "HIGH",
        "ml": {"score": 0.93, "threshold": 0.5, "flagged": True},
        "baseline": {"flagged": True, "rules_triggered": ["HIGH_FAN_IN"]},
        "top_reasons": [
            {
                "feature": "fan_in_count",
                "value": 14.0,
                "typical_value": 2.0,
                "explanation": "Received transfers from 14 distinct counterparties.",
            }
        ],
        "context_flags": {
            "shared_device_detected": False,
            "rapid_pass_through_detected": True,
            "note": "Rapid consolidation detected.",
        },
    }


class TestAlertSummaryExcludesSensitiveFields(unittest.TestCase):
    def test_summary_dump_omits_evidence_and_previous_review(self) -> None:
        summary = AlertSummary(
            **_alert_core_kwargs(),
            review=ReviewQueueState(status="OPEN", is_stale=False),
        )
        dumped = summary.model_dump()
        self.assertNotIn("evidence", dumped)
        self.assertNotIn("previous_review", dumped["review"])

    def test_summary_forbids_previous_review_on_queue_review(self) -> None:
        with self.assertRaises(ValidationError):
            ReviewQueueState(
                status="OPEN",
                previous_review={"status": "CONFIRMED_FRAUD"},  # type: ignore[arg-type]
            )

    def test_full_alert_includes_previous_review_and_evidence(self) -> None:
        alert = Alert(
            **_alert_core_kwargs(),
            review=ReviewState(
                status="OPEN",
                is_stale=True,
                staleness_reason="evidence_or_score_changed",
                previous_review={
                    "status": "CONFIRMED_FRAUD",
                    "analyst_id": "ANALYST_01",
                    "updated_at": "2026-10-15T16:05:00Z",
                    "verdict": "CONFIRMED_MULE_RING",
                    "notes": "Verified layering.",
                },
            ),
            evidence=Evidence(nodes=[], edges=[], evidence_path=[]),
        )
        dumped = alert.model_dump()
        self.assertIn("evidence", dumped)
        self.assertIsNotNone(dumped["review"]["previous_review"])
        self.assertEqual(dumped["evidence"]["evidence_path"], [])

    def test_alerts_response_only_accepts_summaries(self) -> None:
        summary = AlertSummary(
            **_alert_core_kwargs(),
            review=ReviewQueueState(),
        )
        payload = AlertsResponse(alerts=[summary]).model_dump()
        self.assertNotIn("evidence", payload["alerts"][0])
        self.assertNotIn("previous_review", payload["alerts"][0]["review"])

    def test_evidence_caps(self) -> None:
        with self.assertRaises(ValidationError):
            Evidence(nodes=[], edges=[], evidence_path=[f"E{i}" for i in range(11)])


class TestTransactionEvent(unittest.TestCase):
    def _base(self, **overrides: object) -> dict:
        payload: dict = {
            "txn_id": "T000123",
            "timestamp": "2026-10-01T10:15:30Z",
            "sender_account": "ACC_0042",
            "receiver_account": "ACC_0917",
            "amount_inr": 4999.0,
            "status": "SUCCESS",
        }
        payload.update(overrides)
        return payload

    def test_legacy_fixture_record_parses(self) -> None:
        event = TransactionEvent.model_validate(
            {
                "txn_id": "T000001",
                "timestamp": "2026-10-01T08:04:48Z",
                "sender_account": "ACC_0321",
                "receiver_account": "ACC_0304",
                "sender_device_id": "DEV_0321",
                "amount_inr": 236.33,
                "status": "SUCCESS",
                "complaint_filed": False,
                "ground_truth": {"scenario": "normal", "ring_member_accounts": []},
            }
        )
        self.assertIsNone(event.complaint)
        self.assertFalse(event.complaint_filed)

    def test_nullable_device_allowed(self) -> None:
        event = TransactionEvent.model_validate(self._base(sender_device_id=None))
        self.assertIsNone(event.sender_device_id)

    def test_conflicting_complaint_telemetry_rejected(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            TransactionEvent.model_validate(
                self._base(
                    complaint_filed=False,
                    complaint={
                        "complaint_id": "CMP_0012",
                        "filed_at": "2026-10-01T14:30:00Z",
                        "ingested_at": "2026-10-01T14:30:05Z",
                        "category": "UNAUTHORIZED_TRANSACTION",
                    },
                )
            )
        self.assertIn("Conflicting complaint telemetry", str(ctx.exception))

    def test_invalid_complaint_category_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            TransactionEvent.model_validate(
                self._base(
                    complaint={
                        "complaint_id": "CMP_0012",
                        "filed_at": "2026-10-01T14:30:00Z",
                        "category": "NOT_A_REAL_CATEGORY",
                    }
                )
            )

    def test_merchant_category_requires_merchant_id(self) -> None:
        with self.assertRaises(ValidationError):
            TransactionEvent.model_validate(
                self._base(merchant_category="ELECTRONICS")
            )

    def test_same_sender_receiver_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            TransactionEvent.model_validate(
                self._base(receiver_account="ACC_0042")
            )


class TestMetricsAndCounterfactualSchemas(unittest.TestCase):
    def test_metrics_allow_null_precision_and_zero_f1(self) -> None:
        metrics = MetricsResponse.model_validate(
            {
                "generated_at": "2026-10-15T16:00:00Z",
                "budget_k": 20,
                "evaluation": {
                    "evaluated_on": "held_out_accounts",
                    "n_accounts": 18,
                    "n_positive_accounts": 4,
                    "n_shared_device_accounts": 4,
                },
                "ml": {
                    "threshold": 0.5,
                    "precision": 0.0,
                    "recall": 0.0,
                    "f1": 0.0,
                    "true_positives": 0,
                    "false_positives": 2,
                    "false_negatives": 4,
                    "budget_metrics": {
                        "budget_k": 20,
                        "k_effective": 18,
                        "precision_at_k": 0.0,
                        "recall_at_k": 0.0,
                    },
                    "fairness": {
                        "fpr_benign_shared_device": 0.0,
                        "n_shared_device_evaluated": 4,
                    },
                },
                "baseline": {
                    "precision": None,
                    "recall": None,
                    "f1": None,
                    "true_positives": 0,
                    "false_positives": 0,
                    "false_negatives": 4,
                    "budget_metrics": {
                        "budget_k": 20,
                        "k_effective": 18,
                        "precision_at_k": None,
                        "recall_at_k": None,
                    },
                },
                "by_scenario": [],
            }
        )
        self.assertEqual(metrics.ml.f1, 0.0)
        self.assertIsNone(metrics.baseline.f1)

    def test_counterfactual_requires_hypothesis_prefix(self) -> None:
        with self.assertRaises(ValidationError):
            CounterfactualResponse.model_validate(
                {
                    "alert_id": "ALT_0001",
                    "account_id": "ACC_0917",
                    "original_score": 0.93,
                    "counterfactual_score": 0.12,
                    "score_delta": -0.81,
                    "original_flagged": True,
                    "counterfactual_flagged": False,
                    "rules_removed": [],
                    "rules_added": [],
                    "plausible_benign_alternative": "Looks benign.",
                }
            )

    def test_pipeline_run_request_allows_omitted_as_of(self) -> None:
        req = PipelineRunRequest.model_validate({})
        self.assertIsNone(req.as_of)


if __name__ == "__main__":
    unittest.main()
