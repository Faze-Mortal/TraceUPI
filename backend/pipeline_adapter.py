"""Adapter between the ML pipeline and the backend investigation store."""

from __future__ import annotations

from typing import Any

from backend.dataset_loader import load_transactions
from backend.pipeline_port import load_analysis_pipeline
from backend.schemas import ContextFlags, Evidence, TopReason
from backend.store import (
    AccountEvidence,
    AnalysisSnapshot,
    IncomingFlaggedAccount,
)


def _account_evidence(
    account_id: str,
    transactions: list[dict[str, Any]],
) -> AccountEvidence:
    """Build account-local fingerprint evidence from visible transactions."""
    account_txns = [
        txn
        for txn in transactions
        if txn["sender_account"] == account_id
        or txn["receiver_account"] == account_id
    ]

    txn_ids = {txn["txn_id"] for txn in account_txns}
    txn_ingested_at = {
        txn["txn_id"]: txn.get("ingested_at") or txn["timestamp"]
        for txn in account_txns
    }

    account_devices = {
        txn["sender_device_id"]
        for txn in account_txns
        if txn["sender_account"] == account_id
        and txn.get("sender_device_id")
    }

    device_to_senders: dict[str, set[str]] = {}
    device_ingested_at: dict[str, str] = {}

    for txn in transactions:
        device_id = txn.get("sender_device_id")
        if device_id in account_devices:
            device_to_senders.setdefault(device_id, set()).add(
                txn["sender_account"]
            )
            ingested_at = txn.get("ingested_at") or txn["timestamp"]
            previous = device_ingested_at.get(device_id)
            if previous is None or ingested_at < previous:
                device_ingested_at[device_id] = ingested_at

    complaints_by_id: dict[str, tuple[str, str, str]] = {}
    complaint_ingested_at: dict[str, str] = {}

    for txn in account_txns:
        complaint = txn.get("complaint")
        if complaint:
            complaint_id = complaint["complaint_id"]
            complaints_by_id[complaint_id] = (
                complaint_id,
                complaint["category"],
                complaint["filed_at"],
            )
            complaint_ingested_at[complaint_id] = (
                complaint.get("ingested_at")
                or complaint["filed_at"]
            )
        elif txn.get("complaint_filed") is True:
            # Legacy telemetry has no explicit complaint ID.
            # Do not invent one for fingerprinting.
            continue

    return AccountEvidence(
        txn_ids=frozenset(txn_ids),
        txn_ingested_at=txn_ingested_at,
        device_to_senders={
            device: frozenset(senders)
            for device, senders in device_to_senders.items()
        },
        device_ingested_at=device_ingested_at,
        complaints=tuple(
            sorted(complaints_by_id.values())
        ),
        complaint_ingested_at=complaint_ingested_at,
    )


def build_analysis_snapshot(
    as_of: str | None = None,
) -> AnalysisSnapshot:
    """Run the ML pipeline and adapt its output to the backend store."""
    # Load the complete validated dataset so the ML pipeline can apply
    # its own as-of logic while retaining historical context.
    all_transactions = load_transactions()
    visible_transactions = (
        load_transactions(as_of=as_of)
        if as_of is not None
        else all_transactions
    )

    from backend.main import load_analysis_pipeline
    pipeline = load_analysis_pipeline()
    result = pipeline.run_analysis(
        all_transactions,
        as_of=as_of,
        all_raw_transactions=all_transactions,
    )

    incoming_alerts: list[IncomingFlaggedAccount] = []

    for item in result["alerts"]:
        ml = item["ml"]
        baseline = item["baseline"]

        incoming_alerts.append(
            IncomingFlaggedAccount(
                # Let the store own stable alert IDs and fingerprints.
                alert_id=None,
                account_id=item["account_id"],
                created_at=item["created_at"],
                priority=item["priority"],
                ml_score=float(ml["score"]),
                ml_threshold=float(ml["threshold"]),
                ml_flagged=bool(ml["flagged"]),
                baseline_flagged=bool(baseline["flagged"]),
                rules_triggered=tuple(baseline["rules_triggered"]),
                account_evidence=_account_evidence(
                    item["account_id"],
                    visible_transactions,
                ),
                top_reasons=tuple(
                    TopReason.model_validate(reason)
                    for reason in item.get("top_reasons", [])
                ),
                context_flags=ContextFlags.model_validate(
                    item["context_flags"]
                ),
                evidence=Evidence.model_validate(
                    item.get(
                        "evidence",
                        {"nodes": [], "edges": [], "evidence_path": []},
                    )
                ),
            )
        )

    metrics = result.get("metrics")
    metrics_available = bool(result.get("metrics_available") and metrics is not None)

    return AnalysisSnapshot(
        n_transactions=int(result["n_transactions"]),
        as_of=result.get("as_of"),
        alerts=tuple(incoming_alerts),
        metrics=metrics,
        metrics_available=metrics_available,
    )
