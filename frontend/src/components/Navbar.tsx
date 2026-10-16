import React from 'react'

interface NavbarProps {
  currentView: 'landing' | 'dashboard'
  onNavigate: (view: 'landing' | 'dashboard') => void
}

export const Navbar: React.FC<NavbarProps> = ({ currentView, onNavigate }) => {
  return (
    <header className="navbar">
      <div className="navbar-container">
        <button
          type="button"
          className="brand-logo"
          onClick={() => onNavigate('landing')}
          aria-label="TraceUPI Home"
        >
          <svg
            className="brand-icon"
            viewBox="0 0 24 24"
            width="28"
            height="28"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="10" stroke="#F59E0B" />
            <path d="M12 2a10 10 0 0 1 10 10" stroke="#F59E0B" />
            <path d="M12 6a6 6 0 0 1 6 6" stroke="#FBBF24" />
            <circle cx="12" cy="12" r="2" fill="#F59E0B" />
            <line x1="12" y1="12" x2="19" y2="5" stroke="#F59E0B" />
          </svg>
          <span className="brand-name">
            Trace<span className="brand-accent">UPI</span>
          </span>
          <span className="badge-prototype" aria-label="Version: Prototype">
            MVP Prototype
          </span>
        </button>

        <nav className="nav-links" aria-label="Main Navigation">
          {currentView === 'landing' ? (
            <>
              <a href="#problem" className="nav-link">
                The Problem
              </a>
              <a href="#how-it-works" className="nav-link">
                Architecture
              </a>
              <a href="#capabilities" className="nav-link">
                Capabilities
              </a>
              <a href="#limitations" className="nav-link">
                Limitations
              </a>
              <button
                type="button"
                className="btn-primary"
                onClick={() => onNavigate('dashboard')}
                id="btn-nav-dashboard"
              >
                Launch Dashboard
                <svg
                  viewBox="0 0 24 24"
                  width="16"
                  height="16"
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
            </>
          ) : (
            <button
              type="button"
              className="btn-secondary"
              onClick={() => onNavigate('landing')}
              id="btn-back-overview"
            >
              <svg
                viewBox="0 0 24 24"
                width="16"
                height="16"
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
              Back to Overview
            </button>
          )}
        </nav>
      </div>
    </header>
  )
}
