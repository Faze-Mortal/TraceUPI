"""TraceUPI Account-Level Feature Engineering.

Transforms raw UPI transaction records into deterministic, numerical account-level
features for fraud detection and risk ranking. Strictly adheres to TraceUPI
Interface Contract v1.1:
  - No access to or reliance on `ground_truth`, `scenario`, or labels.
  - Device statistics are strictly sender-side only (Limitation L7).
  - Pure numerical values: zero NaNs, infinities, or nulls.
  - Input transactions are never mutated.
  - Standard library only.
"""

from collections import defaultdict
import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

# Ordered list of all features produced by this module.
# Must match the order of columns in feature matrices.
FEATURE_NAMES: List[str] = [
    # 1. Transaction Volumes & Counts
    "txn_count_sent",
    "txn_count_received",
    "txn_count_total",
    "txn_success_sent",
    "txn_success_received",
    "txn_failed_sent",
    "txn_failed_received",
    "failure_rate_sent",
    # 2. Monetary Amounts & Aggregates (INR)
    "amount_sent_total",
    "amount_received_total",
    "net_flow_amount",
    "amount_sent_avg",
    "amount_received_avg",
    "amount_sent_max",
    "amount_received_max",
    "amount_max_overall",
    # 3. Graph Topology & Counterparties
    "fan_in_count",
    "fan_out_count",
    "counterparty_count_total",
    "fan_ratio",
    # 4. Complaints
    "complaint_count_as_receiver",
    "complaint_count_as_sender",
    # 5. Sender-Side Device Sharing (L7)
    "devices_used_count",
    "max_senders_on_used_devices",
    "shared_device_user_flag",
]

# Detailed feature descriptions and exact formulas for every feature
FEATURE_DEFINITIONS: Dict[str, str] = {
    "txn_count_sent": "Count of transactions where the account is the sender.",
    "txn_count_received": "Count of transactions where the account is the receiver.",
    "txn_count_total": "Total transaction count: txn_count_sent + txn_count_received.",
    "txn_success_sent": "Count of successful outgoing transactions (status == 'SUCCESS').",
    "txn_success_received": "Count of successful incoming transactions (status == 'SUCCESS').",
    "txn_failed_sent": "Count of failed outgoing transactions (status == 'FAILED').",
    "txn_failed_received": "Count of failed incoming transactions (status == 'FAILED').",
    "failure_rate_sent": "Failed sent ratio: txn_failed_sent / txn_count_sent (0.0 if txn_count_sent == 0).",
    "amount_sent_total": "Sum of amount_inr for all outgoing transactions (0.0 if none).",
    "amount_received_total": "Sum of amount_inr for all incoming transactions (0.0 if none).",
    "net_flow_amount": "Net INR flow: amount_received_total - amount_sent_total.",
    "amount_sent_avg": "Mean sent amount: amount_sent_total / txn_count_sent (0.0 if txn_count_sent == 0).",
    "amount_received_avg": "Mean received amount: amount_received_total / txn_count_received (0.0 if txn_count_received == 0).",
    "amount_sent_max": "Maximum single outgoing transaction amount (0.0 if none).",
    "amount_received_max": "Maximum single incoming transaction amount (0.0 if none).",
    "amount_max_overall": "Maximum transaction amount overall: max(amount_sent_max, amount_received_max).",
    "fan_in_count": "Count of unique counterparty accounts that sent money to this account.",
    "fan_out_count": "Count of unique counterparty accounts that received money from this account.",
    "counterparty_count_total": "Total unique counterparties: size of (senders_to | receivers_from).",
    "fan_ratio": "In-degree to out-degree ratio: fan_in_count / (fan_out_count + 1.0).",
    "complaint_count_as_receiver": "Count of incoming transactions where complaint_filed is True.",
    "complaint_count_as_sender": "Count of outgoing transactions where complaint_filed is True.",
    "devices_used_count": "Count of unique sender_device_ids used by this account (sender-side only).",
    "max_senders_on_used_devices": "Maximum number of distinct senders associated with any device used by this account.",
    "shared_device_user_flag": "1.0 if max_senders_on_used_devices >= 2.0, else 0.0.",
}

