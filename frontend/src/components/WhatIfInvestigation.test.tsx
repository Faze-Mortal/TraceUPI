import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { WhatIfInvestigation } from './WhatIfInvestigation'
import { apiClient, ApiError } from '../api/client'
import type { Alert, CounterfactualResponse } from '../types/api'

vi.mock('../api/client', () => ({
  apiClient: {
    runCounterfactual: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    readonly status: number
    readonly detail: string
    constructor(status: number, detail: string) {
      super(detail)
      this.status = status
      this.detail = detail
    }
    get isEmptyCounterfactual() {
      return this.status === 422 && this.detail === 'empty_counterfactual_request'
    }
    get isInvalidCounterfactual() {
      return this.status === 422 && this.detail === 'invalid_counterfactual_request'
    }
  },
}))

describe('WhatIfInvestigation Component', () => {
  const mockAlert: Alert = {
    alert_id: 'ALT_0001',
    alert_fingerprint: 'f'.repeat(64),
    account_id: 'ACC_0917',
    created_at: '2026-10-01T12:00:00Z',
    status: 'OPEN',
    priority: 'HIGH',
    ml: { score: 0.93, threshold: 0.85, flagged: true },
    baseline: { flagged: true, rules_triggered: ['HIGH_FAN_IN', 'RAPID_PASS_THROUGH'] },
    top_reasons: [],
    context_flags: {
      shared_device_detected: true,
      rapid_pass_through_detected: true,
      note: 'Suspicious layering ring',
    },
    review: {
      status: 'OPEN',
      is_stale: false,
      staleness_reason: null,
      analyst_id: null,
      updated_at: null,
      verdict: null,
      notes: null,
      previous_review: null,
    },
    evidence: {
      nodes: [
        { id: 'ACC_0917', type: 'account', label: 'ACC_0917', score: 0.93, metadata: {} },
        { id: 'ACC_0042', type: 'account', label: 'ACC_0042', score: 0.15, metadata: {} },
        { id: 'DEV_0001', type: 'device', label: 'DEV_0001', score: null, metadata: {} },
        { id: 'CMP_0012', type: 'complaint', label: 'CMP_0012', score: null, metadata: { category: 'UPI_FRAUD' } },
      ],
      edges: [
        {
          id: 'E1',
          source: 'ACC_0042',
          target: 'ACC_0917',
          type: 'transfer',
          txn_id: 'TXN_001',
          amount_inr: 8500.5,
          timestamp: '2026-10-01T10:10:00Z',
        },
        {
          id: 'E2',
          source: 'ACC_0917',
          target: 'DEV_0001',
          type: 'uses_device',
          txn_id: null,
          amount_inr: null,
          timestamp: null,
        },
        {
          id: 'E3',
          source: 'ACC_0917',
          target: 'CMP_0012',
          type: 'has_complaint',
          txn_id: null,
          amount_inr: null,
          timestamp: '2026-10-01T10:20:00Z',
        },
      ],
      evidence_path: ['E1'],
    },
  }

  const mockSuccessResponse: CounterfactualResponse = {
    alert_id: 'ALT_0001',
    account_id: 'ACC_0917',
    original_score: 0.93,
    counterfactual_score: 0.21,
    score_delta: -0.72,
    original_flagged: true,
    counterfactual_flagged: false,
    rules_removed: ['RAPID_PASS_THROUGH'],
    rules_added: [],
    plausible_benign_alternative:
      'Hypothesis: Excluding transfer E1 removes rapid layering flow; account behavior appears normal.',
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders What-if investigation controls and filters transfer edges only', () => {
    render(<WhatIfInvestigation alert={mockAlert} />)

    expect(screen.getByRole('heading', { name: /What-if investigation/i })).toBeInTheDocument()
    expect(screen.getByText(/Hypothetical sandbox · Original alert unchanged/i)).toBeInTheDocument()

    // Transfer edge E1 is listed
    expect(screen.getByTestId('edge-checkbox-E1')).toBeInTheDocument()
    expect(screen.getByText(/E1/)).toBeInTheDocument()
    expect(screen.getByText(/ACC_0042 → ACC_0917/)).toBeInTheDocument()
    expect(screen.getByText(/₹8,500.50/)).toBeInTheDocument()

    // Device edge E2 and Complaint edge E3 are NOT in transfer checklist
    expect(screen.queryByTestId('edge-checkbox-E2')).not.toBeInTheDocument()
    expect(screen.queryByTestId('edge-checkbox-E3')).not.toBeInTheDocument()

    // Toggles exist
    expect(screen.getByTestId('toggle-suppress-devices')).toBeInTheDocument()
    expect(screen.getByTestId('toggle-suppress-complaints')).toBeInTheDocument()
  })

  it('runs hypothetical analysis with selected edge and suppression toggles', async () => {
    vi.mocked(apiClient.runCounterfactual).mockResolvedValue(mockSuccessResponse)

    render(<WhatIfInvestigation alert={mockAlert} />)

    // Select transfer edge E1
    const edgeCheckbox = screen.getByTestId('edge-checkbox-E1')
    fireEvent.click(edgeCheckbox)

    // Toggle suppress devices
    const deviceToggle = screen.getByTestId('toggle-suppress-devices')
    fireEvent.click(deviceToggle)

    // Run analysis
    const runBtn = screen.getByTestId('btn-run-whatif')
    expect(runBtn).not.toBeDisabled()
    fireEvent.click(runBtn)

    await waitFor(() => {
      expect(apiClient.runCounterfactual).toHaveBeenCalledWith('ALT_0001', {
        remove_edge_ids: ['E1'],
        suppress_device_sharing: true,
        suppress_complaints: false,
      })
    })

    // Results are rendered
    expect(await screen.findByTestId('what-if-results-panel')).toBeInTheDocument()
    expect(screen.getByText(/Hypothetical — original alert unchanged\./i)).toBeInTheDocument()
    expect(screen.getByText('0.9300')).toBeInTheDocument()
    expect(screen.getByText('0.2100')).toBeInTheDocument()

    // Signed delta
    const delta = screen.getByTestId('signed-score-delta')
    expect(delta).toHaveTextContent('-0.7200')
    expect(delta).toHaveClass('delta-negative')
    expect(screen.getByText(/Risk Reduced/i)).toBeInTheDocument()

    // Removed rules
    expect(screen.getByText(/− RAPID_PASS_THROUGH/i)).toBeInTheDocument()

    // Benign alternative hypothesis
    expect(screen.getByTestId('plausible-benign-alternative')).toHaveTextContent(
      /Hypothesis: Excluding transfer E1/i
    )
  })

  it('displays signed positive score delta when risk increases', async () => {
    const positiveDeltaResponse: CounterfactualResponse = {
      ...mockSuccessResponse,
      original_score: 0.40,
      counterfactual_score: 0.65,
      score_delta: 0.25,
      original_flagged: false,
      counterfactual_flagged: true,
      rules_removed: [],
      rules_added: ['HIGH_FAN_IN'],
      plausible_benign_alternative: 'Hypothesis: Alternate scenario shows concentrated counterparty exposure.',
    }
    vi.mocked(apiClient.runCounterfactual).mockResolvedValue(positiveDeltaResponse)

    render(<WhatIfInvestigation alert={mockAlert} />)

    // Select complaint suppression
    fireEvent.click(screen.getByTestId('toggle-suppress-complaints'))
    fireEvent.click(screen.getByTestId('btn-run-whatif'))

    await waitFor(() => {
      expect(screen.getByTestId('signed-score-delta')).toHaveTextContent('+0.2500')
    })
    expect(screen.getByTestId('signed-score-delta')).toHaveClass('delta-positive')
    expect(screen.getByText(/Risk Increased/i)).toBeInTheDocument()
    expect(screen.getByText(/\+ HIGH_FAN_IN/i)).toBeInTheDocument()
  })

  it('resets hypothetical inputs and clears results on reset click', async () => {
    vi.mocked(apiClient.runCounterfactual).mockResolvedValue(mockSuccessResponse)

    render(<WhatIfInvestigation alert={mockAlert} />)

    // Select and run
    fireEvent.click(screen.getByTestId('edge-checkbox-E1'))
    fireEvent.click(screen.getByTestId('btn-run-whatif'))

    expect(await screen.findByTestId('what-if-results-panel')).toBeInTheDocument()

    // Click Reset inputs
    const resetBtn = screen.getByTestId('btn-reset-whatif')
    fireEvent.click(resetBtn)

    // Checkbox unchecked and results removed
    expect(screen.getByTestId('edge-checkbox-E1')).not.toBeChecked()
    expect(screen.queryByTestId('what-if-results-panel')).not.toBeInTheDocument()
  })

  it('disables run button when no interventions are selected', () => {
    render(<WhatIfInvestigation alert={mockAlert} />)

    const runBtn = screen.getByTestId('btn-run-whatif')
    expect(runBtn).toBeDisabled()
  })

  it('handles backend API error gracefully', async () => {
    vi.mocked(apiClient.runCounterfactual).mockRejectedValue(
      new ApiError(422, 'invalid_counterfactual_request')
    )

    render(<WhatIfInvestigation alert={mockAlert} />)

    fireEvent.click(screen.getByTestId('toggle-suppress-devices'))
    fireEvent.click(screen.getByTestId('btn-run-whatif'))

    expect(await screen.findByTestId('what-if-error-banner')).toHaveTextContent(
      /Invalid intervention: invalid_counterfactual_request/i
    )
  })

  it('announces completion to screen readers via polite live region', async () => {
    vi.mocked(apiClient.runCounterfactual).mockResolvedValue(mockSuccessResponse)

    render(<WhatIfInvestigation alert={mockAlert} />)

    fireEvent.click(screen.getByTestId('edge-checkbox-E1'))
    fireEvent.click(screen.getByTestId('btn-run-whatif'))

    await screen.findByTestId('what-if-results-panel')

    const announcement = screen.getByTestId('whatif-live-announcement')
    expect(announcement).toHaveAttribute('role', 'status')
    expect(announcement).toHaveAttribute('aria-live', 'polite')
    expect(announcement).toHaveTextContent(
      /Hypothetical analysis complete\. Original risk score 0\.9300, hypothetical risk score 0\.2100, score delta -0\.7200\./i
    )
  })
})
