# TraceUPI Interface Contract v1.2

**Status:** Effective and frozen; approved by project owner (incorporating Step 8E clarified specifications).  
**Supersedes:** Contract v1.1.  
**Architecture:** Monorepo; React frontend (Vite) → FastAPI backend → in-process `ml` package; synthetic data only; no database; in-memory review persistence.

---

## 1. Summary of Changes from Contract v1.1

1. **Temporal Heterogeneous Graph (§6):** Added explicit `merchant` and `complaint` node and edge types alongside `account` and `device`.
2. **Event Time, Ingestion Time, and Point-in-Time Replay (§3):** Formally partitioned $t_{\text{event}}$ (execution time), $t_{\text{ingested}}$ (system arrival time), $t_{\text{filed}}$ (complaint filing time), and $t_{\text{complaint\_ingested}}$ (complaint system arrival time), defining a five-stage deterministic snapshot processing pipeline.
3. **Incomplete Records & Nullable Telemetry (§2.3, §5.2):** Formally permitted nullable `sender_device_id`, `merchant_id`, `merchant_category`, and `complaint`. Documented that mapping absent device telemetry to zeros is a compatibility compromise for the frozen 25-feature model.
4. **Normalized Complaint Schema & Precedence (§2.3, §2.4):** Defined canonical complaint category enum including `"UNSPECIFIED"`. Specified strict validation rejection (HTTP 422) if legacy `complaint_filed == False` conflicts with a non-null `complaint` object.
5. **Fixed Analyst Alert Budget & Baseline Ranking (§8):** Defined Precision@K, Recall@K, and deterministic tie-breaking for $K \in \{10, 20, 50\}$ (default $K=20$). Defined multi-tier baseline budget ranking alongside fixed-threshold baseline metrics.
6. **Alert Fingerprinting & Review Staleness (§9.2):** Defined canonical string serialization for `alert_fingerprint`. Specified that material evidence/score changes reset active review status to `"OPEN"`, flag `is_stale = true`, and preserve previous review history.
7. **Counterfactual Validation & Tri-Directional Deltas (§10):** Added canonical `POST /api/alerts/{alert_id}/counterfactual` with strict request validation. Defined signed delta $\Delta \text{score} = \text{counterfactual\_score} - \text{original\_score}$ (supporting negative, positive, or zero deltas).
8. **Evidence-Path Edge Cases (§7.2):** Specified that alerts without a valid connected evidence walk must return `evidence_path = []` rather than inventing fictitious paths.
9. **Merchant Settlement Semantics (§6.2):** Formally defined merchant receiver accounts as synthetic settlement accounts linked via structural `merchant_profile` edges, completely eliminating double-counting.
10. **Zero Model Breakage:** Guaranteed 100% backward compatibility with the existing 25-feature model artifact (`data/artifacts/model.joblib`) without retraining or reordering features.
11. **AlertSummary & Budget Filtering (§7.0, §11):** Defined lightweight `AlertSummary` schema (excluding `evidence` and `previous_review` to optimize queue performance) and specified that `GET /api/alerts?budget_k=K` filters the top K alerts by ML score without altering baseline rules.
12. **Canonical Metrics Response Schema (§8.3):** Defined canonical JSON response structure for `GET /api/metrics`, explicitly partitioning unconstrained fixed-threshold baseline metrics from budget-constrained metrics (`budget_metrics`).
13. **Point-in-Time as_of Parameter (§3.2, §11):** Added optional `as_of` ISO 8601 UTC timestamp to `POST /api/pipeline/run`, strictly separating synthetic ledger cutoffs from operational review wall-clock timestamps.
14. **Topology-Aware Fingerprinting & Multi-Staleness Rules (§9.2):** Expanded alert fingerprint serialization to capture multi-account device sharing (`device_links`) and visible complaint bindings (`complaint_links`). Reconciled staleness reasons (`historical_snapshot_evidence_divergence` vs `evidence_or_score_changed`) and defined composite-key `(account_id, alert_fingerprint)` review restoration.
15. **Alert-Centric Graph Explorer Scope (§6.0):** Formally defined the alert-centric evidence subgraph architecture and documented hackathon MVP boundaries.

---

## 2. Transaction Event Schema & Identifiers

Input files: `data/transactions.jsonl` (small regression fixture) and `data/transactions_expanded.jsonl` (primary benchmark), UTF-8, one JSON object per line. Produced by the ML developer and read-only for the backend.

### 2.1 Identifier Formats & Casing

All entity identifiers in Contract v1.2 are strictly uppercase strings:
- **Account ID:** `ACC_` + 4 digits (e.g. `"ACC_0042"`, `"ACC_0917"`). Regex: `^ACC_\d{4}$`.
- **Device ID:** `DEV_` + 4 digits (e.g. `"DEV_0031"`). Regex: `^DEV_\d{4}$`.
- **Transaction ID:** `T` + 6 digits (e.g. `"T000123"`). Regex: `^T\d{6}$`.
- **Merchant ID:** `MER_` + 4 digits (e.g. `"MER_0012"`). Regex: `^MER_\d{4}$`.
- **Complaint ID:** `CMP_` + 4 digits (e.g. `"CMP_0005"`). Regex: `^CMP_\d{4}$`.
- **Alert ID:** `ALT_` + 4 digits (e.g. `"ALT_0001"`). Regex: `^ALT_\d{4}$`.
- **Edge ID:** `E` + integer (e.g. `"E1"`, `"E2"`). Regex: `^E\d+$`.

### 2.2 Canonical Transaction Event Record

