import json

import pytest

from backend.dataset_loader import DatasetLoadError, load_transactions


def make_transaction(
    txn_id="T000001",
    timestamp="2026-10-01T08:00:00Z",
    ingested_at=None,
):
    return {
        "txn_id": txn_id,
        "timestamp": timestamp,
        "ingested_at": ingested_at,
        "sender_account": "ACC_0001",
        "receiver_account": "ACC_0002",
        "sender_device_id": None,
        "merchant_id": None,
        "merchant_category": None,
        "amount_inr": 100.0,
        "status": "SUCCESS",
        "complaint_filed": False,
        "complaint": None,
    }


def write_jsonl(path, records):
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def test_loads_and_sorts_transactions(tmp_path):
    path = tmp_path / "transactions.jsonl"
    later = make_transaction(
        "T000002", "2026-10-01T09:00:00Z"
    )
    earlier = make_transaction(
        "T000001", "2026-10-01T08:00:00Z"
    )
    write_jsonl(path, [later, earlier])

    result = load_transactions(data_path=path)

    assert [txn["txn_id"] for txn in result] == [
        "T000001", "T000002"
    ]


def test_as_of_filters_by_ingestion_time(tmp_path):
    path = tmp_path / "transactions.jsonl"
    visible = make_transaction(
        "T000001",
        "2026-10-01T08:00:00Z",
        "2026-10-01T09:00:00Z",
    )
    not_yet_ingested = make_transaction(
        "T000002",
        "2026-10-01T08:30:00Z",
        "2026-10-01T11:00:00Z",
    )
    write_jsonl(path, [visible, not_yet_ingested])

    result = load_transactions(
        as_of="2026-10-01T10:00:00Z",
        data_path=path,
    )

    assert [txn["txn_id"] for txn in result] == ["T000001"]


def test_complaint_not_yet_ingested_is_hidden(tmp_path):
    path = tmp_path / "transactions.jsonl"
    txn = make_transaction(
        ingested_at="2026-10-01T09:00:00Z"
    )
    txn["complaint_filed"] = True
    txn["complaint"] = {
        "complaint_id": "CMP_0001",
        "filed_at": "2026-10-01T08:30:00Z",
        "ingested_at": "2026-10-01T11:00:00Z",
        "category": "UNSPECIFIED",
    }
    write_jsonl(path, [txn])

    result = load_transactions(
        as_of="2026-10-01T10:00:00Z",
        data_path=path,
    )

    assert len(result) == 1
    assert result[0]["complaint"] is None
    assert result[0]["complaint_filed"] is False


def test_duplicate_transaction_ids_are_rejected(tmp_path):
    path = tmp_path / "transactions.jsonl"
    write_jsonl(
        path,
        [
            make_transaction("T000001"),
            make_transaction("T000001", "2026-10-01T09:00:00Z"),
        ],
    )

    with pytest.raises(DatasetLoadError) as exc:
        load_transactions(data_path=path)

    assert exc.value.detail == "invalid_transactions"


def test_malformed_json_is_rejected(tmp_path):
    path = tmp_path / "transactions.jsonl"
    path.write_text("{not valid json}\n", encoding="utf-8")

    with pytest.raises(DatasetLoadError) as exc:
        load_transactions(data_path=path)

    assert exc.value.detail == "invalid_transactions"


def test_missing_dataset_returns_contract_error(tmp_path):
    path = tmp_path / "missing.jsonl"

    with pytest.raises(DatasetLoadError) as exc:
        load_transactions(data_path=path)

    assert exc.value.detail == "data_file_not_found"
