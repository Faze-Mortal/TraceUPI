
"""HTTP-layer validators that must emit Contract v1.2 string `detail` values."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from backend.constants import (
    ALLOWED_BUDGET_K,
    DETAIL_EMPTY_COUNTERFACTUAL,
    DETAIL_INVALID_AS_OF,
    DETAIL_INVALID_BUDGET_K,
    DETAIL_INVALID_FILTER_PARAM,
    ISO8601_UTC_PATTERN,
)

_ISO8601_UTC_RE = re.compile(ISO8601_UTC_PATTERN)


class ContractValidationError(ValueError):
    def __init__(self, detail: str, extra: dict[str, str] | None = None) -> None:
        self.detail = detail
        self.extra = extra or {}
        super().__init__(detail)


def validate_as_of(as_of: str | None) -> str | None:
    """Validate a real ISO 8601 UTC timestamp ending in Z.

    None means T_as_of = +infinity.
    """
    if as_of is None:
        return None

    if not isinstance(as_of, str) or not _ISO8601_UTC_RE.fullmatch(as_of):
        raise ContractValidationError(DETAIL_INVALID_AS_OF)

    try:
        parsed = datetime.strptime(as_of, "%Y-%m-%dT%H:%M:%SZ")
        parsed.replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ContractValidationError(DETAIL_INVALID_AS_OF) from exc

    return as_of


def validate_budget_k(
    budget_k: Any = None,
    *,
    default: int | None = None,
) -> int | None:
    if budget_k is None or budget_k == "":
        return default
    if isinstance(budget_k, bool):
        raise ContractValidationError(DETAIL_INVALID_BUDGET_K)
    try:
        val = int(budget_k)
        if isinstance(budget_k, float) and budget_k != val:
            raise ContractValidationError(DETAIL_INVALID_BUDGET_K)
        if isinstance(budget_k, str) and str(val) != budget_k.strip():
            raise ContractValidationError(DETAIL_INVALID_BUDGET_K)
    except (ValueError, TypeError) as exc:
        raise ContractValidationError(DETAIL_INVALID_BUDGET_K) from exc

    if val not in ALLOWED_BUDGET_K:
        raise ContractValidationError(DETAIL_INVALID_BUDGET_K)
    return val


def validate_alert_status_filter(status: str | None) -> str | None:
    allowed = {
        "OPEN",
        "INVESTIGATING",
        "CONFIRMED_FRAUD",
        "DISMISSED_BENIGN",
    }
    if status is None:
        return None
    if status not in allowed:
        raise ContractValidationError(DETAIL_INVALID_FILTER_PARAM)
    return status


def validate_counterfactual_interventions(
    remove_edge_ids: list[str],
    suppress_device_sharing: bool,
    suppress_complaints: bool,
) -> None:
    if (
        not remove_edge_ids
        and not suppress_device_sharing
        and not suppress_complaints
    ):
        raise ContractValidationError(DETAIL_EMPTY_COUNTERFACTUAL)
