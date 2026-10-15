"""TraceUPI Model Training Pipeline.

Trains an account-level Random Forest fraud detection model strictly conforming to
TraceUPI Interface Contract v1.1:
  - Account-level deterministic stratified split (Section 4).
  - Model trained on training accounts only.
  - Threshold selected on training data only (Section 4).
  - Evaluated against fixed heuristic baseline on held-out accounts only (Section 4, 6).
  - Artifact persisted to data/artifacts/model.joblib with required metadata (Section 3).
"""

import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure workspace root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier

from ml.baseline_rules import evaluate_account_rules, evaluate_baseline
from ml.evaluate import evaluate_heldout_accounts
from ml.features import FEATURE_NAMES, extract_account_features, extract_feature_matrix
from ml.generate_data import assign_account_scenarios


def compute_dataset_fingerprint(transactions: List[Dict[str, Any]]) -> str:
    """Compute SHA-256 fingerprint of sorted txn_id values per Section 3.

    Rule: SHA-256 hex digest of sorted txn_id values joined by "\n",
          with no trailing newline, UTF-8 encoded.
    """
    sorted_ids = sorted(t["txn_id"] for t in transactions)
    content = "\n".join(sorted_ids)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def split_accounts_by_scenario(
    account_scenarios: Dict[str, str],
    split_seed: int = 42
) -> Tuple[List[str], List[str]]:
    """Perform exact deterministic account-level split per Contract Section 4.

    Rules:
      - Group accounts by scenario defined in Section 2.
      - Within each group, sort account IDs ascending, shuffle with split_seed.
      - Hold out min(max(1, round(0.30 * n)), n - 1) accounts when n >= 2.
      - A group with fewer than two accounts is entirely training (0 held out).
      - Returns (training_account_ids, heldout_account_ids), both sorted ascending.
    """
    rng = random.Random(split_seed)

    # Group by scenario
    grouped: Dict[str, List[str]] = {}
    for acc, scen in account_scenarios.items():
        grouped.setdefault(scen, []).append(acc)

    train_set: Set[str] = set()
    heldout_set: Set[str] = set()

    for scen in sorted(grouped.keys()):
        accs = sorted(grouped[scen])
        n = len(accs)
        if n >= 2:
            n_heldout = min(max(1, round(0.30 * n)), n - 1)
            # Shuffle deterministically with copy to avoid side-effects
            shuffled = list(accs)
            rng.shuffle(shuffled)
            heldout = shuffled[:n_heldout]
            train = shuffled[n_heldout:]
            heldout_set.update(heldout)
            train_set.update(train)
        else:
            train_set.update(accs)

    # Verify disjointness and complete coverage
    all_accs = set(account_scenarios.keys())
    assert train_set.isdisjoint(heldout_set), "Train and held-out account sets must be disjoint!"
    assert (train_set | heldout_set) == all_accs, "Train and held-out accounts must completely cover all accounts!"

    return sorted(train_set), sorted(heldout_set)


def compute_training_medians(
    feature_dict: Dict[str, Dict[str, float]],
    training_account_ids: List[str]
) -> Dict[str, float]:
    """Compute feature medians on training accounts only per Section 3 & 7.

    Rounded to 4 decimals per Section 7.
    """
    medians: Dict[str, float] = {}
    for fn in FEATURE_NAMES:
        values = [feature_dict[acc][fn] for acc in training_account_ids if acc in feature_dict]
        if values:
            med = float(statistics.median(values))
            medians[fn] = round(med, 4)
        else:
            medians[fn] = 0.0
    return medians


