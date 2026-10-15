"""Smoke test for ml/features.py using data/transactions.jsonl."""

import json
import math
import sys
import time
from pathlib import Path

# Ensure workspace root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.features import (
    FEATURE_NAMES,
    extract_account_features,
    extract_feature_matrix,
)

def run_smoke_test(data_path: Path = Path("data/transactions.jsonl")) -> None:
    print(f"\n=== TraceUPI Feature Engineering Smoke Test ===")
    print(f"Loading transactions from: {data_path}")

    if not data_path.exists():
        print(f"ERROR: {data_path} not found!")
        sys.exit(1)

    transactions = []
    with open(data_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if line:
                transactions.append(json.loads(line))

    print(f"Loaded {len(transactions)} transactions.")

    # 1. Feature Extraction Time & Correctness
    t0 = time.perf_counter()
    features_by_acc = extract_account_features(transactions)
    dt_ms = (time.perf_counter() - t0) * 1000.0

    print(f"Extracted features for {len(features_by_acc)} accounts in {dt_ms:.2f} ms.")

    # Collect ground-truth accounts from transactions
    all_senders = {t["sender_account"] for t in transactions}
    all_receivers = {t["receiver_account"] for t in transactions}
    all_expected_accounts = all_senders | all_receivers

    assert len(features_by_acc) == len(all_expected_accounts), (
        f"Expected {len(all_expected_accounts)} accounts, got {len(features_by_acc)}"
    )
    assert set(features_by_acc.keys()) == all_expected_accounts, "Account set mismatch!"

    # 2. Ascending order verification
    sorted_accs = sorted(all_expected_accounts)
    assert list(features_by_acc.keys()) == sorted_accs, "Accounts are not sorted ascending!"

    # 3. Numeric Integrity across all accounts and 25 features
    nan_count = 0
    inf_count = 0
    non_float_count = 0

    for acc, feats in features_by_acc.items():
        assert len(feats) == len(FEATURE_NAMES), f"{acc} has {len(feats)} features, expected {len(FEATURE_NAMES)}"
        for fname in FEATURE_NAMES:
            val = feats[fname]
            if not isinstance(val, float):
                non_float_count += 1
            if math.isnan(val):
                nan_count += 1
            if math.isinf(val):
                inf_count += 1

    print(f"Numerical checks across {len(features_by_acc) * len(FEATURE_NAMES)} values:")
    print(f"  - Non-float values: {non_float_count}")
    print(f"  - NaN values: {nan_count}")
    print(f"  - Infinite values: {inf_count}")

    assert non_float_count == 0, f"Found {non_float_count} non-float values!"
    assert nan_count == 0, f"Found {nan_count} NaNs!"
    assert inf_count == 0, f"Found {inf_count} Infs!"

    # 4. Matrix Extraction Test
    ordered_accs, matrix = extract_feature_matrix(transactions)
    assert ordered_accs == sorted_accs
    assert len(matrix) == len(sorted_accs)
    assert all(len(row) == len(FEATURE_NAMES) for row in matrix)
    print(f"Feature matrix shape: ({len(matrix)}, {len(FEATURE_NAMES)})")

    # 5. Device sharing statistics check
    shared_device_users = [
        acc for acc, feats in features_by_acc.items()
        if feats["shared_device_user_flag"] == 1.0
    ]
    print(f"Accounts with shared_device_user_flag == 1.0: {len(shared_device_users)}")
    print(f"  Sample shared-device accounts: {shared_device_users[:6]}")

    # 6. Sample Account Printout
    sample_acc = sorted_accs[0]
    print(f"\nSample Feature Vector for {sample_acc}:")
    for fname in FEATURE_NAMES:
        print(f"  {fname:<30}: {features_by_acc[sample_acc][fname]}")

    print(f"\n[PASS] All smoke test assertions succeeded cleanly for {data_path}!")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_smoke_test(Path(sys.argv[1]))
    else:
        run_smoke_test(Path("data/transactions.jsonl"))
        expanded = Path("data/transactions_expanded.jsonl")
        if expanded.exists():
            run_smoke_test(expanded)
