# TraceUPI Interface Contract v1.1

**Status:** Final draft, effective once both developers agree.

**Architecture:** One repository; React frontend → FastAPI backend → imported `ml` package; synthetic data only; no database.

## Changes from v1.0

1. Model artifact metadata, split rules, and same-account evaluation for ML and baseline.
2. Deterministic account-level scenario assignment; `ground_truth` is all-or-none.
3. `GET /api/metrics` returns HTTP 404 with `{"detail":"metrics_unavailable"}` when metrics are unavailable.
4. `created_at` and `generated_at` are set in UTC by the ML module and excluded from determinism.
5. Evidence graph integrity and size-limit rules.
6. API response bodies, error codes, and `/api/pipeline/run` behaviour are explicitly defined.

## 1. Transaction event

Input file: `data/transactions.jsonl`, UTF-8, one event per line. It is produced by the ML owner and read-only for the backend.

Example:

```json
{
  "txn_id": "T000123",
  "timestamp": "2026-10-01T10:15:30Z",
  "sender_account": "ACC_0042",
  "receiver_account": "ACC_0917",
  "sender_device_id": "DEV_0031",
  "amount_inr": 4999.0,
  "status": "SUCCESS",
  "complaint_filed": false,
  "ground_truth": {
    "scenario": "mule_ring",
    "ring_member_accounts": ["ACC_0917"]
  }
}
```

### Field rules

| Field | Type | Required | Rule |
|---|---|---|---|
| `txn_id` | string | Yes | `T` + 6 digits; unique across the dataset |
| `timestamp` | string | Yes | ISO 8601 UTC, `YYYY-MM-DDTHH:MM:SSZ` |
| `sender_account` | string | Yes | `ACC_` + 4 digits; must differ from receiver |
| `receiver_account` | string | Yes | `ACC_` + 4 digits; must differ from sender |
| `sender_device_id` | string | Yes | `DEV_` + 4 digits |
| `amount_inr` | number | Yes | Greater than 0 |
| `status` | string | Yes | `"SUCCESS"` or `"FAILED"` |
| `complaint_filed` | boolean | Yes | — |
| `ground_truth` | object | All-or-none | Present only for synthetic labelled data |
| `ground_truth.scenario` | string | If present | `"mule_ring"`, `"shared_device_family"`, or `"normal"` |
| `ground_truth.ring_member_accounts` | list of strings | If present | Ring-member accounts in this transaction; empty list for benign scenarios |

### Dataset rules

- `ground_truth` must be present on every transaction or on none. Mixed input is invalid.
- `txn_id` values must be unique.
- All fields except `ground_truth` may be considered as model and baseline inputs, subject to feature definitions and data availability.

## 2. Account-level scenario and label

Every account appearing as sender or receiver gets exactly one scenario, assigned by the first matching rule:

1. `mule_ring`: the account appears in `ring_member_accounts` of any transaction.
2. `shared_device_family`: otherwise, the account is sender or receiver in any transaction whose `ground_truth.scenario` is `shared_device_family`.
3. `normal`: everything else.

**Label:** positive if and only if the account's scenario is `mule_ring`. All other accounts are negative.

This assignment is used only by training and evaluation. It is never a feature, never a prediction input, and never appears in alerts.

## 3. Model artifact

File: `data/artifacts/model.joblib`.

It contains the fitted model and the following metadata. The ML owner writes it; `run_analysis` reads it.

| Metadata field | Type | Rule |
|---|---|---|
| `artifact_version` | string | `"1.1"` |
| `feature_names` | list of strings | Ordered; exactly the model's input features |
| `decision_threshold` | number | Fixed according to Section 4 |
| `training_feature_medians` | object | Feature name → number, computed on training accounts only |
| `heldout_account_ids` | list of strings | Sorted ascending |
| `dataset_fingerprint` | string | SHA-256 hex digest of sorted `txn_id` values joined by `"\n"`, with no trailing newline, UTF-8 encoded |
| `split_seed` | integer | Seed used for the split |

## 4. Split and evaluation rules

### Split

- The unit is the account. Group accounts by the scenario defined in Section 2.
- Within each group, sort account IDs ascending, shuffle with `split_seed`, and hold out `min(max(1, round(0.30 × n)), n − 1)` accounts when `n >= 2`.
- A group with fewer than two accounts is entirely training. Its scenario cannot be evaluated.
- Therefore, shared-device accounts are included in the held-out set whenever the dataset has at least two of them.

### Training and leakage

