from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from ml.features import FEATURE_NAMES, extract_account_features


REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_PATH = REPO_ROOT / "data" / "artifacts" / "model.joblib"


class ModelAdapterError(RuntimeError):
    """Raised when the saved model cannot safely perform inference."""


@lru_cache(maxsize=1)
def load_model_artifact() -> dict[str, Any]:
    """Load the existing model artifact once. Never train or overwrite it."""
    if not ARTIFACT_PATH.is_file():
        raise ModelAdapterError("model_unavailable")

    try:
        artifact = joblib.load(ARTIFACT_PATH)
    except Exception as exc:
        raise ModelAdapterError("model_unavailable") from exc

    if not isinstance(artifact, dict):
        raise ModelAdapterError("model_unavailable")

    model = artifact.get("model")
    artifact_features = artifact.get("feature_names")
    threshold = artifact.get("decision_threshold")

    if artifact_features != FEATURE_NAMES:
        raise ModelAdapterError("model_feature_mismatch")

    if not hasattr(model, "predict_proba"):
        raise ModelAdapterError("model_unavailable")

    if getattr(model, "n_features_in_", None) != len(FEATURE_NAMES):
        raise ModelAdapterError("model_feature_mismatch")

    if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
        raise ModelAdapterError("model_unavailable")

    classes = list(getattr(model, "classes_", []))
    if 1 not in classes:
        raise ModelAdapterError("model_unavailable")

    return artifact


def score_accounts(
    transactions: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return account scores and flags using the saved model and fixed features."""
    try:
        artifact = load_model_artifact()
        features_by_account = extract_account_features(transactions)

        account_ids = sorted(features_by_account)
        if not account_ids:
            return {}

        matrix = np.asarray(
            [
                [features_by_account[account_id][name] for name in FEATURE_NAMES]
                for account_id in account_ids
            ],
            dtype=np.float64,
        )

        probabilities = artifact["model"].predict_proba(matrix)
        classes = list(artifact["model"].classes_)
        positive_class_index = classes.index(1)
        threshold = float(artifact["decision_threshold"])

        results: dict[str, dict[str, Any]] = {}
        for index, account_id in enumerate(account_ids):
            score = float(probabilities[index, positive_class_index])
            results[account_id] = {
                "score": round(score, 4),
                "threshold": threshold,
                "flagged": score >= threshold,
                "features": features_by_account[account_id],
            }

        return results
    except ModelAdapterError:
        raise
    except Exception as exc:
        raise ModelAdapterError("model_unavailable") from exc
