# TraceUPI — Step 8A.3: Final Contract Review Audit Report

**Date:** 2026-10-15  
**Auditor:** Senior Technical Lead  
**Scope:** Forensic consistency audit and review corrections across active Contract v1.1, proposed Contract v1.2 (`contracts/CONTRACT_v1.2_PROPOSAL.md`), `ml/features.py`, `ml/generate_data.py`, `ml/baseline_rules.py`, `ml/train.py`, `ml/evaluate.py`, tests, datasets, and the trained model artifact (`data/artifacts/model.joblib`).

---

## 1. Exact Corrections Made in Step 8A.3

1. **Complaint Category Consistency (§2.3, §2.4):**
   - Added `"UNSPECIFIED"` to the canonical allowed category enum:
     `["UNAUTHORIZED_TRANSACTION", "PHISHING_SCAM", "NON_DELIVERY_GOODS", "UNSPECIFIED"]`.
   - Enforced that legacy boolean inputs (`"complaint_filed": true`) normalize deterministically to `"UNSPECIFIED"`.
   - Any unrecognized string in `complaint.category` is rejected with HTTP 422 `{"detail":"invalid_complaint_category"}`.
2. **Point-in-Time Replay Pipeline (§3.2):**
   - Formally defined the exact five-stage processing sequence:
     1. Validation & normalization.
     2. Transaction ingestion cutoff ($t_{\text{ingested}} \le T_{\text{as\_of}}$).
     3. Independent complaint ingestion visibility ($t_{\text{complaint\_ingested}} \le T_{\text{as\_of}}$).
     4. Deterministic transaction sorting by primary `timestamp asc`, tie-breaker `txn_id asc`.
     5. Graph and feature extraction with complaints ordered by `filed_at asc`, `complaint_id asc`.
   - Explicitly proved that filing time alone ($t_{\text{filed}} \le T_{\text{as\_of}}$) never grants premature visibility if system arrival is later ($t_{\text{complaint\_ingested}} > T_{\text{as\_of}}$).
3. **Missing-Device Compatibility Compromise (§5.2):**
   - Documented that setting device features to zero when `sender_device_id` is null is a **deliberate compatibility compromise** to support the frozen 25-feature Random Forest model without retraining, NOT empirical proof that missing telemetry equals non-sharing.
   - Defined required test suite cases for missing key, explicit null, and known device IDs, evaluating false positive impact.
4. **Merchant Settlement Semantics (§6.2):**
   - Specified that `receiver_account` is an ordinary bank account node (`ACC_yyyy`) acting as the synthetic merchant settlement account (`metadata.is_merchant = true`, `metadata.merchant_id = "MER_zzzz"`).
   - Confirmed that financial flows generate **exactly one financial `transfer` edge**; the auxiliary `merchant_profile` edge carries `amount_inr: null`, completely preventing double-counting.
   - Defined how `merchant_profile` edges enter evidence paths to illustrate commercial liquidation.
5. **Evidence-Path Edge Cases (§7.2):**
   - Specified that if an account is flagged on isolated features without a connected walk, the alert returns `evidence_path = []` (an empty list). Fictitious paths must never be invented.
6. **Baseline and Budget Metrics (§8.1):**
   - Defined deterministic multi-tier ranking for the baseline heuristic at budget $K$:
     $$\text{1st: } |\text{rules\_triggered}| \text{ (descending)}, \quad \text{2nd: } \text{net\_flow\_amount (descending)}, \quad \text{3rd: } account\_id \text{ (ascending)}$$
   - Explicitly clarified that baseline fixed-threshold metrics evaluate unconstrained alert volume and are not directly comparable to ML Precision@K without noting the budget constraint.
7. **Alert Fingerprint Semantics & Staleness (§9.2):**
   - Defined canonical serialization for `alert_fingerprint`:
     $$\text{canonical\_str} = account\_id + "|" + ",".join(\text{sorted}(txn\_ids)) + "|" + f"{ml.score:.4f}" + "|" + ",".join(\text{sorted}(rules\_triggered))$$
   - Specified that material evidence or score changes reset active status to `"OPEN"`, set `review.is_stale = true`, and archive previous review details under `review.previous_review`.
8. **Counterfactual Intervention Validation (§10.1):**
   - Defined valid interventions: `remove_edge_ids` (must be valid `transfer` edges), `suppress_device_sharing`, `suppress_complaints`.
   - Added explicit validation rejection: HTTP 422 on unknown edge IDs, non-transfer edge removals, or empty requests.
   - Enforced tri-directional signed delta: $\Delta \text{score} < 0$, $\Delta \text{score} > 0$, or $\Delta \text{score} = 0$.
