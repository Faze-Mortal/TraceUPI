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


def calculate_contract_v12_binary_metrics(
    y_true: List[int],
    y_pred: List[bool],
) -> Dict[str, Any]:
    """Calculate TP, FP, FN, precision, recall, and F1 per Contract v1.2 Section 8.3 & 9.3.

    Invariants:
      1. When precision and recall are both defined and equal to 0.0 (e.g. TP=0, FP>0, FN>0),
         f1 evaluates strictly to 0.0 (not null).
      2. When precision or recall is mathematically undefined (e.g. total positives is 0),
         f1 evaluates strictly to null.
      3. Precision is null if TP + FP == 0.
      4. Recall is null if TP + FN == 0.
      5. Floats rounded to 4 decimals per Contract Section 7.
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
    if precision is None or recall is None:
        f1 = None
    elif precision == 0.0 and recall == 0.0:
        f1 = 0.0
    elif (precision + recall) > 0:
        f1 = round((2.0 * precision * recall) / (precision + recall), 4)

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
    }


def compute_contract_v12_metrics(
    transactions: List[Dict[str, Any]],
    scores: Dict[str, float],
    features_by_account: Dict[str, Dict[str, float]],
    decision_threshold: float = 0.5,
    budget_k: int = 20,
    timestamp: Optional[str] = None,
    split_seed: int = 42,
) -> Optional[Dict[str, Any]]:
    """Compute comprehensive Contract v1.2 evaluation metrics strictly on held-out accounts.

    Adheres strictly to Contract v1.2 Section 8 and Section 9.3:
      - Evaluated on held-out partition only (seed 42 deterministic split).
      - Precision@K, Recall@K with deterministic tie-breaking for K in {10, 20, 50}.
      - Benign shared-device False Positive Rate (FPR_shared_device).
      - Returns None if transactions lack ground_truth scenario annotations.
    """
    has_gt = any("ground_truth" in t and t["ground_truth"] is not None for t in transactions)
    if not has_gt:
        return None

    if timestamp is None:
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    from ml.baseline_rules import evaluate_account_rules
    from ml.generate_data import assign_account_scenarios
    from ml.train import split_accounts_by_scenario

    scenarios = assign_account_scenarios(transactions)
    labels = {acc: (1 if scenarios[acc] == "mule_ring" else 0) for acc in scenarios}
    train_accs, heldout_accs = split_accounts_by_scenario(scenarios, split_seed=split_seed)

    if not heldout_accs:
        empty_budget = {
            "budget_k": budget_k,
            "k_effective": 0,
            "precision_at_k": None,
            "recall_at_k": None,
        }
        return {
            "generated_at": timestamp,
            "budget_k": budget_k,
            "evaluation": {
                "evaluated_on": "held_out_accounts",
                "n_accounts": 0,
                "n_positive_accounts": 0,
                "n_shared_device_accounts": 0,
            },
            "ml": {
                "threshold": round(float(decision_threshold), 4),
                "precision": None,
                "recall": None,
                "f1": None,
                "true_positives": 0,
                "false_positives": 0,
                "false_negatives": 0,
                "budget_metrics": empty_budget,
                "fairness": {
                    "fpr_benign_shared_device": None,
                    "n_shared_device_evaluated": 0,
                },
            },
            "baseline": {
                "precision": None,
                "recall": None,
                "f1": None,
                "true_positives": 0,
                "false_positives": 0,
                "false_negatives": 0,
                "budget_metrics": empty_budget,
            },
            "by_scenario": [],
        }

    n_accounts = len(heldout_accs)
    n_positive_accounts = sum(labels[a] for a in heldout_accs)
    shared_dev_heldout = [a for a in heldout_accs if scenarios[a] == "shared_device_family"]
    n_shared_device_accounts = len(shared_dev_heldout)

    # 1. ML fixed-threshold evaluation
    ml_flags = {a: (scores.get(a, 0.0) >= decision_threshold) for a in heldout_accs}
    y_true = [labels[a] for a in heldout_accs]
    ml_pred = [ml_flags[a] for a in heldout_accs]
    ml_metrics = calculate_contract_v12_binary_metrics(y_true, ml_pred)
    ml_metrics["threshold"] = round(float(decision_threshold), 4)

    # 2. Fairness metric: FPR for benign shared_device_family cohort (Section 8.2)
    if n_shared_device_accounts == 0:
        fairness = {
            "fpr_benign_shared_device": None,
            "n_shared_device_evaluated": 0,
        }
    else:
        shared_flagged = sum(1 for a in shared_dev_heldout if ml_flags[a])
        fpr = round(shared_flagged / n_shared_device_accounts, 4)
        fairness = {
            "fpr_benign_shared_device": fpr,
            "n_shared_device_evaluated": n_shared_device_accounts,
        }
    ml_metrics["fairness"] = fairness

    # 3. Baseline fixed-threshold evaluation (Section 8.1, Section 8.3)
    bl_rules_map: Dict[str, List[str]] = {}
    bl_flags: Dict[str, bool] = {}
    for a in heldout_accs:
        acc_feats = features_by_account.get(a, {})
        rules = evaluate_account_rules(acc_feats)
        bl_rules_map[a] = rules
        bl_flags[a] = len(rules) > 0

    bl_pred = [bl_flags[a] for a in heldout_accs]
    bl_metrics = calculate_contract_v12_binary_metrics(y_true, bl_pred)

    # 4. Analyst budget ranking for K in {10, 20, 50} (Section 8.1)
    # ML Ranking: Primary ml.score desc, Tie-breaker account_id asc
    sorted_ml = sorted(heldout_accs, key=lambda a: (-scores.get(a, 0.0), a))

    # Baseline Ranking: 1st |rules_triggered| desc, 2nd net_flow_amount desc, 3rd account_id asc
    sorted_bl = sorted(
        heldout_accs,
        key=lambda a: (
            -len(bl_rules_map[a]),
            -features_by_account.get(a, {}).get("net_flow_amount", 0.0),
            a,
        ),
    )

    budget_metrics_by_k: Dict[int, Dict[str, Any]] = {}
    for k_val in (10, 20, 50):
        n_eff = min(k_val, n_accounts)
        # ML top N
        ml_top = sorted_ml[:n_eff]
        ml_pos = sum(labels[a] for a in ml_top)
        ml_prec_k = round(ml_pos / n_eff, 4) if n_eff > 0 else None
        ml_rec_k = round(ml_pos / n_positive_accounts, 4) if n_positive_accounts > 0 else None

        # Baseline top N
        bl_top = sorted_bl[:n_eff]
        bl_pos = sum(labels[a] for a in bl_top)
        bl_prec_k = round(bl_pos / n_eff, 4) if n_eff > 0 else None
        bl_rec_k = round(bl_pos / n_positive_accounts, 4) if n_positive_accounts > 0 else None

        budget_metrics_by_k[k_val] = {
            "ml": {
                "budget_k": k_val,
                "k_effective": n_eff,
                "precision_at_k": ml_prec_k,
                "recall_at_k": ml_rec_k,
            },
            "baseline": {
                "budget_k": k_val,
                "k_effective": n_eff,
                "precision_at_k": bl_prec_k,
                "recall_at_k": bl_rec_k,
            },
        }

    # Inject default or requested budget metrics
    default_budget_k = budget_k if budget_k in budget_metrics_by_k else 20
    ml_metrics["budget_metrics"] = budget_metrics_by_k[default_budget_k]["ml"]
    bl_metrics["budget_metrics"] = budget_metrics_by_k[default_budget_k]["baseline"]

    # 5. Group by scenario for accounts present in heldout set (Section 8.3)
    scenario_groups: Dict[str, List[str]] = {}
    for a in heldout_accs:
        scen = scenarios[a]
        scenario_groups.setdefault(scen, []).append(a)

    by_scenario: List[Dict[str, Any]] = []
    for scen in sorted(scenario_groups.keys()):
        accs = scenario_groups[scen]
        by_scenario.append({
            "scenario": scen,
            "n_accounts": len(accs),
            "ml_flagged": sum(1 for a in accs if ml_flags[a]),
            "baseline_flagged": sum(1 for a in accs if bl_flags[a]),
        })

    return {
        "generated_at": timestamp,
        "budget_k": default_budget_k,
        "evaluation": {
            "evaluated_on": "held_out_accounts",
            "n_accounts": n_accounts,
            "n_positive_accounts": n_positive_accounts,
            "n_shared_device_accounts": n_shared_device_accounts,
        },
        "ml": ml_metrics,
        "baseline": bl_metrics,
        "by_scenario": by_scenario,
        "_budget_metrics_by_k": budget_metrics_by_k,
    }
