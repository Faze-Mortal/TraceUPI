"""Contract HTTP `detail` errors used by the in-memory store and future API layer."""

from __future__ import annotations

from backend.constants import DETAIL_ALERT_NOT_FOUND, DETAIL_ANALYSIS_NOT_RUN


class AnalysisNotRunError(LookupError):
    detail: str = DETAIL_ANALYSIS_NOT_RUN

    def __init__(self) -> None:
        super().__init__(DETAIL_ANALYSIS_NOT_RUN)


class AlertNotFoundError(LookupError):
    detail: str = DETAIL_ALERT_NOT_FOUND

    def __init__(self, alert_id: str | None = None) -> None:
        self.alert_id = alert_id
        super().__init__(DETAIL_ALERT_NOT_FOUND)
