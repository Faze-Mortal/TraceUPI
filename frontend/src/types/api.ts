export type ReviewStatus =
  | 'OPEN'
  | 'INVESTIGATING'
  | 'CONFIRMED_FRAUD'
  | 'DISMISSED_BENIGN'

export type AlertPriority = 'HIGH' | 'MEDIUM' | 'LOW'

export type StalenessReason =
  | 'historical_snapshot_evidence_divergence'
  | 'evidence_or_score_changed'

export type NodeType = 'account' | 'device' | 'merchant' | 'complaint'

export type EdgeType = 'transfer' | 'uses_device' | 'merchant_profile' | 'has_complaint'

export type BudgetK = 10 | 20 | 50

export interface PipelineRunRequest {
  as_of?: string | null
}

export interface ReviewUpdateRequest {
  status: ReviewStatus
  analyst_id: string
  verdict?: string | null
  notes?: string | null
}

export interface PipelineRunResponse {
  n_transactions: number
  n_alerts: number
  metrics_available: boolean
  as_of: string | null
}

export interface MLResult {
  score: number
  threshold: number
  flagged: boolean
}

export interface BaselineResult {
  flagged: boolean
  rules_triggered: string[]
}

export interface TopReason {
  feature: string
  value: number | string | boolean
  typical_value: number | string | boolean
  explanation: string
}

export interface ContextFlags {
  shared_device_detected: boolean
  rapid_pass_through_detected: boolean
  note: string | null
}

export interface PreviousReview {
  status: ReviewStatus
  analyst_id: string | null
  updated_at: string | null
  verdict: string | null
  notes: string | null
}

export interface ReviewQueueState {
  status: ReviewStatus
  is_stale: boolean
  staleness_reason: StalenessReason | null
  analyst_id: string | null
  updated_at: string | null
  verdict: string | null
  notes: string | null
}

export interface ReviewState extends ReviewQueueState {
  previous_review: PreviousReview | null
}

export interface EvidenceNode {
  id: string
  type: NodeType
  label: string
  score: number | null
  metadata: Record<string, unknown>
}

export interface EvidenceEdge {
  id: string
  source: string
  target: string
  type: EdgeType
  txn_id: string | null
  amount_inr: number | null
  timestamp: string | null
}

export interface Evidence {
  nodes: EvidenceNode[]
  edges: EvidenceEdge[]
  evidence_path: string[]
}

export interface AlertSummary {
  alert_id: string
  alert_fingerprint: string
  account_id: string
  created_at: string
  status: ReviewStatus
  priority: AlertPriority
  ml: MLResult
  baseline: BaselineResult
  top_reasons: TopReason[]
  context_flags: ContextFlags
  review: ReviewQueueState
}

export interface Alert extends Omit<AlertSummary, 'review'> {
  review: ReviewState
  evidence: Evidence
}

export interface AlertsResponse {
  alerts: AlertSummary[]
}

export interface ApiErrorDetail {
  detail: string
  [key: string]: unknown
}

export interface CounterfactualRequest {
  remove_edge_ids?: string[]
  suppress_device_sharing?: boolean
  suppress_complaints?: boolean
}

export interface CounterfactualResponse {
  alert_id: string
  account_id: string
  original_score: number
  counterfactual_score: number
  score_delta: number
  original_flagged: boolean
  counterfactual_flagged: boolean
  rules_removed: string[]
  rules_added: string[]
  plausible_benign_alternative: string
}

export type GroundTruthScenario = 'mule_ring' | 'normal' | 'shared_device_family'

export interface EvaluationInfo {
  evaluated_on: 'held_out_accounts'
  n_accounts: number
  n_positive_accounts: number
  n_shared_device_accounts: number
}

export interface BudgetMetrics {
  budget_k: number
  k_effective: number
  precision_at_k: number | null
  recall_at_k: number | null
}

export interface FairnessMetrics {
  fpr_benign_shared_device: number | null
  n_shared_device_evaluated: number
}

export interface ClassificationMetrics {
  precision: number | null
  recall: number | null
  f1: number | null
  true_positives: number
  false_positives: number
  false_negatives: number
  budget_metrics: BudgetMetrics
}

export interface MLMetrics extends ClassificationMetrics {
  threshold: number
  fairness: FairnessMetrics
}

export type BaselineMetrics = ClassificationMetrics

export interface ScenarioBreakdown {
  scenario: GroundTruthScenario
  n_accounts: number
  ml_flagged: number
  baseline_flagged: number
}

export interface MetricsResponse {
  generated_at: string
  budget_k: number
  evaluation: EvaluationInfo
  ml: MLMetrics
  baseline: BaselineMetrics
  by_scenario: ScenarioBreakdown[]
}