- The model is trained on training accounts only, using labels from Section 2.
- `decision_threshold` is chosen using training accounts only. A fixed constant such as `0.5` is allowed.
- The threshold is written to the artifact before held-out evaluation and is never changed after seeing held-out results.
- Baseline rule parameters are fixed before evaluation and are never tuned on held-out accounts.
- `ground_truth` may be read only by:
  - `ml/generate_data.py`, which writes it.
  - `ml/train.py` and `ml/evaluate.py`, which use labels.
  - `ml/pipeline.py`, which strips it and passes it to evaluation.
- `ml/features.py` and `ml/baseline_rules.py` must not read `ground_truth`.
- No code may use scenario names or labels to decide an account's score, flag, or priority.

### Evaluation

- Metrics are computed only on `heldout_account_ids`.
- The ML model and baseline must use the same held-out accounts.
- ML flagged = `score >= decision_threshold`.
- Baseline flagged = at least one rule triggered.
- Actual positive = the Section 2 label.

## 5. Alert

Illustrative example only:

```json
{
  "alert_id": "ALT_0001",
  "account_id": "ACC_0917",
  "created_at": "2026-10-15T06:40:00Z",
  "status": "OPEN",
  "priority": "HIGH",
  "ml": {
    "score": 0.93,
    "threshold": 0.5,
    "flagged": true
  },
  "baseline": {
    "flagged": true,
    "rules_triggered": ["HIGH_FAN_IN"]
  },
  "top_reasons": [
    {
      "feature": "fan_in_count",
      "value": 14,
      "typical_value": 2,
      "explanation": "Received money from 14 distinct senders (typical: 2)"
    }
  ],
  "context_flags": {
    "shared_device_detected": false,
    "note": null
  },
  "evidence": {
    "nodes": [
      {
        "id": "ACC_0917",
        "type": "account",
        "score": 0.93
      },
      {
        "id": "ACC_0042",
        "type": "account",
        "score": 0.12
      },
      {
        "id": "DEV_0031",
        "type": "device",
        "score": null
      }
    ],
    "edges": [
      {
        "id": "E1",
        "source": "ACC_0042",
        "target": "ACC_0917",
        "type": "transfer",
        "txn_id": "T000123",
        "amount_inr": 4999.0,
        "timestamp": "2026-10-01T10:15:30Z"
      },
      {
        "id": "E2",
        "source": "ACC_0042",
        "target": "DEV_0031",
        "type": "uses_device",
        "txn_id": null,
        "amount_inr": null,
        "timestamp": null
      }
    ],
    "evidence_path": ["E1"]
  }
}
```

### Alert field rules

| Field | Rule |
|---|---|
| `alert_id` | `ALT_` + 4 digits; unique within one result; assigned after sorting |
| `account_id` | Account being investigated; one alert per account at most |
| `created_at` | UTC, set by the ML module |
| `status` | Always `"OPEN"` |
| `ml.score` | 0 to 1, uncalibrated model output used for ranking, not a probability |
| `ml.threshold` | Equals artifact `decision_threshold` |
| `ml.flagged` | `score >= threshold` |
| `baseline.flagged` | True if and only if `rules_triggered` is non-empty |
| `top_reasons` | 1–3 items; `feature` must exist in artifact `feature_names`; `value` is the account's value; `typical_value` is the artifact training median |
| `context_flags.shared_device_detected` | True if a `sender_device_id` used by this account appears with two or more distinct `sender_account` values in the input |
| `context_flags.note` | String or null; generated from computed features only |
| `evidence.nodes[].score` | Account nodes: account's ML score; device nodes: `null` |
| `evidence.edges` | One `transfer` edge per transaction; one `uses_device` edge per sender-account/device pair. The `txn_id`, `amount_inr`, and `timestamp` fields are `null` on `uses_device` edges |

### Priority

| `ml.flagged` | `baseline.flagged` | Result |
|---|---|---|
| True | True | `HIGH` |
| True | False | `MEDIUM` |
| False | True | `LOW` |
| False | False | No alert is generated; the account appears only in metrics counts |

### Evidence graph integrity

1. Node IDs and edge IDs are unique within an alert. Edge IDs use `E<n>`.
2. Every edge's `source` and `target` must exist in `evidence.nodes`.
3. `evidence_path` has at most 10 edge IDs. Every ID must exist in `evidence.edges`. It is ordered so consecutive edges share a node, direction ignored, and at least one path edge touches the alert account. It may be empty.
4. Size limits: at most 25 nodes and 60 edges. When trimming, always keep the alert account node, all `evidence_path` edges, and their endpoint nodes. This is at most 11 nodes and always fits. Trim everything else in deterministic order, then remove any edge whose endpoint was trimmed.

### Alert content rules

