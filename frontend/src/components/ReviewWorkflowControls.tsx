import React, { useState, useEffect } from 'react'
import { apiClient, ApiError } from '../api/client'
import type { Alert, ReviewStatus } from '../types/api'
import {
  ALL_REVIEW_STATUSES,
  isAllowedTransition,
  getDisallowedTransitionReason,
} from '../utils/reviewTransitions'

interface ReviewWorkflowControlsProps {
  alert: Alert
  onReviewUpdated: (updatedAlert: Alert) => void
  onReturnToQueue?: () => void
}

export const ReviewWorkflowControls: React.FC<ReviewWorkflowControlsProps> = ({
  alert,
  onReviewUpdated,
  onReturnToQueue,
}) => {
  const currentStatus = alert.review.status
  const isStale = alert.review.is_stale
  const stalenessReason = alert.review.staleness_reason
  const previousReview = alert.review.previous_review

  // Review form state
  const [analystId, setAnalystId] = useState<string>(
    alert.review.analyst_id || 'ANALYST_01'
  )
  const [verdict, setVerdict] = useState<string>(alert.review.verdict || '')
  const [notes, setNotes] = useState<string>(alert.review.notes || '')

  // Submission state
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false)
  const [submittingTarget, setSubmittingTarget] = useState<ReviewStatus | null>(null)
  const [selectedTargetStatus, setSelectedTargetStatus] = useState<ReviewStatus | null>(null)
  const [errorBanner, setErrorBanner] = useState<string | null>(null)
  const [successBanner, setSuccessBanner] = useState<string | null>(null)

  // Sync state when alert changes
  useEffect(() => {
    setAnalystId(alert.review.analyst_id || 'ANALYST_01')
    setVerdict(alert.review.verdict || '')
    setNotes(alert.review.notes || '')
    setSelectedTargetStatus(null)
    setErrorBanner(null)
    setSuccessBanner(null)
  }, [alert.alert_id])

  // Handle status transition submission
  const handleTransition = async (targetStatus: ReviewStatus) => {
    setErrorBanner(null)
    setSuccessBanner(null)

    const trimmedAnalystId = analystId.trim()
    if (!trimmedAnalystId) {
      setErrorBanner('Analyst ID is required (min 1 character).')
      return
    }

    if (targetStatus === currentStatus) {
      setErrorBanner(`Alert is already in ${currentStatus} status.`)
      return
    }

    setIsSubmitting(true)
    setSubmittingTarget(targetStatus)

    try {
      const payload = {
        status: targetStatus,
        analyst_id: trimmedAnalystId,
        verdict: verdict.trim() || null,
        notes: notes.trim() || null,
      }

      // Execute PATCH API without optimistic local state change
      const updated = await apiClient.updateAlertReview(alert.alert_id, payload)

      setSuccessBanner(
        `Review recorded: Status updated to ${updated.review.status} by ${updated.review.analyst_id || trimmedAnalystId}.`
      )
      onReviewUpdated(updated)
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.isInvalidReviewTransition) {
          const ruleExplanation = getDisallowedTransitionReason(currentStatus, targetStatus)
          setErrorBanner(
            `Invalid Transition (HTTP 422): Backend rejected transition from ${currentStatus} to ${targetStatus}. ${ruleExplanation}`
          )
        } else if (err.isAlertNotFound) {
          setErrorBanner(`Alert Not Found (HTTP 404): Alert '${alert.alert_id}' was not found on the backend.`)
        } else {
          setErrorBanner(`API Error (${err.status}): ${err.detail}`)
        }
      } else {
        const msg = err instanceof Error ? err.message : 'Failed to update review status'
        setErrorBanner(`Network / Client Error: ${msg}`)
      }
    } finally {
      setIsSubmitting(false)
      setSubmittingTarget(null)
    }
  }

  // Pre-fill quick template
  const applyTemplate = (tmplVerdict: string, tmplNotes: string) => {
    setVerdict(tmplVerdict)
    setNotes(tmplNotes)
  }

  return (
    <div
      className="review-workflow-section"
      role="region"
      aria-label="Human Review Workflow Controls"
    >
      <div className="review-section-header">
        <div className="review-title-group">
          <span className="review-status-icon font-mono">§9</span>
          <h4 className="section-title-sm" style={{ margin: 0 }}>
            Human Review Decision
          </h4>
        </div>
        <div className="current-status-display">
          <span className="current-status-label">Current Status:</span>
          <span
            className={`status-pill-badge status-${currentStatus.toLowerCase()}`}
            data-testid="current-review-status-badge"
          >
            {currentStatus}
          </span>
        </div>
      </div>

      {/* Staleness Explanation Banner if alert is stale */}
      {isStale && (
        <div
          className="staleness-banner"
          role="alert"
          data-testid="staleness-warning-banner"
        >
          <div className="stale-title-row">
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="#F59E0B"
              strokeWidth="2.5"
              aria-hidden="true"
            >
              <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            <div className="stale-title-text">
              <strong>Previous Decision Needs Another Look (Stale Review Alert)</strong>
              <span className="stale-badge font-mono">STATUS RESET TO OPEN</span>
            </div>
          </div>

          <div className="stale-cause-box">
            <span className="stale-cause-label font-mono">Reason for Review Reset:</span>
            <p className="stale-explanation" data-testid="staleness-reason-text">
              {stalenessReason === 'historical_snapshot_evidence_divergence' ? (
                <>
                  <strong>Historical Snapshot Evidence Divergence:</strong> The point-in-time
                  cutoff (<em>T_as_of</em>) excluded transactions or device telemetry that were
                  present when previously reviewed.
                </>
              ) : stalenessReason === 'evidence_or_score_changed' ? (
                <>
                  <strong>Evidence or Score Changed:</strong> Underlying graph evidence,
                  participating transactions, baseline rules, or ML risk score materially changed
                  since the last recorded decision.
                </>
              ) : (
                <>Alert evidence has diverged from previous review.</>
              )}
            </p>
          </div>

          {previousReview && (
            <div className="previous-review-audit-card font-mono" data-testid="previous-review-card">
              <div className="prev-review-header">
                <span>Prior Review Audit Record</span>
                <span className={`status-pill-mini status-${previousReview.status.toLowerCase()}`}>
                  {previousReview.status}
                </span>
              </div>
              <div className="prev-review-grid">
                <div>
                  <span className="text-dim">Analyst:</span>{' '}
                  <strong>{previousReview.analyst_id || 'Unknown'}</strong>
                </div>
                <div>
                  <span className="text-dim">Recorded At:</span>{' '}
                  <strong>{previousReview.updated_at || 'N/A'}</strong>
                </div>
                {previousReview.verdict && (
                  <div className="prev-review-full-width">
                    <span className="text-dim">Verdict:</span>{' '}
                    <span>{previousReview.verdict}</span>
                  </div>
                )}
                {previousReview.notes && (
                  <div className="prev-review-full-width">
                    <span className="text-dim">Notes:</span> <span>{previousReview.notes}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          <p className="stale-policy-note font-mono">
            Under Contract v1.2 §9.2, when underlying evidence changes, an alert cannot silently retain an outdated verdict. Submitting your decision below establishes a fresh valid review.
          </p>
        </div>
      )}

      {/* Metadata / Active Review Information */}
      <div className="review-metadata-bar font-mono">
        <div className="meta-item">
          <span className="meta-label">Analyst:</span>
          <span className="meta-value">{alert.review.analyst_id || 'Unassigned'}</span>
        </div>
        <div className="meta-item">
          <span className="meta-label">Updated:</span>
          <span className="meta-value">{alert.review.updated_at || 'Never'}</span>
        </div>
        {alert.review.verdict && (
          <div className="meta-item">
            <span className="meta-label">Verdict:</span>
            <span className="meta-value">{alert.review.verdict}</span>
          </div>
        )}
      </div>

      {alert.review.notes && (
        <div className="review-active-notes">
          <span className="notes-label font-mono">Active Investigation Notes:</span>
          <p className="notes-content">{alert.review.notes}</p>
        </div>
      )}

      {/* Error and Success Feedback Banners */}
      {errorBanner && (
        <div className="review-feedback-banner error-banner" role="alert" data-testid="review-error-banner">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#EF4444" strokeWidth="2" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span className="feedback-text">{errorBanner}</span>
          <button
            type="button"
            className="btn-dismiss-banner"
            onClick={() => setErrorBanner(null)}
            aria-label="Dismiss error message"
          >
            ×
          </button>
        </div>
      )}

      {successBanner && (
        <div className="review-feedback-banner success-banner" role="status" data-testid="review-success-banner">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#10B981" strokeWidth="2.5" aria-hidden="true">
            <polyline points="20 6 9 17 4 12" />
          </svg>
          <div className="success-banner-body">
            <span className="feedback-text">{successBanner}</span>
            {onReturnToQueue && (
              <button
                type="button"
                id="btn-return-to-queue"
                data-testid="btn-return-to-queue"
                className="btn-return-to-queue font-mono"
                onClick={onReturnToQueue}
                title="Return to Alert Queue"
              >
                Return to Alert Queue &rarr;
              </button>
            )}
          </div>
          <button
            type="button"
            className="btn-dismiss-banner"
            onClick={() => setSuccessBanner(null)}
            aria-label="Dismiss success message"
          >
            ×
          </button>
        </div>
      )}

      {/* Review Form Fields */}
      <div className="review-form-body">
        <div className="form-row-2">
          <div className="form-group">
            <label htmlFor="input-analyst-id" className="form-label font-mono">
              Your Analyst ID (Analyst Identifier) <span className="required-star">*</span>
            </label>
            <input
              id="input-analyst-id"
              type="text"
              className="form-input font-mono"
              value={analystId}
              onChange={(e) => setAnalystId(e.target.value)}
              placeholder="e.g. ANALYST_01"
              disabled={isSubmitting}
              required
            />
            <span className="form-help-subtext">
              The identifier used to record who made this review decision in the audit log.
            </span>
          </div>

          <div className="form-group">
            <label htmlFor="input-verdict" className="form-label font-mono">
              Decision Summary (Investigation Verdict)
            </label>
            <input
              id="input-verdict"
              type="text"
              className="form-input font-mono"
              value={verdict}
              onChange={(e) => setVerdict(e.target.value)}
              placeholder="e.g. CONFIRMED_MULE_RING"
              disabled={isSubmitting}
            />
          </div>
        </div>

        <div className="quick-templates-row">
          <span className="quick-tmpl-label font-mono">Quick Verdicts:</span>
          <button
            type="button"
            className="btn-quick-tmpl font-mono"
            onClick={() =>
              applyTemplate(
                'CONFIRMED_MULE_RING',
                'Verified multi-hop rapid layering pattern dispersing funds to merchant cash-out.'
              )
            }
            disabled={isSubmitting}
          >
            Mule Ring
          </button>
          <button
            type="button"
            className="btn-quick-tmpl font-mono"
            onClick={() =>
              applyTemplate(
                'BENIGN_SHARED_DEVICE',
                'Verified legitimate household device sharing; normal pass-through transaction flow.'
              )
            }
            disabled={isSubmitting}
          >
            Benign Device
          </button>
          <button
            type="button"
            className="btn-quick-tmpl font-mono"
            onClick={() =>
              applyTemplate(
                'FALSE_POSITIVE',
                'No coordinated fan-in or velocity burst; single isolated high-amount transfer.'
              )
            }
            disabled={isSubmitting}
          >
            False Positive
          </button>
        </div>

        <div className="form-group">
          <label htmlFor="textarea-review-notes" className="form-label font-mono">
            Review Rationale & Evidentiary Notes
          </label>
          <textarea
            id="textarea-review-notes"
            className="form-textarea"
            rows={3}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Record justification, subgraph findings, and counterparty verification..."
            disabled={isSubmitting}
          />
        </div>

        {/* Status Transition Action Buttons */}
        <div className="status-transition-actions">
          <div className="actions-header-row">
            <span className="actions-title font-mono">Set Final Review Decision (§9.1):</span>
            {isSubmitting && (
              <span className="saving-spinner font-mono">
                <span className="spinner-dots" /> Submitting decision to backend...
              </span>
            )}
          </div>

          <div className="transition-buttons-grid">
            {ALL_REVIEW_STATUSES.map((status) => {
              const isCurrent = status === currentStatus
              const isAllowed = isAllowedTransition(currentStatus, status)
              const isTargetBeingSubmitted = isSubmitting && submittingTarget === status

              return (
                <button
                  key={status}
                  type="button"
                  id={`btn-transition-${status.toLowerCase()}`}
                  data-testid={`btn-transition-${status.toLowerCase()}`}
                  className={`btn-transition-action btn-status-${status.toLowerCase()} ${
                    isCurrent ? 'is-current' : ''
                  } ${isAllowed ? 'is-allowed' : 'is-disallowed'}`}
                  onClick={() => {
                    setSelectedTargetStatus(status)
                    handleTransition(status)
                  }}
                  disabled={isSubmitting || isCurrent}
                  title={
                    isCurrent
                      ? `Alert is already in ${status} status`
                      : isAllowed
                      ? `Transition alert to ${status}`
                      : `Disallowed: ${getDisallowedTransitionReason(currentStatus, status)}`
                  }
                  aria-pressed={isCurrent}
                >
                  <span className="btn-status-title font-mono">
                    {isTargetBeingSubmitted ? 'Saving...' : status}
                  </span>
                  <span className="btn-transition-tag font-mono">
                    {isCurrent ? 'CURRENT' : isAllowed ? 'ALLOWED' : 'DISALLOWED'}
                  </span>
                </button>
              )
            })}
          </div>

          {/* Explicit Save Action Button */}
          <div className="submit-action-row" style={{ marginTop: '0.75rem' }}>
            <button
              type="button"
              id="btn-submit-review"
              data-testid="btn-submit-review"
              className="btn-submit-review font-mono"
              onClick={() => {
                const target =
                  selectedTargetStatus ||
                  (isAllowedTransition(currentStatus, 'INVESTIGATING')
                    ? 'INVESTIGATING'
                    : isAllowedTransition(currentStatus, 'CONFIRMED_FRAUD')
                    ? 'CONFIRMED_FRAUD'
                    : 'INVESTIGATING')
                handleTransition(target)
              }}
              disabled={isSubmitting}
              title="Submit and record review decision"
            >
              {isSubmitting ? (
                <>
                  <span className="spinner-icon-sm" aria-hidden="true" />
                  Submitting review...
                </>
              ) : (
                <>
                  <svg
                    viewBox="0 0 24 24"
                    width="14"
                    height="14"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    aria-hidden="true"
                  >
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  Submit review
                </>
              )}
            </button>
          </div>

          <div className="state-machine-legend font-mono">
            <span>Review Policy Rules:</span>
            <span>OPEN → Any status</span>
            <span>·</span>
            <span>INVESTIGATING → Conclude</span>
            <span>·</span>
            <span>CONFIRMED / DISMISSED → Reopen to INVESTIGATING</span>
          </div>
        </div>
      </div>
    </div>
  )
}
