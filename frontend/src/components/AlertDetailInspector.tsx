import React from 'react'
import type { Alert } from '../types/api'
import { ReviewWorkflowControls } from './ReviewWorkflowControls'
import { WhatIfInvestigation } from './WhatIfInvestigation'

interface AlertDetailInspectorProps {
  alert: Alert | null
  isLoading: boolean
  error: string | null
  onRetry?: () => void
  onReviewUpdated?: (updatedAlert: Alert) => void
  onReturnToQueue?: () => void
}

/**
 * Maps raw rule identifiers to plain-English descriptions for non-technical analysts.
 */
function formatRuleDescription(rule: string): string {
  switch (rule) {
    case 'HIGH_FAN_IN':
      return 'Many incoming transfers from different senders (High Fan-In)'
    case 'RAPID_PASS_THROUGH':
      return 'Money sent out immediately after arrival (Rapid Pass-Through)'
    case 'SHARED_DEVICE_SUSPICIOUS':
      return 'Device shared across multiple distinct accounts'
    case 'HIGH_VELOCITY_BURST':
      return 'Unusually high frequency of transactions in a short window'
    case 'HIGH_TOTAL_AMOUNT':
      return 'Cumulative volume exceeds standard account threshold'
    default:
      return rule.replace(/_/g, ' ')
  }
}

