import { render, screen, fireEvent, within } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { InvestigationQueue } from './InvestigationQueue'
import type { AlertSummary } from '../types/api'

describe('InvestigationQueue Component', () => {
  const mockAlertHigh: AlertSummary = {
    alert_id: 'ALT_0001',
    alert_fingerprint: 'fp_high',
    account_id: 'ACC_0101',
    created_at: '2026-10-01T10:00:00Z',
    status: 'OPEN',
    priority: 'HIGH',
    ml: { score: 0.95, threshold: 0.65, flagged: true },
    baseline: {
      flagged: true,
      rules_triggered: ['RAPID_PASS_THROUGH', 'HIGH_FAN_IN'],
    },
    top_reasons: [{ feature: 'velocity', value: 12, typical_value: 1, explanation: 'Rapid layering velocity' }],
    context_flags: {
      shared_device_detected: true,
      rapid_pass_through_detected: true,
      note: 'High risk pass-through',
    },
    review: {
      status: 'OPEN',
      is_stale: false,
      staleness_reason: null,
      analyst_id: null,
      updated_at: null,
      verdict: null,
      notes: null,
    },
  }

  const mockAlertMedium: AlertSummary = {
    alert_id: 'ALT_0002',
    alert_fingerprint: 'fp_med',
    account_id: 'ACC_0102',
    created_at: '2026-10-01T10:05:00Z',
    status: 'INVESTIGATING',
    priority: 'MEDIUM',
    ml: { score: 0.55, threshold: 0.65, flagged: false },
    baseline: {
      flagged: true,
      rules_triggered: ['HIGH_FAN_OUT'],
    },
    top_reasons: [{ feature: 'fan_out', value: 8, typical_value: 1, explanation: 'Elevated fan out' }],
    context_flags: {
      shared_device_detected: false,
      rapid_pass_through_detected: false,
      note: null,
    },
    review: {
      status: 'INVESTIGATING',
      is_stale: false,
      staleness_reason: null,
      analyst_id: 'ANALYST_01',
      updated_at: '2026-10-01T10:30:00Z',
      verdict: null,
      notes: null,
    },
  }

  const mockAlertLow: AlertSummary = {
    alert_id: 'ALT_0003',
    alert_fingerprint: 'fp_low',
    account_id: 'ACC_0103',
    created_at: '2026-10-01T10:10:00Z',
    status: 'DISMISSED_BENIGN',
    priority: 'LOW',
    ml: { score: 0.2, threshold: 0.65, flagged: false },
    baseline: {
      flagged: false,
      rules_triggered: [],
    },
    top_reasons: [],
    context_flags: {
      shared_device_detected: false,
      rapid_pass_through_detected: true, // Has flag, but rule not triggered
      note: null,
    },
    review: {
      status: 'DISMISSED_BENIGN',
      is_stale: false,
      staleness_reason: null,
      analyst_id: 'ANALYST_02',
      updated_at: '2026-10-01T11:00:00Z',
      verdict: 'BENIGN_SHARED_DEVICE',
      notes: null,
    },
  }

  it('displays HIGH, MEDIUM, and LOW priorities correctly with distinct styling from score and status', () => {
    render(
      <InvestigationQueue
        alerts={[mockAlertHigh, mockAlertMedium, mockAlertLow]}
        selectedAlertId={null}
        onSelectAlert={vi.fn()}
        statusFilter="ALL"
        onStatusFilterChange={vi.fn()}
        budgetFilter="ALL"
        onBudgetFilterChange={vi.fn()}
        searchQuery=""
        onSearchQueryChange={vi.fn()}
        isLoading={false}
      />
    )

    // Check priorities rendered with distinct priority-pill classes
    const highPills = screen.getAllByText('HIGH')
    expect(highPills.length).toBeGreaterThanOrEqual(1)
    expect(highPills[0]).toHaveClass('priority-pill', 'priority-high')

    const medPills = screen.getAllByText('MEDIUM')
    expect(medPills.length).toBeGreaterThanOrEqual(1)
    expect(medPills[0]).toHaveClass('priority-pill', 'priority-medium')

    const lowPills = screen.getAllByText('LOW')
    expect(lowPills.length).toBeGreaterThanOrEqual(1)
    expect(lowPills[0]).toHaveClass('priority-pill', 'priority-low')

    // Verify model score, review priority, and review status are kept distinct
    expect(screen.getByText('0.9500')).toHaveClass('alert-score-pill')
    expect(screen.getAllByText('OPEN').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('INVESTIGATING').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('DISMISSED_BENIGN').length).toBeGreaterThanOrEqual(1)
  })

  it('removes duplicate pass-through badge when RAPID_PASS_THROUGH is in rules_triggered', () => {
    render(
      <InvestigationQueue
        alerts={[mockAlertHigh]}
        selectedAlertId={null}
        onSelectAlert={vi.fn()}
        statusFilter="ALL"
        onStatusFilterChange={vi.fn()}
        budgetFilter="ALL"
        onBudgetFilterChange={vi.fn()}
        searchQuery=""
        onSearchQueryChange={vi.fn()}
        isLoading={false}
      />
    )

    // RAPID_PASS_THROUGH is rendered as a rule tag
    expect(screen.getByText('RAPID_PASS_THROUGH')).toHaveClass('rule-tag')

    // Duplicate "Pass-Through" flag badge should NOT be rendered
    expect(screen.queryByText(/^Pass-Through$/i)).not.toBeInTheDocument()

    // Shared device is rendered
    expect(screen.getByText(/Device Link/i)).toBeInTheDocument()
  })

  it('renders pass-through flag tag when RAPID_PASS_THROUGH rule is not in rules_triggered', () => {
    render(
      <InvestigationQueue
        alerts={[mockAlertLow]}
        selectedAlertId={null}
        onSelectAlert={vi.fn()}
        statusFilter="ALL"
        onStatusFilterChange={vi.fn()}
        budgetFilter="ALL"
        onBudgetFilterChange={vi.fn()}
        searchQuery=""
        onSearchQueryChange={vi.fn()}
        isLoading={false}
      />
    )

    // RAPID_PASS_THROUGH is NOT in rules_triggered, so the flag tag Pass-Through should be shown once
    expect(screen.getByText(/^Pass-Through$/i)).toBeInTheDocument()
  })

  it('implements roving tabindex and aria-selected on listbox option cards', () => {
    const alerts = [mockAlertHigh, mockAlertMedium, mockAlertLow]
    const { rerender } = render(
      <InvestigationQueue
        alerts={alerts}
        selectedAlertId={null}
        onSelectAlert={vi.fn()}
        statusFilter="ALL"
        onStatusFilterChange={vi.fn()}
        budgetFilter="ALL"
        onBudgetFilterChange={vi.fn()}
        searchQuery=""
        onSearchQueryChange={vi.fn()}
        isLoading={false}
      />
    )

    const listbox = screen.getByRole('listbox', { name: /Investigation Alerts/i })
    expect(listbox).toBeInTheDocument()

    const cards = within(listbox).getAllByRole('option')
    expect(cards).toHaveLength(3)

    // When none is selected, first card has tabIndex 0, others -1
    expect(cards[0]).toHaveAttribute('tabindex', '0')
    expect(cards[1]).toHaveAttribute('tabindex', '-1')
    expect(cards[2]).toHaveAttribute('tabindex', '-1')

    // Rerender with selected alert ALT_0002
    rerender(
      <InvestigationQueue
        alerts={alerts}
        selectedAlertId="ALT_0002"
        onSelectAlert={vi.fn()}
        statusFilter="ALL"
        onStatusFilterChange={vi.fn()}
        budgetFilter="ALL"
        onBudgetFilterChange={vi.fn()}
        searchQuery=""
        onSearchQueryChange={vi.fn()}
        isLoading={false}
      />
    )

    const updatedCards = within(listbox).getAllByRole('option')
    expect(updatedCards[0]).toHaveAttribute('tabindex', '-1')
    expect(updatedCards[0]).toHaveAttribute('aria-selected', 'false')
    expect(updatedCards[1]).toHaveAttribute('tabindex', '0')
    expect(updatedCards[1]).toHaveAttribute('aria-selected', 'true')
    expect(updatedCards[2]).toHaveAttribute('tabindex', '-1')
    expect(listbox).toHaveAttribute('aria-activedescendant', 'alert-card-ALT_0002')
  })

  it('navigates through alerts using ArrowDown, ArrowUp, Home, and End keys', () => {
    const onSelect = vi.fn()
    const alerts = [mockAlertHigh, mockAlertMedium, mockAlertLow]
    render(
      <InvestigationQueue
        alerts={alerts}
        selectedAlertId="ALT_0001"
        onSelectAlert={onSelect}
        statusFilter="ALL"
        onStatusFilterChange={vi.fn()}
        budgetFilter="ALL"
        onBudgetFilterChange={vi.fn()}
        searchQuery=""
        onSearchQueryChange={vi.fn()}
        isLoading={false}
      />
    )

    const listbox = screen.getByRole('listbox', { name: /Investigation Alerts/i })
    const cards = within(listbox).getAllByRole('option')

    // Press ArrowDown from first card
    fireEvent.keyDown(cards[0], { key: 'ArrowDown' })
    expect(onSelect).toHaveBeenCalledWith('ALT_0002')

    // Press ArrowUp from second card
    fireEvent.keyDown(cards[1], { key: 'ArrowUp' })
    expect(onSelect).toHaveBeenCalledWith('ALT_0001')

    // Press End key from first card to jump to last
    fireEvent.keyDown(cards[0], { key: 'End' })
    expect(onSelect).toHaveBeenCalledWith('ALT_0003')

    // Press Home key from last card to jump to first
    fireEvent.keyDown(cards[2], { key: 'Home' })
    expect(onSelect).toHaveBeenCalledWith('ALT_0001')
  })

  it('selects alert on Enter and Space keypress', () => {
    const onSelect = vi.fn()
    render(
      <InvestigationQueue
        alerts={[mockAlertHigh]}
        selectedAlertId={null}
        onSelectAlert={onSelect}
        statusFilter="ALL"
        onStatusFilterChange={vi.fn()}
        budgetFilter="ALL"
        onBudgetFilterChange={vi.fn()}
        searchQuery=""
        onSearchQueryChange={vi.fn()}
        isLoading={false}
      />
    )

    const listbox = screen.getByRole('listbox', { name: /Investigation Alerts/i })
    const card = within(listbox).getByRole('option')

    fireEvent.keyDown(card, { key: 'Enter' })
    expect(onSelect).toHaveBeenCalledWith('ALT_0001')

    fireEvent.keyDown(card, { key: ' ' })
    expect(onSelect).toHaveBeenCalledTimes(2)
  })
})