```json
{
  "txn_id": "T000123",
  "timestamp": "2026-10-01T10:15:30Z",
  "ingested_at": "2026-10-01T10:15:32Z",
  "sender_account": "ACC_0042",
  "receiver_account": "ACC_0917",
  "sender_device_id": "DEV_0031",
  "merchant_id": null,
  "merchant_category": null,
  "amount_inr": 4999.0,
  "status": "SUCCESS",
  "complaint_filed": true,
  "complaint": {
    "complaint_id": "CMP_0012",
    "filed_at": "2026-10-01T14:30:00Z",
    "ingested_at": "2026-10-01T14:30:05Z",
    "category": "UNAUTHORIZED_TRANSACTION"
  },
  "ground_truth": {
    "scenario": "mule_ring",
    "ring_member_accounts": ["ACC_0917"]
  }
}
```

### 2.3 Field Rules & Incomplete Record Semantics

| Field | Type | Required | Nullable | Validation Rule & Operational Semantics |
| :--- | :---: | :---: | :---: | :--- |
| `txn_id` | string | Yes | No | Unique across the dataset. |
| `timestamp` | string | Yes | No | **Event Time ($t_{\text{event}}$)**: ISO 8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`). Execution time of the transfer. |
| `ingested_at` | string | Optional | No | **Ingestion Time ($t_{\text{ingested}}$)**: ISO 8601 UTC. Arrival at system ledger. Must satisfy $t_{\text{ingested}} \ge t_{\text{event}}$. If omitted in input, defaults to `timestamp`. |
| `sender_account` | string | Yes | No | `ACC_` + 4 digits; must differ from `receiver_account`. |
| `receiver_account` | string | Yes | No | `ACC_` + 4 digits; must differ from `sender_account`. |
| `sender_device_id` | string | Optional | **Yes** | `DEV_` + 4 digits. **Nullable**: If `null` or omitted, denotes incomplete record (e.g. USSD, web portal, or uncaptured hardware identifier). |
| `merchant_id` | string | Optional | **Yes** | `MER_` + 4 digits. **Nullable**: Present if and only if the transaction represents a commercial retail payment. |
| `merchant_category` | string | Optional | **Yes** | Enum: `"ELECTRONICS"`, `"JEWELRY"`, `"CRYPTO_VOUCHER"`, `"GENERAL_RETAIL"`, `"GAMING"`, `"SERVICES"`, or `null`. Must be non-null if and only if `merchant_id` is non-null. |
| `amount_inr` | number | Yes | No | Float $> 0.0$. |
| `status` | string | Yes | No | Enum: `"SUCCESS"` or `"FAILED"`. |
| `complaint_filed` | boolean | Optional | No | Legacy boolean flag. See Section 2.4 for precedence rules. |
| `complaint` | object | Optional | **Yes** | **Nullable**: Nested complaint telemetry object. |
| `complaint.complaint_id` | string | Conditional | No | Unique complaint identifier (`CMP_` + 4 digits). Required if `complaint` is present. |
| `complaint.filed_at` | string | Conditional | No | **Complaint Filing Time ($t_{\text{filed}}$)**: ISO 8601 UTC. Must satisfy $t_{\text{filed}} \ge t_{\text{event}}$. |
| `complaint.ingested_at` | string | Conditional | No | **Complaint Arrival Time ($t_{\text{complaint\_ingested}}$)**: ISO 8601 UTC ($t_{\text{complaint\_ingested}} \ge t_{\text{filed}}$). If omitted, defaults to `filed_at`. |
| `complaint.category` | string | Conditional | No | **Canonical Enum:** `"UNAUTHORIZED_TRANSACTION"`, `"PHISHING_SCAM"`, `"NON_DELIVERY_GOODS"`, `"UNSPECIFIED"`. Unrecognized strings reject with HTTP 422: `{"detail":"invalid_complaint_category"}`. |
| `ground_truth` | object | Conditional | No | Present only for synthetic benchmark evaluation. All-or-none across input records. |
| `ground_truth.scenario` | string | Conditional | No | Enum: `"mule_ring"`, `"shared_device_family"`, or `"normal"`. |
| `ground_truth.ring_member_accounts` | list of str | Conditional | No | Accounts participating in the mule ring; empty list `[]` for benign scenarios. |

### 2.4 Dual Complaint-Input Precedence & Conflict Validation

To ensure backwards compatibility with `data/transactions.jsonl` while preventing data ambiguity:
1. **Explicit Conflict Error:** If a record provides both `complaint` (non-null object) AND `"complaint_filed": false`, the input is invalid. Validation rejects with HTTP 422: `{"detail":"conflicting_complaint_telemetry"}` or raises `ValueError("Conflicting complaint telemetry: complaint object provided but complaint_filed is False")`.
2. **Consistent Structured Telemetry:** If `complaint` is non-null, and `complaint_filed` is either `true` or omitted, the structured `complaint` object is used.
3. **Legacy Boolean Mode:** If `complaint` is null or omitted, and `"complaint_filed": true`, a complaint event is synthesized with:
   - `complaint_id = "CMP_" + txn_id[1:]`
   - `filed_at = timestamp`
   - `ingested_at = ingested_at`
   - `category = "UNSPECIFIED"`
4. **Clean Negative Mode:** If `complaint` is null or omitted, and `complaint_filed` is `false` (or omitted), no complaint exists.

---

## 3. Event Time, Ingestion Time, Snapshot Isolation, and Replay Pipeline

### 3.1 Four Formal Timestamps
1. **Transaction Event Time ($t_{\text{event}}$):** Physical transfer execution time (`timestamp`). Governs temporal motifs (e.g. rapid pass-through window $\Delta t = t_2 - t_1$) and account velocity.
2. **Transaction Ingestion Time ($t_{\text{ingested}}$):** Time transaction became visible to the banking system (`ingested_at`).
3. **Complaint Filing Time ($t_{\text{filed}}$):** Time the incident was filed by the victim (`complaint.filed_at`).
4. **Complaint Ingestion Time ($t_{\text{complaint\_ingested}}$):** Time the complaint record arrived in the ledger (`complaint.ingested_at`).

### 3.2 Five-Stage Deterministic Replay Pipeline
For an analysis evaluated as of cutoff time $T_{\text{as\_of}}$, `ml.pipeline.run_analysis` processes events in this exact sequence:

```
[Input JSONL Records]
         │
         ▼