- No alert field, including `note` and `explanation`, may contain `ground_truth`, label values, or scenario names.
- Alerts for training accounts are not evaluation evidence. Only Section 6 metrics are evaluation evidence.

## 6. Metrics

All numbers below are format placeholders, not expected results.

```json
{
  "generated_at": "2026-10-15T06:40:00Z",
  "evaluation": {
    "evaluated_on": "held_out_accounts",
    "n_accounts": 0,
    "n_positive_accounts": 0
  },
  "ml": {
    "precision": 0.0,
    "recall": 0.0,
    "f1": 0.0,
    "true_positives": 0,
    "false_positives": 0,
    "false_negatives": 0
  },
  "baseline": {
    "precision": 0.0,
    "recall": 0.0,
    "f1": 0.0,
    "true_positives": 0,
    "false_positives": 0,
    "false_negatives": 0
  },
  "by_scenario": [
    {
      "scenario": "shared_device_family",
      "n_accounts": 0,
      "ml_flagged": 0,
      "baseline_flagged": 0
    }
  ]
}
```

### Metrics rules

- `n_accounts` is the number of held-out accounts evaluated.
- `precision` is `null` if TP + FP = 0.
- `recall` is `null` if TP + FN = 0.
- `f1` is `null` if either precision or recall is `null`, or if both are zero.
- `by_scenario` has one entry per Section 2 scenario that has at least one held-out account. Entries are sorted alphabetically and contain aggregate counts only.
- A scenario with no held-out accounts is omitted, not invented.
- The shared-device result is whatever the evaluation produces.

## 7. `ml.pipeline.run_analysis`

Required signature:

```python
def run_analysis(transactions: list[dict]) -> dict:
    ...
```

### Input

A non-empty list of dictionaries matching Section 1. The list may be unsorted and is designed for up to approximately 10,000 transactions. The function must not modify the input list or its dictionaries.

### Output

```python
{
    "contract_version": "1.1",
    "alerts": [...],
    "metrics": {...}
}
```

`alerts` contains alert dictionaries matching Section 5. `metrics` contains the Section 6 metrics object or `None`.

### Behaviour

- Synchronous; makes no network calls, prints nothing, and never trains.
- Reads `data/artifacts/model.joblib` and strips `ground_truth` before any feature or baseline computation.
- Features are computed only from input transactions. Accounts never seen in training are scored like any other account.
- Every feature must be defined for every account, using zero for no activity and with no missing or NaN feature values.
- `alerts` includes every account flagged by the ML model or baseline, and only those accounts.
- Sort alerts by `ml.score` descending, then `account_id` ascending. Assign `alert_id` after sorting.
- `metrics` is `None` unless all three conditions hold:
  1. Every transaction has `ground_truth`.
  2. The SHA-256 fingerprint of input `txn_id` values, using Section 3's method, equals artifact `dataset_fingerprint`.
  3. At least one held-out account exists.
- A fingerprint mismatch or missing `ground_truth` never blocks inference. Alerts are still produced.
- `created_at` and `generated_at` are UTC strings in `YYYY-MM-DDTHH:MM:SSZ` format. Capture the timestamp once per call and share it across all alerts and metrics.
- Determinism: identical input and identical artifact must produce identical output, excluding `created_at` and `generated_at`.
- Output uses only `dict`, `list`, `str`, `int`, `float`, `bool`, and `None`.
- Floats produced by the ML module are rounded to four decimals, with no NaN or infinity. `amount_inr` is copied unchanged.

### Exceptions

- `ValueError`: empty input, mixed `ground_truth` presence, or otherwise unusable input.
- `RuntimeError`: artifact missing, unreadable, unsupported `artifact_version`, or missing required metadata.

## 8. API behaviour

| Method / path | Success | Failure |
|---|---|---|
| `POST /api/pipeline/run` (no body) | HTTP 200: `{"n_transactions": int, "n_alerts": int, "metrics_available": bool}` | See below |
| `GET /api/alerts[?status=OPEN]` | HTTP 200: `{"alerts": [...]}`. Each item is the full alert without `evidence`, in `run_analysis` order | HTTP 422 for unknown `status` |
| `GET /api/alerts/{alert_id}` | HTTP 200: full alert | HTTP 404: `{"detail":"alert_not_found"}` |
| `GET /api/metrics` | HTTP 200: metrics object | HTTP 404: `{"detail":"metrics_unavailable"}` |

### API rules

