import React, { useMemo, useRef } from 'react'
import type { AlertPriority, AlertSummary, BudgetK, ReviewStatus } from '../types/api'

interface InvestigationQueueProps {
  alerts: AlertSummary[]
  selectedAlertId: string | null
  onSelectAlert: (alertId: string) => void
  onInvestigateAlert?: (alertId: string) => void
  statusFilter: ReviewStatus | 'ALL'
  onStatusFilterChange: (status: ReviewStatus | 'ALL') => void
  budgetFilter: BudgetK | 'ALL'
  onBudgetFilterChange: (budget: BudgetK | 'ALL') => void
  searchQuery: string
  onSearchQueryChange: (query: string) => void
  isLoading: boolean
}

function getPriorityClass(priority: AlertPriority): string {
  switch (priority) {
    case 'HIGH':
      return 'priority-high'
    case 'MEDIUM':
      return 'priority-medium'
    case 'LOW':
      return 'priority-low'
    default:
      return ''
  }
}

function getStatusClass(status: ReviewStatus): string {
  switch (status) {
    case 'OPEN':
      return 'status-open'
    case 'INVESTIGATING':
      return 'status-investigating'
    case 'CONFIRMED_FRAUD':
      return 'status-confirmed'
    case 'DISMISSED_BENIGN':
      return 'status-dismissed'
    default:
      return ''
  }
}

function getScoreTone(score: number): string {
  if (score >= 0.8) return 'score-critical'
  if (score >= 0.5) return 'score-elevated'
  return 'score-neutral'
}

