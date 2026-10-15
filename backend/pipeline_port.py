"""Adapter for the in-process ML analysis pipeline owned by Aum.

Contract v1.2 requires `ml.pipeline.run_analysis` for inference, evidence,
metrics, and counterfactuals. That module is not in the repository yet.
This port names the expected surface and fails closed — it never fabricates
scores, alerts, or metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


class PipelineUnavailableError(RuntimeError):
    """Raised when the ML pipeline cannot be imported or is incomplete."""


@dataclass(frozen=True)
class AnalysisRunResult:
    """HTTP-layer fields from POST /api/pipeline/run plus cached payload refs."""

    n_transactions: int
    n_alerts: int
    metrics_available: bool
    as_of: str | None
    alerts: tuple[dict[str, Any], ...]
    metrics: dict[str, Any] | None


@dataclass(frozen=True)
class CounterfactualRunResult:
    alert_id: str
    account_id: str
    original_score: float
    counterfactual_score: float
    score_delta: float
    original_flagged: bool
    counterfactual_flagged: bool
    rules_removed: tuple[str, ...]
    rules_added: tuple[str, ...]
    plausible_benign_alternative: str


@runtime_checkable
class AnalysisPipeline(Protocol):
    """Expected contract from `ml.pipeline` once Aum lands it."""

    def run_analysis(
        self,
        transactions: list[dict[str, Any]],
        as_of: str | None = None,
    ) -> AnalysisRunResult | dict[str, Any]:
        """Deterministic five-stage snapshot analysis. Must not read ground_truth for scores."""

    def run_counterfactual(
        self,
        alert: dict[str, Any],
        transactions: list[dict[str, Any]],
        *,
        remove_edge_ids: list[str],
        suppress_device_sharing: bool,
        suppress_complaints: bool,
    ) -> CounterfactualRunResult | dict[str, Any]:
        """Sandboxed what-if scoring. Must not mutate the active analysis cache."""


def load_analysis_pipeline() -> AnalysisPipeline:
    """Import `ml.pipeline` if present. Callers must map failures to HTTP 500 model_unavailable."""
    try:
        from ml import pipeline as ml_pipeline  # type: ignore[import-not-found]
    except ImportError as exc:
        raise PipelineUnavailableError(
            "ml.pipeline is missing. Inference, alerts, metrics, and counterfactuals "
            "cannot run until Aum implements ml.pipeline.run_analysis against the "
            "frozen 25-feature artifact. Do not substitute mock scores."
        ) from exc

    if not hasattr(ml_pipeline, "run_analysis"):
        raise PipelineUnavailableError(
            "ml.pipeline exists but does not define run_analysis."
        )
    return ml_pipeline  # type: ignore[return-value]
