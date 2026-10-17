import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { apiClient, ApiError } from './client'
import type { Alert, AlertsResponse, AlertSummary, MetricsResponse, PipelineRunResponse } from '../types/api'

describe('TraceUPI API Client', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  describe('runPipeline', () => {
    it('successfully triggers pipeline without as_of', async () => {
      const mockResult: PipelineRunResponse = {
        n_transactions: 120,
        n_alerts: 4,
        metrics_available: true,
        as_of: null,
      }

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResult,
      })

      const res = await apiClient.runPipeline()
      expect(res).toEqual(mockResult)
      expect(globalThis.fetch).toHaveBeenCalledWith('/api/pipeline/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: undefined,
      })
    })

    it('sends as_of cutoff when supplied', async () => {
      const mockResult: PipelineRunResponse = {
        n_transactions: 85,
        n_alerts: 3,
        metrics_available: true,
        as_of: '2026-10-01T12:00:00Z',
      }

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResult,
      })

      const res = await apiClient.runPipeline({ as_of: '2026-10-01T12:00:00Z' })
      expect(res).toEqual(mockResult)
      expect(globalThis.fetch).toHaveBeenCalledWith('/api/pipeline/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ as_of: '2026-10-01T12:00:00Z' }),
      })
    })

    it('throws ApiError with status 422 for invalid as_of timestamp', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({ detail: 'invalid_as_of_timestamp' }),
      })

      await expect(apiClient.runPipeline({ as_of: 'invalid' })).rejects.toThrow(ApiError)
      try {
        await apiClient.runPipeline({ as_of: 'invalid' })
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        const apiErr = err as ApiError
        expect(apiErr.status).toBe(422)
        expect(apiErr.detail).toBe('invalid_as_of_timestamp')
      }
    })

    it('handles network failure properly', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('Connection refused'))

      try {
        await apiClient.runPipeline()
        expect.unreachable()
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        const apiErr = err as ApiError
        expect(apiErr.status).toBe(0)
        expect(apiErr.isNetworkError).toBe(true)
        expect(apiErr.detail).toContain('Connection refused')
      }
    })
  })

  describe('getAlerts', () => {
    const mockSummary: AlertSummary = {
      alert_id: 'ALT_0001',
      alert_fingerprint: 'a'.repeat(64),
      account_id: 'ACC_0917',
      created_at: '2026-10-01T12:00:00Z',
      status: 'OPEN',
      priority: 'HIGH',
      ml: { score: 0.93, threshold: 0.5, flagged: true },
      baseline: { flagged: true, rules_triggered: ['HIGH_FAN_IN'] },
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
      },
    }

    it('fetches unconstrained alerts', async () => {
      const responsePayload: AlertsResponse = { alerts: [mockSummary] }
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => responsePayload,
      })

      const alerts = await apiClient.getAlerts()
      expect(alerts).toEqual([mockSummary])
      expect(globalThis.fetch).toHaveBeenCalledWith('/api/alerts', {
        method: 'GET',
        headers: { Accept: 'application/json' },
      })
    })

    it('passes status and budget_k query params', async () => {
      const responsePayload: AlertsResponse = { alerts: [mockSummary] }
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => responsePayload,
      })

      await apiClient.getAlerts({ status: 'OPEN', budget_k: 20 })
      expect(globalThis.fetch).toHaveBeenCalledWith('/api/alerts?status=OPEN&budget_k=20', {
        method: 'GET',
        headers: { Accept: 'application/json' },
      })
    })

    it('handles 503 analysis_not_run error', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({ detail: 'analysis_not_run' }),
      })

      try {
        await apiClient.getAlerts()
        expect.unreachable()
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        const apiErr = err as ApiError
        expect(apiErr.status).toBe(503)
        expect(apiErr.detail).toBe('analysis_not_run')
        expect(apiErr.isAnalysisNotRun).toBe(true)
      }
    })

    it('handles 422 invalid_filter_param error', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({ detail: 'invalid_filter_param' }),
      })

      try {
        // @ts-expect-error Testing runtime invalid param
        await apiClient.getAlerts({ status: 'INVALID_STATUS' })
        expect.unreachable()
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        const apiErr = err as ApiError
        expect(apiErr.status).toBe(422)
        expect(apiErr.detail).toBe('invalid_filter_param')
      }
    })
  })

  describe('getAlert', () => {
    const mockFullAlert: Alert = {
      alert_id: 'ALT_0001',
      alert_fingerprint: 'a'.repeat(64),
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
        nodes: [{ id: 'ACC_0917', type: 'account', label: 'ACC_0917', score: 0.93, metadata: {} }],
        edges: [],
        evidence_path: [],
      },
    }

    it('fetches full alert by id', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockFullAlert,
      })

      const alert = await apiClient.getAlert('ALT_0001')
      expect(alert).toEqual(mockFullAlert)
      expect(globalThis.fetch).toHaveBeenCalledWith('/api/alerts/ALT_0001', {
        method: 'GET',
        headers: { Accept: 'application/json' },
      })
    })

    it('rejects empty alert id', async () => {
      await expect(apiClient.getAlert('')).rejects.toThrow(ApiError)
    })

    it('handles 404 alert_not_found', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ detail: 'alert_not_found' }),
      })

      try {
        await apiClient.getAlert('ALT_9999')
        expect.unreachable()
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        const apiErr = err as ApiError
        expect(apiErr.status).toBe(404)
        expect(apiErr.isAlertNotFound).toBe(true)
      }
    })
  })

  describe('updateAlertReview', () => {
    const mockUpdatedAlert: Alert = {
      alert_id: 'ALT_0001',
      alert_fingerprint: 'a'.repeat(64),
      account_id: 'ACC_0917',
      created_at: '2026-10-01T12:00:00Z',
      status: 'CONFIRMED_FRAUD',
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
        status: 'CONFIRMED_FRAUD',
        is_stale: false,
        staleness_reason: null,
        analyst_id: 'ANALYST_01',
        updated_at: '2026-10-01T14:30:00Z',
        verdict: 'CONFIRMED_MULE_RING',
        notes: 'Verified 3-hop rapid layering.',
        previous_review: null,
      },
      evidence: {
        nodes: [{ id: 'ACC_0917', type: 'account', label: 'ACC_0917', score: 0.93, metadata: {} }],
        edges: [],
        evidence_path: [],
      },
    }

    it('sends PATCH request with JSON body and returns updated alert', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockUpdatedAlert,
      })

      const updatePayload = {
        status: 'CONFIRMED_FRAUD' as const,
        analyst_id: 'ANALYST_01',
        verdict: 'CONFIRMED_MULE_RING',
        notes: 'Verified 3-hop rapid layering.',
      }

      const res = await apiClient.updateAlertReview('ALT_0001', updatePayload)
      expect(res).toEqual(mockUpdatedAlert)
      expect(globalThis.fetch).toHaveBeenCalledWith('/api/alerts/ALT_0001', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify(updatePayload),
      })
    })

    it('rejects empty or whitespace alert ID with 400 ApiError', async () => {
      await expect(
        apiClient.updateAlertReview('', {
          status: 'INVESTIGATING',
          analyst_id: 'ANALYST_01',
        })
      ).rejects.toThrow(ApiError)

      await expect(
        apiClient.updateAlertReview('   ', {
          status: 'INVESTIGATING',
          analyst_id: 'ANALYST_01',
        })
      ).rejects.toThrow(ApiError)
    })

    it('identifies 422 invalid_review_transition error', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({ detail: 'invalid_review_transition' }),
      })

      try {
        await apiClient.updateAlertReview('ALT_0001', {
          status: 'DISMISSED_BENIGN',
          analyst_id: 'ANALYST_01',
        })
        expect.unreachable()
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        const apiErr = err as ApiError
        expect(apiErr.status).toBe(422)
        expect(apiErr.detail).toBe('invalid_review_transition')
        expect(apiErr.isInvalidReviewTransition).toBe(true)
      }
    })

    it('identifies 404 alert_not_found error', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ detail: 'alert_not_found' }),
      })

      try {
        await apiClient.updateAlertReview('ALT_9999', {
          status: 'INVESTIGATING',
          analyst_id: 'ANALYST_01',
        })
        expect.unreachable()
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        const apiErr = err as ApiError
        expect(apiErr.status).toBe(404)
        expect(apiErr.isAlertNotFound).toBe(true)
      }
    })

    it('handles network failure during review submission', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network disconnected'))

      try {
        await apiClient.updateAlertReview('ALT_0001', {
          status: 'INVESTIGATING',
          analyst_id: 'ANALYST_01',
        })
        expect.unreachable()
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        const apiErr = err as ApiError
        expect(apiErr.isNetworkError).toBe(true)
        expect(apiErr.detail).toContain('Network disconnected')
      }
    })
  })

  describe('runCounterfactual', () => {
    const mockCounterfactualResponse = {
      alert_id: 'ALT_0001',
      account_id: 'ACC_0917',
      original_score: 0.93,
      counterfactual_score: 0.21,
      score_delta: -0.72,
      original_flagged: true,
      counterfactual_flagged: false,
      rules_removed: ['RAPID_PASS_THROUGH', 'HIGH_FAN_IN'],
      rules_added: [],
      plausible_benign_alternative:
        'Hypothesis: Removal of transfer E1 breaks coordinated rapid fan-out pattern.',
    }

    it('submits valid counterfactual request and returns recomputed results', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockCounterfactualResponse,
      })

      const res = await apiClient.runCounterfactual('ALT_0001', {
        remove_edge_ids: ['E1'],
        suppress_device_sharing: true,
        suppress_complaints: false,
      })

      expect(res).toEqual(mockCounterfactualResponse)
      expect(globalThis.fetch).toHaveBeenCalledWith('/api/alerts/ALT_0001/counterfactual', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify({
          remove_edge_ids: ['E1'],
          suppress_device_sharing: true,
          suppress_complaints: false,
        }),
      })
    })

    it('rejects empty alert id', async () => {
      await expect(
        apiClient.runCounterfactual('', {
          remove_edge_ids: ['E1'],
        })
      ).rejects.toThrow(ApiError)
    })

    it('handles 422 empty_counterfactual_request', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({ detail: 'empty_counterfactual_request' }),
      })

      try {
        await apiClient.runCounterfactual('ALT_0001', {
          remove_edge_ids: [],
          suppress_device_sharing: false,
          suppress_complaints: false,
        })
        expect.unreachable()
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        const apiErr = err as ApiError
        expect(apiErr.status).toBe(422)
        expect(apiErr.isEmptyCounterfactual).toBe(true)
      }
    })

    it('handles 422 invalid_counterfactual_request for non-transfer edge', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({
          detail: 'invalid_counterfactual_request',
          error: 'Only transfer edges can be removed',
        }),
      })

      try {
        await apiClient.runCounterfactual('ALT_0001', {
          remove_edge_ids: ['DEV_EDGE_1'],
        })
        expect.unreachable()
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        const apiErr = err as ApiError
        expect(apiErr.status).toBe(422)
        expect(apiErr.isInvalidCounterfactual).toBe(true)
      }
    })
  })

  describe('getMetrics', () => {
    const mockMetrics: MetricsResponse = {
      generated_at: '2026-10-17T11:49:01Z',
      budget_k: 20,
      evaluation: {
        evaluated_on: 'held_out_accounts',
        n_accounts: 144,
        n_positive_accounts: 26,
        n_shared_device_accounts: 18,
      },
      ml: {
        threshold: 0.5,
        precision: 0.963,
        recall: 1.0,
        f1: 0.9812,
        true_positives: 26,
        false_positives: 1,
        false_negatives: 0,
        budget_metrics: {
          budget_k: 20,
          k_effective: 20,
          precision_at_k: 1.0,
          recall_at_k: 0.7692,
        },
        fairness: {
          fpr_benign_shared_device: 0.0,
          n_shared_device_evaluated: 18,
        },
      },
      baseline: {
        precision: 0.2258,
        recall: 0.2692,
        f1: 0.2456,
        true_positives: 7,
        false_positives: 24,
        false_negatives: 19,
        budget_metrics: {
          budget_k: 20,
          k_effective: 20,
          precision_at_k: 0.3,
          recall_at_k: 0.2308,
        },
      },
      by_scenario: [
        { scenario: 'mule_ring', n_accounts: 26, ml_flagged: 26, baseline_flagged: 7 },
        { scenario: 'normal', n_accounts: 100, ml_flagged: 1, baseline_flagged: 24 },
        { scenario: 'shared_device_family', n_accounts: 18, ml_flagged: 0, baseline_flagged: 0 },
      ],
    }

    it('fetches metrics with default budget (no query param)', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockMetrics,
      })

      const result = await apiClient.getMetrics()
      expect(result).toEqual(mockMetrics)
      expect(globalThis.fetch).toHaveBeenCalledWith('/api/metrics', {
        method: 'GET',
        headers: { Accept: 'application/json' },
      })
    })

    it('passes budget_k query param for K=10, 20, 50', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockMetrics,
      })

      await apiClient.getMetrics(10)
      expect(globalThis.fetch).toHaveBeenCalledWith('/api/metrics?budget_k=10', {
        method: 'GET',
        headers: { Accept: 'application/json' },
      })

      await apiClient.getMetrics(50)
      expect(globalThis.fetch).toHaveBeenCalledWith('/api/metrics?budget_k=50', {
        method: 'GET',
        headers: { Accept: 'application/json' },
      })
    })

    it('handles 503 analysis_not_run error', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({ detail: 'analysis_not_run' }),
      })

      try {
        await apiClient.getMetrics()
        expect.unreachable()
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        const apiErr = err as ApiError
        expect(apiErr.status).toBe(503)
        expect(apiErr.isAnalysisNotRun).toBe(true)
      }
    })

    it('handles 404 metrics_unavailable error', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ detail: 'metrics_unavailable' }),
      })

      try {
        await apiClient.getMetrics()
        expect.unreachable()
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        const apiErr = err as ApiError
        expect(apiErr.status).toBe(404)
        expect(apiErr.detail).toBe('metrics_unavailable')
      }
    })

    it('handles network error', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network failure'))

      try {
        await apiClient.getMetrics()
        expect.unreachable()
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        const apiErr = err as ApiError
        expect(apiErr.status).toBe(0)
      }
    })
  })
})