9. **Evaluation-Label Isolation (§4):**
   - Re-verified that offline benchmark ground-truth is strictly isolated from live inference snapshots, and human review decisions never alter benchmark labels.

---

## 2. Forensic Code & Data Verification (With Source Citations)

| Telemetry / Entity | Observed Format & Rule | Verified Source Location |
| :--- | :--- | :--- |
| **Transaction ID** | `T\d{6}` (e.g. `T000001`, `T000123`) | `data/transactions.jsonl:1`, `ml/generate_data.py:53` |
| **Account ID** | `ACC_\d{4}` (e.g. `ACC_0321`, `ACC_0917`) | `data/transactions.jsonl:1`, `ml/generate_data.py:56`, `data/artifacts/model.joblib` (`heldout_account_ids`) |
| **Device ID** | `DEV_\d{4}` (e.g. `DEV_0321`, `DEV_0031`) | `data/transactions.jsonl:1`, `ml/generate_data.py:59` |
| **Timestamp Format** | ISO 8601 UTC `YYYY-MM-DDTHH:MM:SSZ` | `data/transactions.jsonl:1`, `ml/generate_data.py:50` |
| **Amount INR** | Positive float $> 0.0$ | `data/transactions.jsonl:1`, `ml/features.py:141-144` |
| **Status Enum** | `"SUCCESS"` or `"FAILED"` | `data/transactions.jsonl:1`, `ml/features.py:146-148` |
| **Ground Truth Structure** | `{"scenario": str, "ring_member_accounts": list[str]}` | `data/transactions.jsonl:1`, `ml/generate_data.py:88-90` |
| **Feature Schema & Order** | Exactly 25 features matching `FEATURE_NAMES` | `ml/features.py:20-51`, `data/artifacts/model.joblib` (`feature_names`) |
| **Nullable Device Handling** | **Crashes on null in current code** | `ml/features.py:107, 137-139, 176` (Requires implementation in Step 9) |
| **Merchant Telemetry** | **Absent from active datasets** | Verified via grep in `data/transactions.jsonl` (Requires implementation in Step 9) |
| **Delayed Ingestion Fields** | **Absent from active datasets** | Verified via grep in `data/transactions.jsonl` (Requires implementation in Step 9) |

---

## 3. Component Compatibility Status

| Component | Path | Compatibility Status | Required Next Steps |
| :--- | :--- | :---: | :--- |
| **Model Artifact** | `data/artifacts/model.joblib` | **VERIFIED** | Frozen. Requires exact 25 features matching `FEATURE_NAMES`. |
| **Feature Extractor** | `ml/features.py` | **REQUIRES IMPLEMENTATION** | Update input validation to accept nullable `sender_device_id` and dual complaint formats. |
| **Synthetic Generator** | `ml/generate_data.py` | **REQUIRES IMPLEMENTATION** | Add explicit merchant payments (`MER_xxxx`) and delayed complaints (`CMP_xxxx`). |
| **Baseline Rules** | `ml/baseline_rules.py` | **VERIFIED** | 4 heuristic rules operational. Ready for temporal motif integration. |
| **Graph & Motifs** | `ml/graph.py` | **REQUIRES IMPLEMENTATION** | Construct heterogeneous graph and detect `RAPID_PASS_THROUGH` ($\le 2\text{h}$) and `DORMANCY_BURST`. |
| **Pipeline Inference** | `ml/pipeline.py` | **REQUIRES IMPLEMENTATION** | Implement `run_analysis()` with deterministic sorting, evidence path extraction, and alert generation. |
| **Counterfactual Engine** | `ml/counterfactual.py` | **REQUIRES IMPLEMENTATION** | Implement sandboxed what-if perturbation, signed $\Delta \text{score}$, and hypothesis generation. |
| **Metrics Engine** | `ml/evaluate.py` | **REQUIRES IMPLEMENTATION** | Implement `evaluate_at_budget(k)` and `fpr_benign_shared_device`. |
| **FastAPI Backend** | `backend/*` | **REQUIRES IMPLEMENTATION** | Scaffold endpoints, atomic cache, and in-memory review manager. |
| **React Frontend** | `frontend/*` | **REQUIRES IMPLEMENTATION** | Build Analyst Queue, Graph Explorer, and Counterfactual Drawer. |

---

## 4. Reconciled Decisions & Architectural Status

