"""TraceUPI Temporal Replay and Analysis Pipeline.

Implements the Five-Stage Deterministic Replay Pipeline, temporal motif detection,
alert generation, and topology-aware review fingerprinting strictly adhering to
TraceUPI Interface Contract v1.2:
  - Stage 1: Validation and non-mutating normalization (§2.4, §3.2).
  - Stage 2: Transaction ingestion cutoff (t_ingested <= as_of).
  - Stage 3: Complaint ingestion visibility (t_complaint_ingested <= as_of).
  - Stage 4: Deterministic event sorting (timestamp asc, txn_id asc).
  - Stage 5: Feature extraction, frozen model inference, graph construction,
             temporal motifs (RAPID_PASS_THROUGH, DORMANCY_BURST), and explainable alerts.
  - Review fingerprinting: Canonical serialization matching Contract §9.2.
  - Staleness provenance: Accurate distinction between historical_snapshot_evidence_divergence
    and evidence_or_score_changed (§9.2, §9.3).
"""

from collections import defaultdict
import copy
import datetime
import hashlib
import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import joblib

from ml.baseline_rules import evaluate_account_rules
from ml.features import (
    FEATURE_NAMES,
    extract_account_features,
    extract_feature_matrix,
    is_complaint_active,
    validate_feature_input,
)
from ml.graph import build_graph_from_transactions, extract_evidence_subgraph

_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def parse_utc_timestamp(ts_str: str) -> datetime.datetime:
    """Parse ISO 8601 UTC timestamp string to datetime object."""
    return datetime.datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


