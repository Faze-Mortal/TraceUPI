from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backend.constants import DETAIL_DATA_FILE_NOT_FOUND, DETAIL_INVALID_TRANSACTIONS
from backend.schemas import TransactionEvent
from backend.validation import ContractValidationError, validate_as_of


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_PATH = REPO_ROOT / "data" / "transactions_expanded.jsonl"


class DatasetLoadError(ValueError):
    def __init__(self, detail: str, message: str | None = None) -> None:
        self.detail = detail
        super().__init__(message or detail)


def _effective_transaction_ingestion(txn: dict[str, Any]) -> str:
    return txn.get("ingested_at") or txn["timestamp"]


def _effective_complaint_ingestion(txn: dict[str, Any]) -> str | None:
    complaint = txn.get("complaint")
    if complaint is not None:
        return complaint.get("ingested_at") or complaint["filed_at"]

    # Legacy complaint telemetry is synthesized from the transaction.
    if txn.get("complaint_filed") is True:
        return _effective_transaction_ingestion(txn)

    return None


def load_transactions(
    as_of: str | None = None,
    *,
    data_path: str | Path = DEFAULT_DATA_PATH,
) -> list[dict[str, Any]]:
    """Load and validate JSONL records, then apply the contract's ingestion cutoff.

    ground_truth is preserved for isolated offline evaluation only. This function
    does not use it to filter transactions or derive inference features.
    """
    try:
        cutoff = validate_as_of(as_of)
    except ContractValidationError as exc:
        raise DatasetLoadError(exc.detail) from exc

    path = Path(data_path)
    if not path.is_file():
        raise DatasetLoadError(DETAIL_DATA_FILE_NOT_FOUND)

    transactions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue

                try:
                    raw = json.loads(line)
                    if not isinstance(raw, dict):
                        raise ValueError("record must be a JSON object")

                    event = TransactionEvent.model_validate(raw)
                    txn = event.model_dump(mode="json")
                except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
                    raise DatasetLoadError(
                        DETAIL_INVALID_TRANSACTIONS,
                        f"Invalid transaction record on line {line_number}: {exc}",
                    ) from exc

                if txn["txn_id"] in seen_ids:
                    raise DatasetLoadError(
                        DETAIL_INVALID_TRANSACTIONS,
                        f"Duplicate txn_id on line {line_number}: {txn['txn_id']}",
                    )
                seen_ids.add(txn["txn_id"])
                transactions.append(txn)
    except UnicodeDecodeError as exc:
        raise DatasetLoadError(
            DETAIL_INVALID_TRANSACTIONS,
            "Dataset is not valid UTF-8",
        ) from exc

    if cutoff is not None:
        transactions = [
            txn for txn in transactions
            if _effective_transaction_ingestion(txn) <= cutoff
        ]

        # A complaint is a separate telemetry event. If it has not arrived by
        # the cutoff, remove only that event, retaining the transaction itself.
        for txn in transactions:
            complaint = txn.get("complaint")
            if complaint is not None:
                if _effective_complaint_ingestion(txn) > cutoff:
                    txn["complaint"] = None
                    txn["complaint_filed"] = False
            elif txn.get("complaint_filed") is True:
                # Legacy complaint ingestion follows transaction ingestion.
                if _effective_complaint_ingestion(txn) > cutoff:
                    txn["complaint_filed"] = False

    # Deterministic event ordering required by Contract v1.2.
    transactions.sort(key=lambda txn: (txn["timestamp"], txn["txn_id"]))
    return transactions