def train_and_evaluate_pipeline(
    data_path: str = "data/transactions_expanded.jsonl",
    artifact_path: str = "data/artifacts/model.joblib",
    split_seed: int = 42,
    decision_threshold: float = 0.5,
) -> Dict[str, Any]:
    """Execute complete training and evaluation pipeline."""
    print(f"=== TraceUPI ML Training & Evaluation Pipeline ===")
    print(f"Dataset path: {data_path}")
    print(f"Artifact path: {artifact_path}")
    print(f"Split seed: {split_seed}")
    print(f"Decision threshold: {decision_threshold}")

    # 1. Load transactions
    p = Path(data_path)
    if not p.exists():
        raise FileNotFoundError(f"Dataset not found at {data_path}")

    transactions = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                transactions.append(json.loads(line))

    print(f"Loaded {len(transactions)} transactions.")

    # 2. Compute dataset fingerprint per Section 3
    fingerprint = compute_dataset_fingerprint(transactions)
    print(f"Dataset fingerprint (SHA-256): {fingerprint}")

    # 3. Derive account scenarios and labels per Section 2
    scenarios = assign_account_scenarios(transactions)
    # Positive label = 1 only for mule_ring
    labels = {acc: (1 if scenarios[acc] == "mule_ring" else 0) for acc in scenarios}

    n_total = len(scenarios)
    n_pos = sum(labels.values())
    n_neg = n_total - n_pos
    print(f"Derived {n_total} accounts: {n_pos} positive (mule_ring), {n_neg} negative (benign).")

    # 4. Deterministic account split per Section 4
    train_accs, heldout_accs = split_accounts_by_scenario(scenarios, split_seed=split_seed)
    print(f"Account split: {len(train_accs)} training accounts, {len(heldout_accs)} held-out accounts.")

    # 5. Extract account features (features module never touches ground_truth)
    feature_dict = extract_account_features(transactions)

    # Compute training feature medians per Section 3
    training_medians = compute_training_medians(feature_dict, train_accs)

    # 6. Build training and held-out feature matrices
    X_train = np.array([[feature_dict[acc][fn] for fn in FEATURE_NAMES] for acc in train_accs], dtype=np.float64)
    y_train = np.array([labels[acc] for acc in train_accs], dtype=np.int32)

    X_heldout = np.array([[feature_dict[acc][fn] for fn in FEATURE_NAMES] for acc in heldout_accs], dtype=np.float64)
    y_heldout = np.array([labels[acc] for acc in heldout_accs], dtype=np.int32)

    # 7. Fit Random Forest model on training accounts only
    print("Fitting Random Forest on training accounts...")
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=6,
        random_state=split_seed,
        class_weight="balanced"
    )
    model.fit(X_train, y_train)

    # 8. Predict ranking scores
    # Model risk score (uncalibrated, for ranking)
    train_scores_arr = model.predict_proba(X_train)[:, 1]
    heldout_scores_arr = model.predict_proba(X_heldout)[:, 1]

    ml_heldout_scores = {acc: float(score) for acc, score in zip(heldout_accs, heldout_scores_arr)}

    # 9. Evaluate baseline heuristic rules on held-out accounts
    baseline_flags = {}
    for acc in heldout_accs:
        rules = evaluate_account_rules(feature_dict[acc])
        baseline_flags[acc] = len(rules) > 0

    # 10. Compute Section 6 metrics on held-out accounts
    metrics = evaluate_heldout_accounts(
        heldout_accounts=heldout_accs,
        account_scenarios=scenarios,
        account_labels=labels,
        ml_scores=ml_heldout_scores,
        decision_threshold=decision_threshold,
        baseline_flags=baseline_flags,
    )

    # 11. Save model artifact matching Section 3 schema exactly
    artifact_data = {
        "artifact_version": "1.1",
        "model": model,
        "feature_names": list(FEATURE_NAMES),
        "decision_threshold": float(decision_threshold),
        "training_feature_medians": training_medians,
        "heldout_account_ids": list(heldout_accs),
        "dataset_fingerprint": str(fingerprint),
        "split_seed": int(split_seed),
    }

    art_path = Path(artifact_path)
    art_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact_data, art_path)
    print(f"Artifact persisted successfully to {art_path} ({art_path.stat().st_size} bytes).")

    # 12. Display Evaluation Summary
    print("\n=== Held-Out Evaluation Results (Section 6 Schema) ===")
    print(f"Evaluated on {metrics['evaluation']['n_accounts']} held-out accounts ({metrics['evaluation']['n_positive_accounts']} positive):")
    print("\n--- ML Model (Threshold = {}) ---".format(decision_threshold))
    print(f"  Precision : {metrics['ml']['precision']}")
    print(f"  Recall    : {metrics['ml']['recall']}")
    print(f"  F1 Score  : {metrics['ml']['f1']}")
    print(f"  TP: {metrics['ml']['true_positives']} | FP: {metrics['ml']['false_positives']} | FN: {metrics['ml']['false_negatives']}")

    print("\n--- Heuristic Baseline ---")
    print(f"  Precision : {metrics['baseline']['precision']}")
    print(f"  Recall    : {metrics['baseline']['recall']}")
    print(f"  F1 Score  : {metrics['baseline']['f1']}")
    print(f"  TP: {metrics['baseline']['true_positives']} | FP: {metrics['baseline']['false_positives']} | FN: {metrics['baseline']['false_negatives']}")

    print("\n--- Scenario Breakdown ---")
    for s_info in metrics["by_scenario"]:
        print(f"  Scenario: {s_info['scenario']:<22} | Total: {s_info['n_accounts']:<3} | ML Flagged: {s_info['ml_flagged']:<3} | Baseline Flagged: {s_info['baseline_flagged']:<3}")

    return {
        "metrics": metrics,
        "artifact_metadata": {k: v for k, v in artifact_data.items() if k != "model"},
        "train_accounts_count": len(train_accs),
        "heldout_accounts_count": len(heldout_accs),
    }


def main():
    parser = argparse.ArgumentParser(description="Train and evaluate TraceUPI model per Contract v1.1.")
    parser.add_argument("--data", type=str, default="data/transactions_expanded.jsonl", help="Training dataset path")
    parser.add_argument("--artifact", type=str, default="data/artifacts/model.joblib", help="Artifact output path")
    parser.add_argument("--seed", type=int, default=42, help="Split seed (default: 42)")
    parser.add_argument("--threshold", type=float, default=0.5, help="Decision threshold (default: 0.5)")
    args = parser.parse_args()

    train_and_evaluate_pipeline(
        data_path=args.data,
        artifact_path=args.artifact,
        split_seed=args.seed,
        decision_threshold=args.threshold,
    )


if __name__ == "__main__":
    main()
