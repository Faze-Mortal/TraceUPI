import React, { useState, useEffect, useRef } from 'react'

interface NavbarProps {
  currentView: 'landing' | 'dashboard'
  onNavigate: (view: 'landing' | 'dashboard') => void
}

export const Navbar: React.FC<NavbarProps> = ({ currentView, onNavigate }) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const toggleButtonRef = useRef<HTMLButtonElement>(null)

  // Close mobile menu whenever view changes
  useEffect(() => {
    setIsMobileMenuOpen(false)
  }, [currentView])

  // Handle keyboard operation: close on Escape and restore focus to toggle button
  useEffect(() => {
    if (!isMobileMenuOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsMobileMenuOpen(false)
        toggleButtonRef.current?.focus()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isMobileMenuOpen])

  const handleLinkClick = () => {
    setIsMobileMenuOpen(false)
  }

  const handleLaunchDashboard = () => {
    setIsMobileMenuOpen(false)
    onNavigate('dashboard')
  }

  return (
    <header className="navbar">
      <div className="navbar-container">
        <button
          type="button"
          className="brand-logo"
          onClick={() => {
            setIsMobileMenuOpen(false)
            onNavigate('landing')
          }}
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
            <circle cx="12" cy="12" r="10" stroke="var(--brand-terracotta, #A56F58)" />
            <path d="M12 2a10 10 0 0 1 10 10" stroke="var(--brand-terracotta, #A56F58)" />
            <path d="M12 6a6 6 0 0 1 6 6" stroke="var(--brand-terracotta-hover, #B78066)" />
            <circle cx="12" cy="12" r="2" fill="var(--brand-terracotta, #A56F58)" />
            <line x1="12" y1="12" x2="19" y2="5" stroke="var(--brand-terracotta, #A56F58)" />
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

              <button
                type="button"
                className="btn-nav-toggle"
                data-testid="btn-nav-toggle"
                id="btn-nav-toggle"
                onClick={() => setIsMobileMenuOpen((open) => !open)}
                aria-expanded={isMobileMenuOpen}
                aria-controls="mobile-nav-menu"
                aria-label={isMobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
                ref={toggleButtonRef}
              >
                {isMobileMenuOpen ? (
                  <svg
                    viewBox="0 0 24 24"
                    width="20"
                    height="20"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                ) : (
                  <svg
                    viewBox="0 0 24 24"
                    width="20"
                    height="20"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <line x1="3" y1="12" x2="21" y2="12" />
                    <line x1="3" y1="6" x2="21" y2="6" />
                    <line x1="3" y1="18" x2="21" y2="18" />
                  </svg>
                )}
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

      {/* Accessible Collapsible Mobile Navigation Menu */}
      {currentView === 'landing' && isMobileMenuOpen && (
        <nav
          id="mobile-nav-menu"
          data-testid="mobile-nav-menu"
          className="mobile-nav-menu"
          aria-label="Mobile Navigation Menu"
        >
          <div className="mobile-nav-links">
            <a
              href="#problem"
              className="mobile-nav-link"
              onClick={handleLinkClick}
            >
              The Problem
            </a>
            <a
              href="#how-it-works"
              className="mobile-nav-link"
              onClick={handleLinkClick}
            >
              Architecture
            </a>
            <a
              href="#capabilities"
              className="mobile-nav-link"
              onClick={handleLinkClick}
            >
              Capabilities
            </a>
            <a
              href="#limitations"
              className="mobile-nav-link"
              onClick={handleLinkClick}
            >
              Limitations
            </a>
            <button
              type="button"
              className="btn-primary mobile-btn-dashboard"
              onClick={handleLaunchDashboard}
              id="btn-mobile-nav-dashboard"
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
          </div>
        </nav>
      )}
    </header>
  )
}