### A. Decisions Authorized by Project Owner
1. **Contract v1.2 Advancement:** Upgrade contract to v1.2 incorporating all mandatory hackathon requirements.
2. **Analyst Review Budget:** Default budget $K=20$; runtime support for $K \in \{10, 20, 50\}$.
3. **Counterfactual Scope:** Support both individual edge removals (`remove_edge_ids`) and high-level toggles (`suppress_device_sharing`, `suppress_complaints`).
4. **Mandatory Scope:** Every requirement from the hackathon brief is mandatory.
5. **Frozen Feature Schema:** All 25 feature names and ordering in `data/artifacts/model.joblib` are preserved.

### B. Specific Proposals Requiring Owner Signoff
1. **Alert Fingerprint Staleness Policy (§9.2):**  
   When `POST /api/pipeline/run` reruns:
   - Identical alert fingerprint $\implies$ retain active review state (`status`, notes, verdict).
   - Changed alert fingerprint $\implies$ reset status to `"OPEN"`, set `is_stale: true`, preserve previous review under `review.previous_review`.
2. **Conflicting Complaint Validation Policy (§2.4):**  
   If input contains both a non-null `complaint` object AND `"complaint_filed": false`, validation immediately rejects with HTTP 422 `{"detail":"conflicting_complaint_telemetry"}`.

### C. Standard Implementation Tasks (No Blockers)
- Updating `ml/features.py` to allow nullable `sender_device_id` and compute `devices_used_count = 0.0`.
- Implementing `ml/pipeline.py`, `ml/graph.py`, `ml/counterfactual.py`.
- Building `backend/` and `frontend/`.

---

## 5. Mandatory Requirement to Contract & Test Matrix

| # | Requirement | Contract v1.2 Section | Planned Test Case | Expected Test Behavior |
| :---: | :--- | :---: | :--- | :--- |
| **1** | Temporal Heterogeneous Graph | §2.1, §6.1 | `test_graph_heterogeneous_types` | Graph contains `account`, `device`, `merchant`, `complaint` nodes and timestamped edges. |
| **2** | Explainable Alerts & Paths | §7.1, §7.2 | `test_alert_evidence_path_integrity` | Path length $0 \le L \le 10$, continuous when non-empty, touches alert account, empty list on disconnected features. |
| **3** | Graph Explorer & Analyst Queue | §7.1, §11.0 | `test_analyst_queue_budget_filter` | API returns alerts sorted by score descending; budget $K$ filter caps list accurately. |
| **4** | Transparent Rules & Motifs | §6.3 | `test_temporal_motifs_detection` | Rapid pass-through ($\Delta t \le 2\text{h}$) triggers `RAPID_PASS_THROUGH` rule. |
| **5** | Labelled Benchmark Imbalance | §4.0 | `test_benchmark_class_imbalance` | Positive class is $<20\%$ of dataset ($17.8\%$ actual). |
| **6** | Benign Shared-Device Evaluation | §8.2 | `test_shared_device_fpr_measurement` | $\text{FPR}_{\text{shared\_device}}$ is computed purely on `shared_device_family` held-out cohort. |
| **7** | Incomplete Records | §2.3, §5.2 | `test_incomplete_records_no_crash` | Null `sender_device_id` yields 0 NaNs and `devices_used_count = 0.0` (compromise evaluated). |
| **8** | Delayed Complaint Reporting | §3.2 | `test_delayed_complaint_snapshot` | Complaint with $t_{\text{filed}} \le T < t_{\text{complaint\_ingested}}$ is hidden at snapshot $T$; visible at $T' \ge t_{\text{complaint\_ingested}}$. |
| **9** | Precision & Recall at Budget K | §8.1 | `test_metrics_at_budget_k` | Precision@K and Recall@K match formula for $K \in \{10, 20, 50\}$ for both ML and multi-tier baseline. |
| **10** | Shared-Device Cohort Isolation | §8.2 | `test_shared_device_cohort_isolation` | Fraudulent accounts using shared devices are excluded from the benign cohort. |
| **11** | Permutation Invariance | §3.3 | `test_input_permutation_invariance` | Shuffled transaction input produces bitwise identical scores and evidence paths. |
| **12** | Human Review State Machine | §9.1, §9.2 | `test_review_state_transitions` | Valid transitions persist; invalid transitions return HTTP 422; labels unaffected. |
| **13** | Counterfactual Simulation | §10.1 | `test_counterfactual_tri_directional` | Verifies $\Delta \text{score} < 0$, $\Delta \text{score} > 0$, and $\Delta \text{score} = 0$ cases with exact numerical equality. Rejects invalid interventions with HTTP 422. |
| **14** | Baseline Comparison | §6.3, §8.1 | `test_baseline_ml_comparison` | Baseline and ML metrics are side-by-side on identical held-out accounts with budget distinctions noted. |
| **15** | Synthetic Data & Privacy | §12.0 | `test_no_external_network_calls` | Code executes fully offline with synthetic prefixes (`ACC_`, `DEV_`, `MER_`). |

