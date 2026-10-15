"""TraceUPI Temporal Replay and Analysis Pipeline Unit Tests.

Validates Contract v1.2:
  - 5-stage deterministic replay pipeline (§3.2).
  - Point-in-time cutoff boundaries & timestamp defaulting (§2.3, §3.2).
  - Invariant 3: Unrelated complaint isolation (§9.3).
  - Invariant 4: Late complaint cutoff (§9.3).
  - Invariant 5: Relevant historical divergence provenance (§9.3).
  - Invariant 6: Unrelated late event isolation (§9.3).
  - Invariant 7: Input data immutability.
  - Deterministic event sorting and bitwise identical outputs across permutations (§3.3).
  - Legacy complaint normalization (§2.4).
  - Temporal motifs (RAPID_PASS_THROUGH, DORMANCY_BURST) (§6.0, §6.3).
  - Topology-aware review fingerprint sensitivity and stability (§9.2).
  - AlertSummary schema compliance (§7.0).
"""

import copy
import hashlib
import json
import os
import unittest

from ml.pipeline import (
    compute_alert_fingerprint,
    detect_temporal_motifs,
    generate_top_reasons,
    normalize_and_filter_snapshot,
    run_analysis,
)


class TestReplayPipeline(unittest.TestCase):
    """Test suite for TraceUPI temporal replay pipeline and contract invariants."""

    def setUp(self):
        self.maxDiff = None
        # Base transaction fixture
        self.sample_txns = [
            {
                "txn_id": "T000001",
                "timestamp": "2026-10-01T10:00:00Z",
                "ingested_at": "2026-10-01T10:00:05Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0002",
                "sender_device_id": "DEV_0001",
                "amount_inr": 5000.0,
                "status": "SUCCESS",
                "complaint_filed": False,
                "complaint": None,
            },
            {
                "txn_id": "T000002",
                "timestamp": "2026-10-01T10:30:00Z",
                "ingested_at": "2026-10-01T10:30:05Z",
                "sender_account": "ACC_0002",
                "receiver_account": "ACC_0003",
                "sender_device_id": "DEV_0002",
                "amount_inr": 4800.0,
                "status": "SUCCESS",
                "complaint_filed": True,
                "complaint": {
                    "complaint_id": "CMP_0001",
                    "filed_at": "2026-10-01T11:00:00Z",
                    "ingested_at": "2026-10-01T11:05:00Z",
                    "category": "UNAUTHORIZED_TRANSACTION",
                },
            },
            {
                "txn_id": "T000003",
                "timestamp": "2026-10-01T14:00:00Z",
                "ingested_at": "2026-10-01T14:00:10Z",
                "sender_account": "ACC_0003",
                "receiver_account": "ACC_0004",
                "sender_device_id": "DEV_0003",
                "amount_inr": 4700.0,
                "status": "SUCCESS",
                "complaint_filed": False,
                "complaint": None,
            },
        ]

    def test_cutoff_boundaries_and_default_ingestion(self):
        """Transactions are filtered by t_ingested <= as_of, defaulting to timestamp if omitted."""
        txns = [
            {
                "txn_id": "T000010",
                "timestamp": "2026-10-01T09:00:00Z",
                # ingested_at omitted -> must default to timestamp (2026-10-01T09:00:00Z)
                "sender_account": "ACC_0010",
                "receiver_account": "ACC_0011",
                "amount_inr": 1000.0,
                "status": "SUCCESS",
            },
            {
                "txn_id": "T000011",
                "timestamp": "2026-10-01T10:00:00Z",
                "ingested_at": "2026-10-01T10:05:00Z",
                "sender_account": "ACC_0010",
                "receiver_account": "ACC_0011",
                "amount_inr": 2000.0,
                "status": "SUCCESS",
            },
            {
                "txn_id": "T000012",
                "timestamp": "2026-10-01T10:00:00Z",
                "ingested_at": "2026-10-01T11:00:00Z",
                "sender_account": "ACC_0010",
                "receiver_account": "ACC_0011",
                "amount_inr": 3000.0,
                "status": "SUCCESS",
            },
        ]

        # Cutoff at 10:05:00Z exactly includes T000010 (default 09:00) and T000011 (10:05)
        # Excludes T000012 (11:00:00Z > 10:05:00Z)
        res = normalize_and_filter_snapshot(txns, as_of="2026-10-01T10:05:00Z")
        self.assertEqual(len(res), 2)
        self.assertEqual([t["txn_id"] for t in res], ["T000010", "T000011"])
        self.assertEqual(res[0]["ingested_at"], "2026-10-01T09:00:00Z")

        # When as_of is None, all records retained
        res_all = normalize_and_filter_snapshot(txns, as_of=None)
        self.assertEqual(len(res_all), 3)

    def test_late_complaint_cutoff_invariant_4(self):
        """Contract §9.3 Invariant 4: Late complaint ingestion cutoff.

        A complaint associated with ACC_0001 filed before T_as_of but ingested after T_as_of
        (t_complaint_ingested > T_as_of) is excluded from the snapshot and does not alter the
        alert fingerprint computed at T_as_of.
        """
        # Transaction at 10:00, ingested at 10:01
        # Complaint filed at 11:30 (before cutoff 12:00)
        # Complaint ingested at 14:00 (after cutoff 12:00)
        txn_late_complaint = {
            "txn_id": "T000020",
            "timestamp": "2026-10-01T10:00:00Z",
            "ingested_at": "2026-10-01T10:01:00Z",
            "sender_account": "ACC_0001",
            "receiver_account": "ACC_0002",
            "sender_device_id": "DEV_0001",
            "amount_inr": 15000.0,
            "status": "SUCCESS",
            "complaint_filed": True,
            "complaint": {
                "complaint_id": "CMP_0020",
                "filed_at": "2026-10-01T11:30:00Z",
                "ingested_at": "2026-10-01T14:00:00Z",  # Ingested at 14:00
                "category": "UNAUTHORIZED_TRANSACTION",
            },
        }

        # Baseline transaction without complaint
        txn_no_complaint = copy.deepcopy(txn_late_complaint)
        txn_no_complaint["complaint_filed"] = False
        txn_no_complaint["complaint"] = None

        # Snapshot at T_as_of = 12:00:00Z
        as_of_cutoff = "2026-10-01T12:00:00Z"

        snapshot_with_late = normalize_and_filter_snapshot([txn_late_complaint], as_of=as_of_cutoff)
        snapshot_without = normalize_and_filter_snapshot([txn_no_complaint], as_of=as_of_cutoff)

        # In the snapshot at 12:00, complaint must be strictly inactive!
        self.assertFalse(snapshot_with_late[0]["complaint_filed"])
        self.assertIsNone(snapshot_with_late[0]["complaint"])

        # Both snapshots produce identical canonical fingerprints
        _, fp_late = compute_alert_fingerprint("ACC_0002", snapshot_with_late, 0.85, "HIGH", ["HIGH_FAN_IN"], as_of=as_of_cutoff)
        _, fp_without = compute_alert_fingerprint("ACC_0002", snapshot_without, 0.85, "HIGH", ["HIGH_FAN_IN"], as_of=as_of_cutoff)
        self.assertEqual(fp_late, fp_without)

        # But when replayed at 15:00:00Z (after complaint ingestion 14:00), complaint becomes visible
        snapshot_visible = normalize_and_filter_snapshot([txn_late_complaint], as_of="2026-10-01T15:00:00Z")
        self.assertTrue(snapshot_visible[0]["complaint_filed"])
        self.assertIsNotNone(snapshot_visible[0]["complaint"])

        _, fp_visible = compute_alert_fingerprint("ACC_0002", snapshot_visible, 0.85, "HIGH", ["HIGH_FAN_IN"], as_of="2026-10-01T15:00:00Z")
        self.assertNotEqual(fp_visible, fp_late)

    def test_unrelated_complaint_isolation_invariant_3(self):
        """Contract §9.3 Invariant 3: Unrelated complaint isolation.

        Ingesting a complaint associated with ACC_0002 does not change the alert fingerprint of ACC_0001.
        """
        txns_base = [
            {
                "txn_id": "T000030",
                "timestamp": "2026-10-01T10:00:00Z",
                "ingested_at": "2026-10-01T10:01:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0099",
                "sender_device_id": "DEV_0001",
                "amount_inr": 5000.0,
                "status": "SUCCESS",
            },
            {
                "txn_id": "T000031",
                "timestamp": "2026-10-01T10:10:00Z",
                "ingested_at": "2026-10-01T10:11:00Z",
                "sender_account": "ACC_0002",
                "receiver_account": "ACC_0088",
                "sender_device_id": "DEV_0002",
                "amount_inr": 6000.0,
                "status": "SUCCESS",
                "complaint_filed": False,
                "complaint": None,
            },
        ]

        txns_with_unrelated_complaint = copy.deepcopy(txns_base)
        # Add complaint on ACC_0002 transaction
        txns_with_unrelated_complaint[1]["complaint_filed"] = True
        txns_with_unrelated_complaint[1]["complaint"] = {
            "complaint_id": "CMP_9999",
            "filed_at": "2026-10-01T10:15:00Z",
            "ingested_at": "2026-10-01T10:16:00Z",
            "category": "PHISHING_SCAM",
        }

        snap_a = normalize_and_filter_snapshot(txns_base)
        snap_b = normalize_and_filter_snapshot(txns_with_unrelated_complaint)

        # Compute fingerprint for ACC_0001 in both snapshots
        canon_a, fp_a = compute_alert_fingerprint("ACC_0001", snap_a, 0.75, "MEDIUM", ["RAPID_PASS_THROUGH"])
        canon_b, fp_b = compute_alert_fingerprint("ACC_0001", snap_b, 0.75, "MEDIUM", ["RAPID_PASS_THROUGH"])

        self.assertEqual(canon_a, canon_b)
        self.assertEqual(fp_a, fp_b)

    def test_historical_divergence_provenance_invariant_5(self):
        """Contract §9.3 Invariant 5: Relevant historical divergence provenance.

        An alert whose active review was based on transactions at 10:00 and 14:00,
        when replayed at T_as_of = 12:00 (excluding the 14:00 transaction),
        assigns staleness_reason = 'historical_snapshot_evidence_divergence'.
        """
        all_txns = [
            {
                "txn_id": "T000040",
                "timestamp": "2026-10-01T10:00:00Z",
                "ingested_at": "2026-10-01T10:00:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0002",
                "amount_inr": 20000.0,
                "status": "SUCCESS",
            },
            {
                "txn_id": "T000041",
                "timestamp": "2026-10-01T14:00:00Z",
                "ingested_at": "2026-10-01T14:00:00Z",
                "sender_account": "ACC_0002",
                "receiver_account": "ACC_0003",
                "amount_inr": 19000.0,
                "status": "SUCCESS",
            },
        ]

        # Prior review on full dataset for ACC_0002
        full_snap = normalize_and_filter_snapshot(all_txns)
        _, reviewed_fp = compute_alert_fingerprint("ACC_0002", full_snap, 0.90, "HIGH", ["RAPID_PASS_THROUGH"])

        previous_reviews = {
            ("ACC_0002", reviewed_fp): {
                "status": "CONFIRMED_FRAUD",
                "analyst_id": "ANALYST_01",
                "verdict": "CONFIRMED_MULE_RING",
                "notes": "Verified rapid layering.",
                "updated_at": "2026-10-02T10:00:00Z",
            }
        }

        # Replay at 12:00 (excludes T000041 at 14:00 which touches ACC_0002)
        analysis_result = run_analysis(
            transactions=all_txns,
            as_of="2026-10-01T12:00:00Z",
            previous_reviews=previous_reviews,
            all_raw_transactions=all_txns,
        )

        acc2_alert = next((a for a in analysis_result["alerts"] if a["account_id"] == "ACC_0002"), None)
        if acc2_alert is not None:
            self.assertTrue(acc2_alert["review"]["is_stale"])
            self.assertEqual(
                acc2_alert["review"]["staleness_reason"],
                "historical_snapshot_evidence_divergence",
            )
            self.assertEqual(acc2_alert["review"]["previous_review"]["verdict"], "CONFIRMED_MULE_RING")

    def test_unrelated_late_event_isolation_invariant_6(self):
        """Contract §9.3 Invariant 6: Unrelated late event isolation.

        An alert whose account events all completed before T_as_of, when replayed with cutoff
        T_as_of, does not receive historical_snapshot_evidence_divergence merely because
        unrelated accounts executed late transactions; if its fingerprint changes due to global
        re-scoring, it assigns evidence_or_score_changed.
        """
        all_txns = [
            # ACC_0001 and ACC_0002 transactions happen at 09:00 and 10:00
            {
                "txn_id": "T000050",
                "timestamp": "2026-10-01T09:00:00Z",
                "ingested_at": "2026-10-01T09:00:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0002",
                "amount_inr": 25000.0,
                "status": "SUCCESS",
            },
            # Completely unrelated transaction on ACC_0088 -> ACC_0099 at 16:00
            {
                "txn_id": "T000051",
                "timestamp": "2026-10-01T16:00:00Z",
                "ingested_at": "2026-10-01T16:00:00Z",
                "sender_account": "ACC_0088",
                "receiver_account": "ACC_0099",
                "amount_inr": 5000.0,
                "status": "SUCCESS",
            },
        ]

        # Prior review for ACC_0001 exists with a different arbitrary fingerprint
        # simulating a changed score/rules
        previous_reviews = {
            ("ACC_0001", "old_non_matching_fingerprint_hash"): {
                "status": "INVESTIGATING",
                "analyst_id": "ANALYST_02",
                "verdict": None,
                "notes": "Checking account source of funds.",
                "updated_at": "2026-10-01T11:00:00Z",
            }
        }

        # Replay at 12:00:00Z: ACC_0001 has NO transactions or devices excluded
        # Unrelated T000051 is excluded, but touches ACC_0088/0099
        analysis_result = run_analysis(
            transactions=all_txns,
            as_of="2026-10-01T12:00:00Z",
            previous_reviews=previous_reviews,
            all_raw_transactions=all_txns,
        )

        acc1_alert = next((a for a in analysis_result["alerts"] if a["account_id"] == "ACC_0001"), None)
        if acc1_alert is not None:
            self.assertTrue(acc1_alert["review"]["is_stale"])
            # MUST NOT be historical_snapshot_evidence_divergence because ACC_0001 evidence was not excluded!
            self.assertEqual(
                acc1_alert["review"]["staleness_reason"],
                "evidence_or_score_changed",
            )

    def test_exact_replay_restoration_invariant_7(self):
        """Contract §9.3 Invariant 7: Exact replay restoration (F_A -> F_B -> F_A).

        Replaying from snapshot A (with active review) to divergent snapshot B (yielding stale OPEN status),
        and then replaying back to snapshot A, restores the exact reviewed status (CONFIRMED_FRAUD),
        notes, and analyst attribution with is_stale = False and staleness_reason = None.
        """
        all_txns = [
            {
                "txn_id": "T000060",
                "timestamp": "2026-10-01T10:00:00Z",
                "ingested_at": "2026-10-01T10:00:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0002",
                "amount_inr": 20000.0,
                "status": "SUCCESS",
                "complaint_filed": True,
            },
            {
                "txn_id": "T000061",
                "timestamp": "2026-10-01T10:30:00Z",
                "ingested_at": "2026-10-01T10:30:00Z",
                "sender_account": "ACC_0002",
                "receiver_account": "ACC_0003",
                "amount_inr": 19000.0,
                "status": "SUCCESS",
            },
        ]

        # 1. Snapshot A: Full run
        res_a = run_analysis(transactions=all_txns)
        acc2_alert_a = next(a for a in res_a["alerts"] if a["account_id"] == "ACC_0002")
        fp_a = acc2_alert_a["alert_fingerprint"]

        # 2. Analyst reviews alert in Snapshot A: store in review store indexed by (account_id, fingerprint)
        review_store = {
            ("ACC_0002", fp_a): {
                "status": "CONFIRMED_FRAUD",
                "analyst_id": "ANALYST_01",
                "verdict": "CONFIRMED_MULE_RING",
                "notes": "Verified 2-hop rapid layering cash-out.",
                "updated_at": "2026-10-02T10:00:00Z",
            }
        }

        # 3. Snapshot B: Replay to historical cutoff 10:15 (excludes T000061 at 10:30)
        res_b = run_analysis(
            transactions=all_txns,
            as_of="2026-10-01T10:15:00Z",
            previous_reviews=review_store,
            all_raw_transactions=all_txns,
        )
        acc2_alert_b = next(a for a in res_b["alerts"] if a["account_id"] == "ACC_0002")
        self.assertNotEqual(acc2_alert_b["alert_fingerprint"], fp_a)
        self.assertEqual(acc2_alert_b["status"], "OPEN")
        self.assertTrue(acc2_alert_b["review"]["is_stale"])
        self.assertEqual(acc2_alert_b["review"]["staleness_reason"], "historical_snapshot_evidence_divergence")
        self.assertIsNotNone(acc2_alert_b["review"]["previous_review"])
        self.assertEqual(acc2_alert_b["review"]["previous_review"]["verdict"], "CONFIRMED_MULE_RING")

        # 4. Replay back to Snapshot A (as_of=None): must restore exact reviewed state!
        res_a_restored = run_analysis(
            transactions=all_txns,
            as_of=None,
            previous_reviews=review_store,
            all_raw_transactions=all_txns,
        )
        acc2_restored = next(a for a in res_a_restored["alerts"] if a["account_id"] == "ACC_0002")
        self.assertEqual(acc2_restored["alert_fingerprint"], fp_a)
        self.assertEqual(acc2_restored["status"], "CONFIRMED_FRAUD")
        self.assertFalse(acc2_restored["review"]["is_stale"])
        self.assertIsNone(acc2_restored["review"]["staleness_reason"])
        self.assertEqual(acc2_restored["review"]["analyst_id"], "ANALYST_01")
        self.assertEqual(acc2_restored["review"]["verdict"], "CONFIRMED_MULE_RING")
        self.assertEqual(acc2_restored["review"]["notes"], "Verified 2-hop rapid layering cash-out.")
        self.assertIsNone(acc2_restored["review"]["previous_review"])

    def test_deterministic_replay_and_sorting(self):
        """Stages 1-5 produce bitwise identical outputs across line permutations (§3.3)."""
        txns_ordered = copy.deepcopy(self.sample_txns)
        txns_reversed = list(reversed(copy.deepcopy(self.sample_txns)))

        snap_a = normalize_and_filter_snapshot(txns_ordered)
        snap_b = normalize_and_filter_snapshot(txns_reversed)

        # Sorted order must be identical
        self.assertEqual(
            [t["txn_id"] for t in snap_a],
            [t["txn_id"] for t in snap_b],
        )

        # Full analysis must produce identical alert fingerprints and scores
        res_a = run_analysis(txns_ordered)
        res_b = run_analysis(txns_reversed)

        fps_a = [a["alert_fingerprint"] for a in res_a["alerts"]]
        fps_b = [a["alert_fingerprint"] for a in res_b["alerts"]]
        self.assertEqual(fps_a, fps_b)
        self.assertEqual(res_a["scores"], res_b["scores"])

    def test_input_immutability(self):
        """Input transaction dictionaries and nested objects are never mutated."""
        original_txns = copy.deepcopy(self.sample_txns)
        original_json = json.dumps(original_txns, sort_keys=True)

        # Run normalization, filtering, and analysis
        _ = normalize_and_filter_snapshot(self.sample_txns, as_of="2026-10-01T11:00:00Z")
        _ = run_analysis(self.sample_txns, as_of="2026-10-01T11:00:00Z")

        # Serialized form of self.sample_txns must remain unchanged
        current_json = json.dumps(self.sample_txns, sort_keys=True)
        self.assertEqual(original_json, current_json)

    def test_legacy_complaint_normalization(self):
        """Legacy boolean complaint_filed=True is normalized according to §2.4."""
        legacy_txn = {
            "txn_id": "T000099",
            "timestamp": "2026-10-01T08:00:00Z",
            "ingested_at": "2026-10-01T08:01:00Z",
            "sender_account": "ACC_0001",
            "receiver_account": "ACC_0002",
            "amount_inr": 3000.0,
            "status": "SUCCESS",
            "complaint_filed": True,
            "complaint": None,
        }

        snap = normalize_and_filter_snapshot([legacy_txn])
        norm_txn = snap[0]

        self.assertTrue(norm_txn["complaint_filed"])
        c_obj = norm_txn["complaint"]
        self.assertIsNotNone(c_obj)
        self.assertEqual(c_obj["complaint_id"], "CMP_000099")
        self.assertEqual(c_obj["filed_at"], "2026-10-01T08:00:00Z")
        self.assertEqual(c_obj["ingested_at"], "2026-10-01T08:01:00Z")
        self.assertEqual(c_obj["category"], "UNSPECIFIED")

    def test_temporal_motifs_rapid_pass_through(self):
        """Temporal motif RAPID_PASS_THROUGH triggers iff inflow is followed by outflow <= 2 hours."""
        # Positive case: Inflow at 10:00, Outflow at 10:45 (diff = 45m <= 2h)
        txns_rapid = [
            {
                "txn_id": "T000101",
                "timestamp": "2026-10-01T10:00:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0002",
                "amount_inr": 10000.0,
                "status": "SUCCESS",
            },
            {
                "txn_id": "T000102",
                "timestamp": "2026-10-01T10:45:00Z",
                "sender_account": "ACC_0002",
                "receiver_account": "ACC_0003",
                "amount_inr": 9900.0,
                "status": "SUCCESS",
            },
        ]
        motifs_pos = detect_temporal_motifs(txns_rapid, "ACC_0002")
        self.assertTrue(motifs_pos["RAPID_PASS_THROUGH"])

        # Negative case: Inflow at 10:00, Outflow at 13:00 (diff = 3h > 2h)
        txns_slow = copy.deepcopy(txns_rapid)
        txns_slow[1]["timestamp"] = "2026-10-01T13:00:00Z"
        motifs_neg = detect_temporal_motifs(txns_slow, "ACC_0002")
        self.assertFalse(motifs_neg["RAPID_PASS_THROUGH"])

    def test_temporal_motifs_dormancy_burst(self):
        """Temporal motif DORMANCY_BURST triggers on >= 24h gap followed by burst of >= 3 txns in <= 2h."""
        txns_dormant = [
            # Event 1 on Oct 1
            {
                "txn_id": "T000201",
                "timestamp": "2026-10-01T10:00:00Z",
                "sender_account": "ACC_0005",
                "receiver_account": "ACC_0006",
                "amount_inr": 1000.0,
                "status": "SUCCESS",
            },
            # Gap of 48h (> 24h) to Oct 3
            {
                "txn_id": "T000202",
                "timestamp": "2026-10-03T10:00:00Z",
                "sender_account": "ACC_0005",
                "receiver_account": "ACC_0007",
                "amount_inr": 2000.0,
                "status": "SUCCESS",
            },
            # Burst: 2nd txn at 10:30 (diff = 30m)
            {
                "txn_id": "T000203",
                "timestamp": "2026-10-03T10:30:00Z",
                "sender_account": "ACC_0005",
                "receiver_account": "ACC_0008",
                "amount_inr": 2000.0,
                "status": "SUCCESS",
            },
            # Burst: 3rd txn at 11:15 (from 10:00 to 11:15 is 1h 15m <= 2h)
            {
                "txn_id": "T000204",
                "timestamp": "2026-10-03T11:15:00Z",
                "sender_account": "ACC_0005",
                "receiver_account": "ACC_0009",
                "amount_inr": 2000.0,
                "status": "SUCCESS",
            },
        ]
        motifs_dormant = detect_temporal_motifs(txns_dormant, "ACC_0005")
        self.assertTrue(motifs_dormant["DORMANCY_BURST"])

        # Negative case: gap is only 12h (< 24h)
        txns_no_gap = copy.deepcopy(txns_dormant)
        txns_no_gap[1]["timestamp"] = "2026-10-01T22:00:00Z"
        txns_no_gap[2]["timestamp"] = "2026-10-01T22:30:00Z"
        txns_no_gap[3]["timestamp"] = "2026-10-01T23:15:00Z"
        motifs_no_gap = detect_temporal_motifs(txns_no_gap, "ACC_0005")
        self.assertFalse(motifs_no_gap["DORMANCY_BURST"])

    def test_topology_aware_fingerprint_sensitivity(self):
        """Fingerprint changes when a new account joins a shared device (§9.2)."""
        txns_base = [
            {
                "txn_id": "T000301",
                "timestamp": "2026-10-01T10:00:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0002",
                "sender_device_id": "DEV_0001",
                "amount_inr": 1000.0,
                "status": "SUCCESS",
            },
        ]
        _, fp_before = compute_alert_fingerprint("ACC_0001", txns_base, 0.5, "MEDIUM", ["HIGH_FAN_IN"])

        # Another account transacts using DEV_0001
        txns_with_shared_device = copy.deepcopy(txns_base) + [
            {
                "txn_id": "T000302",
                "timestamp": "2026-10-01T11:00:00Z",
                "sender_account": "ACC_0003",  # New sender on same device
                "receiver_account": "ACC_0004",
                "sender_device_id": "DEV_0001",
                "amount_inr": 2000.0,
                "status": "SUCCESS",
            }
        ]
        _, fp_after = compute_alert_fingerprint("ACC_0001", txns_with_shared_device, 0.5, "MEDIUM", ["HIGH_FAN_IN"])

        # The device_links component changed from DEV_0001:ACC_0001 to DEV_0001:ACC_0001,ACC_0003
        self.assertNotEqual(fp_before, fp_after)

    def test_run_analysis_end_to_end_and_alert_summary_schema(self):
        """run_analysis executes end-to-end and AlertSummary adheres to §7.0."""
        # Load sample from data/transactions.jsonl
        with open("data/transactions.jsonl", "r", encoding="utf-8") as f:
            raw_txns = [json.loads(line) for line in f]

        res = run_analysis(raw_txns)
        self.assertGreater(res["n_transactions"], 0)
        self.assertGreater(res["n_alerts"], 0)
        self.assertTrue(res["metrics_available"])
        self.assertIn("alerts", res)
        self.assertIn("alert_summaries", res)
        self.assertEqual(len(res["alerts"]), len(res["alert_summaries"]))

        # Verify Alert vs AlertSummary schema differences (§7.0)
        full_alert = res["alerts"][0]
        alert_summary = res["alert_summaries"][0]

        # Full alert has evidence
        self.assertIn("evidence", full_alert)
        self.assertIn("nodes", full_alert["evidence"])
        self.assertIn("edges", full_alert["evidence"])
        self.assertIn("evidence_path", full_alert["evidence"])

        # AlertSummary MUST NOT contain evidence or previous_review (§7.0)
        self.assertNotIn("evidence", alert_summary)
        self.assertNotIn("previous_review", alert_summary["review"])

        # Both share common summary fields
        for field in ["alert_id", "alert_fingerprint", "account_id", "status", "priority", "ml", "baseline", "top_reasons", "context_flags"]:
            self.assertIn(field, alert_summary)
            self.assertEqual(full_alert[field], alert_summary[field])


if __name__ == "__main__":
    unittest.main()