[1. Validation & Normalization] ──► Rejects malformed JSON, conflicting complaints, unknown categories
         │
         ▼
[2. Transaction Ingestion Cutoff] ──► Retains records with t_ingested <= T_as_of; drops later transactions
         │
         ▼
[3. Complaint Ingestion Visibility] ──► For visible txns, complaint is active iff t_complaint_ingested <= T_as_of.
         │                              (Filing time t_filed <= T_as_of alone NEVER grants premature visibility)
         ▼
[4. Deterministic Event Sorting] ──► Sort visible txns by primary (timestamp asc), tie-breaker (txn_id asc)
         │
         ▼
[5. Graph & Feature Extraction] ──► Order complaints by (filed_at asc, complaint_id asc).
                                     Edges use t_event for transfers, t_filed for complaints.
```

#### Premature Visibility Prevention Example
- Transaction executed at $t_{\text{event}} = 10:00$, ingested at $t_{\text{ingested}} = 10:02$.
- Victim files complaint at $t_{\text{filed}} = 11:30$, but ledger ingests it at $t_{\text{complaint\_ingested}} = 14:00$.
- **Snapshot at $T_{\text{as\_of}} = 12:00$:** The transaction is visible ($10:02 \le 12:00$). The complaint is **strictly hidden** because $14:00 > 12:00$. Even though $t_{\text{filed}} \le 12:00$, the system had not yet received it. `complaint_count_as_receiver` remains 0.0.
- **Snapshot at $T_{\text{as\_of}} = 15:00$:** Both transaction and complaint are visible ($14:00 \le 15:00$). `complaint_count_as_receiver` increments to 1.0.

#### API Cutoff Parameter & Timestamp Separation
1. **Optional as_of Parameter:** `POST /api/pipeline/run` accepts an optional JSON body: `{"as_of": "YYYY-MM-DDTHH:MM:SSZ"}`.
   - When omitted or null, $T_{\text{as\_of}}$ defaults to $+\infty$ (all ingested records processed).
   - If provided, it must be a valid ISO 8601 UTC timestamp string; malformed inputs reject with HTTP 422: `{"detail":"invalid_as_of_timestamp"}`.
2. **Timestamp Domain Separation:**
   - **Synthetic Ledger Time:** ($t_{\text{event}}$, $t_{\text{ingested}}$, $t_{\text{filed}}$, $t_{\text{complaint\_ingested}}$, $T_{\text{as\_of}}$) belongs strictly to the data domain and governs point-in-time visibility.
   - **Operational Wall-Clock Time:** `review.updated_at` records the real-world system UTC timestamp when an analyst submits a review decision, ensuring operational audit logs are never corrupted by historical replay cutoffs.

### 3.3 Deterministic Output Partitioning
- **Bitwise Deterministic Outputs:** Across any line permutation of input records, these fields must be 100% bitwise identical:
  - `ml.score`, `ml.threshold`, `ml.flagged`
  - `baseline.flagged`, `baseline.rules_triggered`
  - `top_reasons` (feature names, values, training medians, order)
  - `evidence.nodes` (ids, types, labels, scores, order)
  - `evidence.edges` (ids, sources, targets, types, amounts, timestamps, order)
  - `evidence_path` (ordered list of edge IDs)
  - `metrics` (all precision, recall, F1, counts, budget metrics, scenario breakdowns)
- **Runtime Non-Deterministic Outputs:** 
  - `created_at`, `generated_at` (current UTC execution timestamps)
  - Execution duration timers.

---

## 4. Ground-Truth Isolation & Account-Level Scenario Precedence

Every account appearing as sender or receiver gets exactly one scenario, assigned by the first matching rule:

1. `mule_ring`: The account appears in `ring_member_accounts` of any transaction in the dataset.
2. `shared_device_family`: Otherwise, the account is sender or receiver in any transaction whose `ground_truth.scenario` is `shared_device_family`.
3. `normal`: Everything else.

**Binary Label:** Positive (`1`) if and only if the scenario is `mule_ring`. All other accounts are Negative (`0`).

**Evaluation-Label Isolation:** Ground-truth labels are used exclusively for offline benchmark evaluation (`GET /api/metrics`). They must never enter the feature matrix, never be read during inference, never appear in alerts, and never be exposed in API responses. Human review decisions are operational verdicts and **never** overwrite benchmark ground-truth labels.

---

## 5. Model Feature Preservation & Incomplete Records

### 5.1 Preserved Feature Schema

The trained Random Forest model (`data/artifacts/model.joblib`) requires **exactly 25 input features** in the exact order below. This feature vector must never be altered or reordered:

```python
FEATURE_NAMES: list[str] = [
    # 1. Transaction Volumes & Counts
    "txn_count_sent",
    "txn_count_received",
    "txn_count_total",
    "txn_success_sent",
    "txn_success_received",
    "txn_failed_sent",
    "txn_failed_received",
    "failure_rate_sent",
    # 2. Monetary Amounts & Aggregates (INR)
    "amount_sent_total",
    "amount_received_total",
    "net_flow_amount",
    "amount_sent_avg",
    "amount_received_avg",
    "amount_sent_max",
    "amount_received_max",
    "amount_max_overall",
    # 3. Graph Topology & Counterparties
    "fan_in_count",
    "fan_out_count",
    "counterparty_count_total",
    "fan_ratio",
    # 4. Complaints
    "complaint_count_as_receiver",
    "complaint_count_as_sender",
    # 5. Sender-Side Device Sharing (Limitation L7)
    "devices_used_count",
    "max_senders_on_used_devices",
    "shared_device_user_flag",
]
```

### 5.2 Missing-Device Compatibility Compromise

1. **The Compatibility Compromise:**
   - In the existing 25-feature model, mapping absent device telemetry (`sender_device_id: null` or omitted) to zero-valued device features (`devices_used_count = 0.0`, `max_senders_on_used_devices = 0.0`, `shared_device_user_flag = 0.0`) is a **deliberate compatibility compromise** to allow inference on incomplete records without breaking the frozen estimator artifact.
   - **Crucial Caution:** Setting device features to zero does **not** prove that missing telemetry is equivalent to genuine non-sharing. Rather, it represents the complete absence of hardware observations.
2. **Operational Distinctions:**
   - *Verified Dedicated Device:* Account observed using hardware with no multi-user overlap $\implies \text{devices\_used\_count} = 1.0, \text{max\_senders\_on\_used\_devices} = 1.0, \text{shared\_device\_user\_flag} = 0.0$.
   - *Verified Shared Device:* Account observed sharing hardware with other senders $\implies \text{shared\_device\_user\_flag} = 1.0$.
   - *Unobserved Device Telemetry:* Account transacted via web/USSD where device ID was uncaptured $\implies \text{devices\_used\_count} = 0.0, \text{max\_senders\_on\_used\_devices} = 0.0, \text{shared\_device\_user\_flag} = 0.0$.
   - No fictitious device IDs may be invented.
3. **Required Evaluation of Impact:**
   - Automated tests must evaluate the impact of missing device telemetry on benign shared-device false alarms: if a household member's device telemetry is missing, their sharing flag evaluates to 0, which suppresses false alarms on benign families but also risks masking collusion if the user were part of a fraud ring.

---

## 6. Heterogeneous Temporal Graph & Merchant Semantics

The investigation graph is a heterogeneous temporal directed graph $G = (V, E)$.

### 6.0 Graph Exploration Scope & MVP Boundaries
Graph exploration in TraceUPI is delivered as an **alert-centric investigator**:
1. **Alert-Centric Subgraph Delivery:** When an investigator selects an alert from the queue, `GET /api/alerts/{alert_id}` provides the localized 2-hop evidence subgraph (`evidence.nodes`, `evidence.edges`, capped at 25 nodes and 60 edges) centered on the flagged account.
2. **Mandatory Brief Compliance:** This architecture satisfies 100% of the hackathon brief requirements:
   - Heterogeneous node types (`account`, `device`, `merchant`, `complaint`).
   - Heterogeneous edge types (`transfer`, `uses_device`, `merchant_profile`, `has_complaint`).
   - Explainable traceable evidence paths (`evidence_path`) connecting the fraud ring.
   - Temporal motif detection (`RAPID_PASS_THROUGH`, `DORMANCY_BURST`).
   - Interactive counterfactual what-if edge toggling with live recomputation.
3. **Explicit MVP Boundaries:**
   - *Scoped Canvas:* Graph rendering is scoped to alert subgraphs to ensure high-performance rendering and clear visual comprehension without browser WebGL/SVG freeze. Unpartitioned 3,000-edge full-network hairballs are not rendered.
   - *Triage-Driven Rooting:* Unflagged benign accounts without structural links to an alert are not browsable as standalone root nodes.

### 6.1 Node Schema (`evidence.nodes`)
```json
{
  "id": "ACC_0917",
  "type": "account",
  "label": "ACC_0917",
  "score": 0.9300,
  "metadata": {
    "is_merchant": false,
    "merchant_id": null
  }
}
```
- `type == "account"`: Primary bank account. `score` is the account's uncalibrated ML score. `metadata.is_merchant` is true if associated with a `merchant_id`.
- `type == "device"`: Hardware identifier (`DEV_xxxx`). `score: null`.
- `type == "merchant"`: Business commercial profile node (`MER_xxxx`). `score: null`. `metadata.category` contains `merchant_category`.
- `type == "complaint"`: Complaint incident node (`CMP_xxxx`). `score: null`. `metadata.filed_at` contains filing timestamp.

### 6.2 Merchant Settlement Accounts & Non-Double-Counting Semantics

To represent merchant payments accurately without corrupting financial totals:
1. **Synthetic Settlement Account:** In a merchant transaction, `receiver_account` (`ACC_yyyy`) is the merchant's bank settlement account. It is a genuine account node in the graph with `metadata.is_merchant = true` and `metadata.merchant_id = "MER_zzzz"`.
2. **Financial Transfer Edge:** The payment creates **exactly one financial `transfer` edge** from `sender_account` (`ACC_xxxx`) to `receiver_account` (`ACC_yyyy`), carrying `amount_inr`, `timestamp`, and `txn_id`.
3. **Descriptive Profile Edge:** An auxiliary structural edge `merchant_profile` links the settlement account to the commercial entity node:
   $$\text{Edge: } ACC\_yyyy \xrightarrow{\text{type: merchant\_profile}} MER\_zzzz$$
   This edge carries `amount_inr: null`, `timestamp: null`, `txn_id: null`.
4. **Zero Double-Counting Guarantee:** All financial aggregates (`amount_sent_total`, `amount_received_total`, `net_flow_amount`), velocity calculations, and temporal motifs sum amounts and count transactions **strictly across edges where `type == "transfer"`**. Structural `merchant_profile` edges are excluded from monetary math.
5. **Evidence Path Inclusion:** An evidence path tracing fraud cash-out can traverse through the settlement account to the merchant entity node via the `merchant_profile` edge to highlight commercial liquidation.

---

## 7. Alert Schema, Traceable Paths, and Edge Cases

### 7.0 AlertSummary Schema & Budget Filtering (`GET /api/alerts`)

The alert queue endpoint `GET /api/alerts` returns `{"alerts": [AlertSummary, ...]}`:
1. **Payload Optimization:** `AlertSummary` contains all top-level Alert fields (`alert_id`, `alert_fingerprint`, `account_id`, `created_at`, `status`, `priority`, `ml`, `baseline`, `top_reasons`, `context_flags`, `review`) **except** the `evidence` object (`nodes`, `edges`, `evidence_path`) and `review.previous_review`. This keeps queue payloads lightweight (~2 KB vs ~25 KB per alert) while providing full triage data. Full evidence is fetched on demand via `GET /api/alerts/{alert_id}`.
2. **Budget Queue Filtering (`budget_k` query param):**
   - `GET /api/alerts?budget_k=K` (for $K \in \{10, 20, 50\}$): Returns at most the top $K$ alerts ranked by primary $ml.score$ (descending), tie-broken by $account\_id$ (ascending).
   - Omitting `budget_k`: Returns all generated alerts (unconstrained volume).
   - **Non-Interference Rule:** Query parameter `budget_k` is strictly an analyst capacity queue filter. It does **not** alter baseline rule execution, does not modify rule trigger flags, and does not alter assigned alert priority (`HIGH`, `MEDIUM`, `LOW`).

### 7.1 Alert Schema Example

```json
{
  "alert_id": "ALT_0001",
  "alert_fingerprint": "a3f5b7...",
  "account_id": "ACC_0917",
  "created_at": "2026-10-15T16:00:00Z",
  "status": "OPEN",
  "priority": "HIGH",
  "ml": {
    "score": 0.9300,
    "threshold": 0.5000,
    "flagged": true
  },
  "baseline": {
    "flagged": true,
    "rules_triggered": ["HIGH_FAN_IN", "RAPID_PASS_THROUGH"]
  },
  "top_reasons": [
    {
      "feature": "fan_in_count",
      "value": 14.0,
      "typical_value": 2.0,
      "explanation": "Received transfers from 14 distinct counterparties (typical training median: 2.0)."
    },
    {
      "feature": "amount_received_total",
      "value": 48500.0,
      "typical_value": 1950.0,
      "explanation": "Total funds received of Rs 48,500 significantly exceeds training median (Rs 1,950)."
    }
  ],
  "context_flags": {
    "shared_device_detected": false,
    "rapid_pass_through_detected": true,
    "note": "Rapid consolidation detected: Rs 48,500 dispersed within 45 minutes of receipt."
  },
  "review": {
    "status": "OPEN",
    "is_stale": false,
    "staleness_reason": null,
    "analyst_id": null,
    "updated_at": null,
    "verdict": null,
    "notes": null,
    "previous_review": null
  },
  "evidence": {
    "nodes": [
      {"id": "ACC_0917", "type": "account", "label": "ACC_0917", "score": 0.9300, "metadata": {}},
      {"id": "ACC_0042", "type": "account", "label": "ACC_0042", "score": 0.1200, "metadata": {}},
      {"id": "DEV_0031", "type": "device", "label": "DEV_0031", "score": null, "metadata": {}}
    ],
    "edges": [
      {"id": "E1", "source": "ACC_0042", "target": "ACC_0917", "type": "transfer", "txn_id": "T000123", "amount_inr": 4999.0, "timestamp": "2026-10-01T10:15:30Z"},
      {"id": "E2", "source": "ACC_0042", "target": "DEV_0031", "type": "uses_device", "txn_id": null, "amount_inr": null, "timestamp": null}
    ],
    "evidence_path": ["E1"]
  }
}
```

### 7.2 Evidence Path Rules, Disconnected Edge Cases, and Disclaimer
1. **Contiguity When Present:** If `evidence_path` is non-empty, its edges must form a continuous connected walk (direction ignored) where at least one edge touches `account_id`.
2. **Disconnected Edge Case (Empty Path):** If an account is flagged purely on isolated features (e.g. high failure rate on disconnected failed transfers, or volume burst without multi-hop connectivity), the system must return `evidence_path = []` (an empty list). **Fictitious edges or disconnected paths must never be invented.**
3. **Hard Size Caps:**
   - `evidence_path`: Maximum 10 edges ($0 \le |\text{evidence\_path}| \le 10$).
   - `evidence.nodes`: Maximum 25 nodes.
   - `evidence.edges`: Maximum 60 edges.
4. **Causation Disclaimer:** Evidence paths illustrate graph connectivity, transfer flow, and shared infrastructure. **They do not constitute legal proof of conspiratorial causation.**

---

## 8. Fixed Analyst Budget & Evaluation Metrics

### 8.1 Fixed Analyst Budget Ranking ($K \in \{10, 20, 50\}$, default $K=20$)

Investigators evaluate accounts within a fixed operational capacity budget $K$:
1. **ML Model Budget Ranking:** Held-out accounts are sorted deterministically:
   $$\text{Primary: } ml.score \text{ (descending)}, \quad \text{Tie-breaker: } account\_id \text{ (ascending)}$$
   The top $N = \min(K, |\text{Heldout}|)$ accounts form $\mathcal{A}_K$.
   $$\text{Precision@K} = \frac{\sum_{a \in \mathcal{A}_K} \mathbb{I}(y_a = 1)}{N}, \quad \text{Recall@K} = \frac{\sum_{a \in \mathcal{A}_K} \mathbb{I}(y_a = 1)}{\text{Total Positives in Held-Out Set}}$$
   If $N=0$, Precision@K is `null`. If total positives is 0, Recall@K is `null`.
2. **Baseline Budget Ranking:** Because baseline rules produce discrete triggers rather than continuous scores, baseline accounts are ranked at budget $K$ via multi-tier deterministic sorting:
   $$\text{1st: } |\text{rules\_triggered}| \text{ (descending)}, \quad \text{2nd: } \text{net\_flow\_amount (descending)}, \quad \text{3rd: } account\_id \text{ (ascending)}$$
   The top $N$ accounts form $\mathcal{B}_K$, yielding `baseline.budget_metrics.precision_at_k` and `recall_at_k`.
3. **Non-Equivalence Disclaimer:** Baseline fixed-threshold metrics (evaluated over all accounts with $\ge 1$ rule triggered) evaluate an unconstrained alert volume and are **not directly comparable** to ML Precision@K without noting the budget constraint.

### 8.2 Benign Shared-Device False Positive Rate ($\text{FPR}_{\text{shared\_device}}$)

Evaluated strictly on the held-out cohort of accounts whose assigned scenario is `"shared_device_family"`:
$$\text{FPR}_{\text{shared\_device}} = \frac{|\{a \in \text{Heldout} \mid \text{scenario}(a) = \text{shared\_device\_family} \land ml.score(a) \ge \text{threshold}\}|}{|\{a \in \text{Heldout} \mid \text{scenario}(a) = \text{shared\_device\_family}\}|}$$
- **Cohort Purity:** Under Section 4 precedence, mule ring accounts who share a device are assigned to `"mule_ring"`. They are excluded from this denominator.
- **Reporting Rule:** If the denominator is 0 (fewer than 2 shared-device accounts in dataset), `fpr_benign_shared_device` is `null`. $\text{FPR}_{\text{shared\_device}}$ is reported as an **empirical measurement**, not a guaranteed bound. Acceptance target $\le 0.05$ is validated by automated tests.

### 8.3 Canonical JSON Schema (`GET /api/metrics`)

*Note: All numeric values below are format illustrations only, not empirical evaluation results. Actual metrics are computed strictly over the held-out evaluation partition using the frozen deterministic split (seed 42).*

```json
{
  "generated_at": "2026-10-15T16:00:00Z",
  "budget_k": 20,
  "evaluation": {
    "evaluated_on": "held_out_accounts",
    "n_accounts": 18,
    "n_positive_accounts": 4,
    "n_shared_device_accounts": 4
  },
  "ml": {
    "threshold": 0.5000,
    "precision": 1.0,
    "recall": 1.0,
    "f1": 1.0,
    "true_positives": 4,
    "false_positives": 0,
    "false_negatives": 0,
    "budget_metrics": {
      "budget_k": 20,
      "k_effective": 18,
      "precision_at_k": 1.0,
      "recall_at_k": 1.0
    },
    "fairness": {
      "fpr_benign_shared_device": 0.0,
      "n_shared_device_evaluated": 4
    }
  },
  "baseline": {
    "precision": 0.0,
    "recall": 0.0,
    "f1": null,
    "true_positives": 0,
    "false_positives": 2,
    "false_negatives": 4,
    "budget_metrics": {
      "budget_k": 20,
      "k_effective": 18,
      "precision_at_k": 0.0,
      "recall_at_k": 0.0
    }
  },
  "by_scenario": [
    {
      "scenario": "mule_ring",
      "n_accounts": 4,
      "ml_flagged": 4,
      "baseline_flagged": 0
    },
    {
      "scenario": "normal",
      "n_accounts": 10,
      "ml_flagged": 0,
      "baseline_flagged": 1
    },
    {
      "scenario": "shared_device_family",
      "n_accounts": 4,
      "ml_flagged": 0,
      "baseline_flagged": 1
    }
  ]
}
```

#### Metrics Zero-Denominator & Unavailable Rules
1. **Unavailable Data:** If the input dataset lacks ground-truth scenario annotations, `GET /api/metrics` returns HTTP 404: `{"detail":"metrics_unavailable"}`.
2. **Zero Positive Accounts:** If `n_positive_accounts == 0`, `ml.recall`, `ml.budget_metrics.recall_at_k`, and `baseline.budget_metrics.recall_at_k` are `null`.
3. **Zero Flagged Accounts:** If `true_positives + false_positives == 0`, `precision` is `null`.
4. **F1 Nullability:** If precision and recall are both `0.0` or either is `null`, `f1` is `null`.
5. **Zero Shared-Device Cohort:** If `n_shared_device_accounts == 0`, `fpr_benign_shared_device` is `null`.
6. **Effective Budget ($N$):** $N = \min(K, |\text{Heldout}|)$. If $N = 0$, `precision_at_k` is `null`.

---

## 9. Human-Review State Machine & Workflow API

### 9.1 State Transitions

```
               ┌────────────────────────────────────────────────────────┐
               │                          OPEN                          │
               └───────────┬────────────────────────────────┬───────────┘
                           │                                │
            ┌──────────────┴──────────────┐                 │
            ▼                             ▼                 ▼