def normalize_and_filter_snapshot(
    transactions: List[Dict[str, Any]],
    as_of: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Execute Stages 1-4 of the Contract v1.2 Deterministic Replay Pipeline.

    Does not mutate input transactions or nested objects.

    Args:
        transactions: Raw transaction records matching Contract v1.2.
        as_of: Optional ISO 8601 UTC cutoff timestamp string (T_as_of).

    Returns:
        Filtered, normalized, and deterministically sorted transaction records.
    """
    if as_of is not None:
        if not isinstance(as_of, str) or not _TIMESTAMP_RE.fullmatch(as_of):
            raise ValueError(f"Invalid as_of timestamp format '{as_of}' (expected YYYY-MM-DDTHH:MM:SSZ)")

    # Validate raw input schema
    validate_feature_input(transactions)

    snapshot_records: List[Dict[str, Any]] = []

    for raw_txn in transactions:
        # Shallow copy to avoid input mutation
        txn = dict(raw_txn)

        # Stage 1: Ingestion timestamp defaulting
        ts_event = txn["timestamp"]
        t_ingested = txn.get("ingested_at") or ts_event
        txn["ingested_at"] = t_ingested

        # Stage 2: Transaction Ingestion Cutoff
        if as_of is not None and t_ingested > as_of:
            # Transaction had not yet arrived in ledger as of cutoff -> strictly excluded
            continue

        # Stage 1 & 3: Complaint Normalization & Ingestion Visibility
        # Rule (§3.2): Complaint is active iff t_complaint_ingested <= T_as_of
        # Filing time alone NEVER grants premature visibility
        if is_complaint_active(txn):
            raw_c_obj = txn.get("complaint")
            if raw_c_obj is not None:
                c_obj = dict(raw_c_obj)
                c_filed = c_obj["filed_at"]
                c_ingested = c_obj.get("ingested_at") or c_filed
                c_obj["ingested_at"] = c_ingested
            else:
                # Legacy boolean fallback (§2.4)
                c_obj = {
                    "complaint_id": "CMP_" + txn["txn_id"][1:],
                    "filed_at": ts_event,
                    "ingested_at": t_ingested,
                    "category": "UNSPECIFIED",
                }
                c_ingested = t_ingested

            # Check point-in-time visibility of the complaint
            if as_of is not None and c_ingested > as_of:
                # Complaint arrived after cutoff -> hidden from this snapshot!
                txn["complaint"] = None
                txn["complaint_filed"] = False
            else:
                txn["complaint"] = c_obj
                txn["complaint_filed"] = True
        else:
            txn["complaint"] = None
            txn["complaint_filed"] = False

        snapshot_records.append(txn)

    # Stage 4: Deterministic Event Sorting (§3.2 Stage 4)
    # Primary: timestamp asc, Tie-breaker: txn_id asc
    snapshot_records.sort(key=lambda t: (t["timestamp"], t["txn_id"]))

    return snapshot_records


def detect_temporal_motifs(
    transactions: List[Dict[str, Any]],
    account_id: str,
) -> Dict[str, bool]:
    """Detect temporal motifs for an account per Contract §6.0, §6.3.

    Motifs:
    - RAPID_PASS_THROUGH: Inflow followed by outflow within <= 2 hours (7200 seconds).
    - DORMANCY_BURST: Dormancy gap >= 24 hours (86400s) followed by a burst of >= 3 txns within <= 2 hours.
    """
    account_txns = [
        t for t in transactions
        if t["sender_account"] == account_id or t["receiver_account"] == account_id
    ]
    if not account_txns:
        return {"RAPID_PASS_THROUGH": False, "DORMANCY_BURST": False}

    # Sort account transactions chronologically
    account_txns.sort(key=lambda t: (t["timestamp"], t["txn_id"]))

    # 1. RAPID_PASS_THROUGH
    # An incoming transfer followed by an outgoing transfer within <= 2 hours
    rapid_pass_through = False
    inflows = [
        (parse_utc_timestamp(t["timestamp"]), t["amount_inr"])
        for t in account_txns
        if t["receiver_account"] == account_id and t.get("status") == "SUCCESS"
    ]
    outflows = [
        (parse_utc_timestamp(t["timestamp"]), t["amount_inr"])
        for t in account_txns
        if t["sender_account"] == account_id and t.get("status") == "SUCCESS"
    ]

    for t_in, amt_in in inflows:
        for t_out, amt_out in outflows:
            diff_sec = (t_out - t_in).total_seconds()
            if 0 <= diff_sec <= 7200:  # <= 2 hours
                rapid_pass_through = True
                break
        if rapid_pass_through:
            break

    # 2. DORMANCY_BURST
    # Dormancy gap >= 24 hours between transactions, followed by a burst of >= 3 transactions within <= 2 hours
    dormancy_burst = False
    if len(account_txns) >= 3:
        dt_list = [parse_utc_timestamp(t["timestamp"]) for t in account_txns]

        for i in range(len(dt_list) - 1):
            gap_sec = (dt_list[i + 1] - dt_list[i]).total_seconds()
            if gap_sec >= 86400:  # >= 24 hours dormancy
                # Check if from i+1 onwards there is a burst of >= 3 transactions within 2 hours
                subsequent = dt_list[i + 1:]
                for j in range(len(subsequent) - 2):
                    window_sec = (subsequent[j + 2] - subsequent[j]).total_seconds()
                    if window_sec <= 7200:  # >= 3 txns within 2 hours
                        dormancy_burst = True
                        break
                if dormancy_burst:
                    break

    return {
        "RAPID_PASS_THROUGH": rapid_pass_through,
        "DORMANCY_BURST": dormancy_burst,
    }


def compute_alert_fingerprint(
    account_id: str,
    visible_transactions: List[Dict[str, Any]],
    ml_score: float,
    priority: str,
    rules_triggered: List[str],
    as_of: Optional[str] = None,
) -> Tuple[str, str]:
    """Compute topology-aware alert fingerprint strictly conforming to Contract §9.2.

    Formula:
      canonical_str = account_id + "|" + txns + "|" + device_links + "|" + complaint_links + "|" + f"{ml.score:.4f}" + "|" + priority + "|" + rules
      alert_fingerprint = SHA-256(canonical_str.encode('utf-8')).hexdigest()

    Returns:
        Tuple of (canonical_str, alert_fingerprint_hex).
    """
    # 1. txns: ",".join(sorted(txn_ids)) for all visible transactions directly touching account_id
    touching_txns = [
        t for t in visible_transactions
        if t["sender_account"] == account_id or t["receiver_account"] == account_id
    ]
    txn_ids = sorted({t["txn_id"] for t in touching_txns})
    txns_str = ",".join(txn_ids)

    # 2. device_links: ";".join(sorted([f"{dev}:{','.join(sorted(senders))}" for dev, senders in device_to_senders.items()]))
    # For all devices used by account_id in visible transactions
    device_to_senders: Dict[str, Set[str]] = defaultdict(set)
    for t in visible_transactions:
        dev = t.get("sender_device_id")
        if dev is not None:
            device_to_senders[dev].add(t["sender_account"])

    account_devices = {
        t["sender_device_id"]
        for t in touching_txns
        if t.get("sender_account") == account_id and t.get("sender_device_id") is not None
    }
    device_links_list = [
        f"{dev}:{','.join(sorted(device_to_senders[dev]))}"
        for dev in sorted(account_devices)
    ]
    device_links_str = ";".join(device_links_list)

    # 3. complaint_links: ";".join(sorted([f"{c.id}:{c.category}:{c.filed_at}" for c in account_complaints if c.ingested_at <= T_as_of]))
    # Strictly scoped to complaints associated with account_id (filed against or by account_id per §9.2 line 526)
    account_complaints_map: Dict[str, Tuple[str, str]] = {}  # cid -> (category, filed_at)
    for t in touching_txns:
        if is_complaint_active(t):
            c_obj = t.get("complaint")
            if c_obj is not None:
                cid = c_obj["complaint_id"]
                c_ingested = c_obj.get("ingested_at") or c_obj["filed_at"]
                if as_of is None or c_ingested <= as_of:
                    account_complaints_map[cid] = (
                        c_obj.get("category", "UNSPECIFIED"),
                        c_obj["filed_at"],
                    )

    complaint_links_list = [
        f"{cid}:{cat}:{filed}"
        for cid, (cat, filed) in sorted(account_complaints_map.items())
    ]
    complaint_links_str = ";".join(complaint_links_list)

    # 4. score, priority, rules
    score_str = f"{ml_score:.4f}"
    rules_str = ",".join(sorted(rules_triggered))

    canonical_str = (
        f"{account_id}|{txns_str}|{device_links_str}|{complaint_links_str}|{score_str}|{priority}|{rules_str}"
    )
    fingerprint_hex = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    return canonical_str, fingerprint_hex


def generate_top_reasons(
    account_features: Dict[str, float],
    training_medians: Dict[str, float],
) -> List[Dict[str, Any]]:
    """Generate explainable top reasons by comparing account features to training medians."""
    # Priority candidate features for risk explanation
    candidate_features = [
        ("fan_in_count", "Received transfers from {val:.0f} distinct counterparties (typical training median: {med:.0f})."),
        ("amount_received_total", "Total funds received of Rs {val:,.2f} exceeds typical training median (Rs {med:,.2f})."),
        ("complaint_count_as_receiver", "Received {val:.0f} fraud complaints from counterparties (typical training median: {med:.0f})."),
        ("net_flow_amount", "Net INR flow of Rs {val:,.2f} deviates significantly from baseline (Rs {med:,.2f})."),
        ("amount_sent_max", "Single outgoing transfer of Rs {val:,.2f} significantly exceeds median (Rs {med:,.2f})."),
        ("fan_ratio", "High in-degree to out-degree fan ratio of {val:.2f} (typical training median: {med:.2f})."),
        ("devices_used_count", "Used {val:.0f} distinct device IDs (typical training median: {med:.0f})."),
    ]

    scored_reasons = []
    for fname, tmpl in candidate_features:
        val = account_features.get(fname, 0.0)
        med = training_medians.get(fname, 1.0)
        if val > med:
            diff_ratio = (val - med) / (abs(med) + 1e-5)
            explanation = tmpl.format(val=val, med=med)
            scored_reasons.append((diff_ratio, {
                "feature": fname,
                "value": round(val, 4),
                "typical_value": round(med, 4),
                "explanation": explanation,
            }))

    # Sort by deviation ratio descending, take top 2
    scored_reasons.sort(key=lambda x: x[0], reverse=True)
    top = [r[1] for r in scored_reasons[:2]]
    if not top:
        # Fallback if no feature exceeded median
        top.append({
            "feature": "txn_count_total",
            "value": account_features.get("txn_count_total", 0.0),
            "typical_value": training_medians.get("txn_count_total", 0.0),
            "explanation": f"Total transactions: {account_features.get('txn_count_total', 0.0):.0f}.",
        })
    return top


def run_analysis(
    transactions: List[Dict[str, Any]],
    as_of: Optional[str] = None,
    model_artifact: Optional[Dict[str, Any]] = None,
    model_artifact_path: str = "data/artifacts/model.joblib",
    previous_reviews: Optional[Dict[Tuple[str, str], Dict[str, Any]]] = None,
    all_raw_transactions: Optional[List[Dict[str, Any]]] = None,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute the full Contract v1.2 pipeline analysis on transactions.

    Args:
        transactions: Transaction records for the analysis.
        as_of: Optional ISO 8601 UTC cutoff timestamp string.
        model_artifact: Optional loaded model artifact dict. If None, loaded from model_artifact_path.
        model_artifact_path: Path to model.joblib artifact.
        previous_reviews: Optional map of (account_id, fingerprint) -> review dict.
        all_raw_transactions: Full un-truncated transaction list used to verify historical divergence provenance.
        created_at: Optional ISO 8601 UTC string for alert created_at.

    Returns:
        Dictionary matching Contract v1.2 analysis response:
        {
            "n_transactions": int,
            "n_alerts": int,
            "metrics_available": bool,
            "as_of": Optional[str],
            "alerts": List[Dict[str, Any]],
            "alert_summaries": List[Dict[str, Any]],
            "graph": HeterogeneousGraph,
            "features": Dict[str, Dict[str, float]],
            "scores": Dict[str, float],
        }
    """
    if created_at is None:
        created_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if previous_reviews is None:
        previous_reviews = {}

    if all_raw_transactions is None:
        all_raw_transactions = transactions

    # 1. Load model artifact
    if model_artifact is None:
        model_artifact = joblib.load(model_artifact_path)

    model = model_artifact["model"]
    threshold = float(model_artifact.get("decision_threshold", 0.5))
    training_medians = model_artifact.get("training_feature_medians", {})

    # 2. Replay Pipeline: Filter and normalize snapshot (Stages 1-4)
    snapshot_txns = normalize_and_filter_snapshot(transactions, as_of=as_of)

    # 3. Feature Extraction (Stage 5)
    features_by_account = extract_account_features(snapshot_txns)
    ordered_accs, matrix = extract_feature_matrix(snapshot_txns)

    # 4. Model Inference
    scores: Dict[str, float] = {}
    if matrix:
        probs = model.predict_proba(matrix)
        for idx, acc in enumerate(ordered_accs):
            scores[acc] = round(float(probs[idx][1]), 4)
    else:
        for acc in ordered_accs:
            scores[acc] = 0.0

    # 5. Graph Construction
    graph = build_graph_from_transactions(snapshot_txns, scores)

    # 6. Motif & Baseline Rule Evaluation
    alerts: List[Dict[str, Any]] = []
    alert_summaries: List[Dict[str, Any]] = []

    # Check metrics availability
    metrics_available = any("ground_truth" in t for t in transactions)

    # Candidate accounts: sort deterministically by score desc, account_id asc
    candidate_accs = sorted(ordered_accs, key=lambda a: (-scores.get(a, 0.0), a))

    alert_idx = 1
    for acc in candidate_accs:
        acc_feats = features_by_account[acc]
        sc = scores.get(acc, 0.0)
        ml_flagged = sc >= threshold

        # Heuristic rules + temporal motifs
        base_rules = evaluate_account_rules(acc_feats)
        motifs = detect_temporal_motifs(snapshot_txns, acc)
        triggered_motifs = [m for m, val in motifs.items() if val]
        all_rules = sorted(list(set(base_rules + triggered_motifs)))
        baseline_flagged = len(all_rules) > 0

        # Account is flagged if either ML model or baseline rules flag it
        if not (ml_flagged or baseline_flagged):
            continue

        # Priority assignment (§9.2, §7.1)
        if sc >= 0.8 or (ml_flagged and baseline_flagged):
            priority = "HIGH"
        elif sc >= 0.5 or ml_flagged or baseline_flagged:
            priority = "MEDIUM"
        else:
            priority = "LOW"

        # Evidence subgraph and evidence path
        evidence = extract_evidence_subgraph(graph, acc)

        # Context flags
        rapid_pt = motifs.get("RAPID_PASS_THROUGH", False)
        context_flags = {
            "shared_device_detected": bool(acc_feats.get("shared_device_user_flag", 0.0) >= 1.0),
            "rapid_pass_through_detected": rapid_pt,
            "note": (
                f"Rapid pass-through detected on {acc}." if rapid_pt
                else "Elevated risk signals detected."
            ),
        }

        # Top reasons
        top_reasons = generate_top_reasons(acc_feats, training_medians)

        # Topology-aware alert fingerprint (§9.2)
        _, fingerprint = compute_alert_fingerprint(
            account_id=acc,
            visible_transactions=snapshot_txns,
            ml_score=sc,
            priority=priority,
            rules_triggered=all_rules,
            as_of=as_of,
        )

        # Review state machine, restoration, and staleness reason attribution (§9.2)
        review_key = (acc, fingerprint)
        if review_key in previous_reviews:
            # Exact fingerprint match (§9.2 Rule 4): restore active review!
            prev = previous_reviews[review_key]
            review = {
                "status": prev.get("status", "OPEN"),
                "is_stale": False,
                "staleness_reason": None,
                "analyst_id": prev.get("analyst_id"),
                "updated_at": prev.get("updated_at"),
                "verdict": prev.get("verdict"),
                "notes": prev.get("notes"),
                "previous_review": None,
            }
        else:
            # Check if any prior review exists for this account under a different fingerprint
            prior_reviews_for_acc = [
                r for (a, f), r in previous_reviews.items()
                if a == acc
            ]
            if prior_reviews_for_acc:
                # Find most recent prior review
                latest_prior = prior_reviews_for_acc[-1]

                # Determine staleness reason (§9.2 Rule 3):
                # historical_snapshot_evidence_divergence: iff a prior reviewed snapshot existed AND
                # direct comparison establishes that relevant evidence associated with account_id
                # (txns, devices, complaints) present in that reviewed snapshot is excluded from current snapshot
                # due to cutoff (t_ingested > as_of or t_complaint_ingested > as_of).
                is_hist_divergence = False
                if as_of is not None and all_raw_transactions:
                    # Collect devices used by acc in all_raw_transactions
                    acc_devices = {
                        raw_t.get("sender_device_id")
                        for raw_t in all_raw_transactions
                        if raw_t.get("sender_account") == acc and raw_t.get("sender_device_id") is not None
                    }
                    for raw_t in all_raw_transactions:
                        touches_acc = (raw_t["sender_account"] == acc or raw_t["receiver_account"] == acc)
                        touches_dev = (raw_t.get("sender_device_id") in acc_devices if acc_devices else False)
                        if touches_acc or touches_dev:
                            t_ing = raw_t.get("ingested_at") or raw_t["timestamp"]
                            if t_ing > as_of:
                                is_hist_divergence = True
                                break
                            if touches_acc and is_complaint_active(raw_t):
                                c_obj = raw_t.get("complaint")
                                if c_obj:
                                    c_ing = c_obj.get("ingested_at") or c_obj["filed_at"]
                                    if c_ing > as_of:
                                        is_hist_divergence = True
                                        break

                staleness_reason = (
                    "historical_snapshot_evidence_divergence"
                    if is_hist_divergence
                    else "evidence_or_score_changed"
                )

                review = {
                    "status": "OPEN",
                    "is_stale": True,
                    "staleness_reason": staleness_reason,
                    "analyst_id": None,
                    "updated_at": None,
                    "verdict": None,
                    "notes": None,
                    "previous_review": copy.deepcopy(latest_prior),
                }
            else:
                # New alert (§9.2 Rule 4)
                review = {
                    "status": "OPEN",
                    "is_stale": False,
                    "staleness_reason": None,
                    "analyst_id": None,
                    "updated_at": None,
                    "verdict": None,
                    "notes": None,
                    "previous_review": None,
                }

        alert_id = f"ALT_{alert_idx:04d}"
        alert_idx += 1

        alert_obj = {
            "alert_id": alert_id,
            "alert_fingerprint": fingerprint,
            "account_id": acc,
            "created_at": created_at,
            "status": review["status"],
            "priority": priority,
            "ml": {
                "score": sc,
                "threshold": threshold,
                "flagged": ml_flagged,
            },
            "baseline": {
                "flagged": baseline_flagged,
                "rules_triggered": all_rules,
            },
            "top_reasons": top_reasons,
            "context_flags": context_flags,
            "review": review,
            "evidence": evidence,
        }
        alerts.append(alert_obj)

        # Lightweight AlertSummary (§7.0)
        summary_review = dict(review)
        summary_review.pop("previous_review", None)
        alert_summary = {
            "alert_id": alert_id,
            "alert_fingerprint": fingerprint,
            "account_id": acc,
            "created_at": created_at,
            "status": review["status"],
            "priority": priority,
            "ml": alert_obj["ml"],
            "baseline": alert_obj["baseline"],
            "top_reasons": top_reasons,
            "context_flags": context_flags,
            "review": summary_review,
        }
        alert_summaries.append(alert_summary)

    return {
        "n_transactions": len(snapshot_txns),
        "n_alerts": len(alerts),
        "as_of": as_of,
        "metrics_available": metrics_available,
        "alerts": alerts,
        "alert_summaries": alert_summaries,
        "graph": graph,
        "features": features_by_account,
        "scores": scores,
    }
