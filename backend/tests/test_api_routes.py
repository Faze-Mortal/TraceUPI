
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.pipeline_port import PipelineUnavailableError
from backend.schemas import ContextFlags, Evidence
from backend.store import (
    AccountEvidence,
    AnalysisSnapshot,
    IncomingFlaggedAccount,
    InvestigationStore,
)


class TestApiRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _make_alert(self, account_id, score, alert_id):
        evidence = AccountEvidence(
            txn_ids=frozenset(),
            txn_ingested_at={},
            device_to_senders={},
            device_ingested_at={},
            complaints=(),
            complaint_ingested_at={},
        )

        return IncomingFlaggedAccount(
            account_id=account_id,
            created_at="2026-10-15T16:00:00Z",
            priority="HIGH",
            ml_score=score,
            ml_threshold=0.5,
            ml_flagged=score >= 0.5,
            baseline_flagged=True,
            rules_triggered=("HIGH_FAN_IN",),
            account_evidence=evidence,
            alert_id=alert_id,
            top_reasons=(),
            context_flags=ContextFlags(
                shared_device_detected=False,
                rapid_pass_through_detected=False,
            ),
            evidence=Evidence(
                nodes=[],
                edges=[],
                evidence_path=[],
            ),
        )

    def test_health_still_works(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "service": "TraceUPI API",
            },
        )

    def test_alerts_before_analysis_returns_503(self):
        store = InvestigationStore()

        with patch(
            "backend.main.get_investigation_store",
            return_value=store,
        ):
            response = self.client.get("/api/alerts")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "analysis_not_run"},
        )

    def test_alert_detail_before_analysis_returns_503(self):
        store = InvestigationStore()

        with patch(
            "backend.main.get_investigation_store",
            return_value=store,
        ):
            response = self.client.get("/api/alerts/ALT_0001")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "analysis_not_run"},
        )

    def test_invalid_status_filter_returns_422(self):
        response = self.client.get("/api/alerts?status=CLOSED")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json(),
            {"detail": "invalid_filter_param"},
        )

    def test_invalid_budget_returns_422(self):
        for route in ("/api/alerts", "/api/metrics"):
            for val in (15, 0, -1, "abc", "10.5"):
                response = self.client.get(f"{route}?budget_k={val}")
                self.assertEqual(
                    response.status_code,
                    422,
                    msg=f"Expected 422 for {route}?budget_k={val}",
                )
                self.assertEqual(
                    response.json(),
                    {"detail": "invalid_budget_k"},
                    msg=f"Expected invalid_budget_k for {route}?budget_k={val}",
                )

    def test_metrics_before_analysis_returns_503(self):
        store = InvestigationStore()

        with patch(
            "backend.main.get_investigation_store",
            return_value=store,
        ):
            response = self.client.get("/api/metrics")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "analysis_not_run"},
        )

    def test_metrics_unavailable_after_analysis_returns_404(self):
        store = InvestigationStore()
        store.replace_analysis(
            AnalysisSnapshot(
                n_transactions=1,
                as_of=None,
                alerts=(),
                metrics=None,
                metrics_available=False,
            )
        )

        with patch(
            "backend.main.get_investigation_store",
            return_value=store,
        ):
            response = self.client.get("/api/metrics")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {"detail": "metrics_unavailable"},
        )

    def test_metrics_success_with_budget(self):
        store = InvestigationStore()
        mock_metrics = {
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
                "precision": 1.0,
                "recall": 1.0,
                "f1": 1.0,
                "true_positives": 4,
                "false_positives": 0,
                "false_negatives": 0,
                "budget_metrics": {
                    "budget_k": 20,
                    "k_effective": 18,
                    "precision_at_k": 0.2222,
                    "recall_at_k": 1.0,
                },
                "fairness": {
                    "fpr_benign_shared_device": 0.0,
                    "n_shared_device_evaluated": 4,
                },
            },
            "baseline": {
                "precision": 0.0,
                "recall": 0.0,
                "f1": 0.0,
                "true_positives": 0,
                "false_positives": 2,
                "false_negatives": 4,
                "budget_metrics": {
                    "budget_k": 20,
                    "k_effective": 18,
                    "precision_at_k": 0.2222,
                    "recall_at_k": 1.0,
                },
            },
            "by_scenario": [
                {
                    "scenario": "mule_ring",
                    "n_accounts": 4,
                    "ml_flagged": 4,
                    "baseline_flagged": 0,
                }
            ],
            "_budget_metrics_by_k": {
                10: {
                    "ml": {
                        "budget_k": 10,
                        "k_effective": 10,
                        "precision_at_k": 0.4,
                        "recall_at_k": 1.0,
                    },
                    "baseline": {
                        "budget_k": 10,
                        "k_effective": 10,
                        "precision_at_k": 0.2,
                        "recall_at_k": 0.5,
                    },
                },
                20: {
                    "ml": {
                        "budget_k": 20,
                        "k_effective": 18,
                        "precision_at_k": 0.2222,
                        "recall_at_k": 1.0,
                    },
                    "baseline": {
                        "budget_k": 20,
                        "k_effective": 18,
                        "precision_at_k": 0.2222,
                        "recall_at_k": 1.0,
                    },
                },
            },
        }
        store.replace_analysis(
            AnalysisSnapshot(
                n_transactions=10,
                as_of=None,
                alerts=(),
                metrics=mock_metrics,
                metrics_available=True,
            )
        )

        with patch(
            "backend.main.get_investigation_store",
            return_value=store,
        ):
            # 1. Default budget K=20
            resp20 = self.client.get("/api/metrics")
            self.assertEqual(resp20.status_code, 200)
            data20 = resp20.json()
            self.assertEqual(data20["budget_k"], 20)
            self.assertEqual(data20["ml"]["budget_metrics"]["budget_k"], 20)

            # 2. Parameterized budget K=10
            resp10 = self.client.get("/api/metrics?budget_k=10")
            self.assertEqual(resp10.status_code, 200)
            data10 = resp10.json()
            self.assertEqual(data10["budget_k"], 10)
            self.assertEqual(data10["ml"]["budget_metrics"]["budget_k"], 10)
            self.assertEqual(data10["ml"]["budget_metrics"]["k_effective"], 10)
            self.assertEqual(data10["ml"]["budget_metrics"]["precision_at_k"], 0.4)


    def test_pipeline_fails_closed_when_model_missing(self):
        with patch(
            "backend.main.load_analysis_pipeline",
            side_effect=PipelineUnavailableError("pipeline unavailable"),
        ):
            response = self.client.post(
                "/api/pipeline/run",
                json={},
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            {"detail": "model_unavailable"},
        )

    def test_alert_list_returns_empty_list_after_empty_analysis(self):
        store = InvestigationStore()
        store.replace_analysis(
            AnalysisSnapshot(
                n_transactions=0,
                as_of=None,
                alerts=(),
                metrics=None,
                metrics_available=False,
            )
        )

        with patch(
            "backend.main.get_investigation_store",
            return_value=store,
        ):
            response = self.client.get("/api/alerts")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"alerts": []})

    def test_alerts_sorted_by_score_then_account_id(self):
        store = InvestigationStore()
        store.replace_analysis(
            AnalysisSnapshot(
                n_transactions=3,
                as_of=None,
                alerts=(
                    self._make_alert("ACC_0002", 0.9, "ALT_0002"),
                    self._make_alert("ACC_0003", 0.7, "ALT_0003"),
                    self._make_alert("ACC_0001", 0.9, "ALT_0001"),
                ),
            )
        )

        with patch(
            "backend.main.get_investigation_store",
            return_value=store,
        ):
            response = self.client.get("/api/alerts")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [
                alert["account_id"]
                for alert in response.json()["alerts"]
            ],
            ["ACC_0001", "ACC_0002", "ACC_0003"],
        )

    def test_alert_budget_limits_results(self):
        store = InvestigationStore()

        alerts = tuple(
            self._make_alert(
                f"ACC_{i:04d}",
                0.99 - i * 0.01,
                f"ALT_{i:04d}",
            )
            for i in range(1, 13)
        )

        store.replace_analysis(
            AnalysisSnapshot(
                n_transactions=12,
                as_of=None,
                alerts=alerts,
            )
        )

        with patch(
            "backend.main.get_investigation_store",
            return_value=store,
        ):
            response = self.client.get("/api/alerts?budget_k=10")

        self.assertEqual(response.status_code, 200)

        results = response.json()["alerts"]
        self.assertEqual(len(results), 10)

        self.assertEqual(
            [alert["account_id"] for alert in results],
            [f"ACC_{i:04d}" for i in range(1, 11)],
        )

    def test_alert_status_filter(self):
        store = InvestigationStore()
        store.replace_analysis(
            AnalysisSnapshot(
                n_transactions=2,
                as_of=None,
                alerts=(
                    self._make_alert("ACC_0001", 0.9, "ALT_0001"),
                    self._make_alert("ACC_0002", 0.8, "ALT_0002"),
                ),
            )
        )

        store.apply_review(
            "ALT_0001",
            status="INVESTIGATING",
            analyst_id="ANALYST_01",
        )

        with patch(
            "backend.main.get_investigation_store",
            return_value=store,
        ):
            response = self.client.get(
                "/api/alerts?status=INVESTIGATING"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [
                alert["account_id"]
                for alert in response.json()["alerts"]
            ],
            ["ACC_0001"],
        )


if __name__ == "__main__":
    unittest.main()