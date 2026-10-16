import React from 'react'

interface DashboardPlaceholderProps {
  onBackToOverview: () => void
}

export const DashboardPlaceholder: React.FC<DashboardPlaceholderProps> = ({ onBackToOverview }) => {
  return (
    <div className="dashboard-placeholder" role="region" aria-label="Investigation Dashboard Console">
      {/* Console Top Bar */}
      <div className="console-header">
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
          <span className="console-divider" aria-hidden="true">/</span>
          <h1 className="console-title">Investigation Workbench</h1>
          <span className="badge-milestone">Milestone 1 Checkpoint</span>
        </div>

        <div className="console-actions">
          <div className="status-pill">
            <span className="status-indicator online" aria-hidden="true" />
            <span className="status-text font-mono">Backend Port 8000 Ready</span>
          </div>
        </div>
      </div>

      {/* Scaffold Overview Card */}
      <div className="console-container">
        <div className="milestone-notice-banner">
          <div className="notice-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#F59E0B" strokeWidth="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </div>
          <div className="notice-content">
            <h2 className="notice-title">Milestone 1 Completed: Scaffolding, Design Tokens & Foundation</h2>
            <p className="notice-text">
              The application foundation, color tokens, typography, and responsive shells are initialized.
              The three workbench columns below represent the investigation workspace scheduled for Milestone 2+ integration.
            </p>
          </div>
        </div>

        {/* 3-Column Workbench Blueprint */}
        <div className="workbench-grid">
          {/* Column 1: Alert Queue Blueprint */}
          <section className="workbench-column" aria-labelledby="col-queue-title">
            <div className="col-header">
              <h3 id="col-queue-title" className="col-title">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#F59E0B" strokeWidth="2" aria-hidden="true">
                  <line x1="8" y1="6" x2="21" y2="6" />
                  <line x1="8" y1="12" x2="21" y2="12" />
                  <line x1="8" y1="18" x2="21" y2="18" />
                  <line x1="3" y1="6" x2="3.01" y2="6" strokeWidth="3" />
                  <line x1="3" y1="12" x2="3.01" y2="12" strokeWidth="3" />
                  <line x1="3" y1="18" x2="3.01" y2="18" strokeWidth="3" />
                </svg>
                1. Prioritized Alert Queue
              </h3>
              <span className="badge-dim font-mono">GET /api/alerts</span>
            </div>
            <div className="col-body placeholder-box">
              <p className="placeholder-desc">
                Ranks accounts by risk score descending with deterministic account ID tie-breaking.
              </p>
              <ul className="spec-list">
                <li>• Capacity budget filters: <code>K ∈ &#123;10, 20, 50&#125;</code></li>
                <li>• Status filters: <code>OPEN</code>, <code>INVESTIGATING</code>, <code>CONFIRMED_FRAUD</code></li>
                <li>• Multi-tier baseline heuristic comparison</li>
              </ul>
              <div className="mock-card">
                <span className="badge-high">HIGH · 0.9630</span>
                <span className="font-mono text-strong">ACC_0101</span>
                <span className="text-dim">Mule Ring · 20 txns</span>
              </div>
            </div>
          </section>

          {/* Column 2: Evidence Graph Blueprint */}
          <section className="workbench-column" aria-labelledby="col-graph-title">
            <div className="col-header">
              <h3 id="col-graph-title" className="col-title">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#06B6D4" strokeWidth="2" aria-hidden="true">
                  <circle cx="18" cy="5" r="3" />
                  <circle cx="6" cy="12" r="3" />
                  <circle cx="18" cy="19" r="3" />
                  <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
                  <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
                </svg>
                2. Interactive Evidence Graph Canvas
              </h3>
              <span className="badge-dim font-mono">GET /api/alerts/&#123;id&#125;</span>
            </div>
            <div className="col-body placeholder-box">
              <div className="graph-guideline-box">
                <h4 className="guideline-title">Core Visualization Design Standard</h4>
                <p className="guideline-text">
                  The graph communicates relationships at a glance without appearing overcrowded.
                  Shows a compact, relevant overview rather than every possible detail. Clicking a node
                  reveals its inspector details; clicking an edge reveals transfer details. Highlights the
                  contiguous evidence path with an accessible tabular fallback. Hard capped at 25 nodes and 60 edges.
                </p>
              </div>

              <div className="mock-graph-preview font-mono" aria-hidden="true">
                <div className="mock-node node-acc">ACC_0101 (Target)</div>
                <div className="mock-edge">&darr; Rs 48,500 (E1)</div>
                <div className="mock-node node-dev">DEV_0001 (Shared)</div>
                <div className="mock-edge">&darr; Layering</div>
                <div className="mock-node node-mer">MER_0002 (Cash-out)</div>
              </div>
            </div>
          </section>

          {/* Column 3: Review & Counterfactual Studio Blueprint */}
          <section className="workbench-column" aria-labelledby="col-studio-title">
            <div className="col-header">
              <h3 id="col-studio-title" className="col-title">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#8B5CF6" strokeWidth="2" aria-hidden="true">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <polyline points="10 9 9 9 8 9" />
                </svg>
                3. Review & Counterfactual Studio
              </h3>
              <span className="badge-dim font-mono">PATCH / POST</span>
            </div>
            <div className="col-body placeholder-box">
              <p className="placeholder-desc">
                Human-in-the-loop review workflow and hypothesis perturbation sandbox.
              </p>
              <ul className="spec-list">
                <li>• FSM Review: <code>OPEN &rarr; INVESTIGATING &rarr; CONFIRMED</code></li>
                <li>• SHA-256 fingerprint staleness detection</li>
                <li>• Transfer-edge perturbation (&Delta; score display)</li>
                <li>• Plausible benign alternative generation</li>
              </ul>
              <div className="mock-cf-preview font-mono">
                <div>Original Score: <span className="text-strong">0.9630</span></div>
                <div>Counterfactual: <span className="text-emerald">0.1200</span></div>
                <div>Score Delta: <span className="text-emerald">-0.8430</span></div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
