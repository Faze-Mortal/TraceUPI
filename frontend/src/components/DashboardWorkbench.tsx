import React, { useState, useEffect, useCallback } from 'react'
import { apiClient, ApiError } from '../api/client'
import type { Alert, AlertSummary, BudgetK, PipelineRunResponse, ReviewStatus } from '../types/api'
import { InvestigationQueue } from './InvestigationQueue'
import { AlertDetailInspector } from './AlertDetailInspector'
import { EvidenceGraphCanvas } from './EvidenceGraphCanvas'

interface DashboardWorkbenchProps {
  onBackToOverview: () => void
}

export const DashboardWorkbench: React.FC<DashboardWorkbenchProps> = ({ onBackToOverview }) => {
  // Pipeline state
  const [isPipelineRunning, setIsPipelineRunning] = useState(false)
  const [pipelineResult, setPipelineResult] = useState<PipelineRunResponse | null>(null)
  const [pipelineError, setPipelineError] = useState<string | null>(null)
  const [asOfInput, setAsOfInput] = useState<string>('')

  // Historical cutoff date & time picker state
  const [cutoffDate, setCutoffDate] = useState<string>('')
  const [cutoffTime, setCutoffTime] = useState<string>('12:00')
  const [cutoffError, setCutoffError] = useState<string | null>(null)

  // 30-minute time increments for dropdown (48 slots: 00:00 to 23:30)
  const timeOptions = Array.from({ length: 48 }, (_, i) => {
    const h = String(Math.floor(i / 2)).padStart(2, '0')
    const m = i % 2 === 0 ? '00' : '30'
    return `${h}:${m}`
  })

  // Compute and validate explicit UTC ISO 8601 string from local date and time
  const computeUtcCutoff = (dateStr: string, timeStr: string) => {
    try {
      const localDateTime = new Date(`${dateStr}T${timeStr}:00`)
      if (isNaN(localDateTime.getTime())) {
        setCutoffError('Invalid date or time selected.')
        setAsOfInput('')
        return
      }
      // Explicit UTC ISO format ending in Z without milliseconds: YYYY-MM-DDTHH:MM:SSZ
      const utcIso = localDateTime.toISOString().replace(/\.\d{3}Z$/, 'Z')
      setAsOfInput(utcIso)
      setCutoffError(null)
    } catch {
      setCutoffError('Failed to convert selected date/time to UTC.')
      setAsOfInput('')
    }
  }

  // Handle calendar date selection
  const handleCutoffDateChange = (newDate: string) => {
    setCutoffDate(newDate)
    if (!newDate) {
      setAsOfInput('')
      setCutoffError(null)
      return
    }
    computeUtcCutoff(newDate, cutoffTime)
  }

  // Handle 30-minute time selection
  const handleCutoffTimeChange = (newTime: string) => {
    setCutoffTime(newTime)
    if (!cutoffDate) {
      return
    }
    computeUtcCutoff(cutoffDate, newTime)
  }

  // Clear / Reset cutoff to full history
  const handleResetCutoff = () => {
    setCutoffDate('')
    setCutoffTime('12:00')
    setAsOfInput('')
    setCutoffError(null)
  }

  // Alerts queue state
  const [alerts, setAlerts] = useState<AlertSummary[]>([])
  const [isAlertsLoading, setIsAlertsLoading] = useState<boolean>(false)
  const [alertsError, setAlertsError] = useState<string | null>(null)
  const [isAnalysisNotRun, setIsAnalysisNotRun] = useState<boolean>(false)

  // Filters
  const [statusFilter, setStatusFilter] = useState<ReviewStatus | 'ALL'>('ALL')
  const [budgetFilter, setBudgetFilter] = useState<BudgetK | 'ALL'>('ALL')
  const [searchQuery, setSearchQuery] = useState<string>('')

  // Active workflow section: 'queue' | 'graph' | 'review'
  const [activeSection, setActiveSection] = useState<'queue' | 'graph' | 'review'>('queue')

  // Selected alert inspector state
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null)
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null)
  const [isDetailLoading, setIsDetailLoading] = useState<boolean>(false)
  const [detailError, setDetailError] = useState<string | null>(null)

  // Handle alert selection from queue
  const handleSelectAlert = (alertId: string) => {
    setSelectedAlertId(alertId)
    setActiveSection('review')
  }

  // Handle alert investigation navigation directly to graph
  const handleInvestigateAlert = (alertId: string) => {
    setSelectedAlertId(alertId)
    setActiveSection('graph')
  }

  // Fetch alerts from backend
  const fetchAlerts = useCallback(
    async (currentStatus: ReviewStatus | 'ALL', currentBudget: BudgetK | 'ALL') => {
      setIsAlertsLoading(true)
      setAlertsError(null)

      try {
        const params: { status?: ReviewStatus; budget_k?: BudgetK } = {}
        if (currentStatus !== 'ALL') {
          params.status = currentStatus
        }
        if (currentBudget !== 'ALL') {
          params.budget_k = currentBudget
        }

        const data = await apiClient.getAlerts(params)
        setAlerts(data)
        setIsAnalysisNotRun(false)

        // If currently selected alert is no longer in queue, deselect or re-evaluate
        if (selectedAlertId && !data.some((a) => a.alert_id === selectedAlertId)) {
          // keep selectedAlertId if user still wants to inspect it, or auto-select first
        }
      } catch (err) {
        if (err instanceof ApiError && err.isAnalysisNotRun) {
          setIsAnalysisNotRun(true)
          setAlerts([])
        } else {
          const msg = err instanceof Error ? err.message : 'Failed to retrieve alerts'
          setAlertsError(msg)
        }
      } finally {
        setIsAlertsLoading(false)
      }
    },
    [selectedAlertId]
  )

  // Initial load
  useEffect(() => {
    fetchAlerts(statusFilter, budgetFilter)
  }, [fetchAlerts, statusFilter, budgetFilter])

  // Fetch full details when an alert is selected
  useEffect(() => {
    if (!selectedAlertId) {
      setSelectedAlert(null)
      setDetailError(null)
      return
    }

    let isMounted = true
    setIsDetailLoading(true)
    setDetailError(null)

    apiClient
      .getAlert(selectedAlertId)
      .then((data) => {
        if (isMounted) {
          setSelectedAlert(data)
        }
      })
      .catch((err) => {
        if (isMounted) {
          const msg = err instanceof Error ? err.message : 'Failed to load alert details'
          setDetailError(msg)
        }
      })
      .finally(() => {
        if (isMounted) {
          setIsDetailLoading(false)
        }
      })

    return () => {
      isMounted = false
    }
  }, [selectedAlertId])

  // Trigger pipeline run
  const handleRunPipeline = async () => {
    setIsPipelineRunning(true)
    setPipelineError(null)

    try {
      const trimmedAsOf = asOfInput.trim() || null
      const res = await apiClient.runPipeline(trimmedAsOf ? { as_of: trimmedAsOf } : undefined)
      setPipelineResult(res)
      setIsAnalysisNotRun(false)

      // Refresh alerts queue after analysis
      await fetchAlerts(statusFilter, budgetFilter)
    } catch (err) {
      const msg = err instanceof ApiError ? `${err.detail}` : err instanceof Error ? err.message : 'Pipeline run failed'
      setPipelineError(msg)
    } finally {
      setIsPipelineRunning(false)
    }
  }

  // Handle successful human review updates from AlertDetailInspector
  const handleReviewUpdated = (updatedAlert: Alert) => {
    setSelectedAlert(updatedAlert)

    // Update alerts queue item in place to keep queue synchronized immediately
    setAlerts((prevAlerts) =>
      prevAlerts.map((item) => {
        if (item.alert_id === updatedAlert.alert_id) {
          return {
            ...item,
            status: updatedAlert.review.status,
            review: {
              status: updatedAlert.review.status,
              is_stale: updatedAlert.review.is_stale,
              staleness_reason: updatedAlert.review.staleness_reason,
              analyst_id: updatedAlert.review.analyst_id,
              updated_at: updatedAlert.review.updated_at,
              verdict: updatedAlert.review.verdict,
              notes: updatedAlert.review.notes,
            },
          }
        }
        return item
      })
    )

    // If an explicit status filter is active, refresh from backend to respect filter
    if (statusFilter !== 'ALL') {
      fetchAlerts(statusFilter, budgetFilter)
    }
  }

  return (
    <div className="dashboard-workbench" role="region" aria-label="TraceUPI Investigation Console">
      {/* Console Top Header Bar */}
      <header className="console-header">
        <div className="console-title-group">
          <button
            type="button"
            className="btn-back-link"
            onClick={onBackToOverview}
            id="btn-back-to-overview"
            aria-label="Back to landing page overview"
          >
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </svg>
            Overview
          </button>
          <span className="console-divider" aria-hidden="true">
            /
          </span>
          <h1 className="console-title">Investigation Workbench</h1>
          <span className="badge-milestone">Milestone 4: Review Active</span>
          <h2 className="guideline-title sr-only">Core Visualization Design Standard</h2>
        </div>

        {/* Pipeline Execution Controls */}
        <div className="console-actions">
          <details className="advanced-options-disclosure font-mono">
            <summary className="btn-toggle-asof font-mono" title="Show advanced historical cutoff options">
              Advanced options
            </summary>
            <div className="advanced-options-panel">
              <label htmlFor="input-asof-date" className="advanced-options-label">
                Analyze data up to a time:
              </label>

              <div className="datetime-picker-row">
                <div className="picker-field">
                  <label htmlFor="input-asof-date" className="picker-sublabel">
                    Date:
                  </label>
                  <input
                    type="date"
                    id="input-asof-date"
                    data-testid="input-asof-date"
                    aria-label="Analyze data up to a time"
                    className="input-asof-date font-mono"
                    value={cutoffDate}
                    onChange={(e) => handleCutoffDateChange(e.target.value)}
                  />
                </div>

                <div className="picker-field">
                  <label htmlFor="select-asof-time" className="picker-sublabel">
                    Time (30m):
                  </label>
                  <select
                    id="select-asof-time"
                    data-testid="select-asof-time"
                    aria-label="Historical cutoff time"
                    className="select-asof-time font-mono"
                    value={cutoffTime}
                    onChange={(e) => handleCutoffTimeChange(e.target.value)}
                  >
                    {timeOptions.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </div>

                <button
                  type="button"
                  id="btn-clear-asof"
                  data-testid="btn-clear-asof"
                  className="btn-clear-asof font-mono"
                  onClick={handleResetCutoff}
                  title="Clear cutoff to analyze full available history"
                >
                  Clear cutoff
                </button>
              </div>

              {cutoffError && (
                <div className="cutoff-error-text" role="alert">
                  {cutoffError}
                </div>
              )}

              {/* Display of selected date/time */}
              {asOfInput && cutoffDate ? (
                <div className="cutoff-display-card font-mono" data-testid="cutoff-display-active">
                  <div className="cutoff-display-row">
                    <span className="text-dim">Selected Local:</span>
                    <span className="text-strong">
                      {new Date(`${cutoffDate}T${cutoffTime}:00`).toLocaleString()}
                    </span>
                  </div>
                  <div className="cutoff-display-row">
                    <span className="text-dim">Cutoff (UTC):</span>
                    <span className="text-amber font-mono" data-testid="active-cutoff-utc">
                      {asOfInput}
                    </span>
                  </div>
                </div>
              ) : (
                <div className="cutoff-display-card empty font-mono" data-testid="cutoff-display-empty">
                  <span className="text-dim">Active Mode: Full history (no historical cutoff)</span>
                </div>
              )}

              <p className="advanced-help-text">
                Analyze only data available by this date and time. Rerunning fraud-risk analysis evaluates only transactions ingested on or before this time. If historical evidence diverges from an earlier review, existing review verdicts will be marked STALE under Contract v1.2.
              </p>
            </div>
          </details>

          <button
            type="button"
            id="btn-run-pipeline"
            className="btn-run-pipeline"
            onClick={handleRunPipeline}
            disabled={isPipelineRunning}
            aria-busy={isPipelineRunning}
          >
            {isPipelineRunning ? (
              <>
                <span className="spinner-icon" aria-hidden="true" />
                Running fraud-risk analysis...
              </>
            ) : (
              <>
                <svg
                  viewBox="0 0 24 24"
                  width="16"
                  height="16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  aria-hidden="true"
                >
                  <polygon points="5 3 19 12 5 21 5 3" />
                </svg>
                Run fraud-risk analysis
              </>
            )}
          </button>

          {/* Backend Status Telemetry */}
          <div className="status-pill font-mono">
            {isAnalysisNotRun ? (
              <>
                <span className="status-indicator offline" aria-hidden="true" />
                <span className="status-text">Analysis Not Run (503)</span>
              </>
            ) : pipelineResult ? (
              <>
                <span className="status-indicator online" aria-hidden="true" />
                <span className="status-text">
                  Ready · {pipelineResult.n_transactions} Txns · {pipelineResult.n_alerts} Alerts
                </span>
              </>
            ) : (
              <>
                <span className="status-indicator online" aria-hidden="true" />
                <span className="status-text">Store Connected</span>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Main Console Workspace */}
      <main className="console-container">
        {/* Pipeline Error Banner */}
        {pipelineError && (
          <div className="alert-banner error" role="alert">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#EF4444" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>Pipeline execution error: {pipelineError}</span>
          </div>
        )}

        {/* Alerts Fetch Error Banner */}
        {alertsError && (
          <div className="alert-banner error" role="alert">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#EF4444" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>Failed to fetch alerts: {alertsError}</span>
            <button
              type="button"
              className="btn-text-retry"
              onClick={() => fetchAlerts(statusFilter, budgetFilter)}
            >
              Retry
            </button>
          </div>
        )}

        {/* 503 Analysis Not Run Standalone Banner */}
        {isAnalysisNotRun && (
          <div className="pre-analysis-banner" role="region" aria-labelledby="pre-analysis-title">
            <div className="pre-analysis-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="#F59E0B" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" strokeWidth="2.5" />
              </svg>
            </div>
            <div className="pre-analysis-content">
              <h2 id="pre-analysis-title" className="pre-analysis-title">
                Analysis Pipeline Has Not Run Yet (HTTP 503)
              </h2>
              <p className="pre-analysis-text">
                The in-memory investigation store is currently empty. Run the backend pipeline to ingest
                synthetic transactions, extract 25-dimensional structural and graph features, calculate
                model risk scores, and populate prioritized alerts.
              </p>
              <div className="pre-analysis-actions">
                <button
                  type="button"
                  id="btn-preanalysis-run"
                  className="btn-primary"
                  onClick={handleRunPipeline}
                  disabled={isPipelineRunning}
                >
                  {isPipelineRunning ? 'Running Pipeline...' : 'Run Analysis Pipeline Now'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Persistent Guided Workflow Navigation Tabs */}
        <div className="workbench-workflow-nav" role="navigation" aria-label="Investigation Stages">
          <div className="workflow-tabs">
            <button
              type="button"
              id="tab-section-queue"
              data-testid="tab-section-queue"
              className={`workflow-tab ${activeSection === 'queue' ? 'active' : ''}`}
              onClick={() => setActiveSection('queue')}
              aria-current={activeSection === 'queue' ? 'page' : undefined}
            >
              <span className="tab-number font-mono">1</span>
              <span className="tab-title">Alert Queue</span>
              <span className="tab-count font-mono">{alerts.length}</span>
            </button>

            <span className="tab-connector" aria-hidden="true">→</span>

            <button
              type="button"
              id="tab-section-graph"
              data-testid="tab-section-graph"
              className={`workflow-tab ${activeSection === 'graph' ? 'active' : ''} ${!selectedAlert ? 'no-selection' : ''}`}
              onClick={() => setActiveSection('graph')}
              aria-current={activeSection === 'graph' ? 'page' : undefined}
            >
              <span className="tab-number font-mono">2</span>
              <span className="tab-title">Evidence Graph</span>
              <span className="tab-badge-info font-mono">
                {selectedAlert
                  ? `${selectedAlert.evidence.nodes.length}N · ${selectedAlert.evidence.edges.length}E`
                  : 'Awaiting Selection'}
              </span>
            </button>

            <span className="tab-connector" aria-hidden="true">→</span>

            <button
              type="button"
              id="tab-section-review"
              data-testid="tab-section-review"
              className={`workflow-tab ${activeSection === 'review' ? 'active' : ''} ${!selectedAlert ? 'no-selection' : ''}`}
              onClick={() => setActiveSection('review')}
              aria-current={activeSection === 'review' ? 'page' : undefined}
            >
              <span className="tab-number font-mono">3</span>
              <span className="tab-title">Alert Inspector & Review</span>
              {selectedAlert && (
                <span className={`status-pill-mini status-${selectedAlert.status.toLowerCase()}`}>
                  {selectedAlert.status}
                </span>
              )}
            </button>
          </div>
        </div>

        {/* Persistent Selected Alert Context Banner */}
        {selectedAlert && (
          <div className="active-target-context-bar" role="region" aria-label="Active Investigation Context">
            <div className="target-info-group">
              <span className="target-label font-mono">ACTIVE ALERT (UNDER REVIEW):</span>
              <span className="target-account font-mono">{selectedAlert.account_id}</span>
              <span className="target-id font-mono">({selectedAlert.alert_id})</span>
              <span className="target-score font-mono">
                Risk Score: <strong>{selectedAlert.ml.score.toFixed(4)}</strong>
              </span>
              <span className={`priority-pill priority-${selectedAlert.priority.toLowerCase()}`}>
                {selectedAlert.priority}
              </span>
              <span className={`status-pill-badge status-${selectedAlert.status.toLowerCase()}`}>
                {selectedAlert.status}
              </span>
              {selectedAlert.review.is_stale && (
                <span className="stale-warning-badge font-mono">STALE</span>
              )}
            </div>

            <div className="target-nav-actions">
              {activeSection === 'queue' && (
                <>
                  <button
                    type="button"
                    className="btn-context-cta btn-accent"
                    onClick={() => setActiveSection('graph')}
                  >
                    Investigate Graph →
                  </button>
                  <button
                    type="button"
                    className="btn-context-cta btn-secondary"
                    onClick={() => setActiveSection('review')}
                  >
                    Inspect & Review →
                  </button>
                </>
              )}

              {activeSection === 'graph' && (
                <>
                  <button
                    type="button"
                    className="btn-context-cta btn-secondary"
                    onClick={() => setActiveSection('queue')}
                  >
                    ← Back to Queue
                  </button>
                  <button
                    type="button"
                    className="btn-context-cta btn-accent"
                    onClick={() => setActiveSection('review')}
                  >
                    Proceed to Review →
                  </button>
                </>
              )}

              {activeSection === 'review' && (
                <>
                  <button
                    type="button"
                    className="btn-context-cta btn-secondary"
                    onClick={() => setActiveSection('graph')}
                  >
                    ← Back to Graph
                  </button>
                  <button
                    type="button"
                    className="btn-context-cta btn-secondary"
                    onClick={() => setActiveSection('queue')}
                  >
                    ← Back to Queue
                  </button>
                </>
              )}
            </div>
          </div>
        )}

        {/* Section A: Dedicated Full-Width Alert Queue */}
        {activeSection === 'queue' && (
          <div className="workbench-section-container" data-testid="section-queue-container">
            <InvestigationQueue
              alerts={alerts}
              selectedAlertId={selectedAlertId}
              onSelectAlert={handleSelectAlert}
              onInvestigateAlert={handleInvestigateAlert}
              statusFilter={statusFilter}
              onStatusFilterChange={setStatusFilter}
              budgetFilter={budgetFilter}
              onBudgetFilterChange={setBudgetFilter}
              searchQuery={searchQuery}
              onSearchQueryChange={setSearchQuery}
              isLoading={isAlertsLoading}
            />
          </div>
        )}

        {/* Section B: Dedicated Full-Width Evidence Graph Investigation */}
        {activeSection === 'graph' && (
          <div className="workbench-section-container" data-testid="section-graph-container">
            <section className="workbench-full-card graph-full-card" aria-labelledby="col-graph-title">
              <div className="card-top-header">
                <div className="header-left">
                  <h2 id="col-graph-title" className="section-heading">
                    <svg
                      viewBox="0 0 24 24"
                      width="20"
                      height="20"
                      fill="none"
                      stroke="#06B6D4"
                      strokeWidth="2"
                      aria-hidden="true"
                    >
                      <circle cx="18" cy="5" r="3" />
                      <circle cx="6" cy="12" r="3" />
                      <circle cx="18" cy="19" r="3" />
                      <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
                      <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
                    </svg>
                    2. Evidence Graph Investigation
                  </h2>
                  <span className="badge-dim font-mono">
                    {selectedAlert
                      ? `${selectedAlert.account_id} (${selectedAlert.alert_id}) · ${selectedAlert.evidence.nodes.length} Nodes · ${selectedAlert.evidence.edges.length} Edges`
                      : 'No alert selected'}
                  </span>
                </div>

                <div className="header-actions">
                  <button
                    type="button"
                    className="btn-secondary font-mono"
                    onClick={() => setActiveSection('queue')}
                  >
                    ← Back to Queue
                  </button>
                  {selectedAlert && (
                    <button
                      type="button"
                      className="btn-primary font-mono"
                      onClick={() => setActiveSection('review')}
                    >
                      Proceed to Review →
                    </button>
                  )}
                </div>
              </div>

              <div className="graph-guideline-box mini">
                <h3 className="guideline-title sr-only">Core Visualization Design Standard</h3>
                <span className="guideline-badge font-mono">Standard</span>
                <span className="guideline-text">
                  Core Visualization Design Standard: Compact overview; click node/edge to inspect; glowing evidence path; accessible tabular fallback. Hard capped at 25 nodes / 60 edges.
                </span>
              </div>

              {selectedAlert ? (
                <div className="graph-spacious-body">
                  <EvidenceGraphCanvas
                    evidence={selectedAlert.evidence}
                    targetAccountId={selectedAlert.account_id}
                  />
                </div>
              ) : (
                <div className="empty-section-prompt">
                  <div className="empty-prompt-box">
                    <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="#6B7280" strokeWidth="1.5">
                      <circle cx="18" cy="5" r="3" />
                      <circle cx="6" cy="12" r="3" />
                      <circle cx="18" cy="19" r="3" />
                      <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
                      <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
                    </svg>
                    <h3 className="empty-prompt-title">No Alert Selected for Evidence Graph</h3>
                    <p className="empty-prompt-desc">
                      Select an alert from the Alert Queue to examine its 2-hop evidence subgraph, inspect connected
                      mule ring accounts, shared devices, and transfer trails.
                    </p>
                    <button
                      type="button"
                      className="btn-primary"
                      onClick={() => setActiveSection('queue')}
                    >
                      Go to Alert Queue →
                    </button>
                  </div>
                </div>
              )}
            </section>
          </div>
        )}

        {/* Section C: Dedicated Full-Width Alert Inspector & Review */}
        {activeSection === 'review' && (
          <div className="workbench-section-container" data-testid="section-review-container">
            <section className="workbench-full-card review-full-card" aria-labelledby="col-studio-title">
              <div className="card-top-header">
                <div className="header-left">
                  <h2 id="col-studio-title" className="section-heading">
                    <svg
                      viewBox="0 0 24 24"
                      width="20"
                      height="20"
                      fill="none"
                      stroke="#8B5CF6"
                      strokeWidth="2"
                      aria-hidden="true"
                    >
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                      <line x1="16" y1="13" x2="8" y2="13" />
                      <line x1="16" y1="17" x2="8" y2="17" />
                      <polyline points="10 9 9 9 8 9" />
                    </svg>
                    3. Alert Inspector & Review
                  </h2>
                  <span className="badge-dim font-mono">
                    {selectedAlertId ? `${selectedAlertId} Analysis` : 'No Selection'}
                  </span>
                </div>

                <div className="header-actions">
                  <button
                    type="button"
                    className="btn-secondary font-mono"
                    onClick={() => setActiveSection('graph')}
                  >
                    ← Back to Graph
                  </button>
                  <button
                    type="button"
                    className="btn-secondary font-mono"
                    onClick={() => setActiveSection('queue')}
                  >
                    ← Back to Queue
                  </button>
                </div>
              </div>

              <div className="inspector-spacious-body">
                <AlertDetailInspector
                  alert={selectedAlert}
                  isLoading={isDetailLoading}
                  error={detailError}
                  onReviewUpdated={handleReviewUpdated}
                  onReturnToQueue={() => setActiveSection('queue')}
                  onRetry={() => {
                    if (selectedAlertId) {
                      setIsDetailLoading(true)
                      setDetailError(null)
                      apiClient
                        .getAlert(selectedAlertId)
                        .then((data) => setSelectedAlert(data))
                        .catch((e) => setDetailError(e.message))
                        .finally(() => setIsDetailLoading(false))
                    }
                  }}
                />
              </div>
            </section>
          </div>
        )}
      </main>
    </div>
  )
}
