"""Deterministic topology-aware alert fingerprinting (Contract v1.2 §9.2)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping


def canonical_fingerprint_string(
    account_id: str,
    txn_ids: Iterable[str],
    device_to_senders: Mapping[str, Iterable[str]],
    complaints: Iterable[tuple[str, str, str]],
    ml_score: float,
    priority: str,
    rules_triggered: Iterable[str],
) -> str:
    """Serialize the fingerprint payload. Excludes created_at/generated_at and UI metadata.

    `complaints` items are `(complaint_id, category, filed_at)` already filtered to
    those ingested at or before T_as_of and associated with `account_id` only.
    """
    txns = ",".join(sorted(txn_ids))
    device_links = ";".join(
        sorted(
            f"{dev}:{','.join(sorted(senders))}"
            for dev, senders in device_to_senders.items()
        )
    )
    complaint_links = ";".join(
        sorted(f"{cid}:{category}:{filed_at}" for cid, category, filed_at in complaints)
    )
    score = f"{ml_score:.4f}"
    rules = ",".join(sorted(rules_triggered))
    return (
        f"{account_id}|{txns}|{device_links}|{complaint_links}|{score}|{priority}|{rules}"
    )


def compute_alert_fingerprint(
    account_id: str,
    txn_ids: Iterable[str],
    device_to_senders: Mapping[str, Iterable[str]],
    complaints: Iterable[tuple[str, str, str]],
    ml_score: float,
    priority: str,
    rules_triggered: Iterable[str],
) -> str:
    canonical = canonical_fingerprint_string(
        account_id,
        txn_ids,
        device_to_senders,
        complaints,
        ml_score,
        priority,
        rules_triggered,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def classify_staleness_reason(
    *,
    has_prior_reviewed_snapshot: bool,
    relevant_evidence_excluded_by_cutoff: bool,
) -> str:
    """Assign §9.2 staleness reason. Unrelated late events must not yield historical divergence."""
    if has_prior_reviewed_snapshot and relevant_evidence_excluded_by_cutoff:
        return "historical_snapshot_evidence_divergence"
    return "evidence_or_score_changed"


def relevant_evidence_excluded_by_cutoff(
    *,
    as_of: str | None,
    prior_txn_ids: Iterable[str],
    current_txn_ids: Iterable[str],
    prior_txn_ingested_at: Mapping[str, str],
    prior_device_ids: Iterable[str],
    current_device_ids: Iterable[str],
    prior_device_ingested_at: Mapping[str, str],
    prior_complaint_ids: Iterable[str],
    current_complaint_ids: Iterable[str],
    prior_complaint_ingested_at: Mapping[str, str],
) -> bool:
    """True only when missing account evidence is proven excluded by t_ingested > T_as_of.

    An explicit as_of with no proven cutoff exclusion, or missing ingestion timestamps,
    must not be treated as historical snapshot divergence.
    """
    if as_of is None:
        return False

    for txn_id in set(prior_txn_ids) - set(current_txn_ids):
        ingested = prior_txn_ingested_at.get(txn_id)
        if ingested is not None and ingested > as_of:
            return True

    for device_id in set(prior_device_ids) - set(current_device_ids):
        ingested = prior_device_ingested_at.get(device_id)
        if ingested is not None and ingested > as_of:
            return True

    for complaint_id in set(prior_complaint_ids) - set(current_complaint_ids):
        ingested = prior_complaint_ingested_at.get(complaint_id)
        if ingested is not None and ingested > as_of:
            return True

    return False