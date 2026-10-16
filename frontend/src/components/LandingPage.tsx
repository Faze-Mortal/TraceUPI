import React from 'react'

interface LandingPageProps {
  onOpenDashboard: () => void
}

export const LandingPage: React.FC<LandingPageProps> = ({ onOpenDashboard }) => {
  return (
    <main className="landing-page">
      {/* 1. Hero Section */}
      <section className="hero-section" aria-labelledby="hero-heading">
        <div className="hero-content">
          <div className="hero-tag">
            <span className="pulse-dot" aria-hidden="true" />
            <span>Explainable Syndicate Intelligence</span>
          </div>

          <h1 id="hero-heading" className="hero-title">
            Follow the money. <br />
            <span className="hero-gradient">Reveal the network.</span>
          </h1>

          <p className="hero-subtitle">
            TraceUPI is an investigative prototype designed for digital payment compliance
            and fraud analysts. By mapping multi-hop entity graphs, detecting temporal pass-through motifs,
            and evaluating counterfactual hypotheses, it uncovers organized UPI mule syndicates that
            single-transaction rules miss.
          </p>

          <div className="hero-actions">
            <button
              type="button"
              className="btn-primary-lg"
              onClick={onOpenDashboard}
              id="btn-hero-dashboard"
            >
              Open Investigation Dashboard
              <svg
                viewBox="0 0 24 24"
                width="20"
                height="20"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <line x1="5" y1="12" x2="19" y2="12" />
                <polyline points="12 5 19 12 12 19" />
              </svg>
            </button>

            <a href="#how-it-works" className="btn-secondary-lg">
              Explore Pipeline
            </a>
          </div>

          <div className="hero-metrics-pill" role="group" aria-label="Key Architectural Tenets">
            <div className="metric-item">
              <span className="metric-label">Graph Evidence</span>
              <span className="metric-value">Bounded Walks</span>
            </div>
            <div className="metric-divider" aria-hidden="true" />
            <div className="metric-item">
              <span className="metric-label">Capacity Prioritization</span>
              <span className="metric-value">Top-K Budget</span>
            </div>
            <div className="metric-divider" aria-hidden="true" />
            <div className="metric-item">
              <span className="metric-label">What-If Reasoning</span>
              <span className="metric-value">Counterfactuals</span>
            </div>
          </div>
        </div>
      </section>

      {/* 2. The Problem Section */}
      <section id="problem" className="section-container" aria-labelledby="problem-heading">
        <div className="section-header">
          <span className="section-badge">Structural Vulnerabilities</span>
          <h2 id="problem-heading" className="section-title">
            The Problem: Why Single-Transaction Scoring Fails
          </h2>
          <p className="section-description">
            Unified Payments Interface (UPI) processes billions of instant peer-to-peer transfers.
            Organized fraud syndicates exploit this speed by engineering layered laundering chains
            that defeat isolated point-in-time threshold checks.
          </p>
        </div>

        <div className="cards-grid-3">
          <article className="card">
            <div className="card-icon-wrapper" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="var(--color-warning, #D4A15A)" strokeWidth="2">
                <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
                <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
              </svg>
            </div>
            <h3 className="card-title">Mule Account Layering</h3>
            <p className="card-body">
              Stolen or phishing proceeds are split across multiple intermediary accounts within minutes.
              Each individual transfer appears modest, evading isolated high-value alerts while the syndicate
              consolidates total funds.
            </p>
          </article>

          <article className="card">
            <div className="card-icon-wrapper" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="var(--color-high-risk, #C65B4A)" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
            </div>
            <h3 className="card-title">Temporal Velocity Motifs</h3>
            <p className="card-body">
              Dormant accounts suddenly reactivate with rapid bursts of inflows followed immediately by
              outflows to merchant cash-out points. Rules that lack temporal lookbacks fail to correlate
              inflows with their rapid evacuation.
            </p>
          </article>

          <article className="card">
            <div className="card-icon-wrapper" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="var(--brand-terracotta, #A56F58)" strokeWidth="2">
                <rect x="5" y="2" width="14" height="20" rx="2" ry="2" />
                <line x1="12" y1="18" x2="12.01" y2="18" strokeWidth="3" />
              </svg>
            </div>
            <h3 className="card-title">Shared Infrastructure</h3>
            <p className="card-body">
              Syndicate operators rotate hundreds of Virtual Payment Addresses (VPAs) across emulator farms
              and physical devices. Without device-to-account link analysis, disparate accounts cannot be
              correlated to a shared coordinator.
            </p>
          </article>
        </div>
      </section>

      {/* 3. How It Works Section */}
      <section id="how-it-works" className="section-container" aria-labelledby="pipeline-heading">
        <div className="section-header">
          <span className="section-badge">Methodology</span>
          <h2 id="pipeline-heading" className="section-title">
            How TraceUPI Works: From Ingestion to Explainable Alert
          </h2>
          <p className="section-description">
            A deterministic four-stage pipeline processes transaction telemetry without data leakage,
            generating accountable risk rankings with traceable graph evidence.
          </p>
        </div>

        <div className="pipeline-steps">
          <div className="step-card">
            <div className="step-number">01</div>
            <h3 className="step-title">Temporal Cutoff Replay</h3>
            <p className="step-desc">
              Transactions and complaints are ingested strictly up to point-in-time <code>T_as_of</code>.
              Events arriving after the cutoff are isolated to ensure exact historical auditability and reproducible replays.
            </p>
          </div>

          <div className="step-card">
            <div className="step-number">02</div>
            <h3 className="step-title">Graph Entity Linkage</h3>
            <p className="step-desc">
              Constructs multi-relational graphs of accounts, physical devices, merchants, and complaints.
              Financial flows aggregate transfer edges only, keeping non-financial associations strictly unweighted.
            </p>
          </div>

          <div className="step-card">
            <div className="step-number">03</div>
            <h3 className="step-title">Structural Feature Extraction</h3>
            <p className="step-desc">
              Computes 25 structural signals including fan ratios, net flows, rapid pass-through velocity (Rs. 45k+ dispersed &le; 2h),
              and device-sharing markers. An ensemble model outputs uncalibrated ranking scores.
            </p>
          </div>

          <div className="step-card">
            <div className="step-number">04</div>
            <h3 className="step-title">Bounded Evidence Paths</h3>
            <p className="step-desc">
              Surfaces continuous, contiguous walks linking suspect accounts to counterparty nodes (capped at 10 edges,
              25 nodes). No disconnected fictitious paths are ever fabricated.
            </p>
          </div>
        </div>
      </section>

      {/* 4. Core Capabilities Section */}
      <section id="capabilities" className="section-container" aria-labelledby="capabilities-heading">
        <div className="section-header">
          <span className="section-badge">Platform Capabilities</span>
          <h2 id="capabilities-heading" className="section-title">
            Core Investigative Capabilities
          </h2>
          <p className="section-description">
            Equipping financial crime analysts with the tools needed to prioritize, inspect, verify,
            and test hypotheses.
          </p>
        </div>

        <div className="capabilities-grid">
          <div className="capability-box">
            <div className="capability-header">
              <span className="capability-tag amber">Network Visualizer</span>
              <h3 className="capability-title">Graph-Based Investigation</h3>
            </div>
            <p className="capability-body">
              Inspect multi-hop money flow directly on an interactive canvas. Trace fund dispersal from victim accounts
              through intermediary mules to final merchant cash-out points with directional timestamps and transaction amounts.
            </p>
            <div className="capability-footer font-mono">Max 25 nodes · 60 edges · Tabular fallback</div>
          </div>

          <div className="capability-box">
            <div className="capability-header">
              <span className="capability-tag cyan">Analyst Capacity</span>
              <h3 className="capability-title">Top-K Budget Prioritization</h3>
            </div>
            <p className="capability-body">
              Human review time is scarce. TraceUPI ranks accounts by model score with deterministic account-ID tie-breaking,
              allowing compliance teams to focus on the top 10, 20, or 50 highest-yield accounts without altering baseline rule execution.
            </p>
            <div className="capability-footer font-mono">Budgets: K ∈ &#123;10, 20, 50&#125; · Default K=20</div>
          </div>

          <div className="capability-box">
            <div className="capability-header">
              <span className="capability-tag violet">Auditability</span>
              <h3 className="capability-title">Human-in-the-Loop Review</h3>
            </div>
            <p className="capability-body">
              Record formal analyst verdicts (<code>OPEN</code> &rarr; <code>INVESTIGATING</code> &rarr; <code>CONFIRMED_FRAUD</code> / <code>DISMISSED_BENIGN</code>).
              Topology-aware SHA-256 fingerprinting flags stale reviews if underlying evidence shifts across historical replays.
            </p>
            <div className="capability-footer font-mono">Finite State Machine · Staleness Attribution</div>
          </div>

          <div className="capability-box">
            <div className="capability-header">
              <span className="capability-tag emerald">Explainability</span>
              <h3 className="capability-title">Counterfactual What-If Studio</h3>
            </div>
            <p className="capability-body">
              Test alternative hypotheses in a clean sandbox. Remove specific transfer edges, suppress device-sharing links, or
              mute complaints to observe signed score deltas (&Delta;) and inspect plausible benign alternative explanations.
            </p>
            <div className="capability-footer font-mono">Immutable Recomputation · Signed Score Delta</div>
          </div>
        </div>
      </section>

      {/* 5. Limitations & Synthetic Data Notice */}
      <section id="limitations" className="section-container" aria-labelledby="limitations-heading">
        <div className="callout-card" role="region" aria-labelledby="limitations-heading">
          <div className="callout-badge-wrapper">
            <span className="badge-warning">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              Mandatory Project Notice
            </span>
          </div>

          <h2 id="limitations-heading" className="callout-title">
            Synthetic Data Benchmark & System Limitations
          </h2>

          <div className="callout-grid">
            <div className="callout-item">
              <h3 className="callout-subtitle">100% Synthetic Telemetry</h3>
              <p className="callout-text">
                All transaction identifiers (e.g. <code>T000123</code>), Virtual Payment Addresses, account IDs (<code>ACC_0101</code>),
                device IDs, and merchant records used in this prototype are entirely synthetic. They do not represent real-world
                banking customers, identifiable citizens, or active UPI transactions.
              </p>
            </div>

            <div className="callout-item">
              <h3 className="callout-subtitle">Offline Research Prototype</h3>
              <p className="callout-text">
                TraceUPI is designed for technical hackathon demonstration and academic evaluation. It is not connected to live NPCI or
                banking payment switches, does not execute automated fund blocking, and does not provide real-time stream processing.
              </p>
            </div>

            <div className="callout-item">
              <h3 className="callout-subtitle">Uncalibrated Ranking Scores</h3>
              <p className="callout-text">
                Model risk scores (0.0000 to 1.0000) are uncalibrated ordering signals for investigative triage. They do not represent
                calibrated statistical probabilities of guilt or legal proof of conspiratorial intent.
              </p>
            </div>

            <div className="callout-item">
              <h3 className="callout-subtitle">Fairness Objective</h3>
              <p className="callout-text">
                Empirical fairness metrics specifically evaluate False Positive Rates on benign shared-device households
                (family members sharing a single phone). Benchmark targets (&le; 0.05) are empirical measurements over synthetic cohorts.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* 6. Call To Action Footer Banner */}
      <section className="cta-banner" aria-labelledby="cta-heading">
        <h2 id="cta-heading" className="cta-title">
          Ready to inspect suspicious UPI clusters?
        </h2>
        <p className="cta-desc">
          Launch the investigation console to explore prioritized alerts, inspect multi-hop graph walks,
          and run counterfactual perturbations.
        </p>
        <button
          type="button"
          className="btn-primary-lg"
          onClick={onOpenDashboard}
          id="btn-footer-dashboard"
        >
          Open Investigation Dashboard
          <svg
            viewBox="0 0 24 24"
            width="20"
            height="20"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <line x1="5" y1="12" x2="19" y2="12" />
            <polyline points="12 5 19 12 12 19" />
          </svg>
        </button>
      </section>

      {/* Footer */}
      <footer className="footer">
        <div className="footer-content">
          <p className="footer-brand">
            <strong>TraceUPI</strong> — Explainable UPI Fraud-Ring Investigation MVP
          </p>
          <p className="footer-meta">
            Monorepo Architecture · React 19 + TypeScript + FastAPI · Interface Contract v1.2 Compliant
          </p>
        </div>
      </footer>
    </main>
  )
}
