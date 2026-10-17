import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { BenchmarkMetricsView } from './BenchmarkMetricsView'
import { apiClient, ApiError } from '../api/client'
import type { MetricsResponse } from '../types/api'

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return {
    ...actual,
    apiClient: {
      getMetrics: vi.fn(),
      runPipeline: vi.fn(),
    },
  }
})

describe('BenchmarkMetricsView Component', () => {
  const mockMetricsK20: MetricsResponse = {
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

  const mockMetricsK10: MetricsResponse = {
    ...mockMetricsK20,
    budget_k: 10,
    ml: {
      ...mockMetricsK20.ml,
      budget_metrics: {
        budget_k: 10,
        k_effective: 10,
        precision_at_k: 1.0,
        recall_at_k: 0.3846,
      },
    },
    baseline: {
      ...mockMetricsK20.baseline,
      budget_metrics: {
        budget_k: 10,
        k_effective: 10,
        precision_at_k: 0.4,
        recall_at_k: 0.1538,
      },
    },
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('displays loading indicator initially', () => {
    vi.mocked(apiClient.getMetrics).mockReturnValue(new Promise(() => {}))
    render(<BenchmarkMetricsView />)

    expect(screen.getByTestId('metrics-loading')).toBeInTheDocument()
    expect(screen.getByText(/Loading evaluation benchmark data from \/api\/metrics/i)).toBeInTheDocument()
  })

  it('renders HTTP 503 pre-analysis state and triggers onRunPipeline on user click', async () => {
    const onRun = vi.fn()
    vi.mocked(apiClient.getMetrics).mockRejectedValue(new ApiError(503, 'analysis_not_run'))

    render(<BenchmarkMetricsView onRunPipeline={onRun} />)

    const banner = await screen.findByTestId('metrics-preanalysis')
    expect(banner).toBeInTheDocument()
    expect(screen.getByText(/Analysis Pipeline Has Not Run Yet \(HTTP 503\)/i)).toBeInTheDocument()

    const runBtn = screen.getByTestId('btn-metrics-preanalysis-run')
    fireEvent.click(runBtn)
    expect(onRun).toHaveBeenCalledTimes(1)
  })

  it('renders HTTP 404 metrics-unavailable banner', async () => {
    vi.mocked(apiClient.getMetrics).mockRejectedValue(new ApiError(404, 'metrics_unavailable'))

    render(<BenchmarkMetricsView />)

    const banner = await screen.findByTestId('metrics-unavailable')
    expect(banner).toBeInTheDocument()
    expect(screen.getByText(/Benchmark Metrics Unavailable \(HTTP 404\)/i)).toBeInTheDocument()
  })

  it('renders error banner on unexpected failure and retries when clicked', async () => {
    vi.mocked(apiClient.getMetrics)
      .mockRejectedValueOnce(new ApiError(500, 'Internal Server Error'))
      .mockResolvedValueOnce(mockMetricsK20)

    render(<BenchmarkMetricsView />)

    const errorBanner = await screen.findByTestId('metrics-error-banner')
    expect(errorBanner).toBeInTheDocument()

    const retryBtn = screen.getByTestId('btn-retry-metrics')
    fireEvent.click(retryBtn)

    await waitFor(() => {
      expect(screen.getByTestId('metrics-display-content')).toBeInTheDocument()
    })
    expect(apiClient.getMetrics).toHaveBeenCalledTimes(2)
  })

  it('renders loaded metrics, metadata, denominators, disclaimers, and scenario breakdown', async () => {
    vi.mocked(apiClient.getMetrics).mockResolvedValue(mockMetricsK20)

    render(<BenchmarkMetricsView />)

    await screen.findByTestId('metrics-display-content')

    // Context metadata
    expect(screen.getByText(/held_out_accounts \(144 Accounts\)/i)).toBeInTheDocument()
    expect(screen.getByText(/26 Mule Ring Accounts/i)).toBeInTheDocument()
    expect(screen.getByText(/18 Benign Accounts/i)).toBeInTheDocument()
    expect(screen.getByText('2026-10-17T11:49:01Z')).toBeInTheDocument()

    // Disclaimers
    expect(screen.getByText(/Synthetic Benchmark Evaluation/i)).toBeInTheDocument()
    expect(screen.getByText(/uncalibrated ranking signals/i)).toBeInTheDocument()
    expect(screen.getByText(/Baseline unconstrained metrics evaluate all accounts/i)).toBeInTheDocument()
    expect(screen.getByText(/Specific to evaluated synthetic cohort; not a guarantee or proof of real-world fairness/i)).toBeInTheDocument()

    // ML Metrics
    expect(screen.getByTestId('ml-precision').textContent).toBe('96.30%')
    expect(screen.getByTestId('ml-recall').textContent).toBe('100.00%')
    expect(screen.getByTestId('ml-f1').textContent).toBe('0.9812')
    expect(screen.getByTestId('ml-precision-k').textContent).toBe('100.00%')
    expect(screen.getByTestId('ml-recall-k').textContent).toBe('76.92%')

    // Visible fractional denominators
    expect(screen.getByText('TP / (TP + FP): 26 / 27')).toBeInTheDocument()
    expect(screen.getByText('TP / Actual Positives: 26 / 26')).toBeInTheDocument()

    // Confusion counts
    const mlCounts = screen.getByTestId('ml-confusion-counts')
    expect(mlCounts.textContent).toContain('26')
    expect(mlCounts.textContent).toContain('1')
    expect(mlCounts.textContent).toContain('0')

    // Baseline Metrics
    expect(screen.getByTestId('baseline-precision').textContent).toBe('22.58%')
    expect(screen.getByTestId('baseline-recall').textContent).toBe('26.92%')
    expect(screen.getByTestId('baseline-f1').textContent).toBe('0.2456')
    expect(screen.getByTestId('baseline-precision-k').textContent).toBe('30.00%')
    expect(screen.getByTestId('baseline-recall-k').textContent).toBe('23.08%')
    expect(screen.getByText('TP / (TP + FP): 7 / 31')).toBeInTheDocument()
    expect(screen.getByText('TP / Actual Positives: 7 / 26')).toBeInTheDocument()

    // Fairness metric
    expect(screen.getByTestId('fairness-fpr').textContent).toBe('0.00%')
    expect(screen.getByText(/Evaluated on 18 benign shared-device family accounts/i)).toBeInTheDocument()

    // Scenario rows
    expect(screen.getByTestId('row-scenario-mule_ring')).toBeInTheDocument()
    expect(screen.getByTestId('row-scenario-normal')).toBeInTheDocument()
    expect(screen.getByTestId('row-scenario-shared_device_family')).toBeInTheDocument()
  })

  it('provides an accessible, keyboard-scrollable container for the scenario breakdown table', async () => {
    vi.mocked(apiClient.getMetrics).mockResolvedValue(mockMetricsK20)

    render(<BenchmarkMetricsView />)

    await screen.findByTestId('metrics-display-content')

    const tableRegion = screen.getByRole('region', { name: /Scenario Detection Breakdown/i })
    expect(tableRegion).toBeInTheDocument()
    expect(tableRegion).toHaveAttribute('tabIndex', '0')
    expect(tableRegion).toHaveAttribute('aria-labelledby', 'scenario-breakdown-heading')
    expect(screen.getByText(/Scroll horizontally →/i)).toBeInTheDocument()
  })

  it('switches capacity budget K dynamically and refetches metrics', async () => {
    vi.mocked(apiClient.getMetrics)
      .mockResolvedValueOnce(mockMetricsK20)
      .mockResolvedValueOnce(mockMetricsK10)

    render(<BenchmarkMetricsView />)

    await screen.findByTestId('metrics-display-content')
    expect(apiClient.getMetrics).toHaveBeenCalledWith(20)

    const btnK10 = screen.getByTestId('btn-budget-k-10')
    fireEvent.click(btnK10)

    await waitFor(() => {
      expect(apiClient.getMetrics).toHaveBeenCalledWith(10)
    })
    expect(btnK10).toHaveAttribute('aria-pressed', 'true')
  })

  it('handles null metrics and zero denominators safely without crashing or displaying NaN', async () => {
    const mockZeroMetrics: MetricsResponse = {
      generated_at: '2026-10-17T11:49:01Z',
      budget_k: 20,
      evaluation: {
        evaluated_on: 'held_out_accounts',
        n_accounts: 0,
        n_positive_accounts: 0,
        n_shared_device_accounts: 0,
      },
      ml: {
        threshold: 0.5,
        precision: null,
        recall: null,
        f1: null,
        true_positives: 0,
        false_positives: 0,
        false_negatives: 0,
        budget_metrics: {
          budget_k: 20,
          k_effective: 0,
          precision_at_k: null,
          recall_at_k: null,
        },
        fairness: {
          fpr_benign_shared_device: null,
          n_shared_device_evaluated: 0,
        },
      },
      baseline: {
        precision: null,
        recall: null,
        f1: null,
        true_positives: 0,
        false_positives: 0,
        false_negatives: 0,
        budget_metrics: {
          budget_k: 20,
          k_effective: 0,
          precision_at_k: null,
          recall_at_k: null,
        },
      },
      by_scenario: [
        { scenario: 'mule_ring', n_accounts: 0, ml_flagged: 0, baseline_flagged: 0 },
      ],
    }

    vi.mocked(apiClient.getMetrics).mockResolvedValue(mockZeroMetrics)

    render(<BenchmarkMetricsView />)

    await screen.findByTestId('metrics-display-content')

    // Null metrics should render as em-dash '—', not NaN or 0%
    expect(screen.getByTestId('ml-precision').textContent).toBe('—')
    expect(screen.getByTestId('ml-recall').textContent).toBe('—')
    expect(screen.getByTestId('ml-f1').textContent).toBe('—')
    expect(screen.getByTestId('ml-precision-k').textContent).toBe('—')
    expect(screen.getByTestId('ml-recall-k').textContent).toBe('—')
    expect(screen.getByTestId('fairness-fpr').textContent).toBe('—')
  })

  it('refreshes metrics when clicking the refresh button', async () => {
    vi.mocked(apiClient.getMetrics).mockResolvedValue(mockMetricsK20)

    render(<BenchmarkMetricsView />)

    await screen.findByTestId('metrics-display-content')
    expect(apiClient.getMetrics).toHaveBeenCalledTimes(1)

    const refreshBtn = screen.getByTestId('btn-refresh-metrics')
    fireEvent.click(refreshBtn)

    await waitFor(() => {
      expect(apiClient.getMetrics).toHaveBeenCalledTimes(2)
    })
  })
})
