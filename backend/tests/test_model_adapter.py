import pytest

from backend.model_adapter import (
    ModelAdapterError,
    load_model_artifact,
    score_accounts,
)


def test_saved_artifact_has_expected_feature_order():
    artifact = load_model_artifact()

    assert len(artifact["feature_names"]) == 25
    assert artifact["feature_names"][-1] == "shared_device_user_flag"
    assert artifact["model"].n_features_in_ == 25
    assert artifact["decision_threshold"] == 0.5


def test_empty_transactions_return_no_scores():
    assert score_accounts([]) == {}


def test_real_fixture_produces_valid_account_scores():
    import json
    from pathlib import Path

    path = Path("data/transactions.jsonl")
    transactions = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    results = score_accounts(transactions)

    assert results
    assert all(account_id.startswith("ACC_") for account_id in results)
    assert all(0.0 <= item["score"] <= 1.0 for item in results.values())
    assert all(item["threshold"] == 0.5 for item in results.values())
    assert all(item["flagged"] == (item["score"] >= 0.5) for item in results.values())


def test_artifact_feature_mismatch_fails_closed(monkeypatch):
    import backend.model_adapter as adapter

    artifact = dict(load_model_artifact())
    artifact["feature_names"] = ["wrong_feature"]

    monkeypatch.setattr(adapter, "ARTIFACT_PATH", adapter.ARTIFACT_PATH)
    monkeypatch.setattr(adapter, "joblib", type(
        "FakeJoblib", (), {"load": staticmethod(lambda _: artifact)}
    ))
    adapter.load_model_artifact.cache_clear()

    try:
        with pytest.raises(ModelAdapterError, match="model_feature_mismatch"):
            adapter.load_model_artifact()
    finally:
        adapter.load_model_artifact.cache_clear()
