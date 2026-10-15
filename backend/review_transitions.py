"""Human-review state machine (Contract v1.2 §9.1). Independent of ML scores."""

from __future__ import annotations

from backend.constants import ALLOWED_REVIEW_TRANSITIONS, DETAIL_INVALID_REVIEW_TRANSITION


class InvalidReviewTransition(ValueError):
    detail: str = DETAIL_INVALID_REVIEW_TRANSITION

    def __init__(self, current: str, requested: str) -> None:
        self.current = current
        self.requested = requested
        super().__init__(DETAIL_INVALID_REVIEW_TRANSITION)


def is_allowed_review_transition(current: str, requested: str) -> bool:
    if current == requested:
        return False
    return requested in ALLOWED_REVIEW_TRANSITIONS.get(current, frozenset())


def apply_review_transition(current: str, requested: str) -> str:
    if not is_allowed_review_transition(current, requested):
        raise InvalidReviewTransition(current, requested)
    return requested
