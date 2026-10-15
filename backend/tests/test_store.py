import unittest

from backend.errors import AlertNotFoundError, AnalysisNotRunError
from backend.review_transitions import InvalidReviewTransition
from backend.schemas import ContextFlags, Evidence, TopReason
from backend.store import (
    AccountEvidence,
    AnalysisSnapshot,
    IncomingFlaggedAccount,
    InvestigationStore,
    get_investigation_store,
)


def _txns(*pairs: tuple[str, str]) -> AccountEvidence:
    txn_ids = frozenset(txn_id for txn_id, _ingested in pairs)
    ingested = {txn_id: ingested_at for txn_id, ingested_at in pairs}
    return AccountEvidence(
        txn_ids=txn_ids,
        txn_ingested_at=ingested,
        device_to_senders={},
        device_ingested_at={},
        complaints=(),
        complaint_ingested_at={},
    )


def _incoming(
    *,
    account_id: str,
    created_at: str = "2026-10-15T16:00:00Z",
    priority: str = "HIGH",
    ml_score: float = 0.93,
    ml_threshold: float = 0.5,
    rules: tuple[str, ...] = ("HIGH_FAN_IN",),
    evidence: AccountEvidence | None = None,
    alert_id: str | None = None,
    devices: dict[str, frozenset[str]] | None = None,
    device_ingested_at: dict[str, str] | None = None,
    complaints: tuple[tuple[str, str, str], ...] = (),
    complaint_ingested_at: dict[str, str] | None = None,
) -> IncomingFlaggedAccount:
    base = evidence or _txns(("T000123", "2026-10-01T10:15:30Z"))
    if devices is not None or complaints:
        base = AccountEvidence(
            txn_ids=base.txn_ids,
            txn_ingested_at=base.txn_ingested_at,
            device_to_senders=devices or base.device_to_senders,
            device_ingested_at=device_ingested_at or dict(base.device_ingested_at),
            complaints=complaints or base.complaints,
            complaint_ingested_at=complaint_ingested_at or dict(base.complaint_ingested_at),
        )
    return IncomingFlaggedAccount(
        account_id=account_id,
        created_at=created_at,
        priority=priority,
        ml_score=ml_score,
        ml_threshold=ml_threshold,
        ml_flagged=True,
        baseline_flagged=True,
        rules_triggered=rules,
        account_evidence=base,
        alert_id=alert_id,
        top_reasons=(
            TopReason(
                feature="fan_in_count",
                value=14.0,
                typical_value=2.0,
                explanation="fixture explanation",
            ),
        ),
        context_flags=ContextFlags(
            shared_device_detected=False,
            rapid_pass_through_detected=True,
            note="fixture note",
        ),
        evidence=Evidence(nodes=[], edges=[], evidence_path=[]),
    )


def _snapshot(
    *alerts: IncomingFlaggedAccount,
    as_of: str | None = None,
    n_transactions: int = 2,
) -> AnalysisSnapshot:
    return AnalysisSnapshot(
        n_transactions=n_transactions,
        as_of=as_of,
        alerts=alerts,
        metrics=None,
        metrics_available=False,
    )


