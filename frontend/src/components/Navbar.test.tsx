import { render, screen, fireEvent, within } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { Navbar } from './Navbar'

describe('Navbar Component & Mobile Navigation (Milestone 2.2)', () => {
  it('renders brand logo and desktop navigation on landing view', () => {
    const handleNavigate = vi.fn()
    render(<Navbar currentView="landing" onNavigate={handleNavigate} />)

    expect(screen.getByRole('button', { name: /TraceUPI Home/i })).toBeInTheDocument()
    expect(screen.getByText(/MVP Prototype/i)).toBeInTheDocument()

    // Desktop nav links present
    expect(screen.getByRole('link', { name: /^The Problem$/i })).toHaveAttribute('href', '#problem')
    expect(screen.getByRole('link', { name: /^Architecture$/i })).toHaveAttribute('href', '#how-it-works')
    expect(screen.getByRole('link', { name: /^Capabilities$/i })).toHaveAttribute('href', '#capabilities')
    expect(screen.getByRole('link', { name: /^Limitations$/i })).toHaveAttribute('href', '#limitations')
    expect(screen.getByRole('button', { name: /Launch Dashboard/i })).toBeInTheDocument()
  })

  it('renders mobile menu toggle button with correct accessible attributes', () => {
    const handleNavigate = vi.fn()
    render(<Navbar currentView="landing" onNavigate={handleNavigate} />)

    const toggleBtn = screen.getByTestId('btn-nav-toggle')
    expect(toggleBtn).toBeInTheDocument()
    expect(toggleBtn).toHaveAttribute('aria-expanded', 'false')
    expect(toggleBtn).toHaveAttribute('aria-controls', 'mobile-nav-menu')
    expect(toggleBtn).toHaveAttribute('aria-label', 'Open navigation menu')

    // Mobile nav menu should not be rendered initially
    expect(screen.queryByTestId('mobile-nav-menu')).not.toBeInTheDocument()
  })

  it('toggles mobile menu on click and exposes all 4 anchor links plus CTA', () => {
    const handleNavigate = vi.fn()
    render(<Navbar currentView="landing" onNavigate={handleNavigate} />)

    const toggleBtn = screen.getByTestId('btn-nav-toggle')

    // Click to open
    fireEvent.click(toggleBtn)
    expect(toggleBtn).toHaveAttribute('aria-expanded', 'true')
    expect(toggleBtn).toHaveAttribute('aria-label', 'Close navigation menu')

    const mobileMenu = screen.getByTestId('mobile-nav-menu')
    expect(mobileMenu).toBeInTheDocument()
    expect(mobileMenu).toHaveAttribute('aria-label', 'Mobile Navigation Menu')

    // Verify all 4 anchor links exist inside the mobile navigation menu
    const problemLink = within(mobileMenu).getByRole('link', { name: /^The Problem$/i })
    expect(problemLink).toBeInTheDocument()
    expect(problemLink).toHaveAttribute('href', '#problem')

    const archLink = within(mobileMenu).getByRole('link', { name: /^Architecture$/i })
    expect(archLink).toBeInTheDocument()
    expect(archLink).toHaveAttribute('href', '#how-it-works')

    const capLink = within(mobileMenu).getByRole('link', { name: /^Capabilities$/i })
    expect(capLink).toBeInTheDocument()
    expect(capLink).toHaveAttribute('href', '#capabilities')

    const limitLink = within(mobileMenu).getByRole('link', { name: /^Limitations$/i })
    expect(limitLink).toBeInTheDocument()
    expect(limitLink).toHaveAttribute('href', '#limitations')

    // Verify mobile CTA exists
    const mobileCta = within(mobileMenu).getByRole('button', { name: /Launch Dashboard/i })
    expect(mobileCta).toBeInTheDocument()

    // Click to close
    fireEvent.click(toggleBtn)
    expect(toggleBtn).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByTestId('mobile-nav-menu')).not.toBeInTheDocument()
  })

  it('closes mobile menu when a navigation anchor link is selected', () => {
    const handleNavigate = vi.fn()
    render(<Navbar currentView="landing" onNavigate={handleNavigate} />)

    const toggleBtn = screen.getByTestId('btn-nav-toggle')
    fireEvent.click(toggleBtn)
    const mobileMenu = screen.getByTestId('mobile-nav-menu')
    expect(mobileMenu).toBeInTheDocument()

    const problemLink = within(mobileMenu).getByRole('link', { name: /^The Problem$/i })
    fireEvent.click(problemLink)

    // Menu should close
    expect(screen.queryByTestId('mobile-nav-menu')).not.toBeInTheDocument()
    expect(toggleBtn).toHaveAttribute('aria-expanded', 'false')
  })

  it('closes mobile menu on Escape key press and restores focus to toggle button', () => {
    const handleNavigate = vi.fn()
    render(<Navbar currentView="landing" onNavigate={handleNavigate} />)

    const toggleBtn = screen.getByTestId('btn-nav-toggle')
    fireEvent.click(toggleBtn)
    expect(screen.getByTestId('mobile-nav-menu')).toBeInTheDocument()

    // Press Escape
    fireEvent.keyDown(window, { key: 'Escape' })

    expect(screen.queryByTestId('mobile-nav-menu')).not.toBeInTheDocument()
    expect(toggleBtn).toHaveAttribute('aria-expanded', 'false')
    expect(document.activeElement).toBe(toggleBtn)
  })

  it('navigates to dashboard from mobile CTA and closes menu', () => {
    const handleNavigate = vi.fn()
    render(<Navbar currentView="landing" onNavigate={handleNavigate} />)

    const toggleBtn = screen.getByTestId('btn-nav-toggle')
    fireEvent.click(toggleBtn)

    const mobileMenu = screen.getByTestId('mobile-nav-menu')
    const mobileCta = within(mobileMenu).getByRole('button', { name: /Launch Dashboard/i })
    fireEvent.click(mobileCta)

    expect(handleNavigate).toHaveBeenCalledWith('dashboard')
    expect(screen.queryByTestId('mobile-nav-menu')).not.toBeInTheDocument()
  })

  it('closes menu and navigates to landing when brand logo is clicked', () => {
    const handleNavigate = vi.fn()
    render(<Navbar currentView="landing" onNavigate={handleNavigate} />)

    const toggleBtn = screen.getByTestId('btn-nav-toggle')
    fireEvent.click(toggleBtn)
    expect(screen.getByTestId('mobile-nav-menu')).toBeInTheDocument()

    const brandBtn = screen.getByRole('button', { name: /TraceUPI Home/i })
    fireEvent.click(brandBtn)

    expect(handleNavigate).toHaveBeenCalledWith('landing')
    expect(screen.queryByTestId('mobile-nav-menu')).not.toBeInTheDocument()
  })

  it('renders Back to Overview in dashboard view and does not render mobile toggle', () => {
    const handleNavigate = vi.fn()
    render(<Navbar currentView="dashboard" onNavigate={handleNavigate} />)

    const backBtn = screen.getByRole('button', { name: /Back to Overview/i })
    expect(backBtn).toBeInTheDocument()
    expect(screen.queryByTestId('btn-nav-toggle')).not.toBeInTheDocument()

    fireEvent.click(backBtn)
    expect(handleNavigate).toHaveBeenCalledWith('landing')
  })
})
