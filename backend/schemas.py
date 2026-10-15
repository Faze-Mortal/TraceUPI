import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.constants import (
    ACCOUNT_ID_PATTERN,
    ALERT_ID_PATTERN,
    AlertPriority,
    COMPLAINT_ID_PATTERN,
    ComplaintCategory,
    DEVICE_ID_PATTERN,
    EDGE_ID_PATTERN,
    EdgeType,
    GroundTruthScenario,
    ISO8601_UTC_PATTERN,
    MERCHANT_ID_PATTERN,
    MerchantCategory,
    NodeType,
    ReviewStatus,
    StalenessReason,
    TXN_ID_PATTERN,
    TxnStatus,
)


def _matches(pattern: str, value: str) -> bool:
    return re.fullmatch(pattern, value) is not None


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PipelineRunRequest(StrictModel):
    """Optional body for POST /api/pipeline/run. Timestamp format is enforced in validation.py
    so malformed `as_of` maps to HTTP 422 `{"detail":"invalid_as_of_timestamp"}`.
    """

    as_of: str | None = None


class PipelineRunResponse(StrictModel):
    n_transactions: int = Field(ge=0)
    n_alerts: int = Field(ge=0)
    metrics_available: bool
    as_of: str | None = None


class MLResult(StrictModel):
    score: float
    threshold: float
    flagged: bool


class BaselineResult(StrictModel):
    flagged: bool
    rules_triggered: list[str]


class TopReason(StrictModel):
    feature: str
    value: Any
    typical_value: Any
    explanation: str


class ContextFlags(StrictModel):
    shared_device_detected: bool
    rapid_pass_through_detected: bool
    note: str | None = None


