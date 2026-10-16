import React, { useState } from 'react'
import { apiClient, ApiError } from '../api/client'
import type { Alert, CounterfactualResponse, EvidenceEdge } from '../types/api'

interface WhatIfInvestigationProps {
  alert: Alert
}

export const WhatIfInvestigation: React.FC<WhatIfInvestigationProps> = ({ alert }) => {
  // Intervention selections
  const [selectedEdgeIds, setSelectedEdgeIds] = useState<string[]>([])
  const [suppressDevices, setSuppressDevices] = useState<boolean>(false)
  const [suppressComplaints, setSuppressComplaints] = useState<boolean>(false)

  // Execution state
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<CounterfactualResponse | null>(null)

  // Filter actual transfer edges from evidence
  const transferEdges: EvidenceEdge[] = alert.evidence.edges.filter(
    (edge) => edge.type === 'transfer'
  )

  const hasDeviceNodes = alert.evidence.nodes.some((n) => n.type === 'device') ||
    alert.evidence.edges.some((e) => e.type === 'uses_device')
  const hasComplaintNodes = alert.evidence.nodes.some((n) => n.type === 'complaint') ||
    alert.evidence.edges.some((e) => e.type === 'has_complaint')

  // Toggle individual transfer edge
  const handleToggleEdge = (edgeId: string) => {
    setSelectedEdgeIds((prev) =>
      prev.includes(edgeId) ? prev.filter((id) => id !== edgeId) : [...prev, edgeId]
    )
    setError(null)
  }

  // Select / Deselect all transfer edges
  const handleSelectAllEdges = () => {
    if (selectedEdgeIds.length === transferEdges.length) {
      setSelectedEdgeIds([])
    } else {
      setSelectedEdgeIds(transferEdges.map((e) => e.id))
    }
    setError(null)
  }

  // Reset all hypothetical inputs
  const handleReset = () => {
    setSelectedEdgeIds([])
    setSuppressDevices(false)
    setSuppressComplaints(false)
    setResult(null)
    setError(null)
  }

  // Validation: at least one intervention is required
  const hasInterventions =
    selectedEdgeIds.length > 0 || suppressDevices || suppressComplaints

  // Run hypothetical analysis in sandbox
  const handleRunAnalysis = async () => {
    if (!hasInterventions) {
      setError('Please select at least one hypothetical intervention (remove a transfer edge, suppress devices, or suppress complaints).')
      return
    }

    setIsLoading(true)
    setError(null)

    try {
      const res = await apiClient.runCounterfactual(alert.alert_id, {
        remove_edge_ids: selectedEdgeIds,
        suppress_device_sharing: suppressDevices,
        suppress_complaints: suppressComplaints,
      })
      setResult(res)
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.isEmptyCounterfactual) {
          setError('Backend rejected request: At least one intervention is required.')
        } else if (err.isInvalidCounterfactual) {
          setError(`Invalid intervention: ${err.detail}`)
        } else {
          setError(`API Error (${err.status}): ${err.detail}`)
        }
      } else {
        const msg = err instanceof Error ? err.message : 'Hypothetical analysis failed'
        setError(`Error: ${msg}`)
      }
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div
      className="what-if-investigation-card font-mono"
      role="region"
      aria-label="What-if Counterfactual Investigation"
      id="what-if-investigation"
    >
      <div className="what-if-header">
        <div className="what-if-title-group">
          <svg
            viewBox="0 0 24 24"
            width="20"
            height="20"
            fill="none"
            stroke="#A78BFA"
            strokeWidth="2"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="9" />
            <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          <h4 className="what-if-title font-sans">What-if investigation</h4>
          <span className="what-if-badge">Contract v1.2 Sandbox</span>
        </div>
        <span className="what-if-scope-tag font-sans">
          Hypothetical sandbox · Original alert unchanged
        </span>
      </div>

      <p className="what-if-intro font-sans">
        Test alternate fraud hypotheses by removing participating transfer edges or suppressing hardware/complaint signals.
        Evaluates whether the account's elevated risk score relies primarily on specific connections.
      </p>

      {/* Intervention Controls */}
      <div className="what-if-controls-grid">
        {/* Transfer Edges Section */}
        <div className="control-box">
          <div className="control-box-header">
            <span className="control-box-title">
              1. Remove Transfer Edges ({selectedEdgeIds.length}/{transferEdges.length} selected)
            </span>
            {transferEdges.length > 0 && (
              <button
                type="button"
                className="btn-select-all"
                onClick={handleSelectAllEdges}
                disabled={isLoading}
              >
                {selectedEdgeIds.length === transferEdges.length ? 'Clear all' : 'Select all'}
              </button>
            )}
          </div>

          {transferEdges.length === 0 ? (
            <p className="control-empty-note font-sans">
              No participating transfer edges available in this alert's evidence subgraph.
            </p>
          ) : (
            <div className="edges-checklist" role="group" aria-label="Transfer edges to remove">
              {transferEdges.map((edge) => {
                const isChecked = selectedEdgeIds.includes(edge.id)
                return (
                  <label
                    key={edge.id}
                    className={`edge-checkbox-item ${isChecked ? 'is-checked' : ''}`}
                    htmlFor={`edge-chk-${edge.id}`}
                  >
                    <input
                      type="checkbox"
                      id={`edge-chk-${edge.id}`}
                      data-testid={`edge-checkbox-${edge.id}`}
                      checked={isChecked}
                      onChange={() => handleToggleEdge(edge.id)}
                      disabled={isLoading}
                    />
                    <div className="edge-item-details">
                      <div className="edge-item-top">
                        <strong className="edge-id-tag">{edge.id}</strong>
                        <span>{edge.source} &rarr; {edge.target}</span>
                      </div>
                      <div className="edge-item-meta">
                        {edge.amount_inr !== null && (
                          <span className="inr-tag">
                            ₹{edge.amount_inr.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </span>
                        )}
                        {edge.txn_id && <span>Txn: {edge.txn_id}</span>}
                      </div>
                    </div>
                  </label>
                )
              })}
            </div>
          )}
        </div>

        {/* Behavioral & Entity Toggles */}
        <div className="control-box">
          <span className="control-box-title">2. Contextual Telemetry Toggles</span>

          <div className="toggles-list">
            <label
              className={`toggle-item ${suppressDevices ? 'is-active' : ''}`}
              htmlFor="toggle-suppress-devices"
            >
              <input
                type="checkbox"
                id="toggle-suppress-devices"
                data-testid="toggle-suppress-devices"
                checked={suppressDevices}
                onChange={(e) => {
                  setSuppressDevices(e.target.checked)
                  setError(null)
                }}
                disabled={isLoading}
              />
              <div className="toggle-text">
                <span className="toggle-label">Suppress Shared-Device Evidence</span>
                <span className="toggle-desc font-sans">
                  Hypothetically assumes the account hardware is isolated and not linked to any multi-account device ring.
                  {hasDeviceNodes ? ' (Evidence contains shared device nodes)' : ' (No device nodes in current subgraph)'}
                </span>
              </div>
            </label>

            <label
              className={`toggle-item ${suppressComplaints ? 'is-active' : ''}`}
              htmlFor="toggle-suppress-complaints"
            >
              <input
                type="checkbox"
                id="toggle-suppress-complaints"
                data-testid="toggle-suppress-complaints"
                checked={suppressComplaints}
                onChange={(e) => {
                  setSuppressComplaints(e.target.checked)
                  setError(null)
                }}
                disabled={isLoading}
              />
              <div className="toggle-text">
                <span className="toggle-label">Suppress Consumer Complaints</span>
                <span className="toggle-desc font-sans">
                  Hypothetically assumes no consumer fraud grievances were registered against this account.
                  {hasComplaintNodes ? ' (Evidence contains complaint nodes)' : ' (No complaints in current subgraph)'}
                </span>
              </div>
            </label>
          </div>

          <div className="what-if-actions-bar">
            <button
              type="button"
              id="btn-run-whatif"
              data-testid="btn-run-whatif"
              className="btn-run-whatif"
              onClick={handleRunAnalysis}
              disabled={isLoading || !hasInterventions}
              aria-busy={isLoading}
            >
              {isLoading ? (
                <>
                  <span className="spinner-dots" aria-hidden="true" />
                  Recomputing in sandbox...
                </>
              ) : (
                <>
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                    <polygon points="5 3 19 12 5 21 5 3" />
                  </svg>
                  Run hypothetical analysis
                </>
              )}
            </button>

            <button
              type="button"
              id="btn-reset-whatif"
              data-testid="btn-reset-whatif"
              className="btn-reset-whatif"
              onClick={handleReset}
              disabled={isLoading}
            >
              Reset inputs
            </button>
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="what-if-error-banner" role="alert" data-testid="what-if-error-banner">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#EF4444" strokeWidth="2" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span>{error}</span>
        </div>
      )}

      {/* Results Display */}
      {result && (
        <div
          className="what-if-results-panel"
          data-testid="what-if-results-panel"
          role="region"
          aria-label="Hypothetical Analysis Results"
        >
          <div className="results-header-banner">
            <span className="results-badge font-sans">
              Hypothetical — original alert unchanged.
            </span>
            <span className="results-timestamp font-mono">
              Account: {result.account_id}
            </span>
          </div>

          <div className="results-metrics-grid">
            <div className="result-metric-card">
              <span className="metric-tag font-sans">Original Score</span>
              <div className="metric-number-row">
                <span className="metric-number">{result.original_score.toFixed(4)}</span>
                <span className={`metric-flag ${result.original_flagged ? 'flagged' : 'unflagged'}`}>
                  {result.original_flagged ? 'FLAGGED' : 'BELOW THRESHOLD'}
                </span>
              </div>
            </div>

            <div className="result-metric-card">
              <span className="metric-tag font-sans">Hypothetical Score</span>
              <div className="metric-number-row">
                <span className="metric-number">{result.counterfactual_score.toFixed(4)}</span>
                <span className={`metric-flag ${result.counterfactual_flagged ? 'flagged' : 'unflagged'}`}>
                  {result.counterfactual_flagged ? 'FLAGGED' : 'BELOW THRESHOLD'}
                </span>
              </div>
            </div>

            <div className="result-metric-card">
              <span className="metric-tag font-sans">Signed Score Delta</span>
              <div className="metric-number-row">
                <span
                  className={`metric-number-delta ${
                    result.score_delta < 0
                      ? 'delta-negative'
                      : result.score_delta > 0
                      ? 'delta-positive'
                      : 'delta-zero'
                  }`}
                  data-testid="signed-score-delta"
                >
                  {result.score_delta >= 0
                    ? `+${result.score_delta.toFixed(4)}`
                    : result.score_delta.toFixed(4)}
                </span>
                <span className="delta-label font-sans">
                  {result.score_delta < 0
                    ? 'Risk Reduced'
                    : result.score_delta > 0
                    ? 'Risk Increased'
                    : 'No Score Change'}
                </span>
              </div>
            </div>
          </div>

          {/* Applied Interventions Summary */}
          <div className="applied-summary-box font-sans">
            <strong>Applied Interventions:</strong>
            <ul className="applied-list font-mono">
              {selectedEdgeIds.length > 0 && (
                <li>Removed {selectedEdgeIds.length} transfer edge(s): {selectedEdgeIds.join(', ')}</li>
              )}
              {suppressDevices && <li>Suppressed shared-device hardware telemetry</li>}
              {suppressComplaints && <li>Suppressed consumer fraud complaints</li>}
            </ul>
          </div>

          {/* Changed Rules */}
          {(result.rules_removed.length > 0 || result.rules_added.length > 0) && (
            <div className="rules-diff-box">
              <span className="diff-title font-sans">Changed Baseline Rules:</span>
              <div className="diff-grid">
                {result.rules_removed.length > 0 && (
                  <div className="diff-col removed">
                    <span className="col-title font-sans">Rules Removed in Sandbox ({result.rules_removed.length}):</span>
                    <div className="rules-pills">
                      {result.rules_removed.map((r) => (
                        <span key={r} className="rule-pill removed">− {r}</span>
                      ))}
                    </div>
                  </div>
                )}
                {result.rules_added.length > 0 && (
                  <div className="diff-col added">
                    <span className="col-title font-sans">Rules Added in Sandbox ({result.rules_added.length}):</span>
                    <div className="rules-pills">
                      {result.rules_added.map((r) => (
                        <span key={r} className="rule-pill added">+ {r}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Plausible Benign Alternative Explanation */}
          <div className="hypothesis-box">
            <span className="hypothesis-label font-sans">Benign Alternative Explanation:</span>
            <p className="hypothesis-text font-sans" data-testid="plausible-benign-alternative">
              {result.plausible_benign_alternative}
            </p>
          </div>

          <p className="results-disclaimer font-sans">
            * Note: Hypothetical results are computed in an isolated sandbox per Contract v1.2 §10.
            Risk scores prioritize accounts for review and do not represent a calibrated percentage probability of fraud or legal proof.
          </p>
        </div>
      )}
    </div>
  )
}
