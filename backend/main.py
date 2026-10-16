
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from backend.dataset_loader import load_transactions

from backend.constants import (
    DEFAULT_BUDGET_K,
    DETAIL_ANALYSIS_NOT_RUN,
    DETAIL_ALERT_NOT_FOUND,
    DETAIL_DATA_FILE_NOT_FOUND,
    DETAIL_INVALID_AS_OF,
    DETAIL_INVALID_BUDGET_K,
    DETAIL_INVALID_FILTER_PARAM,
    DETAIL_INVALID_REVIEW_TRANSITION,
    DETAIL_METRICS_UNAVAILABLE,
    DETAIL_MODEL_UNAVAILABLE,
)
from backend.errors import AlertNotFoundError, AnalysisNotRunError
from backend.pipeline_adapter import build_analysis_snapshot
from backend.pipeline_port import (
    PipelineUnavailableError,
    load_analysis_pipeline,
)
from backend.review_transitions import InvalidReviewTransition
from backend.schemas import (
    AlertsResponse,
    CounterfactualRequest,
    CounterfactualResponse,
    Alert,
    AlertSummary,
    HealthResponse,
    MetricsResponse,
    PipelineRunRequest,
    PipelineRunResponse,
    ReviewUpdateRequest,
)
from backend.store import get_investigation_store
from ml.counterfactual import CounterfactualError, recompute_counterfactual

from backend.validation import (
    ContractValidationError,
    validate_alert_status_filter,
    validate_as_of,
    validate_budget_k,
)

app = FastAPI(
    title="TraceUPI API",
    description="Synthetic UPI fraud-ring investigation API",
    version="1.2.0",
)


@app.exception_handler(ContractValidationError)
async def contract_validation_handler(request, exc: ContractValidationError):
    payload = {"detail": exc.detail}
    payload.update(exc.extra)
    return JSONResponse(status_code=422, content=payload)


@app.exception_handler(AnalysisNotRunError)
async def analysis_not_run_handler(request, exc: AnalysisNotRunError):
    return JSONResponse(status_code=503, content={"detail": DETAIL_ANALYSIS_NOT_RUN})


@app.exception_handler(AlertNotFoundError)
async def alert_not_found_handler(request, exc: AlertNotFoundError):
    return JSONResponse(status_code=404, content={"detail": DETAIL_ALERT_NOT_FOUND})


@app.exception_handler(InvalidReviewTransition)
async def invalid_transition_handler(request, exc: InvalidReviewTransition):
    return JSONResponse(
        status_code=422,
        content={"detail": DETAIL_INVALID_REVIEW_TRANSITION},
    )


@app.exception_handler(PipelineUnavailableError)
async def pipeline_unavailable_handler(request, exc: PipelineUnavailableError):
    return JSONResponse(status_code=500, content={"detail": DETAIL_MODEL_UNAVAILABLE})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    for err in exc.errors():
        loc = err.get("loc", ())
        if "budget_k" in loc:
            return JSONResponse(
                status_code=422,
                content={"detail": DETAIL_INVALID_BUDGET_K},
            )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="TraceUPI API")


@app.post("/api/pipeline/run", response_model=PipelineRunResponse)
def run_pipeline(
    body: PipelineRunRequest | None = None,
) -> PipelineRunResponse:
    as_of = validate_as_of(body.as_of if body is not None else None)

    try:
        snapshot = build_analysis_snapshot(as_of=as_of)
        store = get_investigation_store()
        store.replace_analysis(snapshot)
    except PipelineUnavailableError:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=DETAIL_MODEL_UNAVAILABLE,
        ) from exc

    return PipelineRunResponse(
        n_transactions=snapshot.n_transactions,
        n_alerts=len(snapshot.alerts),
        metrics_available=store.metrics_available(),
        as_of=snapshot.as_of,
    )


@app.get("/api/alerts", response_model=AlertsResponse)
def list_alerts(
    status: str | None = Query(default=None),
    budget_k: Any = Query(default=None),
) -> AlertsResponse:
    status = validate_alert_status_filter(status)
    budget = validate_budget_k(budget_k)

    store = get_investigation_store()
    alerts = store.list_active_alerts()

    if status is not None:
        alerts = [alert for alert in alerts if alert.status == status]

    alerts.sort(key=lambda alert: (-alert.ml.score, alert.account_id))

    if budget is not None:
        alerts = alerts[:budget]

    return AlertsResponse(
        alerts=[store.to_summary(alert) for alert in alerts]
    )


@app.get("/api/alerts/{alert_id}", response_model=Alert)
def get_alert(alert_id: str) -> Alert:
    return get_investigation_store().get_alert(alert_id)


@app.patch("/api/alerts/{alert_id}", response_model=Alert)
def update_alert_review(
    alert_id: str,
    body: ReviewUpdateRequest,
) -> Alert:
    return get_investigation_store().apply_review(
        alert_id,
        status=body.status,
        analyst_id=body.analyst_id,
        verdict=body.verdict,
        notes=body.notes,
    )


@app.post(
    "/api/alerts/{alert_id}/counterfactual",
    response_model=CounterfactualResponse,
)
def run_counterfactual(
    alert_id: str,
    body: CounterfactualRequest,
) -> CounterfactualResponse:
    store = get_investigation_store()
    alert = store.get_alert(alert_id)

    try:
        result = recompute_counterfactual(
            alert=alert.model_dump(mode="json"),
            transactions=load_transactions(),
            remove_edge_ids=body.remove_edge_ids,
            suppress_device_sharing=body.suppress_device_sharing,
            suppress_complaints=body.suppress_complaints,
            as_of=store.as_of(),
        )
    except CounterfactualError as exc:
        payload = exc.to_dict()
        return JSONResponse(status_code=422, content=payload)

    return CounterfactualResponse.model_validate({k: v for k, v in result.items() if k != 'evidence'})


@app.get("/api/metrics", response_model=MetricsResponse)
def get_metrics(
    budget_k: Any = Query(default=DEFAULT_BUDGET_K),
) -> MetricsResponse:
    budget = validate_budget_k(budget_k, default=DEFAULT_BUDGET_K)
    store = get_investigation_store()

    if not store.has_analysis():
        raise HTTPException(
            status_code=503,
            detail=DETAIL_ANALYSIS_NOT_RUN,
        )

    if not store.metrics_available():
        raise HTTPException(
            status_code=404,
            detail=DETAIL_METRICS_UNAVAILABLE,
        )

    metrics = store.get_metrics(budget_k=budget)
    if metrics is None:
        raise HTTPException(
            status_code=404,
            detail=DETAIL_METRICS_UNAVAILABLE,
        )

    return MetricsResponse.model_validate(metrics)