- `POST /api/pipeline/run` re-reads `data/transactions.jsonl`, validates it, and re-runs analysis.
- Generating data and training are separate command-line scripts owned by the ML developer. They are not part of this API contract.
- Backend runs the pipeline once at startup if the data file exists.
- The cache is replaced atomically and only on success. A failed run keeps the previous cache.
- Before any successful run, all three GET endpoints return HTTP 503: `{"detail":"analysis_not_run"}`. This takes precedence over `metrics_unavailable`.
- `metrics_unavailable` is returned whenever `metrics` is `None`.
- The frontend hides the metrics panel on HTTP 404 and shows an empty or retry state on HTTP 503.
- No endpoint returns transactions or `ground_truth`.

## 9. Error handling

| Where | Condition | Result |
|---|---|---|
| Backend, on `POST /api/pipeline/run` | Data file missing | HTTP 404: `{"detail":"data_file_not_found"}` |
| Backend | File fails Section 1 validation, including types, enums, duplicate `txn_id`, or mixed `ground_truth` | HTTP 422: `{"detail":"invalid_transactions"}` |
| ML | `ValueError` | Backend returns HTTP 422: `{"detail":"invalid_transactions"}` |
| ML | `RuntimeError` | Backend returns HTTP 500: `{"detail":"model_unavailable"}` |
| Backend | ML output fails validation | HTTP 500: `{"detail":"ml_output_invalid"}` |

### Backend output validation

Before caching, validate:
- JSON schema types and enums, with unknown fields rejected. This also blocks stray `ground_truth`.
- `ml.flagged == (score >= threshold)`.
- `baseline.flagged == (rules_triggered is non-empty)`.
- Priority matches Section 5, and every alert has at least one flag.
- Evidence integrity rules in Section 5.
- No alert string contains `ground_truth`, `mule_ring`, or `shared_device_family`.

## 10. Frozen names and rules

Neither developer changes these without agreement from the other:

1. All field names, enums, ID formats, endpoint paths, the function name `run_analysis`, and output keys `contract_version`, `alerts`, and `metrics`.
2. Section 2 precedence, Section 3 metadata fields, Section 4 split and threshold rules, and Section 5 priority and integrity rules.
3. `ground_truth` is never a feature, never in alerts, and never returned by any endpoint.
4. The score field is `score`. UI text says **"Model risk score (uncalibrated, for ranking)"**. It never says "probability" or "% chance".
5. Missing values are `null`, never `""`, `0`, or NaN.
6. Any contract change bumps `contract_version` and, if Section 3 changes, `artifact_version`. Both developers must approve the change.

## 11. File ownership

| Owner | Files |
|---|---|
| **ML developer (you)** | `ml/*` (`generate_data.py`, `features.py`, `baseline_rules.py`, `train.py`, `evaluate.py`, `pipeline.py`, `__init__.py`, `requirements.txt`); `frontend/*`; `contracts/alert.schema.json`; `contracts/metrics.schema.json`; `contracts/sample_alerts.json`; generated `data/transactions.jsonl` and `data/artifacts/*` |
| **Amishi (backend)** | `backend/*` (`main.py`, `routes.py`, `schemas.py`, `services.py`, `requirements.txt`); `contracts/transaction.schema.json` |
| **Shared** | `contracts/CONTRACT.md`, `README.md`, `.gitignore` |

Owning a file under `contracts/` does not permit changing contract-defined content independently. Every such change requires the other developer's agreement.

`sample_alerts.json` must validate against `alert.schema.json`, must not contain `ground_truth`, and is placeholder data, not evidence of model behaviour.

## 12. Unresolved limitations

These limitations are documented and are not fixed in v1.1:

- **L1. Weak fingerprint:** The fingerprint covers only `txn_id` values. A dataset with the same IDs but altered amounts, accounts, or devices will match, potentially producing metrics against a mismatched model.
- **L2. Shared graph structure:** Features for held-out accounts come from the full transaction graph, so held-out and training accounts share edges. This is not label leakage, but the held-out set is not a fully isolated test.
- **L3. Small groups:** If the dataset has fewer than two shared-device-family accounts, they cannot be held out. The scenario is omitted from `by_scenario`, and the benign shared-device case cannot be evaluated. Small held-out sets produce noisy metrics.
- **L4. One reason for metrics unavailability:** Missing `ground_truth`, fingerprint mismatch, and an empty held-out set all produce the same `metrics_unavailable` response. The contract exposes no reason.
- **L5. Label design:** Victim accounts in `mule_ring` transactions that are not listed as ring members are labelled `normal` (negative), according to Section 2.
- **L6. Generation and training are not callable through the API:** Synthetic data generation happens through the ML developer's scripts, not an endpoint.
- **L7. Device data is sender-side only:** Receive-only accounts have no device nodes because the schema records only `sender_device_id`.