export const AlertDetailInspector: React.FC<AlertDetailInspectorProps> = ({
  alert,
  isLoading,
  error,
  onRetry,
  onReviewUpdated,
  onReturnToQueue,
}) => {
  if (isLoading) {
    return (
      <div className="inspector-panel" aria-busy="true" aria-label="Loading Alert Details">
        <div className="inspector-header skeleton-pulse">
          <div className="skeleton-line title" />
          <div className="skeleton-line subtitle" />
        </div>
        <div className="inspector-body">
          <div className="skeleton-block" />
          <div className="skeleton-block" />
          <div className="skeleton-block" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="inspector-panel error-panel" role="alert">
        <div className="inspector-error-content">
          <svg
            viewBox="0 0 24 24"
            width="32"
            height="32"
            fill="none"
            stroke="var(--color-high-risk, #C65B4A)"
            strokeWidth="2"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <h3 className="error-title">Failed to load alert details</h3>
          <p className="error-desc">{error}</p>
          {onRetry && (
            <button type="button" className="btn-secondary" onClick={onRetry}>
              Retry Load
            </button>
          )}
        </div>
      </div>
    )
  }

  if (!alert) {
    return (
      <div className="inspector-panel empty-panel">
        <div className="inspector-placeholder">
          <svg
            viewBox="0 0 24 24"
            width="40"
            height="40"
            fill="none"
            stroke="var(--color-text-muted, #7B7F76)"
            strokeWidth="1.5"
            aria-hidden="true"
          >
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
            <polyline points="10 9 9 9 8 9" />
          </svg>
          <h3 className="placeholder-title">No Alert Selected</h3>
          <p className="placeholder-hint">
            Select an alert card from the queue on the left to inspect its multi-hop evidence, model
            scoring breakdown, and behavioral telemetry.
          </p>
        </div>
      </div>
    )
  }

  // Count node types in 2-hop subgraph
  const nodeCounts = alert.evidence.nodes.reduce(
    (acc, node) => {
      acc[node.type] = (acc[node.type] || 0) + 1
      return acc
    },
    {} as Record<string, number>
  )

  // Risk classification in plain English
  const riskCategory =
    alert.ml.score >= 0.8
      ? 'Many transfers in a short time'
      : alert.ml.score >= 0.5
      ? 'Elevated suspicious patterns'
      : 'Low risk pattern'

  return (
    <div className="inspector-panel" role="region" aria-label={`Inspection Details for ${alert.account_id}`}>
      {/* Inspector Top Bar */}
      <div className="inspector-header">
        <div className="inspector-id-block">
          <div className="account-title-row">
            <h3 className="account-heading font-mono">{alert.account_id}</h3>
            <span className="alert-tag font-mono">{alert.alert_id}</span>
          </div>
          <div className="fingerprint-row font-mono" title={`Security SHA-256 Fingerprint: ${alert.alert_fingerprint}`}>
            <span className="fp-label">Audit Fingerprint:</span>
            <span className="fp-value">{alert.alert_fingerprint.slice(0, 16)}...</span>
          </div>
        </div>

        <div className="inspector-status-badges">
          <span className={`priority-pill priority-${alert.priority.toLowerCase()}`}>
            {alert.priority} Priority
          </span>
          <span className={`status-pill-badge status-${alert.status.toLowerCase()}`}>
            {alert.status}
          </span>
        </div>
      </div>

      <div className="inspector-body">
        {/* 1. Risk Summary with Plain-English Explanations */}
        <div className="inspector-section" id="inspector-risk-summary">
          <div className="section-header-compact">
            <h4 className="section-title-sm">1. Risk Summary</h4>
            <span className={`priority-pill priority-${alert.priority.toLowerCase()}`}>
              {alert.priority} Priority
            </span>
          </div>

          <div className="metrics-grid-2">
            <div className="metric-box">
              <span className="metric-label">Risk Score</span>
              <div className="metric-score-row font-mono">
                <span className="metric-score-big">{alert.ml.score.toFixed(4)}</span>
                <span className="metric-threshold text-dim">/ cutoff: {alert.ml.threshold.toFixed(2)}</span>
              </div>
              <span className={`score-verdict ${alert.ml.flagged ? 'flagged' : 'unflagged'}`}>
                {alert.ml.flagged
                  ? 'Model recommends reviewing this account'
                  : 'Below flagging cutoff'}
              </span>
              <p className="metric-explainer-note">
                Investigative score (0.0 to 1.0). Higher score indicates strong resemblance to mule ring patterns; not a percentage probability of fraud.
              </p>
            </div>

            <div className="metric-box">
              <span className="metric-label">Risk Category</span>
              <div className="metric-score-row font-mono">
                <span className="metric-stat-text">{riskCategory}</span>
              </div>
              <span className="text-muted" style={{ fontSize: '0.75rem', marginTop: 'auto' }}>
                Flagging Cutoff: {alert.ml.threshold.toFixed(2)}
              </span>
              <p className="metric-explainer-note">
                Prioritizes this account for human analyst investigation based on velocity and counterparty dispersion.
              </p>
            </div>
          </div>
        </div>

        {/* 2. Warning Signs Detected by Rules */}
        <div className="inspector-section" id="inspector-triggered-rules">
          <div className="section-header-compact">
            <h4 className="section-title-sm">2. Warning Signs Detected by Rules</h4>
            <span className="badge-dim font-mono">
              Rules Triggered: {alert.baseline.flagged ? 'YES' : 'NONE'}
            </span>
          </div>
          <div className="rules-badges-wrap">
            {alert.baseline.rules_triggered.length > 0 ? (
              alert.baseline.rules_triggered.map((rule) => (
                <div key={rule} className="rule-card-item">
                  <span className="rule-icon" aria-hidden="true">⚠️</span>
                  <div className="rule-info">
                    <span className="rule-plain-title">{formatRuleDescription(rule)}</span>
                    <span className="rule-technical-code font-mono">Rule code: {rule}</span>
                  </div>
                </div>
              ))
            ) : (
              <span className="text-dim font-mono">No heuristic baseline warning signs triggered.</span>
            )}
          </div>
        </div>

        {/* 3. Reasons Behind the Risk Score */}
        <div className="inspector-section" id="inspector-explanatory-features">
          <div className="section-header-compact">
            <h4 className="section-title-sm">3. Reasons Behind the Risk Score</h4>
            <span className="badge-dim font-mono">{alert.top_reasons.length} Factors</span>
          </div>

          <p className="section-context-desc">
            These features contributed most heavily to the account's risk score relative to normal transaction baselines:
          </p>

          {alert.top_reasons.length > 0 ? (
            <div className="reasons-list">
              {alert.top_reasons.map((reason, idx) => (
                <div key={idx} className="reason-card">
                  <div className="reason-header">
                    <span className="reason-feature font-mono">{reason.feature}</span>
                    <span className="reason-values font-mono">
                      Observed: <strong>{String(reason.value)}</strong> (Typical baseline median: {String(reason.typical_value)})
                    </span>
                  </div>
                  <p className="reason-explanation">{reason.explanation}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-dim">No specific outlier features recorded.</p>
          )}

          <p className="feature-disclaimer-note">
            Note: Deviations from median baselines represent suspicious behavioral signals, not independent proof of fraudulent conduct.
          </p>
        </div>

        {/* 4. Patterns Noticed */}
        <div className="inspector-section" id="inspector-behavioral-context">
          <h4 className="section-title-sm">4. Patterns Noticed</h4>
          <div className="flags-grid">
            <div className={`flag-status-card ${alert.context_flags.shared_device_detected ? 'active' : ''}`}>
              <div className="flag-card-header">
                <span className="flag-title">Accounts Sharing a Device</span>
                <span className="flag-indicator font-mono">
                  {alert.context_flags.shared_device_detected ? 'DETECTED' : 'NONE'}
                </span>
              </div>
              <p className="flag-description">
                {alert.context_flags.shared_device_detected
                  ? 'Other accounts in the network have authenticated from the same physical device identifier.'
                  : 'No shared device authentication observed across other accounts.'}
              </p>
            </div>

            <div className={`flag-status-card ${alert.context_flags.rapid_pass_through_detected ? 'active' : ''}`}>
              <div className="flag-card-header">
                <span className="flag-title">Rapid Money Pass-Through</span>
                <span className="flag-indicator font-mono">
                  {alert.context_flags.rapid_pass_through_detected ? 'DETECTED' : 'NONE'}
                </span>
              </div>
              <p className="flag-description">
                {alert.context_flags.rapid_pass_through_detected
                  ? 'Inbound funds were immediately forwarded to another recipient within minutes, characteristic of a mule transit account.'
                  : 'No immediate fund forwarding motif detected.'}
              </p>
            </div>
          </div>

          {nodeCounts['complaint'] ? (
            <div className="complaint-notice-box">
              <span className="complaint-icon" aria-hidden="true">📋</span>
              <span className="complaint-text">
                {nodeCounts['complaint']} consumer complaint(s) linked in 2-hop neighborhood. Complaints provide valuable investigative leads but do not independently prove fraud without corroborated transaction evidence.
              </span>
            </div>
          ) : null}

          {alert.context_flags.note && (
            <p className="context-note-text font-mono">Investigative note: {alert.context_flags.note}</p>
          )}
        </div>

        {/* 5. Review Decision & Notes */}
        <div className="inspector-section" id="inspector-review-decision">
          <h4 className="section-title-sm">5. Review Decision & Notes</h4>
          <ReviewWorkflowControls
            alert={alert}
            onReviewUpdated={(updated) => {
              if (onReviewUpdated) {
                onReviewUpdated(updated)
              }
            }}
            onReturnToQueue={onReturnToQueue}
          />
        </div>

        {/* Collapsible What-if Investigation Section */}
        <details className="inspector-section what-if-disclosure" id="inspector-what-if">
          <summary className="what-if-summary font-mono">
            <span className="what-if-summary-title">What-if investigation (Counterfactual Analysis)</span>
            <span className="collapsible-hint">Explore alternate hypotheses</span>
          </summary>
          <div style={{ marginTop: '0.75rem' }}>
            <WhatIfInvestigation alert={alert} />
          </div>
        </details>

        {/* Collapsed Technical Details Area for genuine debugging telemetry */}
        <details className="inspector-section technical-details-disclosure" id="inspector-technical-details">
          <summary className="technical-summary font-mono">
            <span className="technical-title">Technical Details &amp; Debugging Information</span>
            <span className="collapsible-hint">Click to expand</span>
          </summary>

          <div className="technical-details-content font-mono" style={{ marginTop: '0.75rem' }}>
            <div className="evidence-stat-row">
              <span>Nodes: {alert.evidence.nodes.length} / 25 max</span>
              <span>Edges: {alert.evidence.edges.length} / 60 max</span>
              <span>Path: {alert.evidence.evidence_path.length} hops</span>
            </div>

            <div className="node-types-breakdown" style={{ marginTop: '0.4rem' }}>
              {nodeCounts['account'] ? <span>Accounts: {nodeCounts['account']}</span> : null}
              {nodeCounts['device'] ? <span>Devices: {nodeCounts['device']}</span> : null}
              {nodeCounts['merchant'] ? <span>Merchants: {nodeCounts['merchant']}</span> : null}
              {nodeCounts['complaint'] ? <span>Complaints: {nodeCounts['complaint']}</span> : null}
            </div>

            <div className="fingerprint-full-row" style={{ marginTop: '0.5rem', wordBreak: 'break-all', fontSize: '0.75rem' }}>
              <span className="text-dim">Full SHA-256 Alert Fingerprint:</span>
              <div className="fp-full-text font-mono" style={{ color: 'var(--color-text-primary, #EAE7DF)' }}>{alert.alert_fingerprint}</div>
            </div>

            <div className="raw-fields-grid font-mono" style={{ marginTop: '0.5rem', padding: '0.5rem', background: 'var(--app-bg, #121411)', border: '1px solid var(--border-subtle, #2C3028)', borderRadius: '4px', fontSize: '0.75rem' }}>
              <div><strong>ml.score:</strong> {alert.ml.score}</div>
              <div><strong>ml.threshold:</strong> {alert.ml.threshold}</div>
              <div><strong>ml.flagged:</strong> {String(alert.ml.flagged)}</div>
              <div><strong>baseline.flagged:</strong> {String(alert.baseline.flagged)}</div>
              <div><strong>rules_triggered:</strong> {JSON.stringify(alert.baseline.rules_triggered)}</div>
              <div><strong>alert_id:</strong> {alert.alert_id}</div>
              <div><strong>account_id:</strong> {alert.account_id}</div>
              <div><strong>created_at:</strong> {alert.created_at}</div>
            </div>
          </div>
        </details>
      </div>
    </div>
  )
}
