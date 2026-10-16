import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ReviewWorkflowControls } from './ReviewWorkflowControls'
import { apiClient, ApiError } from '../api/client'
import type { Alert } from '../types/api'

vi.mock('../api/client', () => ({
  apiClient: {
    updateAlertReview: vi.fn(),
  },
  ApiError: class extends Error {
    readonly status: number
    readonly detail: string
    readonly extra: Record<string, unknown>
    constructor(status: number, detail: string, extra: Record<string, unknown> = {}) {
      super(`API Error ${status}: ${detail}`)
      this.name = 'ApiError'
      this.status = status
      this.detail = detail
      this.extra = extra
    }
    get isInvalidReviewTransition() {
      return this.status === 422 && this.detail === 'invalid_review_transition'
    }
    get isAlertNotFound() {
      return this.status === 404 && this.detail === 'alert_not_found'
    }
    get isNetworkError() {
      return this.status === 0
    }
  },
}))

describe('ReviewWorkflowControls Component (Contract v1.2 §9)', () => {
  const baseAlert: Alert = {
    alert_id: 'ALT_0001',
    alert_fingerprint: 'abcdef1234567890'.repeat(4),
    account_id: 'ACC_0917',
    created_at: '2026-10-01T12:00:00Z',
    status: 'OPEN',
    priority: 'HIGH',
    ml: { score: 0.93, threshold: 0.5, flagged: true },
    baseline: { flagged: true, rules_triggered: ['HIGH_FAN_IN'] },
    top_reasons: [],
    context_flags: {
      shared_device_detected: false,
      rapid_pass_through_detected: true,
      note: null,
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
      nodes: [],
      edges: [],
      evidence_path: [],
    },
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders current status and metadata when unassigned', () => {
    const onReviewUpdated = vi.fn()
    render(<ReviewWorkflowControls alert={baseAlert} onReviewUpdated={onReviewUpdated} />)

    expect(screen.getByTestId('current-review-status-badge')).toHaveTextContent('OPEN')
    expect(screen.getByText(/Unassigned/i)).toBeInTheDocument()
    expect(screen.getByText(/Never/i)).toBeInTheDocument()
    expect(screen.queryByTestId('staleness-warning-banner')).not.toBeInTheDocument()
  })

  it('executes valid transition to INVESTIGATING without optimistic state spoofing', async () => {
    const onReviewUpdated = vi.fn()
    const updatedAlert: Alert = {
      ...baseAlert,
      status: 'INVESTIGATING',
      review: {
        ...baseAlert.review,
        status: 'INVESTIGATING',
        analyst_id: 'ANALYST_01',
        updated_at: '2026-10-01T13:00:00Z',
        verdict: null,
        notes: 'Commencing deep-dive.',
      },
    }

    vi.mocked(apiClient.updateAlertReview).mockResolvedValueOnce(updatedAlert)

    render(<ReviewWorkflowControls alert={baseAlert} onReviewUpdated={onReviewUpdated} />)

    // Fill notes
    const notesArea = screen.getByLabelText(/Review Rationale/i)
    fireEvent.change(notesArea, { target: { value: 'Commencing deep-dive.' } })

    // Click transition to INVESTIGATING
    const btnInvestigating = screen.getByTestId('btn-transition-investigating')
    fireEvent.click(btnInvestigating)

    await waitFor(() => {
      expect(apiClient.updateAlertReview).toHaveBeenCalledWith('ALT_0001', {
        status: 'INVESTIGATING',
        analyst_id: 'ANALYST_01',
        verdict: null,
        notes: 'Commencing deep-dive.',
      })
    })

    await waitFor(() => {
      expect(screen.getByTestId('review-success-banner')).toHaveTextContent(
        /Status updated to INVESTIGATING by ANALYST_01/i
      )
    })

    expect(onReviewUpdated).toHaveBeenCalledWith(updatedAlert)
  })

  it('blocks submission and displays error when analyst ID is cleared', async () => {
    const onReviewUpdated = vi.fn()
    render(<ReviewWorkflowControls alert={baseAlert} onReviewUpdated={onReviewUpdated} />)

    const analystInput = screen.getByLabelText(/Analyst Identifier/i)
    fireEvent.change(analystInput, { target: { value: '   ' } })

    const btnInvestigating = screen.getByTestId('btn-transition-investigating')
    fireEvent.click(btnInvestigating)

    expect(apiClient.updateAlertReview).not.toHaveBeenCalled()
    expect(screen.getByTestId('review-error-banner')).toHaveTextContent(
      /Analyst ID is required/i
    )
    expect(onReviewUpdated).not.toHaveBeenCalled()
  })

  it('handles backend 422 invalid_review_transition with contract rule explanation', async () => {
    const onReviewUpdated = vi.fn()
    const confirmedAlert: Alert = {
      ...baseAlert,
      status: 'CONFIRMED_FRAUD',
      review: {
        ...baseAlert.review,
        status: 'CONFIRMED_FRAUD',
        analyst_id: 'ANALYST_02',
        updated_at: '2026-10-01T14:00:00Z',
      },
    }

    vi.mocked(apiClient.updateAlertReview).mockRejectedValueOnce(
      new (ApiError as any)(422, 'invalid_review_transition')
    )

    render(<ReviewWorkflowControls alert={confirmedAlert} onReviewUpdated={onReviewUpdated} />)

    // Attempt direct transition from CONFIRMED_FRAUD to DISMISSED_BENIGN
    const btnDismiss = screen.getByTestId('btn-transition-dismissed_benign')
    fireEvent.click(btnDismiss)

    await waitFor(() => {
      expect(screen.getByTestId('review-error-banner')).toBeInTheDocument()
    })

    const banner = screen.getByTestId('review-error-banner')
    expect(banner).toHaveTextContent(/Invalid Transition \(HTTP 422\)/i)
    expect(banner).toHaveTextContent(/CONFIRMED_FRAUD to DISMISSED_BENIGN/i)
    expect(banner).toHaveTextContent(/reopen the alert to INVESTIGATING/i)
    expect(onReviewUpdated).not.toHaveBeenCalled()
  })

  it('handles generic API failures and re-enables submission', async () => {
    const onReviewUpdated = vi.fn()
    vi.mocked(apiClient.updateAlertReview).mockRejectedValueOnce(
      new (ApiError as any)(500, 'internal_server_error')
    )

    render(<ReviewWorkflowControls alert={baseAlert} onReviewUpdated={onReviewUpdated} />)

    const btnInvestigating = screen.getByTestId('btn-transition-investigating')
    fireEvent.click(btnInvestigating)

    await waitFor(() => {
      expect(screen.getByTestId('review-error-banner')).toHaveTextContent(
        /API Error \(500\): internal_server_error/i
      )
    })

    expect(onReviewUpdated).not.toHaveBeenCalled()
  })

  it('displays historical divergence staleness warning and prior review audit card', () => {
    const onReviewUpdated = vi.fn()
    const staleHistoricalAlert: Alert = {
      ...baseAlert,
      review: {
        ...baseAlert.review,
        status: 'OPEN',
        is_stale: true,
        staleness_reason: 'historical_snapshot_evidence_divergence',
        previous_review: {
          status: 'CONFIRMED_FRAUD',
          analyst_id: 'ANALYST_09',
          updated_at: '2026-10-01T10:00:00Z',
          verdict: 'CONFIRMED_MULE_RING',
          notes: 'Tagged during pilot investigation.',
        },
      },
    }

    render(
      <ReviewWorkflowControls
        alert={staleHistoricalAlert}
        onReviewUpdated={onReviewUpdated}
      />
    )

    expect(screen.getByTestId('staleness-warning-banner')).toBeInTheDocument()
    expect(screen.getByText(/STATUS RESET TO OPEN/i)).toBeInTheDocument()
    expect(screen.getByTestId('staleness-reason-text')).toHaveTextContent(
      /Historical Snapshot Evidence Divergence/i
    )
    expect(screen.getByTestId('previous-review-card')).toBeInTheDocument()
    expect(screen.getByText(/ANALYST_09/i)).toBeInTheDocument()
    expect(screen.getByText(/CONFIRMED_MULE_RING/i)).toBeInTheDocument()
    expect(screen.getByText(/Tagged during pilot investigation/i)).toBeInTheDocument()
  })

  it('displays evidence_or_score_changed staleness warning when evidence changed', () => {
    const onReviewUpdated = vi.fn()
    const staleEvidenceAlert: Alert = {
      ...baseAlert,
      review: {
        ...baseAlert.review,
        status: 'OPEN',
        is_stale: true,
        staleness_reason: 'evidence_or_score_changed',
        previous_review: {
          status: 'DISMISSED_BENIGN',
          analyst_id: 'ANALYST_04',
          updated_at: '2026-10-01T09:00:00Z',
          verdict: 'BENIGN_SHARED_DEVICE',
          notes: 'Family transfer pattern.',
        },
      },
    }

    render(
      <ReviewWorkflowControls
        alert={staleEvidenceAlert}
        onReviewUpdated={onReviewUpdated}
      />
    )

    expect(screen.getByTestId('staleness-reason-text')).toHaveTextContent(
      /Evidence or Score Changed/i
    )
    expect(screen.getByText(/Underlying graph evidence, participating transactions/i)).toBeInTheDocument()
    expect(screen.getByText(/ANALYST_04/i)).toBeInTheDocument()
  })

  it('populates fields when quick verdict template buttons are clicked', () => {
    const onReviewUpdated = vi.fn()
    render(<ReviewWorkflowControls alert={baseAlert} onReviewUpdated={onReviewUpdated} />)

    const btnMule = screen.getByRole('button', { name: /^Mule Ring$/i })
    fireEvent.click(btnMule)

    const verdictInput = screen.getByLabelText(/Investigation Verdict/i) as HTMLInputElement
    const notesArea = screen.getByLabelText(/Review Rationale/i) as HTMLTextAreaElement

    expect(verdictInput.value).toBe('CONFIRMED_MULE_RING')
    expect(notesArea.value).toContain('rapid layering pattern')
  })

  it('submits review through explicit "Submit review" button with exact payload schema', async () => {
    const onReviewUpdated = vi.fn()
    const onReturnToQueue = vi.fn()
    const updatedAlert: Alert = {
      ...baseAlert,
      status: 'INVESTIGATING',
      review: {
        ...baseAlert.review,
        status: 'INVESTIGATING',
        analyst_id: 'ANALYST_01',
        verdict: 'CONFIRMED_MULE_RING',
        notes: 'Submitted via explicit button.',
      },
    }

    vi.mocked(apiClient.updateAlertReview).mockResolvedValueOnce(updatedAlert)

    render(
      <ReviewWorkflowControls
        alert={baseAlert}
        onReviewUpdated={onReviewUpdated}
        onReturnToQueue={onReturnToQueue}
      />
    )

    // Fill verdict and notes
    fireEvent.change(screen.getByLabelText(/Investigation Verdict/i), {
      target: { value: 'CONFIRMED_MULE_RING' },
    })
    fireEvent.change(screen.getByLabelText(/Review Rationale/i), {
      target: { value: 'Submitted via explicit button.' },
    })

    // Click explicit "Submit review" button
    const submitBtn = screen.getByTestId('btn-submit-review')
    expect(submitBtn).toBeInTheDocument()
    expect(submitBtn).toHaveTextContent(/Submit review/i)
    fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(apiClient.updateAlertReview).toHaveBeenCalledWith('ALT_0001', {
        status: 'INVESTIGATING',
        analyst_id: 'ANALYST_01',
        verdict: 'CONFIRMED_MULE_RING',
        notes: 'Submitted via explicit button.',
      })
    })

    // Confirmed success state displayed
    expect(await screen.findByTestId('review-success-banner')).toBeInTheDocument()

    // Return to Alert Queue action is available
    const returnBtn = screen.getByTestId('btn-return-to-queue')
    expect(returnBtn).toBeInTheDocument()
    fireEvent.click(returnBtn)
    expect(onReturnToQueue).toHaveBeenCalledTimes(1)
  })

  it('prevents duplicate submissions while request is pending', async () => {
    const onReviewUpdated = vi.fn()
    let resolvePromise: (val: any) => void
    const pendingPromise = new Promise((resolve) => {
      resolvePromise = resolve
    })
    vi.mocked(apiClient.updateAlertReview).mockReturnValueOnce(pendingPromise as any)

    render(<ReviewWorkflowControls alert={baseAlert} onReviewUpdated={onReviewUpdated} />)

    const submitBtn = screen.getByTestId('btn-submit-review')
    fireEvent.click(submitBtn)

    // Button should be disabled and show loading state
    expect(submitBtn).toBeDisabled()
    expect(submitBtn).toHaveTextContent(/Submitting review\.\.\./i)

    // Subsequent clicks should not trigger another API call
    fireEvent.click(submitBtn)
    expect(apiClient.updateAlertReview).toHaveBeenCalledTimes(1)

    // Resolve promise
    resolvePromise!({
      ...baseAlert,
      status: 'INVESTIGATING',
      review: { ...baseAlert.review, status: 'INVESTIGATING' },
    })

    await waitFor(() => {
      expect(screen.getByTestId('review-success-banner')).toBeInTheDocument()
    })
  })
})
