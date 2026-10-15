"""TraceUPI Counterfactual Engine.

Answers what-if investigative questions by perturbing evidence in a clean sandbox
strictly conforming to Contract v1.2 §10:
  - Deep-copies original inputs to guarantee sandbox isolation without mutating active state.
  - Allows removal of valid transfer edges only (rejects unknown edge IDs and non-transfer edges).
  - Implements device-sharing and complaint-suppression toggles by perturbing underlying inputs.
  - Recomputes model score, decision threshold flagging, and triggered baseline/temporal rules.
  - Computes signed delta: counterfactual_score - original_score.
  - Generates hypothesis explanation strictly starting with "Hypothesis:" and disclaiming legal proof.
  - Rejects empty or malformed requests with structured errors for HTTP 422 mapping.
"""

import copy
from typing import Any, Dict, List, Optional, Set, Tuple

import joblib

from ml.baseline_rules import evaluate_account_rules
from ml.features import extract_account_features, extract_feature_matrix
from ml.graph import build_graph_from_transactions, extract_evidence_subgraph
from ml.pipeline import detect_temporal_motifs, normalize_and_filter_snapshot


class CounterfactualError(ValueError):
    """Exception raised for invalid counterfactual interventions per Contract §10.1."""

    def __init__(self, detail: str, error: Optional[str] = None):
        self.detail = detail
        self.error = error
        msg = f"{detail}: {error}" if error else detail
        super().__init__(msg)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict matching Contract v1.2 error schema."""
        d = {"detail": self.detail}
        if self.error:
            d["error"] = self.error
        return d


def recompute_counterfactual(
    alert: Dict[str, Any],
    transactions: List[Dict[str, Any]],
    remove_edge_ids: Optional[List[str]] = None,
    suppress_device_sharing: bool = False,
    suppress_complaints: bool = False,
    as_of: Optional[str] = None,
    model_artifact: Optional[Dict[str, Any]] = None,
    model_artifact_path: str = "data/artifacts/model.joblib",
) -> Dict[str, Any]:
    """Execute counterfactual what-if perturbation in an isolated sandbox.

    Args:
        alert: Original Alert dict (matching Contract §7.1).
        transactions: Transaction records for the baseline snapshot.
        remove_edge_ids: Optional list of transfer edge IDs to remove from evidence.
        suppress_device_sharing: Toggle to isolate account's hardware usage from other senders.
        suppress_complaints: Toggle to suppress counterparty fraud complaints on account.
        as_of: Optional ISO 8601 UTC timestamp cutoff.
        model_artifact: Optional loaded model artifact dict. If None, loaded from path.
        model_artifact_path: Path to model.joblib.

    Returns:
        Counterfactual result dictionary strictly matching Contract v1.2 §10.1:
        {
            "alert_id": str,
            "account_id": str,
            "original_score": float,
            "counterfactual_score": float,
            "score_delta": float,
            "original_flagged": bool,
            "counterfactual_flagged": bool,
            "rules_removed": List[str],
            "rules_added": List[str],
            "plausible_benign_alternative": str,
        }

    Raises:
        CounterfactualError: If request is empty or specifies invalid/non-transfer edge IDs.
    """
    # 1. Validation rule (§10.1): Empty request rejection
    clean_remove_edge_ids = list(remove_edge_ids) if remove_edge_ids else []
    if (
        not clean_remove_edge_ids
        and not suppress_device_sharing
        and not suppress_complaints
    ):
        raise CounterfactualError(detail="empty_counterfactual_request")

    account_id = alert["account_id"]
    alert_id = alert["alert_id"]

    # 2. Validation rule (§10.1): Supported edge removals
    # remove_edge_ids must contain only valid edge IDs present in evidence.edges where type == "transfer"
    evidence_edges = {
        e["id"]: e
        for e in alert.get("evidence", {}).get("edges", [])
    }

    txns_to_remove: Set[str] = set()
    removed_edge_details: List[str] = []

    for eid in clean_remove_edge_ids:
        if eid not in evidence_edges:
            raise CounterfactualError(
                detail="invalid_counterfactual_intervention",
                error="unknown_or_unsupported_edge_id",
            )
        edge = evidence_edges[eid]
        if edge.get("type") != "transfer":
            raise CounterfactualError(
                detail="invalid_counterfactual_intervention",
                error="unknown_or_unsupported_edge_id",
            )
        tid = edge.get("txn_id")
        if tid:
            txns_to_remove.add(tid)
            amt = edge.get("amount_inr")
            amt_str = f" (Rs {amt:,.2f})" if amt is not None else ""
            removed_edge_details.append(f"transfer {tid}{amt_str}")

    # 3. Sandbox Isolation (§10 Operational Rule 2): Deep copy
    sandbox_txns = copy.deepcopy(transactions)

    # 4. Apply Interventions on underlying transaction data
    # (a) Edge removal: drop corresponding transfer transactions
    if txns_to_remove:
        sandbox_txns = [t for t in sandbox_txns if t["txn_id"] not in txns_to_remove]

    # (b) Device sharing suppression: isolate account's devices so no other sender shares them
    if suppress_device_sharing:
        acc_devices = {
            t["sender_device_id"]
            for t in sandbox_txns
            if t.get("sender_account") == account_id and t.get("sender_device_id") is not None
        }
        for t in sandbox_txns:
            # If another account used one of account_id's devices, unlink that device in sandbox
            if t.get("sender_account") != account_id and t.get("sender_device_id") in acc_devices:
                t["sender_device_id"] = None

    # (c) Complaint suppression: remove active complaints on account_id
    if suppress_complaints:
        for t in sandbox_txns:
            if t.get("sender_account") == account_id or t.get("receiver_account") == account_id:
                t["complaint_filed"] = False
                t["complaint"] = None

    # 5. Load model artifact
    if model_artifact is None:
        model_artifact = joblib.load(model_artifact_path)

    model = model_artifact["model"]
    threshold = float(model_artifact.get("decision_threshold", 0.5))

    # 6. Recompute snapshot, features, model score, and rules
    norm_txns = normalize_and_filter_snapshot(sandbox_txns, as_of=as_of)
    features_by_account = extract_account_features(norm_txns)
    ordered_accs, matrix = extract_feature_matrix(norm_txns)

    # Counterfactual ML score for account_id
    if account_id in ordered_accs and matrix:
        idx = ordered_accs.index(account_id)
        probs = model.predict_proba([matrix[idx]])
        cf_score = round(float(probs[0][1]), 4)
    else:
        # If account was removed entirely by edge deletions
        cf_score = 0.0

    # Counterfactual rules & motifs
    cf_feats = features_by_account.get(account_id, {})
    cf_base_rules = evaluate_account_rules(cf_feats) if cf_feats else []
    cf_motifs = detect_temporal_motifs(norm_txns, account_id)
    cf_triggered_motifs = [m for m, val in cf_motifs.items() if val]
    cf_rules = sorted(list(set(cf_base_rules + cf_triggered_motifs)))

    cf_ml_flagged = cf_score >= threshold
    cf_baseline_flagged = len(cf_rules) > 0
    cf_flagged = cf_ml_flagged or cf_baseline_flagged

    # Original values
    orig_score = float(alert.get("ml", {}).get("score", 0.0))
    orig_flagged = bool(
        alert.get("ml", {}).get("flagged", False)
        or alert.get("baseline", {}).get("flagged", False)
    )
    orig_rules = list(alert.get("baseline", {}).get("rules_triggered", []))

    # Signed delta: cf_score - orig_score (§10 Operational Rule 1)
    score_delta = round(cf_score - orig_score, 4)

    rules_removed = sorted([r for r in orig_rules if r not in cf_rules])
    rules_added = sorted([r for r in cf_rules if r not in orig_rules])

    # 7. Recompute Graph Evidence
    cf_scores: Dict[str, float] = {}
    if matrix:
        all_probs = model.predict_proba(matrix)
        for i, acc in enumerate(ordered_accs):
            cf_scores[acc] = round(float(all_probs[i][1]), 4)
    cf_graph = build_graph_from_transactions(norm_txns, cf_scores)
    cf_evidence = extract_evidence_subgraph(cf_graph, account_id)

    # 8. Generate Plausible Benign Alternative (§10 Operational Rule 3)
    # Must begin with "Hypothesis:" and avoid claiming proof of innocence or guilt
    interventions_desc_list = []
    if removed_edge_details:
        interventions_desc_list.append(f"transfer ({', '.join(removed_edge_details)}) is excluded")
    if suppress_device_sharing:
        interventions_desc_list.append("device sharing is treated as private hardware")
    if suppress_complaints:
        interventions_desc_list.append("counterparty fraud complaints are suppressed")

    interventions_str = "; ".join(interventions_desc_list)

    if score_delta < 0:
        if not cf_flagged:
            effect_str = (
                f"risk score drops by {abs(score_delta):.4f} (from {orig_score:.4f} to {cf_score:.4f}), "
                f"falling below the decision threshold. Alert status resets to unflagged."
            )
        else:
            effect_str = (
                f"risk score drops by {abs(score_delta):.4f} (from {orig_score:.4f} to {cf_score:.4f}), "
                f"though residual risk signals remain."
            )
        rule_str = f" Rules removed: {', '.join(rules_removed)}." if rules_removed else ""
        benign_pattern = (
            " Plausible benign pattern: Routine peer-to-peer commerce or isolated multi-user device "
            "usage rather than coordinated mule ring layering."
        )
    elif score_delta > 0:
        effect_str = (
            f"risk score increases by {score_delta:.4f} (from {orig_score:.4f} to {cf_score:.4f})."
        )
        rule_str = f" Rules added: {', '.join(rules_added)}." if rules_added else ""
        benign_pattern = (
            " Plausible pattern: Excluding this transfer worsens transaction flow ratios or failure concentration."
        )
    else:
        effect_str = f"risk score remains unchanged at {orig_score:.4f}."
        rule_str = ""
        benign_pattern = (
            " Plausible pattern: The intervention does not cross decision tree split boundaries."
        )

    disclaimer = " Note: Simulation does not constitute legal proof of causation or innocence."

    plausible_benign_alternative = (
        f"Hypothesis: If {interventions_str}, {effect_str}{rule_str}{benign_pattern}{disclaimer}"
    )

    return {
        "alert_id": alert_id,
        "account_id": account_id,
        "original_score": orig_score,
        "counterfactual_score": cf_score,
        "score_delta": score_delta,
        "original_flagged": orig_flagged,
        "counterfactual_flagged": cf_flagged,
        "rules_removed": rules_removed,
        "rules_added": rules_added,
        "plausible_benign_alternative": plausible_benign_alternative,
        "evidence": cf_evidence,
    }
