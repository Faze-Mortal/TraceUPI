import React, { useState, useEffect, useCallback } from 'react'
import { apiClient, ApiError } from '../api/client'
import type { BudgetK, MetricsResponse } from '../types/api'

interface BenchmarkMetricsViewProps {
  onRunPipeline?: () => void
  isPipelineRunning?: boolean
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || isNaN(value)) {
    return '—'
  }
  return `${(value * 100).toFixed(2)}%`
}

function formatScore(value: number | null | undefined, decimals = 4): string {
  if (value === null || value === undefined || isNaN(value)) {
    return '—'
  }
  return value.toFixed(decimals)
}

function formatRatio(numerator: number, denominator: number): string {
  if (isNaN(numerator) || isNaN(denominator)) {
    return '—'
  }
  return `${numerator} / ${denominator}`
}

export const BenchmarkMetricsView: React.FC<BenchmarkMetricsViewProps> = ({
  onRunPipeline,
  isPipelineRunning = false,
}) => {
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null)
  const [selectedBudgetK, setSelectedBudgetK] = useState<BudgetK>(20)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [isAnalysisNotRun, setIsAnalysisNotRun] = useState<boolean>(false)
  const [isMetricsUnavailable, setIsMetricsUnavailable] = useState<boolean>(false)

  const fetchMetrics = useCallback(async (budgetK: BudgetK) => {
    setIsLoading(true)
    setError(null)
    setIsAnalysisNotRun(false)
    setIsMetricsUnavailable(false)

    try {
      const data = await apiClient.getMetrics(budgetK)
      setMetrics(data)
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 503 || err.isAnalysisNotRun) {
          setIsAnalysisNotRun(true)
        } else if (err.status === 404) {
          setIsMetricsUnavailable(true)
        } else {
          setError(err.message)
        }
      } else if (err instanceof Error) {
        setError(err.message)
      } else {
        setError('An unexpected error occurred while loading metrics.')
      }
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchMetrics(selectedBudgetK)
  }, [fetchMetrics, selectedBudgetK])

  const handleBudgetChange = (k: BudgetK) => {
    if (k !== selectedBudgetK) {
      setSelectedBudgetK(k)
    }
  }

  return (
    <div className="workbench-section-container benchmark-metrics-view" data-testid="section-metrics-container">
      <section className="workbench-full-card metrics-full-card" aria-labelledby="metrics-view-title">
        {/* Top Header */}
        <div className="card-top-header">
          <div className="header-left">
            <h2 id="metrics-view-title" className="section-heading">
              <svg
                viewBox="0 0 24 24"
                width="20"
                height="20"
                fill="none"
                stroke="var(--brand-terracotta, #A56F58)"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <line x1="18" y1="20" x2="18" y2="10" />
                <line x1="12" y1="20" x2="12" y2="4" />
                <line x1="6" y1="20" x2="6" y2="14" />
              </svg>
              4. Benchmark Evaluation & Fairness
            </h2>
            <span className="badge-dim font-mono">
              Offline Ground-Truth Benchmark · Contract v1.2 §8
            </span>
          </div>

          <div className="header-actions">
            <div className="budget-selector-group" role="group" aria-label="Analyst Capacity Budget K">
              <span className="budget-label font-mono">Capacity Budget (K):</span>
              {([10, 20, 50] as BudgetK[]).map((k) => (
                <button
                  key={k}
                  type="button"
                  data-testid={`btn-budget-k-${k}`}
                  className={`btn-budget-toggle font-mono ${selectedBudgetK === k ? 'active' : ''}`}
                  onClick={() => handleBudgetChange(k)}
                  aria-pressed={selectedBudgetK === k}
                  disabled={isLoading}
                >
                  K = {k}
                </button>
              ))}
            </div>

            <button
              type="button"
              className="btn-secondary font-mono"
              onClick={() => fetchMetrics(selectedBudgetK)}
              disabled={isLoading || isPipelineRunning}
              data-testid="btn-refresh-metrics"
              aria-label="Refresh benchmark metrics"
            >
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
              </svg>
              Refresh
            </button>
          </div>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="metrics-loading-state font-mono" role="status" data-testid="metrics-loading">
            <span className="spinner-icon" aria-hidden="true" />
            <span>Loading evaluation benchmark data from /api/metrics...</span>
          </div>
        )}

        {/* Error Banner */}
        {error && !isLoading && (
          <div className="alert-banner error" role="alert" data-testid="metrics-error-banner">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="var(--color-high-risk, #C65B4A)" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>Failed to load benchmark metrics: {error}</span>
            <button
              type="button"
              className="btn-text-retry font-mono"
              onClick={() => fetchMetrics(selectedBudgetK)}
              data-testid="btn-retry-metrics"
            >
              Retry
            </button>
          </div>
        )}

        {/* 503 Pre-Analysis Not Run State */}
        {isAnalysisNotRun && !isLoading && (
          <div className="pre-analysis-banner" role="region" aria-labelledby="metrics-preanalysis-title" data-testid="metrics-preanalysis">
            <div className="pre-analysis-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="var(--color-warning, #D4A15A)" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" strokeWidth="2.5" />
              </svg>
            </div>
            <div className="pre-analysis-content">
              <h3 id="metrics-preanalysis-title" className="pre-analysis-title">
                Analysis Pipeline Has Not Run Yet (HTTP 503)
              </h3>
              <p className="pre-analysis-text">
                Benchmark evaluation metrics are calculated during pipeline execution against frozen ground-truth labels.
                Run the fraud-risk analysis pipeline to generate scores, populate alerts, and compute benchmark performance.
              </p>
              {onRunPipeline && (
                <div className="pre-analysis-actions">
                  <button
                    type="button"
                    id="btn-metrics-preanalysis-run"
                    data-testid="btn-metrics-preanalysis-run"
                    className="btn-primary"
                    onClick={onRunPipeline}
                    disabled={isPipelineRunning}
                  >
                    {isPipelineRunning ? 'Running Pipeline...' : 'Run Analysis Pipeline Now'}
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* 404 Metrics Unavailable State */}
        {isMetricsUnavailable && !isLoading && (
          <div className="pre-analysis-banner" role="region" aria-labelledby="metrics-unavailable-title" data-testid="metrics-unavailable">
            <div className="pre-analysis-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="#6B7280" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" strokeWidth="2.5" />
              </svg>
            </div>
            <div className="pre-analysis-content">
              <h3 id="metrics-unavailable-title" className="pre-analysis-title">
                Benchmark Metrics Unavailable (HTTP 404)
              </h3>
              <p className="pre-analysis-text">
                The current dataset does not contain ground-truth scenario annotations (<code>ground_truth.scenario</code>).
                Benchmark metrics require ground-truth labels for offline evaluation.
              </p>
            </div>
          </div>
        )}

        {/* Loaded Metrics View */}
        {metrics && !isLoading && !isAnalysisNotRun && !isMetricsUnavailable && (
          <div className="metrics-body" data-testid="metrics-display-content">
            {/* Context & Metadata Banner */}
            <div className="metrics-metadata-card font-mono" data-testid="metrics-metadata-card">
              <div className="meta-item">
                <span className="meta-label">Evaluated Cohort:</span>
                <span className="meta-value text-strong">
                  {metrics.evaluation.evaluated_on} ({metrics.evaluation.n_accounts} Accounts)
                </span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Ground-Truth Positives:</span>
                <span className="meta-value text-amber">
                  {metrics.evaluation.n_positive_accounts} Mule Ring Accounts
                </span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Shared-Device Cohort:</span>
                <span className="meta-value text-cyan">
                  {metrics.evaluation.n_shared_device_accounts} Benign Accounts
                </span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Generated UTC:</span>
                <span className="meta-value text-dim">{metrics.generated_at}</span>
              </div>
            </div>

            {/* Mandatory Disclaimers Callout */}
            <div className="metrics-disclaimer-callout" role="note" aria-label="Benchmark Methodology Notice">
              <span className="disclaimer-badge font-mono">Methodology Notice</span>
              <p className="disclaimer-text">
                <strong>Synthetic Benchmark Evaluation:</strong> Evaluated strictly on the frozen held-out partition (seed 42).
                Risk scores are <em>uncalibrated ranking signals</em> for analyst triage prioritization and do not represent
                calibrated probabilities of guilt or legal proof of fraud.
              </p>
            </div>

            {/* Head-to-Head Comparison Grid */}
            <div className="metrics-comparison-grid">
              {/* Card 1: Machine Learning Classifier */}
              <div className="metrics-card ml-card" data-testid="card-ml-metrics">
                <div className="card-badge-header">
                  <span className="model-badge ml">ML Anomaly Classifier</span>
                  <span className="threshold-pill font-mono">
                    Threshold: {formatScore(metrics.ml.threshold)}
                  </span>
                </div>

                <div className="metrics-stat-grid">
                  <div className="stat-box">
                    <span className="stat-label">Precision</span>
                    <span className="stat-number font-mono text-cyan" data-testid="ml-precision">
                      {formatPercent(metrics.ml.precision)}
                    </span>
                    <span className="stat-denominator font-mono">
                      TP / (TP + FP):{' '}
                      {formatRatio(
                        metrics.ml.true_positives,
                        metrics.ml.true_positives + metrics.ml.false_positives
                      )}
                    </span>
                  </div>

                  <div className="stat-box">
                    <span className="stat-label">Recall</span>
                    <span className="stat-number font-mono text-cyan" data-testid="ml-recall">
                      {formatPercent(metrics.ml.recall)}
                    </span>
                    <span className="stat-denominator font-mono">
                      TP / Actual Positives:{' '}
                      {formatRatio(
                        metrics.ml.true_positives,
                        metrics.evaluation.n_positive_accounts
                      )}
                    </span>
                  </div>

                  <div className="stat-box">
                    <span className="stat-label">F1 Score</span>
                    <span className="stat-number font-mono text-cyan" data-testid="ml-f1">
                      {formatScore(metrics.ml.f1)}
                    </span>
                    <span className="stat-denominator font-mono">Harmonic Mean</span>
                  </div>

                  <div className="stat-box highlight">
                    <span className="stat-label">Precision @ K ({metrics.ml.budget_metrics.budget_k})</span>
                    <span className="stat-number font-mono text-strong" data-testid="ml-precision-k">
                      {formatPercent(metrics.ml.budget_metrics.precision_at_k)}
                    </span>
                    <span className="stat-denominator font-mono">
                      Top {metrics.ml.budget_metrics.k_effective} Ranked Accounts
                    </span>
                  </div>

                  <div className="stat-box highlight">
                    <span className="stat-label">Recall @ K ({metrics.ml.budget_metrics.budget_k})</span>
                    <span className="stat-number font-mono text-strong" data-testid="ml-recall-k">
                      {formatPercent(metrics.ml.budget_metrics.recall_at_k)}
                    </span>
                    <span className="stat-denominator font-mono">
                      Mules Captured in Top {metrics.ml.budget_metrics.k_effective}
                    </span>
                  </div>
                </div>

                {/* Confusion Matrix Counts */}
                <div className="confusion-matrix-strip font-mono" data-testid="ml-confusion-counts">
                  <div className="cm-count">
                    <span className="cm-label">True Positives:</span>
                    <span className="cm-value text-green">{metrics.ml.true_positives}</span>
                  </div>
                  <div className="cm-count">
                    <span className="cm-label">False Positives:</span>
                    <span className="cm-value text-red">{metrics.ml.false_positives}</span>
                  </div>
                  <div className="cm-count">
                    <span className="cm-label">False Negatives:</span>
                    <span className="cm-value text-amber">{metrics.ml.false_negatives}</span>
                  </div>
                </div>
              </div>

              {/* Card 2: Baseline Rule Engine */}
              <div className="metrics-card baseline-card" data-testid="card-baseline-metrics">
                <div className="card-badge-header">
                  <span className="model-badge baseline">Baseline Rule Engine</span>
                  <span className="threshold-pill font-mono">Threshold: &ge; 1 Rule Triggered</span>
                </div>

                <div className="metrics-stat-grid">
                  <div className="stat-box">
                    <span className="stat-label">Precision</span>
                    <span className="stat-number font-mono text-dim" data-testid="baseline-precision">
                      {formatPercent(metrics.baseline.precision)}
                    </span>
                    <span className="stat-denominator font-mono">
                      TP / (TP + FP):{' '}
                      {formatRatio(
                        metrics.baseline.true_positives,
                        metrics.baseline.true_positives + metrics.baseline.false_positives
                      )}
                    </span>
                  </div>

                  <div className="stat-box">
                    <span className="stat-label">Recall</span>
                    <span className="stat-number font-mono text-dim" data-testid="baseline-recall">
                      {formatPercent(metrics.baseline.recall)}
                    </span>
                    <span className="stat-denominator font-mono">
                      TP / Actual Positives:{' '}
                      {formatRatio(
                        metrics.baseline.true_positives,
                        metrics.evaluation.n_positive_accounts
                      )}
                    </span>
                  </div>

                  <div className="stat-box">
                    <span className="stat-label">F1 Score</span>
                    <span className="stat-number font-mono text-dim" data-testid="baseline-f1">
                      {formatScore(metrics.baseline.f1)}
                    </span>
                    <span className="stat-denominator font-mono">Harmonic Mean</span>
                  </div>

                  <div className="stat-box highlight">
                    <span className="stat-label">Precision @ K ({metrics.baseline.budget_metrics.budget_k})</span>
                    <span className="stat-number font-mono text-strong" data-testid="baseline-precision-k">
                      {formatPercent(metrics.baseline.budget_metrics.precision_at_k)}
                    </span>
                    <span className="stat-denominator font-mono">
                      Top {metrics.baseline.budget_metrics.k_effective} Ranked by Rules & Flow
                    </span>
                  </div>

                  <div className="stat-box highlight">
                    <span className="stat-label">Recall @ K ({metrics.baseline.budget_metrics.budget_k})</span>
                    <span className="stat-number font-mono text-strong" data-testid="baseline-recall-k">
                      {formatPercent(metrics.baseline.budget_metrics.recall_at_k)}
                    </span>
                    <span className="stat-denominator font-mono">
                      Mules Captured in Top {metrics.baseline.budget_metrics.k_effective}
                    </span>
                  </div>
                </div>

                {/* Confusion Matrix Counts */}
                <div className="confusion-matrix-strip font-mono" data-testid="baseline-confusion-counts">
                  <div className="cm-count">
                    <span className="cm-label">True Positives:</span>
                    <span className="cm-value text-green">{metrics.baseline.true_positives}</span>
                  </div>
                  <div className="cm-count">
                    <span className="cm-label">False Positives:</span>
                    <span className="cm-value text-red">{metrics.baseline.false_positives}</span>
                  </div>
                  <div className="cm-count">
                    <span className="cm-label">False Negatives:</span>
                    <span className="cm-value text-amber">{metrics.baseline.false_negatives}</span>
                  </div>
                </div>

                <div className="card-subnote font-mono">
                  * Baseline unconstrained metrics evaluate all accounts triggering &ge; 1 rule.
                  They are not directly comparable to ML Precision@K without noting the capacity budget constraint.
                </div>
              </div>
            </div>

            {/* Fairness & Demographic Cohort Section */}
            <div className="fairness-card" data-testid="card-fairness-metrics">
              <div className="fairness-header">
                <span className="fairness-badge font-mono">Fairness Objective (§8.2)</span>
                <h3 className="fairness-title">Benign Shared-Device False Positive Rate</h3>
              </div>

              <div className="fairness-content">
                <div className="fairness-stat-block">
                  <span className="fairness-value font-mono text-cyan" data-testid="fairness-fpr">
                    {formatPercent(metrics.ml.fairness.fpr_benign_shared_device)}
                  </span>
                  <span className="fairness-subtext font-mono">
                    Evaluated on {metrics.ml.fairness.n_shared_device_evaluated} benign shared-device family accounts
                  </span>
                </div>

                <div className="fairness-explanation">
                  <p>
                    Evaluates false positive suppression on legitimate multi-user households sharing a single smartphone.
                    Under Section 4 precedence, collusion mule accounts who share devices are strictly assigned to <code>mule_ring</code> and excluded from this denominator.
                  </p>
                  <span className="fairness-disclaimer text-dim font-mono">
                    * Specific to evaluated synthetic cohort; not a guarantee or proof of real-world fairness.
                  </span>
                </div>
              </div>
            </div>

            {/* Scenario Breakdown Table */}
            <div className="scenario-table-container" data-testid="card-scenario-breakdown">
              <div className="scenario-table-header">
                <h3 id="scenario-breakdown-heading" className="scenario-table-title font-mono">
                  Scenario Detection Breakdown (Held-out Partition)
                </h3>
                <span className="table-scroll-hint font-mono text-dim" aria-hidden="true">
                  Scroll horizontally &rarr;
                </span>
              </div>

              <div
                className="scenario-table-scroll-wrapper"
                role="region"
                aria-labelledby="scenario-breakdown-heading"
                tabIndex={0}
              >
                <table className="scenario-table font-mono" aria-label="Scenario Detection Breakdown">
                  <thead>
                    <tr>
                      <th scope="col">Ground-Truth Scenario</th>
                      <th scope="col" className="text-right">Cohort Accounts</th>
                      <th scope="col" className="text-right">ML Flagged</th>
                      <th scope="col" className="text-right">ML Rate</th>
                      <th scope="col" className="text-right">Baseline Flagged</th>
                      <th scope="col" className="text-right">Baseline Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.by_scenario.map((sc) => {
                      const mlRate = sc.n_accounts > 0 ? sc.ml_flagged / sc.n_accounts : null
                      const baselineRate = sc.n_accounts > 0 ? sc.baseline_flagged / sc.n_accounts : null
                      const isMule = sc.scenario === 'mule_ring'
                      return (
                        <tr key={sc.scenario} className={isMule ? 'row-positive' : 'row-negative'} data-testid={`row-scenario-${sc.scenario}`}>
                          <td className="scenario-name">
                            <span className={`scenario-dot ${isMule ? 'mule' : 'benign'}`} aria-hidden="true" />
                            <code>{sc.scenario}</code>
                          </td>
                          <td className="text-right text-strong">{sc.n_accounts}</td>
                          <td className="text-right text-cyan">{sc.ml_flagged}</td>
                          <td className="text-right">{formatPercent(mlRate)}</td>
                          <td className="text-right text-dim">{sc.baseline_flagged}</td>
                          <td className="text-right text-dim">{formatPercent(baselineRate)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