class TestInvestigationStore(unittest.TestCase):
    def setUp(self) -> None:
        self.clock_value = "2026-10-15T16:05:00Z"

        def clock() -> str:
            return self.clock_value

        self.store = InvestigationStore(clock=clock)

    def test_analysis_not_run(self) -> None:
        with self.assertRaises(AnalysisNotRunError) as ctx:
            self.store.list_active_alerts()
        self.assertEqual(ctx.exception.detail, "analysis_not_run")

    def test_new_alert_initializes_open_not_stale(self) -> None:
        self.store.replace_analysis(_snapshot(_incoming(account_id="ACC_0001", alert_id="ALT_0001")))
        alert = self.store.get_active_alert_for_account("ACC_0001")
        self.assertEqual(alert.alert_id, "ALT_0001")
        self.assertEqual(alert.status, "OPEN")
        self.assertEqual(alert.review.status, "OPEN")
        self.assertFalse(alert.review.is_stale)
        self.assertIsNone(alert.review.staleness_reason)
        self.assertIsNone(alert.review.analyst_id)
        self.assertIsNone(alert.review.previous_review)
        events = self.store.review_history("ACC_0001")
        self.assertEqual(events[0].event, "initialized")

    def test_valid_and_invalid_review_transitions(self) -> None:
        self.store.replace_analysis(_snapshot(_incoming(account_id="ACC_0001", alert_id="ALT_0001")))
        updated = self.store.apply_review(
            "ALT_0001",
            status="CONFIRMED_FRAUD",
            analyst_id="ANALYST_01",
            verdict="CONFIRMED_MULE_RING",
            notes="Verified layering.",
        )
        self.assertEqual(updated.status, "CONFIRMED_FRAUD")
        self.assertEqual(updated.review.analyst_id, "ANALYST_01")
        self.assertEqual(updated.review.notes, "Verified layering.")
        self.assertEqual(updated.review.updated_at, "2026-10-15T16:05:00Z")

        with self.assertRaises(InvalidReviewTransition) as ctx:
            self.store.apply_review(
                "ALT_0001",
                status="DISMISSED_BENIGN",
                analyst_id="ANALYST_01",
            )
        self.assertEqual(ctx.exception.detail, "invalid_review_transition")
        still = self.store.get_alert("ALT_0001")
        self.assertEqual(still.review.status, "CONFIRMED_FRAUD")
        self.assertEqual(still.review.notes, "Verified layering.")

        reopened = self.store.apply_review(
            "ALT_0001",
            status="INVESTIGATING",
            analyst_id="ANALYST_01",
            notes="Reopened.",
        )
        self.assertEqual(reopened.status, "INVESTIGATING")

    def test_fingerprint_match_preserves_review(self) -> None:
        first = _incoming(account_id="ACC_0001", alert_id="ALT_0001")
        self.store.replace_analysis(_snapshot(first))
        self.store.apply_review(
            "ALT_0001",
            status="DISMISSED_BENIGN",
            analyst_id="ANALYST_01",
            verdict="BENIGN_FAMILY",
            notes="Household device.",
        )
        self.store.replace_analysis(_snapshot(first, as_of="2026-10-01T23:00:00Z"))
        alert = self.store.get_alert("ALT_0001")
        self.assertEqual(alert.review.status, "DISMISSED_BENIGN")
        self.assertEqual(alert.review.analyst_id, "ANALYST_01")
        self.assertEqual(alert.review.verdict, "BENIGN_FAMILY")
        self.assertEqual(alert.review.notes, "Household device.")
        self.assertFalse(alert.review.is_stale)
        self.assertIsNone(alert.review.staleness_reason)
        self.assertEqual(self.store.as_of(), "2026-10-01T23:00:00Z")

    def test_fingerprint_divergence_marks_stale_open(self) -> None:
        self.store.replace_analysis(
            _snapshot(
                _incoming(
                    account_id="ACC_0001",
                    alert_id="ALT_0001",
                    evidence=_txns(("T000010", "2026-10-01T10:00:00Z")),
                )
            )
        )
        self.store.apply_review(
            "ALT_0001",
            status="CONFIRMED_FRAUD",
            analyst_id="ANALYST_01",
            notes="Ring confirmed.",
        )
        self.store.replace_analysis(
            _snapshot(
                _incoming(
                    account_id="ACC_0001",
                    alert_id="ALT_0001",
                    evidence=_txns(
                        ("T000010", "2026-10-01T10:00:00Z"),
                        ("T000020", "2026-10-01T16:00:00Z"),
                    ),
                    ml_score=0.99,
                )
            )
        )
        alert = self.store.get_alert("ALT_0001")
        self.assertEqual(alert.status, "OPEN")
        self.assertTrue(alert.review.is_stale)
        self.assertEqual(alert.review.staleness_reason, "evidence_or_score_changed")
        self.assertIsNone(alert.review.analyst_id)
        self.assertIsNone(alert.review.notes)
        self.assertIsNotNone(alert.review.previous_review)
        assert alert.review.previous_review is not None
        self.assertEqual(alert.review.previous_review.status, "CONFIRMED_FRAUD")
        self.assertEqual(alert.review.previous_review.notes, "Ring confirmed.")
        self.assertEqual(alert.review.previous_review.analyst_id, "ANALYST_01")
        self.assertIn("previous_review", alert.model_dump()["review"])
        summary = self.store.to_summary(alert)
        self.assertNotIn("previous_review", summary.model_dump()["review"])
        self.assertNotIn("evidence", summary.model_dump())

    def test_replay_a_b_a_restores_exact_review(self) -> None:
        snapshot_a = _snapshot(
            _incoming(
                account_id="ACC_0001",
                alert_id="ALT_0001",
                evidence=_txns(
                    ("T000010", "2026-10-01T10:00:00Z"),
                    ("T000014", "2026-10-01T14:00:00Z"),
                ),
                ml_score=0.91,
            )
        )
        snapshot_b = _snapshot(
            _incoming(
                account_id="ACC_0001",
                alert_id="ALT_0001",
                evidence=_txns(("T000010", "2026-10-01T10:00:00Z")),
                ml_score=0.40,
            ),
            as_of="2026-10-01T12:00:00Z",
        )
        self.store.replace_analysis(snapshot_a)
        self.store.apply_review(
            "ALT_0001",
            status="CONFIRMED_FRAUD",
            analyst_id="ANALYST_01",
            verdict="CONFIRMED_MULE_RING",
            notes="Keep these notes.",
        )
        fingerprint_a = self.store.get_alert("ALT_0001").alert_fingerprint
        self.store.replace_analysis(snapshot_b)
        stale = self.store.get_alert("ALT_0001")
        self.assertEqual(stale.status, "OPEN")
        self.assertTrue(stale.review.is_stale)
        self.assertNotEqual(stale.alert_fingerprint, fingerprint_a)
        self.store.replace_analysis(snapshot_a)
        restored = self.store.get_alert("ALT_0001")
        self.assertEqual(restored.alert_fingerprint, fingerprint_a)
        self.assertEqual(restored.status, "CONFIRMED_FRAUD")
        self.assertEqual(restored.review.status, "CONFIRMED_FRAUD")
        self.assertEqual(restored.review.analyst_id, "ANALYST_01")
        self.assertEqual(restored.review.verdict, "CONFIRMED_MULE_RING")
        self.assertEqual(restored.review.notes, "Keep these notes.")
        self.assertFalse(restored.review.is_stale)
        self.assertIsNone(restored.review.staleness_reason)
        events = [event.event for event in self.store.review_history("ACC_0001")]
        self.assertIn("diverged", events)
        self.assertIn("restored", events)

    def test_disappeared_alerts_are_archived(self) -> None:
        self.store.replace_analysis(
            _snapshot(
                _incoming(account_id="ACC_0001", alert_id="ALT_0001"),
                _incoming(
                    account_id="ACC_0002",
                    alert_id="ALT_0002",
                    evidence=_txns(("T000222", "2026-10-01T11:00:00Z")),
                    ml_score=0.2,
                    priority="LOW",
                    rules=(),
                ),
            )
        )
        self.store.apply_review(
            "ALT_0001",
            status="INVESTIGATING",
            analyst_id="ANALYST_01",
            notes="Still looking.",
        )
        self.store.replace_analysis(
            _snapshot(
                _incoming(
                    account_id="ACC_0002",
                    alert_id="ALT_0002",
                    evidence=_txns(("T000222", "2026-10-01T11:00:00Z")),
                    ml_score=0.2,
                    priority="LOW",
                    rules=(),
                )
            )
        )
        archived = self.store.list_archived_alerts()
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0].account_id, "ACC_0001")
        self.assertEqual(archived[0].review.status, "INVESTIGATING")
        self.assertEqual(archived[0].review.notes, "Still looking.")
        active_ids = {alert.account_id for alert in self.store.list_active_alerts()}
        self.assertEqual(active_ids, {"ACC_0002"})
        with self.assertRaises(AlertNotFoundError) as ctx:
            self.store.get_alert("ALT_0001")
        self.assertEqual(ctx.exception.detail, "alert_not_found")

    def test_historical_divergence_versus_score_change(self) -> None:
        snapshot_full = _snapshot(
            _incoming(
                account_id="ACC_0001",
                alert_id="ALT_0001",
                evidence=_txns(
                    ("T000010", "2026-10-01T10:00:00Z"),
                    ("T000014", "2026-10-01T14:00:00Z"),
                ),
            )
        )
        self.store.replace_analysis(snapshot_full)
        self.store.apply_review(
            "ALT_0001",
            status="CONFIRMED_FRAUD",
            analyst_id="ANALYST_01",
            notes="Based on 10:00 and 14:00.",
        )
        self.store.replace_analysis(
            _snapshot(
                _incoming(
                    account_id="ACC_0001",
                    alert_id="ALT_0001",
                    evidence=_txns(("T000010", "2026-10-01T10:00:00Z")),
                    ml_score=0.4,
                ),
                as_of="2026-10-01T12:00:00Z",
            )
        )
        cutoff_alert = self.store.get_alert("ALT_0001")
        self.assertEqual(
            cutoff_alert.review.staleness_reason,
            "historical_snapshot_evidence_divergence",
        )

        store2 = InvestigationStore(clock=lambda: "2026-10-15T16:05:00Z")
        store2.replace_analysis(snapshot_full)
        store2.apply_review(
            "ALT_0001",
            status="CONFIRMED_FRAUD",
            analyst_id="ANALYST_01",
            notes="Based on 10:00 and 14:00.",
        )
        store2.replace_analysis(
            _snapshot(
                _incoming(
                    account_id="ACC_0001",
                    alert_id="ALT_0001",
                    evidence=_txns(
                        ("T000010", "2026-10-01T10:00:00Z"),
                        ("T000014", "2026-10-01T14:00:00Z"),
                    ),
                    ml_score=0.11,
                ),
                as_of="2026-10-01T18:00:00Z",
            )
        )
        rescore = store2.get_alert("ALT_0001")
        self.assertTrue(rescore.review.is_stale)
        self.assertEqual(rescore.review.staleness_reason, "evidence_or_score_changed")

    def test_unrelated_late_events_do_not_count_as_historical_divergence(self) -> None:
        self.store.replace_analysis(
            _snapshot(
                _incoming(account_id="ACC_0001", alert_id="ALT_0001"),
                _incoming(
                    account_id="ACC_0002",
                    alert_id="ALT_0002",
                    evidence=_txns(("T000200", "2026-10-01T09:00:00Z")),
                    ml_score=0.2,
                    priority="LOW",
                    rules=(),
                ),
            )
        )
        self.store.apply_review(
            "ALT_0001",
            status="CONFIRMED_FRAUD",
            analyst_id="ANALYST_01",
            notes="ACC_0001 only.",
        )
        self.store.replace_analysis(
            _snapshot(
                _incoming(account_id="ACC_0001", alert_id="ALT_0001", ml_score=0.50),
                _incoming(
                    account_id="ACC_0002",
                    alert_id="ALT_0002",
                    evidence=_txns(
                        ("T000200", "2026-10-01T09:00:00Z"),
                        ("T000299", "2026-10-01T20:00:00Z"),
                    ),
                    ml_score=0.2,
                    priority="LOW",
                    rules=(),
                ),
                as_of="2026-10-01T12:00:00Z",
            )
        )
        one = self.store.get_alert("ALT_0001")
        self.assertTrue(one.review.is_stale)
        self.assertEqual(one.review.staleness_reason, "evidence_or_score_changed")
        self.assertEqual(one.review.previous_review.notes, "ACC_0001 only.")
        two = self.store.get_alert("ALT_0002")
        self.assertNotEqual(two.review.staleness_reason, "historical_snapshot_evidence_divergence")

    def test_account_isolation(self) -> None:
        self.store.replace_analysis(
            _snapshot(
                _incoming(account_id="ACC_0001", alert_id="ALT_0001"),
                _incoming(
                    account_id="ACC_0002",
                    alert_id="ALT_0002",
                    evidence=_txns(("T000222", "2026-10-01T11:00:00Z")),
                    ml_score=0.22,
                    complaints=(
                        ("CMP_0002", "PHISHING_SCAM", "2026-10-01T12:00:00Z"),
                    ),
                    complaint_ingested_at={"CMP_0002": "2026-10-01T12:00:05Z"},
                ),
            )
        )
        fp_before = self.store.get_alert("ALT_0001").alert_fingerprint
        self.store.apply_review(
            "ALT_0001",
            status="CONFIRMED_FRAUD",
            analyst_id="ANALYST_01",
            notes="Do not leak.",
        )
        self.store.replace_analysis(
            _snapshot(
                _incoming(account_id="ACC_0001", alert_id="ALT_0001"),
                _incoming(
                    account_id="ACC_0002",
                    alert_id="ALT_0002",
                    evidence=_txns(("T000222", "2026-10-01T11:00:00Z")),
                    ml_score=0.88,
                    complaints=(
                        ("CMP_0002", "PHISHING_SCAM", "2026-10-01T12:00:00Z"),
                        ("CMP_0009", "UNSPECIFIED", "2026-10-01T13:00:00Z"),
                    ),
                    complaint_ingested_at={
                        "CMP_0002": "2026-10-01T12:00:05Z",
                        "CMP_0009": "2026-10-01T13:00:05Z",
                    },
                ),
            )
        )
        one = self.store.get_alert("ALT_0001")
        self.assertEqual(one.alert_fingerprint, fp_before)
        self.assertEqual(one.review.status, "CONFIRMED_FRAUD")
        self.assertEqual(one.review.notes, "Do not leak.")
        self.assertFalse(one.review.is_stale)
        two = self.store.get_alert("ALT_0002")
        self.assertTrue(two.review.is_stale)
        self.assertEqual(two.review.staleness_reason, "evidence_or_score_changed")
        self.assertIsNone(two.review.notes)

    def test_in_memory_across_calls_not_across_new_store(self) -> None:
        self.store.replace_analysis(_snapshot(_incoming(account_id="ACC_0001", alert_id="ALT_0001")))
        self.store.apply_review(
            "ALT_0001",
            status="INVESTIGATING",
            analyst_id="ANALYST_01",
            notes="Persists on this instance.",
        )
        self.assertEqual(self.store.get_alert("ALT_0001").review.notes, "Persists on this instance.")
        restarted = InvestigationStore()
        with self.assertRaises(AnalysisNotRunError):
            restarted.get_alert("ALT_0001")

    def test_process_store_is_shared_instance(self) -> None:
        first = get_investigation_store()
        second = get_investigation_store()
        self.assertIs(first, second)

    def test_get_alert_returns_copy(self) -> None:
        self.store.replace_analysis(_snapshot(_incoming(account_id="ACC_0001", alert_id="ALT_0001")))
        alert = self.store.get_alert("ALT_0001")
        alert.review.notes = "mutated copy"
        self.assertIsNone(self.store.get_alert("ALT_0001").review.notes)

    def test_returned_alert_has_no_ground_truth(self) -> None:
        self.store.replace_analysis(_snapshot(_incoming(account_id="ACC_0001", alert_id="ALT_0001")))
        dumped = self.store.get_alert("ALT_0001").model_dump()
        self.assertNotIn("ground_truth", dumped)
        self.assertNotIn("ground_truth", dumped["review"])


if __name__ == "__main__":
    unittest.main()