# Exact ID and enum patterns per Contract v1.2
_TXN_ID_RE = re.compile(r"^T\d{6}$")
_ACC_ID_RE = re.compile(r"^ACC_\d{4}$")
_DEV_ID_RE = re.compile(r"^DEV_\d{4}$")
_CMP_ID_RE = re.compile(r"^CMP_\d{4}$")
_MER_ID_RE = re.compile(r"^MER_\d{4}$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_ALLOWED_STATUSES = {"SUCCESS", "FAILED"}
_ALLOWED_COMPLAINT_CATEGORIES = {
    "UNAUTHORIZED_TRANSACTION",
    "PHISHING_SCAM",
    "NON_DELIVERY_GOODS",
    "UNSPECIFIED",
}


def is_complaint_active(txn: Dict[str, Any]) -> bool:
    """Determine whether a complaint event is active on this transaction per Contract v1.2 §2.4.

    Precedence & Validation:
    1. If `complaint` dict is present and `complaint_filed` is False -> Conflicting telemetry (raises ValueError).
    2. If `complaint` dict is present -> True.
    3. If `complaint` is null/omitted and `complaint_filed` is True -> True (legacy boolean fallback).
    4. Otherwise -> False.
    """
    complaint_obj = txn.get("complaint")
    complaint_flag = txn.get("complaint_filed")
    if complaint_obj is not None and complaint_flag is False:
        tid = txn.get("txn_id", "UNKNOWN")
        raise ValueError(
            f"Txn #{tid}: conflicting complaint telemetry (complaint object provided but complaint_filed is False)"
        )
    if complaint_obj is not None:
        return True
    return bool(complaint_flag)


def validate_feature_input(transactions: Any) -> None:
    """Validate that input transactions conform to the contract schema without reading ground_truth."""
    if not isinstance(transactions, list):
        raise TypeError(f"Expected transactions to be a list, got {type(transactions).__name__}")

    seen_txn_ids: Set[str] = set()

    for idx, txn in enumerate(transactions):
        if not isinstance(txn, dict):
            raise TypeError(f"Transaction #{idx} is not a dictionary (got {type(txn).__name__})")

        # Required fields for feature extraction per Contract v1.2 §2.3
        required_keys = (
            "txn_id",
            "timestamp",
            "sender_account",
            "receiver_account",
            "amount_inr",
            "status",
        )
        missing = [k for k in required_keys if k not in txn]
        if missing:
            raise ValueError(f"Transaction #{idx} missing required fields: {missing}")

        tid = txn["txn_id"]
        if not isinstance(tid, str) or not _TXN_ID_RE.fullmatch(tid):
            raise ValueError(f"Transaction #{idx}: invalid txn_id '{tid}' (expected T + 6 digits)")

        if tid in seen_txn_ids:
            raise ValueError(f"Duplicate txn_id '{tid}' at index {idx}")
        seen_txn_ids.add(tid)

        ts = txn["timestamp"]
        if not isinstance(ts, str) or not _TIMESTAMP_RE.fullmatch(ts):
            raise ValueError(f"Txn #{tid}: invalid timestamp '{ts}' (expected ISO 8601 UTC YYYY-MM-DDTHH:MM:SSZ)")

        sender = txn["sender_account"]
        receiver = txn["receiver_account"]
        if not isinstance(sender, str) or not _ACC_ID_RE.fullmatch(sender):
            raise ValueError(f"Txn #{tid}: invalid sender_account '{sender}' (expected ACC_ + 4 digits)")
        if not isinstance(receiver, str) or not _ACC_ID_RE.fullmatch(receiver):
            raise ValueError(f"Txn #{tid}: invalid receiver_account '{receiver}' (expected ACC_ + 4 digits)")
        if sender == receiver:
            raise ValueError(f"Txn #{tid}: sender_account cannot equal receiver_account ('{sender}')")

        amt = txn["amount_inr"]
        # Python treats bool as subclass of int, so reject booleans explicitly
        if isinstance(amt, bool) or not isinstance(amt, (int, float)) or amt <= 0 or math.isnan(amt) or math.isinf(amt):
            raise ValueError(f"Txn #{tid}: invalid amount_inr '{amt}' (must be a positive number)")

        status = txn["status"]
        if status not in _ALLOWED_STATUSES:
            raise ValueError(f"Txn #{tid}: invalid status '{status}' (expected 'SUCCESS' or 'FAILED')")

        # Nullable device telemetry per Contract v1.2 §2.3 and §5.2
        if "sender_device_id" in txn and txn["sender_device_id"] is not None:
            dev = txn["sender_device_id"]
            if not isinstance(dev, str) or not _DEV_ID_RE.fullmatch(dev):
                raise ValueError(f"Txn #{tid}: invalid sender_device_id '{dev}' (expected DEV_ + 4 digits)")

        # Optional merchant telemetry per Contract v1.2 §2.3
        if "merchant_id" in txn and txn["merchant_id"] is not None:
            mer = txn["merchant_id"]
            if not isinstance(mer, str) or not _MER_ID_RE.fullmatch(mer):
                raise ValueError(f"Txn #{tid}: invalid merchant_id '{mer}' (expected MER_ + 4 digits)")

        # Dual complaint telemetry & conflict validation per Contract v1.2 §2.4
        complaint_obj = txn.get("complaint")
        complaint_filed_flag = txn.get("complaint_filed")

        if complaint_obj is not None and complaint_filed_flag is False:
            raise ValueError(
                f"Txn #{tid}: conflicting complaint telemetry (complaint object provided but complaint_filed is False)"
            )

        if complaint_filed_flag is not None and type(complaint_filed_flag) is not bool:
            raise ValueError(f"Txn #{tid}: invalid complaint_filed '{complaint_filed_flag}' (must be a boolean)")

        if complaint_obj is not None:
            if not isinstance(complaint_obj, dict):
                raise ValueError(f"Txn #{tid}: complaint must be a dictionary")

            cid = complaint_obj.get("complaint_id")
            if not isinstance(cid, str) or not _CMP_ID_RE.fullmatch(cid):
                raise ValueError(f"Txn #{tid}: invalid complaint.complaint_id '{cid}' (expected CMP_ + 4 digits)")

            filed_at = complaint_obj.get("filed_at")
            if not isinstance(filed_at, str) or not _TIMESTAMP_RE.fullmatch(filed_at):
                raise ValueError(f"Txn #{tid}: invalid complaint.filed_at '{filed_at}'")
            if filed_at < ts:
                raise ValueError(f"Txn #{tid}: complaint.filed_at '{filed_at}' cannot be before transaction timestamp '{ts}'")

            if "ingested_at" in complaint_obj and complaint_obj["ingested_at"] is not None:
                ingested_at = complaint_obj["ingested_at"]
                if not isinstance(ingested_at, str) or not _TIMESTAMP_RE.fullmatch(ingested_at):
                    raise ValueError(f"Txn #{tid}: invalid complaint.ingested_at '{ingested_at}'")
                if ingested_at < filed_at:
                    raise ValueError(f"Txn #{tid}: complaint.ingested_at '{ingested_at}' cannot be before filed_at '{filed_at}'")

            if "category" in complaint_obj and complaint_obj["category"] is not None:
                cat = complaint_obj["category"]
                if cat not in _ALLOWED_COMPLAINT_CATEGORIES:
                    raise ValueError(f"Txn #{tid}: invalid complaint.category '{cat}'")


def extract_account_features(transactions: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Extract account-level features from transactions.

    Args:
        transactions: List of transaction dictionaries matching Contract v1.2.
            The list and its dictionaries are never mutated.

    Returns:
        Dict mapping account_id -> Dict of feature_name -> numerical value.
        Accounts are returned sorted ascending by account ID.
        If transactions is empty, returns an empty dictionary.
    """
    if not transactions:
        return {}

    validate_feature_input(transactions)

    # Global pass 1: Map each sender_device_id to the set of distinct sender accounts
    # Contract L7: Device data is sender-side only. We NEVER infer a receiver's device.
    # Contract §5.2: Unobserved devices (None or omitted) contribute zero device observations.
    device_to_senders: Dict[str, Set[str]] = defaultdict(set)
    for txn in transactions:
        dev = txn.get("sender_device_id")
        if dev is not None:
            device_to_senders[dev].add(txn["sender_account"])

    # Global pass 2: Collect all accounts (senders and receivers)
    all_accounts: Set[str] = set()
    for txn in transactions:
        all_accounts.add(txn["sender_account"])
        all_accounts.add(txn["receiver_account"])

    # Account accumulators
    sent_txns: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    received_txns: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    used_devices: Dict[str, Set[str]] = defaultdict(set)

    for txn in transactions:
        s = txn["sender_account"]
        r = txn["receiver_account"]
        sent_txns[s].append(txn)
        received_txns[r].append(txn)
        dev = txn.get("sender_device_id")
        if dev is not None:
            used_devices[s].add(dev)

    features_by_account: Dict[str, Dict[str, float]] = {}

    for acc in sorted(all_accounts):
        s_list = sent_txns.get(acc, [])
        r_list = received_txns.get(acc, [])

        # 1. Transaction Volumes & Counts
        count_sent = len(s_list)
        count_received = len(r_list)
        count_total = count_sent + count_received

        success_sent = sum(1 for t in s_list if t["status"] == "SUCCESS")
        success_received = sum(1 for t in r_list if t["status"] == "SUCCESS")
        failed_sent = sum(1 for t in s_list if t["status"] == "FAILED")
        failed_received = sum(1 for t in r_list if t["status"] == "FAILED")

        failure_rate = (failed_sent / count_sent) if count_sent > 0 else 0.0

        # 2. Monetary Amounts & Aggregates
        amt_sent_total = sum((t["amount_inr"] for t in s_list), 0.0)
        amt_received_total = sum((t["amount_inr"] for t in r_list), 0.0)
        net_flow = amt_received_total - amt_sent_total

        amt_sent_avg = (amt_sent_total / count_sent) if count_sent > 0 else 0.0
        amt_received_avg = (amt_received_total / count_received) if count_received > 0 else 0.0

        amt_sent_max = float(max((t["amount_inr"] for t in s_list), default=0.0))
        amt_received_max = float(max((t["amount_inr"] for t in r_list), default=0.0))
        amt_max_overall = max(amt_sent_max, amt_received_max)

        # 3. Graph Topology & Counterparties
        senders_to_acc = {t["sender_account"] for t in r_list}
        receivers_from_acc = {t["receiver_account"] for t in s_list}

        fan_in = len(senders_to_acc)
        fan_out = len(receivers_from_acc)
        total_counterparties = len(senders_to_acc | receivers_from_acc)
        # Ratio of incoming to outgoing counterparties; +1 prevents division by zero
        fan_ratio = fan_in / (fan_out + 1.0)

        # 4. Complaints (handles structured complaint and legacy boolean fallback)
        complaints_as_receiver = sum((1 for t in r_list if is_complaint_active(t)), 0)
        complaints_as_sender = sum((1 for t in s_list if is_complaint_active(t)), 0)

        # 5. Sender-Side Device Sharing (L7 & §5.2)
        # Unobserved devices evaluate to 0.0 without inventing fictitious hardware IDs
        acc_devices = used_devices.get(acc, set())
        dev_count = len(acc_devices)
        if acc_devices:
            max_senders_sharing = max(len(device_to_senders[d]) for d in acc_devices)
        else:
            max_senders_sharing = 0
        shared_device_flag = 1.0 if max_senders_sharing >= 2 else 0.0

        # Assemble feature dict with 4-decimal rounding per Section 7
        acc_features = {
            "txn_count_sent": float(count_sent),
            "txn_count_received": float(count_received),
            "txn_count_total": float(count_total),
            "txn_success_sent": float(success_sent),
            "txn_success_received": float(success_received),
            "txn_failed_sent": float(failed_sent),
            "txn_failed_received": float(failed_received),
            "failure_rate_sent": float(round(failure_rate, 4)),
            "amount_sent_total": float(round(amt_sent_total, 4)),
            "amount_received_total": float(round(amt_received_total, 4)),
            "net_flow_amount": float(round(net_flow, 4)),
            "amount_sent_avg": float(round(amt_sent_avg, 4)),
            "amount_received_avg": float(round(amt_received_avg, 4)),
            "amount_sent_max": float(round(amt_sent_max, 4)),
            "amount_received_max": float(round(amt_received_max, 4)),
            "amount_max_overall": float(round(amt_max_overall, 4)),
            "fan_in_count": float(fan_in),
            "fan_out_count": float(fan_out),
            "counterparty_count_total": float(total_counterparties),
            "fan_ratio": float(round(fan_ratio, 4)),
            "complaint_count_as_receiver": float(complaints_as_receiver),
            "complaint_count_as_sender": float(complaints_as_sender),
            "devices_used_count": float(dev_count),
            "max_senders_on_used_devices": float(max_senders_sharing),
            "shared_device_user_flag": float(shared_device_flag),
        }

        # Verify all features exist in FEATURE_NAMES and have no NaNs/Infs
        for fname in FEATURE_NAMES:
            val = float(acc_features[fname])
            if math.isnan(val) or math.isinf(val):
                acc_features[fname] = 0.0
            else:
                acc_features[fname] = val

        features_by_account[acc] = acc_features

    return features_by_account


def extract_feature_matrix(
    transactions: List[Dict[str, Any]],
    account_ids: Optional[List[str]] = None
) -> Tuple[List[str], List[List[float]]]:
    """Convert transactions into a 2D numerical matrix aligned with FEATURE_NAMES.

    Args:
        transactions: List of transaction dictionaries.
        account_ids: Optional list of accounts to filter/order the rows. If None,
            returns all accounts present in transactions, sorted ascending.

    Returns:
        Tuple of (ordered_account_ids, matrix_rows), where each row is a list of
        float feature values in the exact order of FEATURE_NAMES.
    """
    feature_dict = extract_account_features(transactions)
    if account_ids is None:
        target_accounts = sorted(feature_dict.keys())
    else:
        target_accounts = list(account_ids)

    matrix: List[List[float]] = []
    for acc in target_accounts:
        if acc in feature_dict:
            row = [feature_dict[acc][f] for f in FEATURE_NAMES]
        else:
            # Accounts with no activity default to 0.0 per Section 7
            row = [0.0 for _ in FEATURE_NAMES]
        matrix.append(row)

    return target_accounts, matrix