┌───────────────────────┐     ┌───────────────────────┐     │
│     INVESTIGATING     ├────►│    CONFIRMED_FRAUD    │◄────┘
└───────────┬───────────┘     └───────────▲───────────┘
            │                             │
            │  ┌──────────────────────────┘ (Reopen)
            ▼  │
┌───────────────────────┐
│   DISMISSED_BENIGN    │◄──────────────────────────────────┐
└───────────┬───────────┘                                   │
            │                                               │
            └───────────────────────────────────────────────┘ (Direct)
```

- **Allowed Transitions:**
  - `OPEN` $\to$ `INVESTIGATING`, `CONFIRMED_FRAUD`, `DISMISSED_BENIGN`
  - `INVESTIGATING` $\to$ `CONFIRMED_FRAUD`, `DISMISSED_BENIGN`
  - `CONFIRMED_FRAUD` $\to$ `INVESTIGATING`
  - `DISMISSED_BENIGN` $\to$ `INVESTIGATING`
- Invalid transitions return HTTP 422: `{"detail":"invalid_review_transition"}`.

### 9.2 Canonical Endpoint: `PATCH /api/alerts/{alert_id}`

#### Request Body
```json
{
  "status": "CONFIRMED_FRAUD",
  "analyst_id": "ANALYST_01",
  "verdict": "CONFIRMED_MULE_RING",
  "notes": "Verified 3-hop rapid layering into merchant cash-out."
}
```

#### Alert Fingerprinting, Composite Key Storage, and Replay Staleness
1. **Topology-Aware Canonical Fingerprint Serialization:**
   $$\text{canonical\_str} = account\_id + "|" + \text{txns} + "|" + \text{device\_links} + "|" + \text{complaint\_links} + "|" + f"{ml.score:.4f}" + "|" + priority + "|" + \text{rules}$$

   Where:
   - `account_id`: String (e.g. `"ACC_0917"`).
   - `txns`: `",".join(sorted(txn_ids))` for all transactions directly touching `account_id` visible in the current snapshot ($t_{\text{ingested}} \le T_{\text{as\_of}}$).
   - `device_links`: `";".join(sorted([f"{dev}:{','.join(sorted(senders))}" for dev, senders in device_to_senders.items()]))` for all devices used by `account_id`. If a new account joins an already-linked device, this component changes deterministically.
   - `complaint_links`: `";".join(sorted([f"{c.id}:{c.category}:{c.filed_at}" for c in complaints if c.ingested_at <= T_as_of]))`. Complaints not yet ingested as of cutoff $T_{\text{as\_of}}$ are strictly excluded.
   - `score`: `f"{ml.score:.4f}"` (ensemble voting score rounded to 4 decimal places).
   - `priority`: Assigned alert priority (`"HIGH"`, `"MEDIUM"`, `"LOW"`).
   - `rules`: `",".join(sorted(rules_triggered))` (e.g. `"DORMANCY_BURST,HIGH_FAN_IN"`).

   $$\text{alert\_fingerprint} = \text{SHA-256}(\text{canonical\_str.encode('utf-8')}).hexdigest()$$

   *Zero-Noise Guarantee:* Excludes all presentation metadata (node SVG coordinates, layout bounding boxes, UI colors) and nondeterministic runtime timestamps (`created_at`, `generated_at`).

2. **Composite Key Review Storage:**
   Reviews are stored and retrieved in the in-memory review store indexed by composite key:
   $$\text{Key: } (account\_id, alert\_fingerprint)$$

3. **Reconciled Staleness Reasons:**
   When an alert regenerates with a fingerprint that does not match an active review:
   - `historical_snapshot_evidence_divergence`: Assigned when pipeline execution specifies an explicit historical cutoff ($T_{\text{as\_of}} \ne \text{null}$), and the resulting alert excludes late events that were present during the review.
   - `evidence_or_score_changed`: Assigned on standard runs ($T_{\text{as\_of}} = \text{null}$) when new or altered transactions, device links, or complaints modify the account's evidence, score, or rules compared to the previously reviewed alert.

4. **Lifecycle & Historical Review Restoration ($F_A \to F_B \to F_A$):**
   - **Exact Match ($F_{\text{current}} == F_{\text{reviewed}}$):** If the recomputed alert matches the exact fingerprint of a review in the store for `account_id`, the review state (`status`, `analyst_id`, `updated_at`, `verdict`, `notes`) is **restored/retained as active** with `is_stale = false`, `staleness_reason = null`.
   - **Divergent Snapshot ($F_{\text{current}} \ne F_{\text{reviewed}}$):** Status resets to `"OPEN"`, `review.is_stale = true` with the applicable staleness reason above, and prior review details are preserved in `review.previous_review` and logged in `review_history`.
   - **Replay Restoration:** Replaying from snapshot $A$ to historical snapshot $B$ and back to snapshot $A$ safely restores review $A$ as active (`is_stale = false`), preserving full audit continuity without overwriting prior notes.
   - **Disappeared Alert:** If an account is no longer flagged in the current snapshot, its alert is moved to `archived_alerts`.
   - **New Alert:** Newly flagged accounts initialize strictly with `status = "OPEN"`, `is_stale = false`.
5. **Process Restart Boundary:** Review decisions persist in memory across client requests during the server process lifecycle, but reset upon server restart.
6. **Strict Ground-Truth Isolation:** Human review decisions **never** modify the synthetic `ground_truth` object, model weights, or held-out evaluation labels.

---

## 10. Counterfactual Engine Specification

Answers what-if questions by perturbing evidence in a clean sandbox.

### 10.1 Endpoint: `POST /api/alerts/{alert_id}/counterfactual`

#### Request Body
```json
{
  "remove_edge_ids": ["E1"],
  "suppress_device_sharing": false,
  "suppress_complaints": false
}
```

#### Request Validation Rules
1. **Supported Edge Removals:** `remove_edge_ids` must contain only valid edge IDs present in `evidence.edges` where `type == "transfer"`.
2. **Error Rejection:**
   - If `remove_edge_ids` contains an unknown edge ID or a non-transfer edge ID (e.g. attempting to delete `merchant_profile` directly): HTTP 422 `{"detail":"invalid_counterfactual_intervention","error":"unknown_or_unsupported_edge_id"}`.
   - If all three interventions are empty/false: HTTP 422 `{"detail":"empty_counterfactual_request"}`.
   - Malformed interventions must **never** be silently ignored.

#### Response Body
```json
{
  "alert_id": "ALT_0001",
  "account_id": "ACC_0917",
  "original_score": 0.9300,
  "counterfactual_score": 0.1200,
  "score_delta": -0.8100,
  "original_flagged": true,
  "counterfactual_flagged": false,
  "rules_removed": ["HIGH_FAN_IN", "RAPID_PASS_THROUGH"],
  "rules_added": [],
  "plausible_benign_alternative": "Hypothesis: If transfer T000123 (Rs 4,999) is excluded, rapid pass-through velocity drops below threshold. Plausible benign pattern: Routine peer-to-peer transaction without layering behavior."
}
```

#### Operational Rules
1. **Signed Delta Definition:**
   $$\Delta \text{score} = \text{counterfactual\_score} - \text{original\_score}$$
   - $\Delta \text{score} < 0$: Suspicion decreased (e.g. suspicious layering transfer removed).
   - $\Delta \text{score} > 0$: Suspicion increased (e.g. legitimate high-volume flow removed, worsening failure rate or flow divergence).
   - $\Delta \text{score} = 0$: Suspicion unchanged (e.g. removing unflagged low-value transfer that does not alter decision tree splits).
   - All three signs are mathematically valid. Tests must verify numerical equality against returned original and counterfactual scores.
2. **Sandbox Isolation:** Evaluation executes on a deep copy of transactions in-memory and never mutates active alert caches.
3. **Hypothesis Labeling:** The `plausible_benign_alternative` text must begin with `"Hypothesis:"` to distinguish simulated conjectures from verified facts.

---

## 11. Complete API Endpoint Specification

| Method & Route | Success Status & Body | Error Codes & Reasons |
| :--- | :--- | :--- |
| `POST /api/pipeline/run` | HTTP 200: `{"n_transactions": int, "n_alerts": int, "metrics_available": bool, "as_of": Optional[str]}`<br>*(Optional Body: `{"as_of": "YYYY-MM-DDTHH:MM:SSZ"}`)* | HTTP 404: `{"detail":"data_file_not_found"}`<br>HTTP 422: `{"detail":"invalid_transactions"}` or `{"detail":"invalid_as_of_timestamp"}`<br>HTTP 500: `{"detail":"model_unavailable"}` |
| `GET /api/alerts` | HTTP 200: `{"alerts": [AlertSummary, ...]}` matching Section 7.0<br>*(Query params: `status`, `budget_k` where $K \in \{10, 20, 50\}$)* | HTTP 422: `{"detail":"invalid_filter_param"}`<br>HTTP 503: `{"detail":"analysis_not_run"}` |
| `GET /api/alerts/{alert_id}` | HTTP 200: Full `Alert` object matching Section 7.1 with heterogeneous `evidence` | HTTP 404: `{"detail":"alert_not_found"}`<br>HTTP 503: `{"detail":"analysis_not_run"}` |
| `PATCH /api/alerts/{alert_id}` | HTTP 200: Updated `Alert` object with new review metadata matching Section 9 | HTTP 404: `{"detail":"alert_not_found"}`<br>HTTP 422: `{"detail":"invalid_review_transition"}`<br>HTTP 503: `{"detail":"analysis_not_run"}` |
| `POST /api/alerts/{alert_id}/counterfactual` | HTTP 200: Counterfactual delta object matching Section 10 | HTTP 404: `{"detail":"alert_not_found"}`<br>HTTP 422: `{"detail":"invalid_counterfactual_request"}`<br>HTTP 503: `{"detail":"analysis_not_run"}` |
| `GET /api/metrics` | HTTP 200: Metrics object matching Section 8.3<br>*(Query param: `budget_k`, default 20)* | HTTP 404: `{"detail":"metrics_unavailable"}`<br>HTTP 422: `{"detail":"invalid_budget_k"}`<br>HTTP 503: `{"detail":"analysis_not_run"}` |

---

## 12. Known Limitations & Hackathon Boundaries

1. **Uncalibrated Ranking Score (L1):** `ml.score` is an ensemble voting ratio for ranking risk, not an empirical probability of fraud.
2. **Sender-Side Device Visibility (L7):** Hardware telemetry is observed on senders only. Pure receivers have no direct device node.
3. **In-Memory Review State:** Review decisions persist in memory across queries, but reset upon backend server process restart.
4. **Synthetic Data Only:** All accounts (`ACC_xxxx`), devices (`DEV_xxxx`), merchants (`MER_xxxx`), and amounts are entirely synthetic. No live UPI network connections or PII exist.

---

*End of Contract v1.2.*