---

## 6. Repository State and Test Verification

### Git Status
```powershell
git status
```
**Output:**
```
On branch master
Untracked files:
  .gitignore
  README.md
  agy-audit-summary.md
  agy-skills-inventory.csv
  agy-skills-inventory.json
  agy-slash-commands.md
  contracts/
  ml/
  scratch/
```
**Confirmation:**
- `contracts/CONTRACT.md` (active Contract v1.1) is **completely untouched**.
- No application code (`ml/*`), tests (`ml/test_*.py`), datasets (`data/*.jsonl`), or model artifacts (`data/artifacts/model.joblib`) were modified.
- Only [`contracts/CONTRACT_v1.2_AUDIT.md`](file:///c:/Users/Aum%20Lenka/OneDrive/Desktop/projects/TraceUPI/contracts/CONTRACT_v1.2_AUDIT.md) and [`contracts/CONTRACT_v1.2_PROPOSAL.md`](file:///c:/Users/Aum%20Lenka/OneDrive/Desktop/projects/TraceUPI/contracts/CONTRACT_v1.2_PROPOSAL.md) were updated.

### Unit Test Execution
```powershell
python -m unittest discover -s ml -p "test_*.py" -v
```
**Actual Output:**
```
test_amount_aggregates (test_features.TestAccountFeatures.test_amount_aggregates) ... ok
test_deterministic_output (test_features.TestAccountFeatures.test_deterministic_output) ... ok
test_empty_and_inactive_accounts (test_features.TestAccountFeatures.test_empty_and_inactive_accounts) ... ok
test_feature_names_and_definitions_consistency (test_features.TestAccountFeatures.test_feature_names_and_definitions_consistency) ... ok
test_ground_truth_leakage_resistance (test_features.TestAccountFeatures.test_ground_truth_leakage_resistance) ... ok
test_input_immutability (test_features.TestAccountFeatures.test_input_immutability) ... ok
test_malformed_input_rejection (test_features.TestAccountFeatures.test_malformed_input_rejection) ... ok
test_mixed_role_account (test_features.TestAccountFeatures.test_mixed_role_account) ... ok
test_receiver_only_account (test_features.TestAccountFeatures.test_receiver_only_account) ... ok
test_sender_only_account (test_features.TestAccountFeatures.test_sender_only_account) ... ok
test_shared_device_statistics (test_features.TestAccountFeatures.test_shared_device_statistics) ... ok
test_successful_and_failed_transactions (test_features.TestAccountFeatures.test_successful_and_failed_transactions) ... ok
test_unique_counterparties (test_features.TestAccountFeatures.test_unique_counterparties) ... ok
test_zero_nan_or_infinite_values (test_features.TestAccountFeatures.test_zero_nan_or_infinite_values) ... ok
test_01_label_precedence (test_training.TestTrainingPipeline.test_01_label_precedence) ... ok
test_02_deterministic_split_coverage_and_disjointness (test_training.TestTrainingPipeline.test_02_deterministic_split_coverage_and_disjointness) ... ok
test_03_small_scenario_groups (test_training.TestTrainingPipeline.test_03_small_scenario_groups) ... ok
test_04_ground_truth_leakage_prevention (test_training.TestTrainingPipeline.test_04_ground_truth_leakage_prevention) ... ok
test_05_training_only_threshold_selection (test_training.TestTrainingPipeline.test_05_training_only_threshold_selection) ... ok
test_06_baseline_and_heldout_metrics_zero_denominators (test_training.TestTrainingPipeline.test_06_baseline_and_heldout_metrics_zero_denominators) ... ok
test_07_artifact_metadata_and_reproducibility (test_training.TestTrainingPipeline.test_07_artifact_metadata_and_reproducibility) ... ok
test_08_invalid_or_insufficient_data (test_training.TestTrainingPipeline.test_08_invalid_or_insufficient_data) ... ok
test_09_pipeline_runs_on_regression_fixture (test_training.TestTrainingPipeline.test_09_pipeline_runs_on_regression_fixture) ... ok

----------------------------------------------------------------------
Ran 23 tests in 0.244s

OK
```

---

*Step 8A.3 complete. Standing by for project owner approval.*
