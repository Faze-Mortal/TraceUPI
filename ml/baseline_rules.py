"""TraceUPI Rule-Based Heuristic Baseline.

Implements fixed, explainable heuristic fraud-detection rules per Interface Contract v1.1:
  - Parameters are fixed before evaluation and never tuned on held-out data.
  - Zero access to ground_truth or labels.
  - An account is flagged if and only if at least one rule is triggered.
"""

from typing import Any, Dict, List, Set, Tuple

# Fixed baseline rule threshold definitions
BASELINE_RULES = {
    "HIGH_FAN_IN": {
        "description": "Received payments from 10 or more distinct senders (mule aggregation pattern).",
        "feature": "fan_in_count",
        "threshold": 10.0,
    },
    "HIGH_INBOUND_COMPLAINT": {
        "description": "At least one incoming payment had a fraud complaint filed against it.",
        "feature": "complaint_count_as_receiver",
        "threshold": 1.0,
    },
    "HIGH_INFLOW_ACCUMULATOR": {
        "description": "In-degree to out-degree ratio >= 3.0 with large inbound volume (>= 50,000 INR).",
        "feature": "fan_ratio",
        "threshold": 3.0,
        "secondary_feature": "amount_received_total",
        "secondary_threshold": 50000.0,
    },
    "UNUSUAL_FAILURE_SPIKE": {
        "description": "Outbound failure rate >= 20% with at least 5 outbound attempts.",
        "feature": "failure_rate_sent",
        "threshold": 0.20,
        "secondary_feature": "txn_count_sent",
        "secondary_threshold": 5.0,
    },
}


def evaluate_account_rules(account_features: Dict[str, float]) -> List[str]:
    """Evaluate fixed heuristic baseline rules on a single account's features.

    Args:
        account_features: Dictionary mapping feature name to numerical float value.

    Returns:
        List of triggered rule names, sorted alphabetically.
    """
    triggered: List[str] = []

    # Rule 1: High Fan-In
    if account_features.get("fan_in_count", 0.0) >= 10.0:
        triggered.append("HIGH_FAN_IN")

    # Rule 2: High Inbound Complaint
    if account_features.get("complaint_count_as_receiver", 0.0) >= 1.0:
        triggered.append("HIGH_COMPLAINT_RATE")

    # Rule 3: High Inflow Accumulator
    if (
        account_features.get("fan_ratio", 0.0) >= 3.0
        and account_features.get("amount_received_total", 0.0) >= 50000.0
    ):
        triggered.append("HIGH_INFLOW_ACCUMULATOR")

    # Rule 4: Unusual Failure Spike
    if (
        account_features.get("failure_rate_sent", 0.0) >= 0.20
        and account_features.get("txn_count_sent", 0.0) >= 5.0
    ):
        triggered.append("UNUSUAL_FAILURE_SPIKE")

    return sorted(triggered)


def evaluate_baseline(
    all_account_features: Dict[str, Dict[str, float]]
) -> Dict[str, Dict[str, Any]]:
    """Evaluate the baseline across a dictionary of accounts.

    Args:
        all_account_features: Dict of account_id -> {feature_name: value}.

    Returns:
        Dict of account_id -> {
            "flagged": bool,
            "rules_triggered": List[str]
        }
    """
    results: Dict[str, Dict[str, Any]] = {}
    for acc in sorted(all_account_features.keys()):
        rules = evaluate_account_rules(all_account_features[acc])
        results[acc] = {
            "flagged": len(rules) > 0,
            "rules_triggered": rules,
        }
    return results
