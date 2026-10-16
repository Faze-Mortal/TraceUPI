import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { DashboardWorkbench } from './DashboardWorkbench'
import { apiClient, ApiError } from '../api/client'
import type { Alert, AlertSummary, PipelineRunResponse } from '../types/api'

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return {
    ...actual,
    apiClient: {
      runPipeline: vi.fn(),
      getAlerts: vi.fn(),
      getAlert: vi.fn(),
      updateAlertReview: vi.fn(),
    },
  }
})

describe('DashboardWorkbench Component', () => {
  const mockAlertSummary1: AlertSummary = {
    alert_id: 'ALT_0001',
    alert_fingerprint: 'a'.repeat(64),
    account_id: 'ACC_0917',
    created_at: '2026-10-01T12:00:00Z',
    status: 'OPEN',
    priority: 'HIGH',
    ml: { score: 0.93, threshold: 0.5, flagged: true },
    baseline: { flagged: true, rules_triggered: ['HIGH_FAN_IN', 'RAPID_PASS_THROUGH'] },
    top_reasons: [
      {
        feature: 'fan_in_count',
        value: 14,
        typical_value: 2,
        explanation: 'Received transfers from 14 counterparties',
      },
    ],
    context_flags: {
      shared_device_detected: false,
      rapid_pass_through_detected: true,
      note: 'Rapid pass-through detected',
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

  const mockAlertSummary2: AlertSummary = {
    alert_id: 'ALT_0002',
    alert_fingerprint: 'b'.repeat(64),
    account_id: 'ACC_0101',
    created_at: '2026-10-01T12:30:00Z',
    status: 'INVESTIGATING',
    priority: 'MEDIUM',
    ml: { score: 0.75, threshold: 0.5, flagged: true },
    baseline: { flagged: false, rules_triggered: [] },
    top_reasons: [
      {
        feature: 'devices_used_count',
        value: 3,
        typical_value: 1,
        explanation: 'Observed 3 devices for account',
      },
    ],
    context_flags: {
      shared_device_detected: true,
      rapid_pass_through_detected: false,
      note: null,
    },
    review: {
      status: 'INVESTIGATING',
      is_stale: true,
      staleness_reason: 'evidence_or_score_changed',
      analyst_id: 'ANALYST_01',
      updated_at: '2026-10-01T13:00:00Z',
      verdict: null,
      notes: null,
    },
  }

  const mockFullAlert1: Alert = {
    ...mockAlertSummary1,
    review: {
      ...mockAlertSummary1.review,
      previous_review: null,
    },
    evidence: {
      nodes: [
        { id: 'ACC_0917', type: 'account', label: 'ACC_0917', score: 0.93, metadata: {} },
        { id: 'DEV_0001', type: 'device', label: 'DEV_0001', score: null, metadata: {} },
      ],
      edges: [
        {
          id: 'E1',
          source: 'ACC_0917',
          target: 'DEV_0001',
          type: 'uses_device',
          txn_id: null,
          amount_inr: null,
          timestamp: null,
        },
      ],
      evidence_path: ['E1'],
    },
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('displays pre-analysis state when backend returns 503 analysis_not_run', async () => {
    vi.mocked(apiClient.getAlerts).mockRejectedValue(new ApiError(503, 'analysis_not_run'))

    render(<DashboardWorkbench onBackToOverview={vi.fn()} />)

    expect(await screen.findByText(/Analysis Pipeline Has Not Run Yet \(HTTP 503\)/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Run Analysis Pipeline Now/i })).toBeInTheDocument()
    expect(screen.getByText(/Analysis Not Run \(503\)/i)).toBeInTheDocument()
  })

  it('runs analysis pipeline and populates alert queue', async () => {
    vi.mocked(apiClient.getAlerts)
      .mockRejectedValueOnce(new ApiError(503, 'analysis_not_run'))
      .mockResolvedValue([mockAlertSummary1, mockAlertSummary2])

    const mockRunResponse: PipelineRunResponse = {
      n_transactions: 120,
      n_alerts: 2,
      metrics_available: true,
      as_of: null,
    }
    vi.mocked(apiClient.runPipeline).mockResolvedValue(mockRunResponse)

    render(<DashboardWorkbench onBackToOverview={vi.fn()} />)

    const runBtn = await screen.findByRole('button', { name: /Run Analysis Pipeline Now/i })
    fireEvent.click(runBtn)

    expect(apiClient.runPipeline).toHaveBeenCalled()

    // Telemetry updates
    expect(await screen.findByText(/Ready · 120 Txns · 2 Alerts/i)).toBeInTheDocument()

    // Alert queue displays both alerts
    expect(screen.getByText('ACC_0917')).toBeInTheDocument()
    expect(screen.getByText('ACC_0101')).toBeInTheDocument()
    expect(screen.getByText('0.9300')).toBeInTheDocument()
    expect(screen.getByText('0.7500')).toBeInTheDocument()
    expect(screen.getByText('STALE')).toBeInTheDocument()
  })

  it('filters alert queue by status and budget K', async () => {
    vi.mocked(apiClient.getAlerts).mockResolvedValue([mockAlertSummary1])

    render(<DashboardWorkbench onBackToOverview={vi.fn()} />)

    await waitFor(() => {
      expect(apiClient.getAlerts).toHaveBeenCalledWith({})
    })

    // Filter by status OPEN
    const statusSelect = screen.getByLabelText(/Filter alerts by review status/i)
    fireEvent.change(statusSelect, { target: { value: 'OPEN' } })

    await waitFor(() => {
      expect(apiClient.getAlerts).toHaveBeenCalledWith({ status: 'OPEN' })
    })

    // Filter by budget K = 20
    const budgetSelect = screen.getByLabelText(/Filter alerts by analyst capacity budget/i)
    fireEvent.change(budgetSelect, { target: { value: '20' } })

    await waitFor(() => {
      expect(apiClient.getAlerts).toHaveBeenCalledWith({ status: 'OPEN', budget_k: 20 })
    })
  })

  it('filters queue with client-side search query', async () => {
    vi.mocked(apiClient.getAlerts).mockResolvedValue([mockAlertSummary1, mockAlertSummary2])

    render(<DashboardWorkbench onBackToOverview={vi.fn()} />)

    expect(await screen.findByText('ACC_0917')).toBeInTheDocument()
    expect(screen.getByText('ACC_0101')).toBeInTheDocument()

    const searchInput = screen.getByLabelText(/Filter alerts by account or alert ID/i)
    fireEvent.change(searchInput, { target: { value: '0917' } })

    expect(screen.getByText('ACC_0917')).toBeInTheDocument()
    expect(screen.queryByText('ACC_0101')).not.toBeInTheDocument()
  })

  it('selects alert and displays full details in inspector', async () => {
    vi.mocked(apiClient.getAlerts).mockResolvedValue([mockAlertSummary1])
    vi.mocked(apiClient.getAlert).mockResolvedValue(mockFullAlert1)

    render(<DashboardWorkbench onBackToOverview={vi.fn()} />)

    const card = await screen.findByRole('option', { name: /ACC_0917/i })
    fireEvent.click(card)

    expect(apiClient.getAlert).toHaveBeenCalledWith('ALT_0001')

    // Inspector section displays loaded details
    const inspector = await screen.findByRole('region', { name: /Inspection Details for ACC_0917/i })
    expect(inspector).toBeInTheDocument()
    expect(screen.getByText(/Nodes: 2 \/ 25 max/i)).toBeInTheDocument()
    expect(screen.getByText(/Path: 1 hops/i)).toBeInTheDocument()
    expect(screen.getByText('Received transfers from 14 counterparties')).toBeInTheDocument()
  })

  it('navigates between 3 distinct sections using workflow tabs', async () => {
    vi.mocked(apiClient.getAlerts).mockResolvedValue([mockAlertSummary1])
    vi.mocked(apiClient.getAlert).mockResolvedValue(mockFullAlert1)

    render(<DashboardWorkbench onBackToOverview={vi.fn()} />)

    // Initially in Section A: Alert Queue
    expect(screen.getByTestId('section-queue-container')).toBeInTheDocument()
    expect(screen.queryByTestId('section-graph-container')).not.toBeInTheDocument()
    expect(screen.queryByTestId('section-review-container')).not.toBeInTheDocument()

    // Switch to Section B: Evidence Graph tab before alert selection
    const graphTab = screen.getByTestId('tab-section-graph')
    fireEvent.click(graphTab)

    expect(screen.getByTestId('section-graph-container')).toBeInTheDocument()
    expect(screen.getByText(/No Alert Selected for Evidence Graph/i)).toBeInTheDocument()

    // Switch to Section C: Review tab before alert selection
    const reviewTab = screen.getByTestId('tab-section-review')
    fireEvent.click(reviewTab)

    expect(screen.getByTestId('section-review-container')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /No Alert Selected/i })).toBeInTheDocument()

    // Switch back to Queue tab
    const queueTab = screen.getByTestId('tab-section-queue')
    fireEvent.click(queueTab)
    expect(screen.getByTestId('section-queue-container')).toBeInTheDocument()
  })

  it('clicking Investigate Graph button navigates directly to Section B with active context banner', async () => {
    vi.mocked(apiClient.getAlerts).mockResolvedValue([mockAlertSummary1])
    vi.mocked(apiClient.getAlert).mockResolvedValue(mockFullAlert1)

    render(<DashboardWorkbench onBackToOverview={vi.fn()} />)

    // Find and click the explicit "Investigate Graph →" button on the card
    const investigateBtn = await screen.findByRole('button', { name: /Investigate Graph →/i })
    fireEvent.click(investigateBtn)

    // Should load alert details and navigate to graph view
    expect(apiClient.getAlert).toHaveBeenCalledWith('ALT_0001')
    expect(await screen.findByTestId('section-graph-container')).toBeInTheDocument()

    // Active context banner should be visible with target info and action CTAs
    const contextBanner = screen.getByRole('region', { name: /Active Investigation Context/i })
    expect(contextBanner).toBeInTheDocument()
    expect(within(contextBanner).getByText('ACC_0917')).toBeInTheDocument()

    // Click "Proceed to Review →" in context bar
    const proceedBtn = within(contextBanner).getByRole('button', { name: /Proceed to Review →/i })
    fireEvent.click(proceedBtn)

    // Should transition to Section C: Review
    expect(screen.getByTestId('section-review-container')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: /Inspection Details for ACC_0917/i })).toBeInTheDocument()

    // Click "← Back to Queue" to return
    const backQueueBtn = screen.getAllByRole('button', { name: /← Back to Queue/i })[0]
    fireEvent.click(backQueueBtn)
    expect(screen.getByTestId('section-queue-container')).toBeInTheDocument()
  })

  it('handles alert detail load error gracefully', async () => {
    vi.mocked(apiClient.getAlerts).mockResolvedValue([mockAlertSummary1])
    vi.mocked(apiClient.getAlert).mockRejectedValue(new Error('Failed to fetch alert details'))

    render(<DashboardWorkbench onBackToOverview={vi.fn()} />)

    const card = await screen.findByRole('option', { name: /ACC_0917/i })
    fireEvent.click(card)

    expect(await screen.findByText(/Failed to load alert details/i)).toBeInTheDocument()
    expect(screen.getByText(/Failed to fetch alert details/i)).toBeInTheDocument()
  })

  it('displays empty state when no alerts match filter', async () => {
    vi.mocked(apiClient.getAlerts).mockResolvedValue([])

    render(<DashboardWorkbench onBackToOverview={vi.fn()} />)

    expect(await screen.findByText(/No alerts matching filter criteria/i)).toBeInTheDocument()
  })

  it('updates alert review state and synchronizes queue upon successful review transition', async () => {
    vi.mocked(apiClient.getAlerts).mockResolvedValue([mockAlertSummary1])
    vi.mocked(apiClient.getAlert).mockResolvedValue(mockFullAlert1)

    const updatedAlert: Alert = {
      ...mockFullAlert1,
      status: 'INVESTIGATING',
      review: {
        ...mockFullAlert1.review,
        status: 'INVESTIGATING',
        analyst_id: 'ANALYST_01',
        updated_at: '2026-10-01T15:00:00Z',
        verdict: null,
        notes: 'Under active review.',
      },
    }
    vi.mocked(apiClient.updateAlertReview).mockResolvedValue(updatedAlert)

    render(<DashboardWorkbench onBackToOverview={vi.fn()} />)

    // Select the card to open inspector
    const card = await screen.findByRole('option', { name: /ACC_0917/i })
    fireEvent.click(card)

    // Wait for inspector to load
    expect(await screen.findByRole('region', { name: /Inspection Details for ACC_0917/i })).toBeInTheDocument()

    // Trigger transition to INVESTIGATING
    const btnInvestigating = screen.getByTestId('btn-transition-investigating')
    fireEvent.click(btnInvestigating)

    await waitFor(() => {
      expect(apiClient.updateAlertReview).toHaveBeenCalledWith('ALT_0001', {
        status: 'INVESTIGATING',
        analyst_id: 'ANALYST_01',
        verdict: null,
        notes: null,
      })
    })

    // Verify success banner appears
    await waitFor(() => {
      expect(screen.getByTestId('review-success-banner')).toHaveTextContent(
        /Status updated to INVESTIGATING/i
      )
    })

    // Click Return to Alert Queue and verify navigation back to Section 1
    const returnBtn = await screen.findByTestId('btn-return-to-queue')
    expect(returnBtn).toBeInTheDocument()
    fireEvent.click(returnBtn)

    // Alert Queue tab is now active
    expect(screen.getByTestId('tab-section-queue')).toHaveClass('active')
  })

  it('renders "Run fraud-risk analysis" button and "Analyze data up to a time" under Advanced options', async () => {
    vi.mocked(apiClient.getAlerts).mockResolvedValue([mockAlertSummary1])
    render(<DashboardWorkbench onBackToOverview={vi.fn()} />)

    // Renamed button
    const runBtn = screen.getByRole('button', { name: /Run fraud-risk analysis/i })
    expect(runBtn).toBeInTheDocument()

    // Advanced options disclosure
    expect(screen.getByText(/Advanced options/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Analyze data up to a time/i)).toBeInTheDocument()
    expect(screen.getByText(/Rerunning fraud-risk analysis evaluates only transactions ingested on or before this time/i)).toBeInTheDocument()
  })

  it('configures historical cutoff with date and time picker and explicitly converts to UTC', async () => {
    vi.mocked(apiClient.getAlerts).mockResolvedValue([mockAlertSummary1])
    vi.mocked(apiClient.runPipeline).mockResolvedValue({
      n_transactions: 50,
      n_alerts: 1,
      metrics_available: true,
      as_of: '2026-10-01T14:30:00Z',
    })

    render(<DashboardWorkbench onBackToOverview={vi.fn()} />)

    // Select date
    const dateInput = screen.getByTestId('input-asof-date')
    fireEvent.change(dateInput, { target: { value: '2026-10-01' } })

    // Select 30-min time increment
    const timeSelect = screen.getByTestId('select-asof-time')
    fireEvent.change(timeSelect, { target: { value: '14:30' } })

    // Active UTC display appears and ends in 'Z'
    const utcDisplay = await screen.findByTestId('active-cutoff-utc')
    expect(utcDisplay.textContent).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/)

    // Crucial check: changing date and time did NOT trigger runPipeline automatically!
    expect(apiClient.runPipeline).not.toHaveBeenCalled()

    // Trigger run fraud-risk analysis button explicitly
    const runBtn = screen.getByRole('button', { name: /Run fraud-risk analysis/i })
    fireEvent.click(runBtn)

    // Verify pipeline was called with the calculated UTC cutoff
    await waitFor(() => {
      expect(apiClient.runPipeline).toHaveBeenCalledWith({
        as_of: utcDisplay.textContent,
      })
    })

    // Click Clear Cutoff button to reset
    const clearBtn = screen.getByTestId('btn-clear-asof')
    fireEvent.click(clearBtn)

    // Mode is restored to full history
    expect(screen.getByText(/Active Mode: Full history \(no historical cutoff\)/i)).toBeInTheDocument()
  })
})
