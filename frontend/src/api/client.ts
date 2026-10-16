import type {
  Alert,
  AlertsResponse,
  AlertSummary,
  BudgetK,
  PipelineRunRequest,
  PipelineRunResponse,
  ReviewStatus,
  ReviewUpdateRequest,
  CounterfactualRequest,
  CounterfactualResponse,
} from '../types/api'

export class ApiError extends Error {
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

  get isAnalysisNotRun(): boolean {
    return this.status === 503 && this.detail === 'analysis_not_run'
  }

  get isAlertNotFound(): boolean {
    return this.status === 404 && this.detail === 'alert_not_found'
  }

  get isInvalidReviewTransition(): boolean {
    return this.status === 422 && this.detail === 'invalid_review_transition'
  }

  get isEmptyCounterfactual(): boolean {
    return this.status === 422 && this.detail === 'empty_counterfactual_request'
  }

  get isInvalidCounterfactual(): boolean {
    return (
      this.status === 422 &&
      (this.detail === 'invalid_counterfactual_request' ||
        this.detail === 'invalid_counterfactual_intervention')
    )
  }

  get isNetworkError(): boolean {
    return this.status === 0
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    let extra: Record<string, unknown> = {}
    try {
      const data = await response.json()
      if (typeof data === 'object' && data !== null) {
        if (typeof data.detail === 'string') {
          detail = data.detail
        } else if (Array.isArray(data.detail)) {
          detail = data.detail.map((d: { msg?: string }) => d.msg || 'Validation error').join('; ')
        }
        extra = data
      }
    } catch {
      // Body not JSON or empty
      detail = response.statusText || detail
    }
    throw new ApiError(response.status, detail, extra)
  }

  return response.json() as Promise<T>
}

async function safeFetch(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init)
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Network request failed'
    throw new ApiError(0, message, { originalError: err })
  }
}

export interface GetAlertsParams {
  status?: ReviewStatus
  budget_k?: BudgetK
}

export const apiClient = {
  /**
   * Run the analysis pipeline on the backend.
   * POST /api/pipeline/run
   */
  async runPipeline(request?: PipelineRunRequest): Promise<PipelineRunResponse> {
    const hasBody = request && request.as_of !== undefined && request.as_of !== null
    const response = await safeFetch('/api/pipeline/run', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: hasBody ? JSON.stringify({ as_of: request.as_of }) : undefined,
    })
    return handleResponse<PipelineRunResponse>(response)
  },

  /**
   * Retrieve active alert summaries, optionally filtered by status and budget K.
   * GET /api/alerts
   */
  async getAlerts(params?: GetAlertsParams): Promise<AlertSummary[]> {
    const query = new URLSearchParams()
    if (params?.status) {
      query.set('status', params.status)
    }
    if (params?.budget_k) {
      query.set('budget_k', String(params.budget_k))
    }

    const url = `/api/alerts${query.toString() ? `?${query.toString()}` : ''}`
    const response = await safeFetch(url, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    })
    const data = await handleResponse<AlertsResponse>(response)
    return data.alerts
  },

  /**
   * Retrieve full details of a specific alert, including 2-hop evidence subgraph.
   * GET /api/alerts/{alert_id}
   */
  async getAlert(alertId: string): Promise<Alert> {
    if (!alertId || !alertId.trim()) {
      throw new ApiError(400, 'alert_id is required')
    }
    const response = await safeFetch(`/api/alerts/${encodeURIComponent(alertId.trim())}`, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    })
    return handleResponse<Alert>(response)
  },

  /**
   * Update the human-review status of an alert.
   * PATCH /api/alerts/{alert_id}
   */
  async updateAlertReview(alertId: string, update: ReviewUpdateRequest): Promise<Alert> {
    if (!alertId || !alertId.trim()) {
      throw new ApiError(400, 'alert_id is required')
    }
    const response = await safeFetch(`/api/alerts/${encodeURIComponent(alertId.trim())}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(update),
    })
    return handleResponse<Alert>(response)
  },

  /**
   * Run a counterfactual what-if perturbation on an alert.
   * POST /api/alerts/{alert_id}/counterfactual
   */
  async runCounterfactual(
    alertId: string,
    request: CounterfactualRequest
  ): Promise<CounterfactualResponse> {
    if (!alertId || !alertId.trim()) {
      throw new ApiError(400, 'alert_id is required')
    }
    const response = await safeFetch(
      `/api/alerts/${encodeURIComponent(alertId.trim())}/counterfactual`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify({
          remove_edge_ids: request.remove_edge_ids ?? [],
          suppress_device_sharing: request.suppress_device_sharing ?? false,
          suppress_complaints: request.suppress_complaints ?? false,
        }),
      }
    )
    return handleResponse<CounterfactualResponse>(response)
  },
}