export const InvestigationQueue: React.FC<InvestigationQueueProps> = ({
  alerts,
  selectedAlertId,
  onSelectAlert,
  onInvestigateAlert,
  statusFilter,
  onStatusFilterChange,
  budgetFilter,
  onBudgetFilterChange,
  searchQuery,
  onSearchQueryChange,
  isLoading,
}) => {
  // Client-side search filtering (preserving deterministic backend ordering: score desc, account_id asc)
  const filteredAlerts = useMemo(() => {
    let list = [...alerts]

    if (searchQuery.trim()) {
      const q = searchQuery.trim().toUpperCase()
      list = list.filter(
        (a) => a.account_id.toUpperCase().includes(q) || a.alert_id.toUpperCase().includes(q)
      )
    }

    // Ensure deterministic sort
    return list.sort((a, b) => {
      if (b.ml.score !== a.ml.score) {
        return b.ml.score - a.ml.score
      }
      return a.account_id.localeCompare(b.account_id)
    })
  }, [alerts, searchQuery])

  const cardRefs = useRef<(HTMLDivElement | null)[]>([])

  const selectedAlertIndex = useMemo(() => {
    return filteredAlerts.findIndex((a) => a.alert_id === selectedAlertId)
  }, [filteredAlerts, selectedAlertId])

  return (
    <section className="workbench-column queue-column" aria-labelledby="queue-heading">
      <div className="col-header">
        <div className="col-title-wrap">
          <h2 id="queue-heading" className="col-title">
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="var(--brand-terracotta, #A56F58)"
              strokeWidth="2"
              aria-hidden="true"
            >
              <line x1="8" y1="6" x2="21" y2="6" />
              <line x1="8" y1="12" x2="21" y2="12" />
              <line x1="8" y1="18" x2="21" y2="18" />
              <line x1="3" y1="6" x2="3.01" y2="6" strokeWidth="3" />
              <line x1="3" y1="12" x2="3.01" y2="12" strokeWidth="3" />
              <line x1="3" y1="18" x2="3.01" y2="18" strokeWidth="3" />
            </svg>
            Alert Queue
          </h2>
          <span className="queue-counter font-mono" aria-label={`${filteredAlerts.length} alerts in queue`}>
            {filteredAlerts.length} {filteredAlerts.length === 1 ? 'Alert' : 'Alerts'}
          </span>
        </div>
      </div>

      {/* Filter and Search Controls */}
      <div className="queue-controls">
        <div className="search-wrap">
          <svg
            className="search-icon"
            viewBox="0 0 24 24"
            width="15"
            height="15"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            id="queue-search"
            type="search"
            className="input-search"
            placeholder="Search account or alert ID..."
            value={searchQuery}
            onChange={(e) => onSearchQueryChange(e.target.value)}
            aria-label="Filter alerts by account or alert ID"
          />
        </div>

        <div className="filter-row">
          <div className="filter-group">
            <label htmlFor="status-select" className="filter-label">
              Review Status:
            </label>
            <select
              id="status-select"
              className="select-control font-mono"
              value={statusFilter}
              onChange={(e) => onStatusFilterChange(e.target.value as ReviewStatus | 'ALL')}
              aria-label="Filter alerts by review status"
            >
              <option value="ALL">ALL STATUSES</option>
              <option value="OPEN">OPEN (Needs Review)</option>
              <option value="INVESTIGATING">INVESTIGATING (In Progress)</option>
              <option value="CONFIRMED_FRAUD">CONFIRMED_FRAUD</option>
              <option value="DISMISSED_BENIGN">DISMISSED_BENIGN</option>
            </select>
          </div>

          <div className="filter-group">
            <label htmlFor="budget-select" className="filter-label" title="Limits how many top-ranked accounts are shown based on analyst review capacity">
              Number of alerts to review (Budget K):
            </label>
            <select
              id="budget-select"
              className="select-control font-mono"
              value={budgetFilter}
              onChange={(e) => {
                const val = e.target.value
                onBudgetFilterChange(val === 'ALL' ? 'ALL' : (Number(val) as BudgetK))
              }}
              aria-label="Filter alerts by analyst capacity budget"
            >
              <option value="ALL">All (Unconstrained)</option>
              <option value="10">Top 10 Highest Risk</option>
              <option value="20">Top 20 (Standard Capacity)</option>
              <option value="50">Top 50</option>
            </select>
          </div>
        </div>

        <div className="filter-help-note font-mono">
          ℹ️ "Number of alerts to review" limits how many top-ranked accounts are shown based on review capacity. It is not a financial transaction limit.
        </div>
      </div>

      {/* Queue Body */}
      <div className="queue-list-container" role="region" aria-label="Alert List">
        {isLoading ? (
          <div className="queue-loading-state" aria-busy="true">
            <div className="skeleton-card" />
            <div className="skeleton-card" />
            <div className="skeleton-card" />
          </div>
        ) : filteredAlerts.length === 0 ? (
          <div className="queue-empty-state">
            <svg
              viewBox="0 0 24 24"
              width="36"
              height="36"
              fill="none"
              stroke="var(--color-text-muted, #7B7F76)"
              strokeWidth="1.5"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" strokeWidth="2.5" />
            </svg>
            <p className="empty-title">No alerts matching filter criteria</p>
            <p className="empty-subtitle">
              Try adjusting your search query, status filter, or budget selection.
            </p>
          </div>
        ) : (
          <div
            className="queue-list"
            role="listbox"
            aria-label="Investigation Alerts"
            aria-activedescendant={selectedAlertId ? `alert-card-${selectedAlertId}` : undefined}
          >
            {filteredAlerts.map((alert, idx) => {
              const isSelected = alert.alert_id === selectedAlertId
              const isFocusable = isSelected || (selectedAlertIndex === -1 && idx === 0)
              const priorityClass = getPriorityClass(alert.priority)
              const statusClass = getStatusClass(alert.status)
              const scoreTone = getScoreTone(alert.ml.score)
              const firstReason = alert.top_reasons[0]

              return (
                <div
                  key={alert.alert_id}
                  id={`alert-card-${alert.alert_id}`}
                  ref={(el) => {
                    cardRefs.current[idx] = el
                  }}
                  role="option"
                  aria-selected={isSelected}
                  tabIndex={isFocusable ? 0 : -1}
                  aria-label={`Alert ${alert.alert_id}, Account ${alert.account_id}, Risk score ${alert.ml.score.toFixed(4)}, Priority ${alert.priority}, Status ${alert.status}`}
                  className={`alert-card ${isSelected ? 'selected' : ''}`}
                  onClick={() => onSelectAlert(alert.alert_id)}
                  onKeyDown={(e) => {
                    if (e.key === 'ArrowDown') {
                      e.preventDefault()
                      const nextIdx = Math.min(idx + 1, filteredAlerts.length - 1)
                      if (nextIdx !== idx) {
                        onSelectAlert(filteredAlerts[nextIdx].alert_id)
                        cardRefs.current[nextIdx]?.focus()
                      }
                    } else if (e.key === 'ArrowUp') {
                      e.preventDefault()
                      const prevIdx = Math.max(idx - 1, 0)
                      if (prevIdx !== idx) {
                        onSelectAlert(filteredAlerts[prevIdx].alert_id)
                        cardRefs.current[prevIdx]?.focus()
                      }
                    } else if (e.key === 'Home') {
                      e.preventDefault()
                      if (filteredAlerts.length > 0) {
                        onSelectAlert(filteredAlerts[0].alert_id)
                        cardRefs.current[0]?.focus()
                      }
                    } else if (e.key === 'End') {
                      e.preventDefault()
                      const lastIdx = filteredAlerts.length - 1
                      if (lastIdx >= 0) {
                        onSelectAlert(filteredAlerts[lastIdx].alert_id)
                        cardRefs.current[lastIdx]?.focus()
                      }
                    } else if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onSelectAlert(alert.alert_id)
                    }
                  }}
                >
                  <div className="alert-card-header">
                    <div className="alert-id-group">
                      <span className="alert-account-id font-mono">{alert.account_id}</span>
                      <span className="alert-id-tag font-mono">{alert.alert_id}</span>
                    </div>

                    <div className="alert-score-badge-wrap">
                      <span
                        className={`alert-score-pill font-mono ${scoreTone}`}
                        title={`Model risk score: ${alert.ml.score.toFixed(4)} (Threshold: ${alert.ml.threshold.toFixed(2)})`}
                      >
                        {alert.ml.score.toFixed(4)}
                      </span>
                    </div>
                  </div>

                  <div className="alert-meta-badges">
                    <span className={`priority-pill ${priorityClass}`}>{alert.priority}</span>
                    <span className={`status-pill-badge ${statusClass}`}>{alert.status}</span>
                    {alert.review.is_stale && (
                      <span className="stale-warning-badge" title="Evidence has changed since prior review">
                        STALE
                      </span>
                    )}
                  </div>

                  {alert.baseline.rules_triggered.length > 0 && (
                    <div className="alert-rules-list">
                      {alert.baseline.rules_triggered.map((rule) => (
                        <span key={rule} className="rule-tag font-mono">
                          {rule}
                        </span>
                      ))}
                    </div>
                  )}

                  {firstReason && (
                    <p className="alert-reason-snippet" title={firstReason.explanation}>
                      {firstReason.explanation}
                    </p>
                  )}

                  <div className="alert-card-footer">
                    <span className="card-timestamp font-mono">
                      {new Date(alert.created_at).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                    <div className="card-flag-tags">
                      {alert.context_flags.shared_device_detected && (
                        <span className="flag-tag device" title="Shared device detected">
                          Device Link
                        </span>
                      )}
                      {alert.context_flags.rapid_pass_through_detected &&
                        !alert.baseline.rules_triggered.includes('RAPID_PASS_THROUGH') && (
                          <span className="flag-tag velocity" title="Rapid pass-through transfer motif detected">
                            Pass-Through
                          </span>
                        )}
                    </div>
                    {onInvestigateAlert && (
                      <button
                        type="button"
                        className="btn-card-investigate font-mono"
                        onClick={(e) => {
                          e.stopPropagation()
                          onInvestigateAlert(alert.alert_id)
                        }}
                        title={`Investigate multi-hop evidence graph for ${alert.account_id}`}
                      >
                        Investigate Graph →
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </section>
  )
}
