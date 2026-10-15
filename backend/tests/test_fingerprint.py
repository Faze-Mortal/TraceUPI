import hashlib
import unittest

from backend.fingerprint import (
    canonical_fingerprint_string,
    classify_staleness_reason,
    compute_alert_fingerprint,
)


class TestAlertFingerprint(unittest.TestCase):
    def test_canonical_serialization_and_sha256(self) -> None:
        canonical = canonical_fingerprint_string(
            account_id="ACC_0917",
            txn_ids=["T000124", "T000123"],
            device_to_senders={"DEV_0002": ["ACC_0009"], "DEV_0001": ["ACC_0917", "ACC_0042"]},
            complaints=[
                ("CMP_0002", "PHISHING_SCAM", "2026-10-01T15:00:00Z"),
                ("CMP_0001", "UNAUTHORIZED_TRANSACTION", "2026-10-01T14:30:00Z"),
            ],
            ml_score=0.93004,
            priority="HIGH",
            rules_triggered=["RAPID_PASS_THROUGH", "HIGH_FAN_IN"],
        )
        expected = (
            "ACC_0917|"
            "T000123,T000124|"
            "DEV_0001:ACC_0042,ACC_0917;DEV_0002:ACC_0009|"
            "CMP_0001:UNAUTHORIZED_TRANSACTION:2026-10-01T14:30:00Z;"
            "CMP_0002:PHISHING_SCAM:2026-10-01T15:00:00Z|"
            "0.9300|"
            "HIGH|"
            "HIGH_FAN_IN,RAPID_PASS_THROUGH"
        )
        self.assertEqual(canonical, expected)
        self.assertEqual(
            compute_alert_fingerprint(
                "ACC_0917",
                ["T000124", "T000123"],
                {"DEV_0002": ["ACC_0009"], "DEV_0001": ["ACC_0917", "ACC_0042"]},
                [
                    ("CMP_0002", "PHISHING_SCAM", "2026-10-01T15:00:00Z"),
                    ("CMP_0001", "UNAUTHORIZED_TRANSACTION", "2026-10-01T14:30:00Z"),
                ],
                0.93004,
                "HIGH",
                ["RAPID_PASS_THROUGH", "HIGH_FAN_IN"],
            ),
            hashlib.sha256(expected.encode("utf-8")).hexdigest(),
        )

    def test_unrelated_complaint_does_not_change_fingerprint_if_not_passed_in(self) -> None:
        args = dict(
            account_id="ACC_0001",
            txn_ids=["T000001"],
            device_to_senders={},
            complaints=[],
            ml_score=0.1,
            priority="LOW",
            rules_triggered=[],
        )
        left = compute_alert_fingerprint(**args)
        right = compute_alert_fingerprint(**args)
        self.assertEqual(left, right)

    def test_staleness_reasons(self) -> None:
        self.assertEqual(
            classify_staleness_reason(
                has_prior_reviewed_snapshot=True,
                relevant_evidence_excluded_by_cutoff=True,
            ),
            "historical_snapshot_evidence_divergence",
        )
        self.assertEqual(
            classify_staleness_reason(
                has_prior_reviewed_snapshot=True,
                relevant_evidence_excluded_by_cutoff=False,
            ),
            "evidence_or_score_changed",
        )
        self.assertEqual(
            classify_staleness_reason(
                has_prior_reviewed_snapshot=False,
                relevant_evidence_excluded_by_cutoff=True,
            ),
            "evidence_or_score_changed",
        )


class TestCutoffExclusion(unittest.TestCase):
    def test_as_of_none_never_cutoff(self) -> None:
        from backend.fingerprint import relevant_evidence_excluded_by_cutoff

        self.assertFalse(
            relevant_evidence_excluded_by_cutoff(
                as_of=None,
                prior_txn_ids=["T000014"],
                current_txn_ids=[],
                prior_txn_ingested_at={"T000014": "2026-10-01T14:00:00Z"},
                prior_device_ids=[],
                current_device_ids=[],
                prior_device_ingested_at={},
                prior_complaint_ids=[],
                current_complaint_ids=[],
                prior_complaint_ingested_at={},
            )
        )

    def test_missing_txn_ingested_after_as_of(self) -> None:
        from backend.fingerprint import relevant_evidence_excluded_by_cutoff

        self.assertTrue(
            relevant_evidence_excluded_by_cutoff(
                as_of="2026-10-01T12:00:00Z",
                prior_txn_ids=["T000010", "T000014"],
                current_txn_ids=["T000010"],
                prior_txn_ingested_at={
                    "T000010": "2026-10-01T10:00:00Z",
                    "T000014": "2026-10-01T14:00:00Z",
                },
                prior_device_ids=[],
                current_device_ids=[],
                prior_device_ingested_at={},
                prior_complaint_ids=[],
                current_complaint_ids=[],
                prior_complaint_ingested_at={},
            )
        )

    def test_missing_txn_without_ingestion_timestamp_is_not_proven_cutoff(self) -> None:
        from backend.fingerprint import relevant_evidence_excluded_by_cutoff

        self.assertFalse(
            relevant_evidence_excluded_by_cutoff(
                as_of="2026-10-01T12:00:00Z",
                prior_txn_ids=["T000014"],
                current_txn_ids=[],
                prior_txn_ingested_at={},
                prior_device_ids=[],
                current_device_ids=[],
                prior_device_ingested_at={},
                prior_complaint_ids=[],
                current_complaint_ids=[],
                prior_complaint_ingested_at={},
            )
        )


if __name__ == "__main__":
    unittest.main()