class PreviousReview(StrictModel):
    status: ReviewStatus
    analyst_id: str | None = None
    updated_at: str | None = None
    verdict: str | None = None
    notes: str | None = None

    @field_validator("updated_at")
    @classmethod
    def updated_at_iso8601(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not _matches(ISO8601_UTC_PATTERN, value):
            raise ValueError("updated_at must be ISO 8601 UTC YYYY-MM-DDTHH:MM:SSZ")
        return value


class ReviewQueueState(StrictModel):
    """Review fields allowed on GET /api/alerts summaries. Excludes previous_review (§7.0)."""

    status: ReviewStatus = "OPEN"
    is_stale: bool = False
    staleness_reason: StalenessReason | None = None
    analyst_id: str | None = None
    updated_at: str | None = None
    verdict: str | None = None
    notes: str | None = None

    @field_validator("updated_at")
    @classmethod
    def updated_at_iso8601(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not _matches(ISO8601_UTC_PATTERN, value):
            raise ValueError("updated_at must be ISO 8601 UTC YYYY-MM-DDTHH:MM:SSZ")
        return value


class ReviewState(ReviewQueueState):
    """Full review object on GET/PATCH /api/alerts/{alert_id}."""

    previous_review: PreviousReview | None = None


class EvidenceNode(StrictModel):
    id: str
    type: NodeType
    label: str
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceEdge(StrictModel):
    id: str = Field(pattern=EDGE_ID_PATTERN)
    source: str
    target: str
    type: EdgeType
    txn_id: str | None = None
    amount_inr: float | None = None
    timestamp: str | None = None

    @field_validator("timestamp")
    @classmethod
    def timestamp_iso8601(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not _matches(ISO8601_UTC_PATTERN, value):
            raise ValueError("timestamp must be ISO 8601 UTC YYYY-MM-DDTHH:MM:SSZ")
        return value


class Evidence(StrictModel):
    nodes: list[EvidenceNode] = Field(max_length=25)
    edges: list[EvidenceEdge] = Field(max_length=60)
    evidence_path: list[str] = Field(max_length=10)


class _AlertCore(StrictModel):
    alert_id: str = Field(pattern=ALERT_ID_PATTERN)
    alert_fingerprint: str = Field(min_length=64, max_length=64)
    account_id: str = Field(pattern=ACCOUNT_ID_PATTERN)
    created_at: str
    status: ReviewStatus
    priority: AlertPriority
    ml: MLResult
    baseline: BaselineResult
    top_reasons: list[TopReason]
    context_flags: ContextFlags

    @field_validator("created_at")
    @classmethod
    def created_at_iso8601(cls, value: str) -> str:
        if not _matches(ISO8601_UTC_PATTERN, value):
            raise ValueError("created_at must be ISO 8601 UTC YYYY-MM-DDTHH:MM:SSZ")
        return value

    @field_validator("alert_fingerprint")
    @classmethod
    def fingerprint_sha256_hex(cls, value: str) -> str:
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("alert_fingerprint must be a SHA-256 hex digest")
        return value


class AlertSummary(_AlertCore):
    """Queue payload. Must not include evidence or review.previous_review (§7.0, §11)."""

    review: ReviewQueueState


class Alert(_AlertCore):
    review: ReviewState
    evidence: Evidence


class ReviewUpdateRequest(StrictModel):
    status: ReviewStatus
    analyst_id: str = Field(min_length=1)
    verdict: str | None = None
    notes: str | None = None


class CounterfactualRequest(StrictModel):
    remove_edge_ids: list[str] = Field(default_factory=list)
    suppress_device_sharing: bool = False
    suppress_complaints: bool = False


class CounterfactualResponse(StrictModel):
    alert_id: str = Field(pattern=ALERT_ID_PATTERN)
    account_id: str = Field(pattern=ACCOUNT_ID_PATTERN)
    original_score: float
    counterfactual_score: float
    score_delta: float
    original_flagged: bool
    counterfactual_flagged: bool
    rules_removed: list[str]
    rules_added: list[str]
    plausible_benign_alternative: str

    @field_validator("plausible_benign_alternative")
    @classmethod
    def hypothesis_prefix(cls, value: str) -> str:
        if not value.startswith("Hypothesis:"):
            raise ValueError("plausible_benign_alternative must begin with 'Hypothesis:'")
        return value


class AlertsResponse(StrictModel):
    alerts: list[AlertSummary]


class BudgetMetrics(StrictModel):
    budget_k: int
    k_effective: int
    precision_at_k: float | None = None
    recall_at_k: float | None = None


class FairnessMetrics(StrictModel):
    fpr_benign_shared_device: float | None = None
    n_shared_device_evaluated: int = Field(ge=0)


class ClassificationMetrics(StrictModel):
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    true_positives: int = Field(ge=0)
    false_positives: int = Field(ge=0)
    false_negatives: int = Field(ge=0)
    budget_metrics: BudgetMetrics


class MLMetrics(ClassificationMetrics):
    threshold: float
    fairness: FairnessMetrics


class BaselineMetrics(ClassificationMetrics):
    pass


class ScenarioBreakdown(StrictModel):
    scenario: GroundTruthScenario
    n_accounts: int = Field(ge=0)
    ml_flagged: int = Field(ge=0)
    baseline_flagged: int = Field(ge=0)


class EvaluationInfo(StrictModel):
    evaluated_on: Literal["held_out_accounts"]
    n_accounts: int = Field(ge=0)
    n_positive_accounts: int = Field(ge=0)
    n_shared_device_accounts: int = Field(ge=0)


class MetricsResponse(StrictModel):
    generated_at: str
    budget_k: int
    evaluation: EvaluationInfo
    ml: MLMetrics
    baseline: BaselineMetrics
    by_scenario: list[ScenarioBreakdown]

    @field_validator("generated_at")
    @classmethod
    def generated_at_iso8601(cls, value: str) -> str:
        if not _matches(ISO8601_UTC_PATTERN, value):
            raise ValueError("generated_at must be ISO 8601 UTC YYYY-MM-DDTHH:MM:SSZ")
        return value


class HealthResponse(StrictModel):
    status: Literal["ok"]
    service: str


class ComplaintObject(StrictModel):
    complaint_id: str = Field(pattern=COMPLAINT_ID_PATTERN)
    filed_at: str
    ingested_at: str | None = None
    category: ComplaintCategory

    @field_validator("filed_at", "ingested_at")
    @classmethod
    def complaint_timestamps(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not _matches(ISO8601_UTC_PATTERN, value):
            raise ValueError("complaint timestamps must be ISO 8601 UTC YYYY-MM-DDTHH:MM:SSZ")
        return value

    @model_validator(mode="after")
    def ingested_not_before_filed(self) -> "ComplaintObject":
        if self.ingested_at is not None and self.ingested_at < self.filed_at:
            raise ValueError("complaint.ingested_at cannot be before filed_at")
        return self


class GroundTruth(StrictModel):
    scenario: GroundTruthScenario
    ring_member_accounts: list[str]


class TransactionEvent(StrictModel):
    """Ingest record shape. ground_truth is accepted for later isolated evaluation only."""

    txn_id: str = Field(pattern=TXN_ID_PATTERN)
    timestamp: str
    ingested_at: str | None = None
    sender_account: str = Field(pattern=ACCOUNT_ID_PATTERN)
    receiver_account: str = Field(pattern=ACCOUNT_ID_PATTERN)
    sender_device_id: str | None = None
    merchant_id: str | None = None
    merchant_category: MerchantCategory | None = None
    amount_inr: float = Field(gt=0)
    status: TxnStatus
    complaint_filed: bool | None = None
    complaint: ComplaintObject | None = None
    ground_truth: GroundTruth | None = None

    @field_validator("timestamp", "ingested_at")
    @classmethod
    def event_timestamps(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not _matches(ISO8601_UTC_PATTERN, value):
            raise ValueError("timestamp must be ISO 8601 UTC YYYY-MM-DDTHH:MM:SSZ")
        return value

    @field_validator("sender_device_id")
    @classmethod
    def device_id_format(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not _matches(DEVICE_ID_PATTERN, value):
            raise ValueError("sender_device_id must match DEV_ + 4 digits")
        return value

    @field_validator("merchant_id")
    @classmethod
    def merchant_id_format(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not _matches(MERCHANT_ID_PATTERN, value):
            raise ValueError("merchant_id must match MER_ + 4 digits")
        return value

    @model_validator(mode="after")
    def field_invariants(self) -> "TransactionEvent":
        if self.sender_account == self.receiver_account:
            raise ValueError("sender_account must differ from receiver_account")
        if self.ingested_at is not None and self.ingested_at < self.timestamp:
            raise ValueError("ingested_at cannot be before timestamp")
        merchant_present = self.merchant_id is not None
        category_present = self.merchant_category is not None
        if merchant_present != category_present:
            raise ValueError("merchant_category must be non-null iff merchant_id is non-null")
        if self.complaint is not None and self.complaint_filed is False:
            raise ValueError(
                "Conflicting complaint telemetry: complaint object provided but complaint_filed is False"
            )
        if self.complaint is not None and self.complaint.filed_at < self.timestamp:
            raise ValueError("complaint.filed_at cannot be before transaction timestamp")
        return self
