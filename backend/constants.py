"""Contract v1.2 identifiers, enums, and review-transition tables."""

from __future__ import annotations

from typing import Final, Literal

ISO8601_UTC_PATTERN: Final[str] = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"

ACCOUNT_ID_PATTERN: Final[str] = r"^ACC_\d{4}$"
DEVICE_ID_PATTERN: Final[str] = r"^DEV_\d{4}$"
TXN_ID_PATTERN: Final[str] = r"^T\d{6}$"
MERCHANT_ID_PATTERN: Final[str] = r"^MER_\d{4}$"
COMPLAINT_ID_PATTERN: Final[str] = r"^CMP_\d{4}$"
ALERT_ID_PATTERN: Final[str] = r"^ALT_\d{4}$"
EDGE_ID_PATTERN: Final[str] = r"^E\d+$"

ReviewStatus = Literal[
    "OPEN",
    "INVESTIGATING",
    "CONFIRMED_FRAUD",
    "DISMISSED_BENIGN",
]

AlertPriority = Literal["HIGH", "MEDIUM", "LOW"]

StalenessReason = Literal[
    "historical_snapshot_evidence_divergence",
    "evidence_or_score_changed",
]

NodeType = Literal["account", "device", "merchant", "complaint"]
EdgeType = Literal["transfer", "uses_device", "merchant_profile", "has_complaint"]

ComplaintCategory = Literal[
    "UNAUTHORIZED_TRANSACTION",
    "PHISHING_SCAM",
    "NON_DELIVERY_GOODS",
    "UNSPECIFIED",
]

MerchantCategory = Literal[
    "ELECTRONICS",
    "JEWELRY",
    "CRYPTO_VOUCHER",
    "GENERAL_RETAIL",
    "GAMING",
    "SERVICES",
]

GroundTruthScenario = Literal["mule_ring", "shared_device_family", "normal"]

TxnStatus = Literal["SUCCESS", "FAILED"]

BudgetK = Literal[10, 20, 50]
DEFAULT_BUDGET_K: Final[int] = 20
ALLOWED_BUDGET_K: Final[frozenset[int]] = frozenset({10, 20, 50})

ALLOWED_REVIEW_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "OPEN": frozenset({"INVESTIGATING", "CONFIRMED_FRAUD", "DISMISSED_BENIGN"}),
    "INVESTIGATING": frozenset({"CONFIRMED_FRAUD", "DISMISSED_BENIGN"}),
    "CONFIRMED_FRAUD": frozenset({"INVESTIGATING"}),
    "DISMISSED_BENIGN": frozenset({"INVESTIGATING"}),
}

DETAIL_INVALID_AS_OF: Final[str] = "invalid_as_of_timestamp"
DETAIL_INVALID_TRANSACTIONS: Final[str] = "invalid_transactions"
DETAIL_DATA_FILE_NOT_FOUND: Final[str] = "data_file_not_found"
DETAIL_MODEL_UNAVAILABLE: Final[str] = "model_unavailable"
DETAIL_ANALYSIS_NOT_RUN: Final[str] = "analysis_not_run"
DETAIL_ALERT_NOT_FOUND: Final[str] = "alert_not_found"
DETAIL_INVALID_FILTER_PARAM: Final[str] = "invalid_filter_param"
DETAIL_INVALID_REVIEW_TRANSITION: Final[str] = "invalid_review_transition"
DETAIL_INVALID_BUDGET_K: Final[str] = "invalid_budget_k"
DETAIL_METRICS_UNAVAILABLE: Final[str] = "metrics_unavailable"
DETAIL_EMPTY_COUNTERFACTUAL: Final[str] = "empty_counterfactual_request"
DETAIL_INVALID_COUNTERFACTUAL: Final[str] = "invalid_counterfactual_request"
DETAIL_INVALID_COUNTERFACTUAL_INTERVENTION: Final[str] = (
    "invalid_counterfactual_intervention"
)
DETAIL_UNKNOWN_OR_UNSUPPORTED_EDGE: Final[str] = "unknown_or_unsupported_edge_id"
DETAIL_CONFLICTING_COMPLAINT: Final[str] = "conflicting_complaint_telemetry"
DETAIL_INVALID_COMPLAINT_CATEGORY: Final[str] = "invalid_complaint_category"
