"""TraceUPI Evaluation Module.

Computes precision, recall, F1, and scenario breakdowns for both the ML model
and the rule-based baseline strictly on held-out accounts per Interface Contract v1.1.
Adheres to zero-denominator rules and missing metrics specifications.
"""

import datetime
from typing import Any, Dict, List, Optional, Tuple


def calculate_binary_metrics(
    y_true: List[int],
    y_pred: List[bool]
) -> Dict[str, Any]:
    """Calculate TP, FP, FN, precision, recall, and F1 with contract zero-denominator handling.

    Contract Section 6 rules:
      - precision is None if TP + FP == 0.
      - recall is None if TP + FN == 0.
      - f1 is None if either precision or recall is None, or if both are zero.
      - Floats are rounded to 4 decimals per Section 7.
    """
    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp is True)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp is True)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp is False)

    precision: Optional[float] = None
    if (tp + fp) > 0:
        precision = round(tp / (tp + fp), 4)

    recall: Optional[float] = None
    if (tp + fn) > 0:
        recall = round(tp / (tp + fn), 4)

    f1: Optional[float] = None
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = round((2.0 * precision * recall) / (precision + recall), 4)

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
    }


def evaluate_heldout_accounts(
    heldout_accounts: List[str],
    account_scenarios: Dict[str, str],
    account_labels: Dict[str, int],
    ml_scores: Dict[str, float],
    decision_threshold: float,
    baseline_flags: Dict[str, bool],
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate ML and baseline flags on held-out accounts per Section 6 schema.

    Args:
        heldout_accounts: List of account IDs in the held-out split.
        account_scenarios: Dict mapping account ID -> scenario ("mule_ring", etc.).
        account_labels: Dict mapping account ID -> binary label (1 for mule_ring, 0 otherwise).
        ml_scores: Dict mapping account ID -> float ranking score.
        decision_threshold: Fixed threshold; account is flagged if score >= threshold.
        baseline_flags: Dict mapping account ID -> bool flag.
        timestamp: Optional ISO 8601 UTC string; defaults to current UTC time.

    Returns:
        Contract Section 6 metrics dictionary.
    """
    if timestamp is None:
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not heldout_accounts:
        return {
            "generated_at": timestamp,
            "evaluation": {
                "evaluated_on": "held_out_accounts",
                "n_accounts": 0,
                "n_positive_accounts": 0,
            },
            "ml": {
                "precision": None,
                "recall": None,
                "f1": None,
                "true_positives": 0,
                "false_positives": 0,
                "false_negatives": 0,
            },
            "baseline": {
                "precision": None,
                "recall": None,
                "f1": None,
                "true_positives": 0,
                "false_positives": 0,
                "false_negatives": 0,
            },
            "by_scenario": [],
        }

    # Evaluate on held-out accounts only
    y_true = [account_labels[acc] for acc in heldout_accounts]
    ml_pred = [ml_scores[acc] >= decision_threshold for acc in heldout_accounts]
    bl_pred = [baseline_flags.get(acc, False) for acc in heldout_accounts]

    ml_metrics = calculate_binary_metrics(y_true, ml_pred)
    bl_metrics = calculate_binary_metrics(y_true, bl_pred)

    # Group by scenario for accounts present in heldout set
    scenario_groups: Dict[str, List[str]] = {}
    for acc in heldout_accounts:
        scen = account_scenarios[acc]
        scenario_groups.setdefault(scen, []).append(acc)

    by_scenario = []
    # Section 6: sorted alphabetically, omitted if no held-out accounts
    for scen in sorted(scenario_groups.keys()):
        accs = scenario_groups[scen]
        by_scenario.append({
            "scenario": scen,
            "n_accounts": len(accs),
            "ml_flagged": sum(1 for a in accs if (ml_scores[a] >= decision_threshold)),
            "baseline_flagged": sum(1 for a in accs if baseline_flags.get(a, False)),
        })

    return {
        "generated_at": timestamp,
        "evaluation": {
            "evaluated_on": "held_out_accounts",
            "n_accounts": len(heldout_accounts),
            "n_positive_accounts": sum(y_true),
        },
        "ml": ml_metrics,
        "baseline": bl_metrics,
        "by_scenario": by_scenario,
    }
