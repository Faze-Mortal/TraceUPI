import { render, screen, fireEvent, within } from '@testing-library/react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import App from './App'

describe('TraceUPI Milestone 1: Landing Page & Navigation', () => {
  beforeEach(() => {
    window.scrollTo = vi.fn()
  })

  it('renders hero section with primary copy', () => {
    render(<App />)
    expect(
      screen.getByRole('heading', { name: /Follow the money\.\s*Reveal the network\./i })
    ).toBeInTheDocument()
    expect(
      screen.getByText(/TraceUPI is an investigative prototype designed for digital payment compliance/i)
    ).toBeInTheDocument()
  })

  it('renders the problem statement explaining multi-hop syndicates', () => {
    render(<App />)
    expect(
      screen.getByRole('heading', { name: /The Problem: Why Single-Transaction Scoring Fails/i })
    ).toBeInTheDocument()
    expect(screen.getByText(/Mule Account Layering/i)).toBeInTheDocument()
    expect(screen.getByText(/Temporal Velocity Motifs/i)).toBeInTheDocument()
    expect(screen.getByText(/Shared Infrastructure/i)).toBeInTheDocument()
  })

  it('renders how it works architecture pipeline', () => {
    render(<App />)
    expect(
      screen.getByRole('heading', { name: /How TraceUPI Works: From Ingestion to Explainable Alert/i })
    ).toBeInTheDocument()
    expect(screen.getByText(/Temporal Cutoff Replay/i)).toBeInTheDocument()
    expect(screen.getByText(/Graph Entity Linkage/i)).toBeInTheDocument()
    expect(screen.getByText(/Structural Feature Extraction/i)).toBeInTheDocument()
    expect(screen.getByText(/Bounded Evidence Paths/i)).toBeInTheDocument()
  })

  it('renders core capabilities', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: /Core Investigative Capabilities/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Graph-Based Investigation/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Top-K Budget Prioritization/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Human-in-the-Loop Review/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Counterfactual What-If Studio/i })).toBeInTheDocument()
  })

  it('clearly explains synthetic data and system limitations', () => {
    render(<App />)
    expect(
      screen.getByRole('heading', { name: /Synthetic Data Benchmark & System Limitations/i })
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /100% Synthetic Telemetry/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Offline Research Prototype/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Uncalibrated Ranking Scores/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Fairness Objective/i })).toBeInTheDocument()
  })

  it('navigates from landing page to dashboard placeholder and back', () => {
    render(<App />)

    // Initially on landing page
    expect(screen.getByRole('heading', { name: /Follow the money/i })).toBeInTheDocument()

    // Click primary hero CTA
    const heroBtn = screen.getAllByRole('button', { name: /Open Investigation Dashboard/i })[0]
    fireEvent.click(heroBtn)

    // Dashboard console is now visible
    expect(screen.getByRole('heading', { name: /Investigation Workbench/i })).toBeInTheDocument()
    expect(screen.getByText(/Milestone 4: Review Active/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Core Visualization Design Standard/i })).toBeInTheDocument()

    // Click Back to Overview
    const backBtn = screen.getByRole('button', { name: /Back to landing page overview/i })
    fireEvent.click(backBtn)

    // Landing page is restored
    expect(screen.getByRole('heading', { name: /Follow the money/i })).toBeInTheDocument()
  })

  it('renders a skip-to-main-content link targeting #main-content as the first landmark link', () => {
    const { container } = render(<App />)
    const skipLink = screen.getByRole('link', { name: /skip to main content/i })
    expect(skipLink).toBeInTheDocument()
    expect(skipLink).toHaveAttribute('href', '#main-content')
    expect(skipLink).toHaveClass('skip-link')

    // Confirm it is positioned before navbar in DOM order for immediate keyboard tab access
    const firstAnchor = container.querySelector('a')
    expect(firstAnchor).toBe(skipLink)
  })

  it('targets existing #main-content landmark on both landing and dashboard views', () => {
    const { container } = render(<App />)

    // Landing view: #main-content exists on landing page landmark
    const mainLanding = container.querySelector('#main-content')
    expect(mainLanding).toBeInTheDocument()
    expect(mainLanding?.tagName.toLowerCase()).toBe('main')
    expect(mainLanding).toHaveAttribute('tabIndex', '-1')

    // Navigate to dashboard
    const heroBtn = screen.getAllByRole('button', { name: /Open Investigation Dashboard/i })[0]
    fireEvent.click(heroBtn)

    // Dashboard view: #main-content exists on workbench console landmark
    const mainDashboard = container.querySelector('#main-content')
    expect(mainDashboard).toBeInTheDocument()
    expect(mainDashboard?.tagName.toLowerCase()).toBe('main')
    expect(mainDashboard).toHaveAttribute('tabIndex', '-1')
  })

  it('supports opening and navigating via mobile hamburger menu', () => {
    render(<App />)

    const toggleBtn = screen.getByTestId('btn-nav-toggle')
    expect(toggleBtn).toBeInTheDocument()
    expect(toggleBtn).toHaveAttribute('aria-expanded', 'false')

    // Open mobile menu
    fireEvent.click(toggleBtn)
    expect(toggleBtn).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByTestId('mobile-nav-menu')).toBeInTheDocument()

    // Click mobile dashboard button
    const mobileMenu = screen.getByTestId('mobile-nav-menu')
    const mobileLaunchBtn = within(mobileMenu).getByRole('button', { name: /Launch Dashboard/i })
    fireEvent.click(mobileLaunchBtn)

    // Should navigate to dashboard
    expect(screen.getByRole('heading', { name: /Investigation Workbench/i })).toBeInTheDocument()
    expect(screen.queryByTestId('mobile-nav-menu')).not.toBeInTheDocument()
  })

  it('closes mobile menu when an anchor link is clicked', () => {
    render(<App />)

    const toggleBtn = screen.getByTestId('btn-nav-toggle')
    fireEvent.click(toggleBtn)
    const mobileMenu = screen.getByTestId('mobile-nav-menu')
    expect(mobileMenu).toBeInTheDocument()

    const archLink = within(mobileMenu).getByRole('link', { name: /^Architecture$/i })
    fireEvent.click(archLink)

    expect(screen.queryByTestId('mobile-nav-menu')).not.toBeInTheDocument()
    expect(toggleBtn).toHaveAttribute('aria-expanded', 'false')
  })
})

