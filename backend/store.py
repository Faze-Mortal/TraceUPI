"""In-memory analysis cache and review store (Contract v1.2 §9.2).

Pipeline output is supplied explicitly. This module never invents ML scores,
never reads ground_truth, and never writes datasets or model artifacts.
State lives for the process lifetime only.
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from backend.constants import ReviewStatus
from backend.errors import AlertNotFoundError, AnalysisNotRunError
from backend.fingerprint import (
    classify_staleness_reason,
    compute_alert_fingerprint,
    relevant_evidence_excluded_by_cutoff,
)
from backend.review_transitions import apply_review_transition
from backend.schemas import (
    Alert,
    AlertSummary,
    BaselineResult,
    ContextFlags,
    Evidence,
    MLResult,
    PreviousReview,
    ReviewQueueState,
    ReviewState,
    TopReason,
)

HistoryEvent = Literal["initialized", "restored", "diverged", "transitioned", "archived"]


def utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class AccountEvidence:
    """Account-local evidence used for fingerprinting and cutoff comparison. No labels."""

    txn_ids: frozenset[str]
    txn_ingested_at: Mapping[str, str]
    device_to_senders: Mapping[str, frozenset[str]]
    device_ingested_at: Mapping[str, str]
    complaints: tuple[tuple[str, str, str], ...]
    complaint_ingested_at: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "txn_ids", frozenset(self.txn_ids))
        object.__setattr__(self, "txn_ingested_at", dict(self.txn_ingested_at))
        object.__setattr__(
            self,
            "device_to_senders",
            {dev: frozenset(senders) for dev, senders in self.device_to_senders.items()},
        )
        object.__setattr__(self, "device_ingested_at", dict(self.device_ingested_at))
        object.__setattr__(self, "complaints", tuple(self.complaints))
        object.__setattr__(self, "complaint_ingested_at", dict(self.complaint_ingested_at))

    @property
    def device_ids(self) -> frozenset[str]:
        return frozenset(self.device_to_senders)

    @property
    def complaint_ids(self) -> frozenset[str]:
        return frozenset(cid for cid, _category, _filed_at in self.complaints)


@dataclass(frozen=True)
class IncomingFlaggedAccount:
    """Caller-supplied flagged account. Scores must come from the pipeline or tests."""

    account_id: str
    created_at: str
    priority: str
    ml_score: float
    ml_threshold: float
    ml_flagged: bool
    baseline_flagged: bool
    rules_triggered: tuple[str, ...]
    account_evidence: AccountEvidence
    alert_id: str | None = None
    top_reasons: tuple[TopReason, ...] = ()
    context_flags: ContextFlags = field(
        default_factory=lambda: ContextFlags(
            shared_device_detected=False,
            rapid_pass_through_detected=False,
            note=None,
        )
    )
    evidence: Evidence = field(
        default_factory=lambda: Evidence(nodes=[], edges=[], evidence_path=[])
    )


@dataclass(frozen=True)
class AnalysisSnapshot:
    """Atomic replacement payload for POST /api/pipeline/run once the pipeline exists."""

    n_transactions: int
    as_of: str | None
    alerts: tuple[IncomingFlaggedAccount, ...]
    metrics: dict[str, Any] | None = None
    metrics_available: bool = False


@dataclass(frozen=True)
class StoredReview:
    account_id: str
    alert_fingerprint: str
    status: str
    is_stale: bool
    staleness_reason: str | None
    analyst_id: str | None
    updated_at: str | None
    verdict: str | None
    notes: str | None
    previous_review: PreviousReview | None
    evidence: AccountEvidence


@dataclass(frozen=True)
class ReviewHistoryEvent:
    account_id: str
    alert_fingerprint: str
    event: HistoryEvent
    status: str
    is_stale: bool
    staleness_reason: str | None
    analyst_id: str | None
    updated_at: str | None
    verdict: str | None
    notes: str | None


@dataclass
class _CachedAlert:
    alert: Alert
    evidence: AccountEvidence


class InvestigationStore:
    """Process-memory analysis cache + composite-key review store."""

    def __init__(self, clock: Callable[[], str] | None = None) -> None:
        self._clock = clock or utc_now_z
        self._lock = threading.RLock()
        self._has_run = False
        self._as_of: str | None = None
        self._n_transactions = 0
        self._metrics: dict[str, Any] | None = None
        self._metrics_available = False
        self._active: dict[str, _CachedAlert] = {}
        self._archived: dict[str, _CachedAlert] = {}
        self._alert_id_by_account: dict[str, str] = {}
        self._account_by_alert_id: dict[str, str] = {}
        self._reviews: dict[tuple[str, str], StoredReview] = {}
        self._history: list[ReviewHistoryEvent] = []
        self._next_alert_n = 1

    def has_analysis(self) -> bool:
        return self._has_run

    def as_of(self) -> str | None:
        self._require_run()
        return self._as_of

    def n_transactions(self) -> int:
        self._require_run()
        return self._n_transactions

    def n_alerts(self) -> int:
        self._require_run()
        return len(self._active)

    def metrics_available(self) -> bool:
        self._require_run()
        return self._metrics_available

    def get_metrics(self) -> dict[str, Any] | None:
        self._require_run()
        if self._metrics is None:
            return None
        return copy.deepcopy(self._metrics)

    def replace_analysis(self, snapshot: AnalysisSnapshot) -> None:
        """Atomically replace the active snapshot. Does not fabricate scores."""
        seen_accounts: set[str] = set()
        for incoming in snapshot.alerts:
            if incoming.account_id in seen_accounts:
                raise ValueError(f"duplicate flagged account '{incoming.account_id}'")
            seen_accounts.add(incoming.account_id)

        with self._lock:
            incoming_by_account = {item.account_id: item for item in snapshot.alerts}
            new_active: dict[str, _CachedAlert] = {}
            new_archived = dict(self._archived)
            new_alert_id_by_account = dict(self._alert_id_by_account)
            new_account_by_alert_id = dict(self._account_by_alert_id)

            for account_id, cached in self._active.items():
                if account_id not in incoming_by_account:
                    new_archived[account_id] = cached
                    self._record_history(
                        account_id=account_id,
                        alert_fingerprint=cached.alert.alert_fingerprint,
                        event="archived",
                        review=cached.alert.review,
                    )

            for account_id, incoming in incoming_by_account.items():
                new_archived.pop(account_id, None)
                fingerprint = self._fingerprint(incoming)
                alert_id = self._resolve_alert_id(
                    account_id,
                    incoming.alert_id,
                    new_alert_id_by_account,
                    new_account_by_alert_id,
                )
                review = self._reconcile_review(account_id, incoming, fingerprint, snapshot.as_of)
                alert = self._build_alert(incoming, alert_id, fingerprint, review)
                new_active[account_id] = _CachedAlert(alert=alert, evidence=incoming.account_evidence)
                new_alert_id_by_account[account_id] = alert_id
                new_account_by_alert_id[alert_id] = account_id
                self._reviews[(account_id, fingerprint)] = self._stored_from_review(
                    account_id, fingerprint, review, incoming.account_evidence
                )

            self._active = new_active
            self._archived = new_archived
            self._alert_id_by_account = new_alert_id_by_account
            self._account_by_alert_id = new_account_by_alert_id
            self._as_of = snapshot.as_of
            self._n_transactions = snapshot.n_transactions
            self._metrics = copy.deepcopy(snapshot.metrics)
            self._metrics_available = snapshot.metrics_available
            self._has_run = True

    def list_active_alerts(self) -> list[Alert]:
        self._require_run()
        with self._lock:
            return [cached.alert.model_copy(deep=True) for cached in self._active.values()]

    def list_alert_summaries(self) -> list[AlertSummary]:
        return [self.to_summary(alert) for alert in self.list_active_alerts()]

    def list_archived_alerts(self) -> list[Alert]:
        self._require_run()
        with self._lock:
            return [cached.alert.model_copy(deep=True) for cached in self._archived.values()]

    def get_alert(self, alert_id: str) -> Alert:
        self._require_run()
        with self._lock:
            account_id = self._account_by_alert_id.get(alert_id)
            if account_id is None or account_id not in self._active:
                raise AlertNotFoundError(alert_id)
            return self._active[account_id].alert.model_copy(deep=True)

    def get_active_alert_for_account(self, account_id: str) -> Alert:
        self._require_run()
        with self._lock:
            cached = self._active.get(account_id)
            if cached is None:
                raise AlertNotFoundError()
            return cached.alert.model_copy(deep=True)

    def apply_review(
        self,
        alert_id: str,
        *,
        status: ReviewStatus,
        analyst_id: str,
        verdict: str | None = None,
        notes: str | None = None,
        updated_at: str | None = None,
    ) -> Alert:
        self._require_run()
        with self._lock:
            account_id = self._account_by_alert_id.get(alert_id)
            if account_id is None or account_id not in self._active:
                raise AlertNotFoundError(alert_id)
            cached = self._active[account_id]
            new_status = apply_review_transition(cached.alert.review.status, status)
            stamp = updated_at or self._clock()
            review = cached.alert.review.model_copy(
                update={
                    "status": new_status,
                    "analyst_id": analyst_id,
                    "verdict": verdict,
                    "notes": notes,
                    "updated_at": stamp,
                    "is_stale": False,
                    "staleness_reason": None,
                }
            )
            alert = cached.alert.model_copy(update={"status": new_status, "review": review})
            self._active[account_id] = _CachedAlert(alert=alert, evidence=cached.evidence)
            self._reviews[(account_id, alert.alert_fingerprint)] = self._stored_from_review(
                account_id, alert.alert_fingerprint, review, cached.evidence
            )
            self._record_history(
                account_id=account_id,
                alert_fingerprint=alert.alert_fingerprint,
                event="transitioned",
                review=review,
            )
            return alert.model_copy(deep=True)

    def review_history(self, account_id: str | None = None) -> list[ReviewHistoryEvent]:
        with self._lock:
            events = list(self._history)
        if account_id is None:
            return events
        return [event for event in events if event.account_id == account_id]

    def stored_review(self, account_id: str, alert_fingerprint: str) -> StoredReview | None:
        with self._lock:
            record = self._reviews.get((account_id, alert_fingerprint))
            return copy.deepcopy(record) if record is not None else None

    @staticmethod
    def to_summary(alert: Alert) -> AlertSummary:
        payload = alert.model_dump()
        payload.pop("evidence", None)
        review = payload.get("review")
        if isinstance(review, dict):
            review.pop("previous_review", None)
            payload["review"] = ReviewQueueState.model_validate(review)
        return AlertSummary.model_validate(payload)

    def _require_run(self) -> None:
        if not self._has_run:
            raise AnalysisNotRunError()

    def _fingerprint(self, incoming: IncomingFlaggedAccount) -> str:
        evidence = incoming.account_evidence
        return compute_alert_fingerprint(
            incoming.account_id,
            evidence.txn_ids,
            evidence.device_to_senders,
            evidence.complaints,
            incoming.ml_score,
            incoming.priority,
            incoming.rules_triggered,
        )

    def _resolve_alert_id(
        self,
        account_id: str,
        requested: str | None,
        alert_id_by_account: dict[str, str],
        account_by_alert_id: dict[str, str],
    ) -> str:
        existing = alert_id_by_account.get(account_id)
        if existing is not None:
            return existing
        if requested is not None:
            owner = account_by_alert_id.get(requested)
            if owner is not None and owner != account_id:
                raise ValueError(f"alert_id '{requested}' already assigned to '{owner}'")
            alert_id_by_account[account_id] = requested
            account_by_alert_id[requested] = account_id
            self._note_allocated(requested)
            return requested
        alert_id = f"ALT_{self._next_alert_n:04d}"
        self._next_alert_n += 1
        alert_id_by_account[account_id] = alert_id
        account_by_alert_id[alert_id] = account_id
        return alert_id

    def _note_allocated(self, alert_id: str) -> None:
        if len(alert_id) == 8 and alert_id.startswith("ALT_"):
            try:
                number = int(alert_id[4:])
            except ValueError:
                return
            if number >= self._next_alert_n:
                self._next_alert_n = number + 1

    def _reconcile_review(
        self,
        account_id: str,
        incoming: IncomingFlaggedAccount,
        fingerprint: str,
        as_of: str | None,
    ) -> ReviewState:
        matched = self._reviews.get((account_id, fingerprint))
        if matched is not None:
            restored = ReviewState(
                status=matched.status,  # type: ignore[arg-type]
                is_stale=False,
                staleness_reason=None,
                analyst_id=matched.analyst_id,
                updated_at=matched.updated_at,
                verdict=matched.verdict,
                notes=matched.notes,
                previous_review=(
                    matched.previous_review.model_copy(deep=True)
                    if matched.previous_review is not None
                    else None
                ),
            )
            self._record_history(
                account_id=account_id,
                alert_fingerprint=fingerprint,
                event="restored",
                review=restored,
            )
            return restored

        prior_cached = self._active.get(account_id) or self._archived.get(account_id)
        account_reviews = [record for (acc, _fp), record in self._reviews.items() if acc == account_id]
        if prior_cached is None and not account_reviews:
            initialized = ReviewState(
                status="OPEN",
                is_stale=False,
                staleness_reason=None,
                analyst_id=None,
                updated_at=None,
                verdict=None,
                notes=None,
                previous_review=None,
            )
            self._record_history(
                account_id=account_id,
                alert_fingerprint=fingerprint,
                event="initialized",
                review=initialized,
            )
            return initialized

        prior_review = prior_cached.alert.review if prior_cached is not None else self._latest_review(account_id)
        prior_evidence = (
            prior_cached.evidence if prior_cached is not None else account_reviews[-1].evidence
        )
        cutoff_excluded = relevant_evidence_excluded_by_cutoff(
            as_of=as_of,
            prior_txn_ids=prior_evidence.txn_ids,
            current_txn_ids=incoming.account_evidence.txn_ids,
            prior_txn_ingested_at=prior_evidence.txn_ingested_at,
            prior_device_ids=prior_evidence.device_ids,
            current_device_ids=incoming.account_evidence.device_ids,
            prior_device_ingested_at=prior_evidence.device_ingested_at,
            prior_complaint_ids=prior_evidence.complaint_ids,
            current_complaint_ids=incoming.account_evidence.complaint_ids,
            prior_complaint_ingested_at=prior_evidence.complaint_ingested_at,
        )
        has_prior_reviewed_snapshot = any(
    record.analyst_id is not None
    and record.updated_at is not None
    and record.status in {
        "INVESTIGATING",
        "CONFIRMED_FRAUD",
        "DISMISSED_BENIGN",
    }
    for record in account_reviews
)

        reason = classify_staleness_reason(
            has_prior_reviewed_snapshot=has_prior_reviewed_snapshot,
            relevant_evidence_excluded_by_cutoff=cutoff_excluded,
)
        previous = PreviousReview(
            status=prior_review.status,
            analyst_id=prior_review.analyst_id,
            updated_at=prior_review.updated_at,
            verdict=prior_review.verdict,
            notes=prior_review.notes,
        )
        diverged = ReviewState(
            status="OPEN",
            is_stale=True,
            staleness_reason=reason,  # type: ignore[arg-type]
            analyst_id=None,
            updated_at=None,
            verdict=None,
            notes=None,
            previous_review=previous,
        )
        self._record_history(
            account_id=account_id,
            alert_fingerprint=fingerprint,
            event="diverged",
            review=diverged,
        )
        return diverged

    def _latest_review(self, account_id: str) -> ReviewState:
        records = [record for (acc, _fp), record in self._reviews.items() if acc == account_id]
        record = records[-1]
        return ReviewState(
            status=record.status,  # type: ignore[arg-type]
            is_stale=record.is_stale,
            staleness_reason=record.staleness_reason,  # type: ignore[arg-type]
            analyst_id=record.analyst_id,
            updated_at=record.updated_at,
            verdict=record.verdict,
            notes=record.notes,
            previous_review=record.previous_review,
        )

    def _build_alert(
        self,
        incoming: IncomingFlaggedAccount,
        alert_id: str,
        fingerprint: str,
        review: ReviewState,
    ) -> Alert:
        return Alert(
            alert_id=alert_id,
            alert_fingerprint=fingerprint,
            account_id=incoming.account_id,
            created_at=incoming.created_at,
            status=review.status,
            priority=incoming.priority,  # type: ignore[arg-type]
            ml=MLResult(
                score=incoming.ml_score,
                threshold=incoming.ml_threshold,
                flagged=incoming.ml_flagged,
            ),
            baseline=BaselineResult(
                flagged=incoming.baseline_flagged,
                rules_triggered=list(incoming.rules_triggered),
            ),
            top_reasons=list(incoming.top_reasons),
            context_flags=incoming.context_flags.model_copy(deep=True),
            review=review,
            evidence=incoming.evidence.model_copy(deep=True),
        )

    @staticmethod
    def _stored_from_review(
        account_id: str,
        fingerprint: str,
        review: ReviewState,
        evidence: AccountEvidence,
    ) -> StoredReview:
        return StoredReview(
            account_id=account_id,
            alert_fingerprint=fingerprint,
            status=review.status,
            is_stale=review.is_stale,
            staleness_reason=review.staleness_reason,
            analyst_id=review.analyst_id,
            updated_at=review.updated_at,
            verdict=review.verdict,
            notes=review.notes,
            previous_review=(
                review.previous_review.model_copy(deep=True) if review.previous_review else None
            ),
            evidence=evidence,
        )

    def _record_history(
        self,
        *,
        account_id: str,
        alert_fingerprint: str,
        event: HistoryEvent,
        review: ReviewState,
    ) -> None:
        self._history.append(
            ReviewHistoryEvent(
                account_id=account_id,
                alert_fingerprint=alert_fingerprint,
                event=event,
                status=review.status,
                is_stale=review.is_stale,
                staleness_reason=review.staleness_reason,
                analyst_id=review.analyst_id,
                updated_at=review.updated_at,
                verdict=review.verdict,
                notes=review.notes,
            )
        )


_PROCESS_STORE: InvestigationStore | None = None
_PROCESS_STORE_LOCK = threading.Lock()


def get_investigation_store() -> InvestigationStore:
    """Same instance across requests in this process; a new process starts empty."""
    global _PROCESS_STORE
    with _PROCESS_STORE_LOCK:
        if _PROCESS_STORE is None:
            _PROCESS_STORE = InvestigationStore()
        return _PROCESS_STORE
