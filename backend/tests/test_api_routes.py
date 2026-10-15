
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
        response = self.client.get("/api/alerts?budget_k=15")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json(),
            {"detail": "invalid_budget_k"},
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