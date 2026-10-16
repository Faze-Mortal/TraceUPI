import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { EvidenceGraphCanvas } from './EvidenceGraphCanvas'
import type { Evidence } from '../types/api'

describe('EvidenceGraphCanvas Component', () => {
  const mockEvidence: Evidence = {
    nodes: [
      { id: 'ACC_0917', type: 'account', label: 'ACC_0917', score: 0.93, metadata: {} },
      { id: 'ACC_0042', type: 'account', label: 'ACC_0042', score: 0.12, metadata: {} },
      { id: 'DEV_0031', type: 'device', label: 'DEV_0031', score: null, metadata: {} },
      { id: 'MER_0005', type: 'merchant', label: 'MER_0005', score: null, metadata: { category: 'ELECTRONICS' } },
      { id: 'CMP_0012', type: 'complaint', label: 'CMP_0012', score: null, metadata: { category: 'PHISHING_SCAM' } },
    ],
    edges: [
      {
        id: 'E1',
        source: 'ACC_0042',
        target: 'ACC_0917',
        type: 'transfer',
        txn_id: 'T000123',
        amount_inr: 4999.0,
        timestamp: '2026-10-01T10:15:30Z',
      },
      {
        id: 'E2',
        source: 'ACC_0042',
        target: 'DEV_0031',
        type: 'uses_device',
        txn_id: null,
        amount_inr: null,
        timestamp: null,
      },
      {
        id: 'E3',
        source: 'ACC_0917',
        target: 'MER_0005',
        type: 'merchant_profile',
        txn_id: null,
        amount_inr: null,
        timestamp: null,
      },
      {
        id: 'E4',
        source: 'ACC_0917',
        target: 'CMP_0012',
        type: 'has_complaint',
        txn_id: null,
        amount_inr: null,
        timestamp: null,
      },
    ],
    evidence_path: ['E1'],
  }

  it('renders empty state when evidence is null or nodes are empty', () => {
    const { rerender } = render(<EvidenceGraphCanvas evidence={null} />)
    expect(screen.getByText(/No Graph Evidence Available/i)).toBeInTheDocument()

    rerender(<EvidenceGraphCanvas evidence={{ nodes: [], edges: [], evidence_path: [] }} />)
    expect(screen.getByText(/No Graph Evidence Available/i)).toBeInTheDocument()
  })

  it('renders graph canvas with nodes, edges, and contract cap meta banner', () => {
    render(<EvidenceGraphCanvas evidence={mockEvidence} targetAccountId="ACC_0917" />)

    // Meta banner
    expect(screen.getByText('Nodes: 5/25')).toBeInTheDocument()
    expect(screen.getByText('Edges: 4/60')).toBeInTheDocument()
    expect(screen.getByText('Path: 1/10 hops')).toBeInTheDocument()

    // SVG elements rendered
    expect(screen.getByRole('img', { name: /Heterogeneous Evidence Subgraph Canvas/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Node ACC_0917: account, Score: 0.93/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Node DEV_0031: device, Score: null/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Node MER_0005: merchant, Score: null/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Node CMP_0012: complaint, Score: null/i })).toBeInTheDocument()
  })

  it('selects a node on click and displays its details in the drawer', () => {
    render(<EvidenceGraphCanvas evidence={mockEvidence} targetAccountId="ACC_0917" />)

    const accNode = screen.getByRole('button', { name: /Node ACC_0917: account/i })
    fireEvent.click(accNode)

    expect(screen.getByRole('region', { name: /Selected Element Details/i })).toBeInTheDocument()
    expect(screen.getByText(/NODE · ACCOUNT/i)).toBeInTheDocument()
    expect(screen.getByText('0.9300')).toBeInTheDocument()

    // Close drawer
    const closeBtn = screen.getByRole('button', { name: /Close inspector/i })
    fireEvent.click(closeBtn)
    expect(screen.queryByRole('region', { name: /Selected Element Details/i })).not.toBeInTheDocument()
  })

  it('selects an edge on click and displays transfer details in the drawer', () => {
    render(<EvidenceGraphCanvas evidence={mockEvidence} targetAccountId="ACC_0917" />)

    const transferEdge = screen.getByRole('button', { name: /Edge E1: ACC_0042 to ACC_0917/i })
    fireEvent.click(transferEdge)

    const drawer = screen.getByRole('region', { name: /Selected Element Details/i })
    expect(drawer).toBeInTheDocument()
    expect(screen.getByText(/EDGE · TRANSFER/i)).toBeInTheDocument()
    expect(screen.getAllByText('Rs 4,999').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('T000123')).toBeInTheDocument()
    expect(screen.getByText('YES (Flagged Hop)')).toBeInTheDocument()
  })

  it('toggles evidence path highlighting on button click', () => {
    render(<EvidenceGraphCanvas evidence={mockEvidence} targetAccountId="ACC_0917" />)

    const pathToggle = screen.getByRole('button', { name: /Evidence Path \(1\)/i })
    expect(pathToggle).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(pathToggle)
    expect(pathToggle).toHaveAttribute('aria-pressed', 'false')
  })

  it('handles empty evidence path without errors', () => {
    const emptyPathEvidence: Evidence = {
      ...mockEvidence,
      evidence_path: [],
    }

    render(<EvidenceGraphCanvas evidence={emptyPathEvidence} targetAccountId="ACC_0917" />)

    expect(screen.getByText(/No contiguous path \(isolated features\)/i)).toBeInTheDocument()
    expect(screen.getByText('Path: 0/10 hops')).toBeInTheDocument()
  })

  it('switches to accessible table view and renders structured tables', () => {
    render(<EvidenceGraphCanvas evidence={mockEvidence} targetAccountId="ACC_0917" />)

    const tableTab = screen.getByRole('tab', { name: /Accessible Table View/i })
    fireEvent.click(tableTab)

    expect(tableTab).toHaveAttribute('aria-selected', 'true')

    // Nodes Table
    expect(screen.getByRole('table', { name: /Evidence Graph Nodes Table/i })).toBeInTheDocument()
    expect(screen.getAllByRole('cell', { name: 'ACC_0917' }).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByRole('cell', { name: 'DEV_0031' }).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByRole('cell', { name: 'MER_0005' }).length).toBeGreaterThanOrEqual(1)

    // Edges Table
    expect(screen.getByRole('table', { name: /Evidence Graph Edges Table/i })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'E1' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'Rs 4,999' })).toBeInTheDocument()

    // Evidence Path Sequence list
    expect(screen.getByText(/3\. Traceable Evidence Path Walk \(1 Hops\)/i)).toBeInTheDocument()
    expect(screen.getByText(/Hop 1:/i)).toBeInTheDocument()
  })

  it('supports keyboard navigation on nodes and edges', () => {
    render(<EvidenceGraphCanvas evidence={mockEvidence} targetAccountId="ACC_0917" />)

    const devNode = screen.getByRole('button', { name: /Node DEV_0031/i })
    fireEvent.keyDown(devNode, { key: 'Enter' })

    expect(screen.getByText(/NODE · DEVICE/i)).toBeInTheDocument()

    const edge = screen.getByRole('button', { name: /Edge E1/i })
    fireEvent.keyDown(edge, { key: ' ' })

    expect(screen.getByText(/EDGE · TRANSFER/i)).toBeInTheDocument()
  })

  it('suppresses non-highlighted edge labels by default and reveals them when Show All Amounts is toggled', () => {
    const multiTransferEvidence: Evidence = {
      nodes: [
        { id: 'ACC_0917', type: 'account', label: 'ACC_0917', score: 0.93, metadata: {} },
        { id: 'ACC_0042', type: 'account', label: 'ACC_0042', score: 0.12, metadata: {} },
        { id: 'ACC_0099', type: 'account', label: 'ACC_0099', score: 0.25, metadata: {} },
      ],
      edges: [
        {
          id: 'E1',
          source: 'ACC_0042',
          target: 'ACC_0917',
          type: 'transfer',
          txn_id: 'T000123',
          amount_inr: 4999.0,
          timestamp: '2026-10-01T10:15:30Z',
        },
        {
          id: 'E2',
          source: 'ACC_0917',
          target: 'ACC_0099',
          type: 'transfer',
          txn_id: 'T000124',
          amount_inr: 2500.0,
          timestamp: '2026-10-01T10:16:00Z',
        },
      ],
      evidence_path: ['E1'], // Only E1 is in key trail
    }

    render(<EvidenceGraphCanvas evidence={multiTransferEvidence} targetAccountId="ACC_0917" />)

    // Key trail transfer E1 is highlighted, so Rs 4,999 is visible
    expect(screen.getByText('Rs 4,999')).toBeInTheDocument()

    // Non-trail transfer E2 (Rs 2,500) is suppressed by default to prevent visual noise
    expect(screen.queryByText('Rs 2,500')).not.toBeInTheDocument()

    // Toggle "Show All Amounts"
    const toggleAmountsBtn = screen.getByRole('button', { name: /Show All Amounts/i })
    fireEvent.click(toggleAmountsBtn)

    // Non-trail amount is now revealed
    expect(screen.getByText('Rs 2,500')).toBeInTheDocument()

    // Toggle off ("Hide Extra Amounts")
    fireEvent.click(toggleAmountsBtn)
    expect(screen.queryByText('Rs 2,500')).not.toBeInTheDocument()
  })

  it('renders target account with distinctive TARGET ACCOUNT role label', () => {
    render(<EvidenceGraphCanvas evidence={mockEvidence} targetAccountId="ACC_0917" />)
    expect(screen.getByText('TARGET ACCOUNT')).toBeInTheDocument()
  })

  it('renders guidance banner explaining account-level alert and non-incrimination notice', () => {
    render(<EvidenceGraphCanvas evidence={mockEvidence} targetAccountId="ACC_0917" />)
    expect(screen.getByText(/Account-Level Alert & Connected Evidence Subgraph/i)).toBeInTheDocument()
    expect(screen.getByText(/evaluated at the/i)).toBeInTheDocument()
    expect(screen.getByText(/prove wrongdoing, criminal guilt, or legal liability/i)).toBeInTheDocument()
  })

  it('renders comprehensive visual symbol guide legend', () => {
    render(<EvidenceGraphCanvas evidence={mockEvidence} targetAccountId="ACC_0917" />)
    expect(screen.getByText(/Graph Symbol Guide:/i)).toBeInTheDocument()
    expect(screen.getByText(/Target Account \(ACC_0917\)/i)).toBeInTheDocument()
    expect(screen.getByText(/Connected Accounts/i)).toBeInTheDocument()
    expect(screen.getByText(/Directed Money Transfers/i)).toBeInTheDocument()
    expect(screen.getAllByText(/Key Transaction Trail/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/Shared Devices/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/Merchants & Aggregators/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/Consumer Complaints/i).length).toBeGreaterThanOrEqual(1)
  })

  it('switches to Chronological Timeline and displays sorted events with key trail badges', () => {
    const multiEventEvidence: Evidence = {
      nodes: [
        { id: 'ACC_0917', type: 'account', label: 'ACC_0917', score: 0.93, metadata: {} },
        { id: 'ACC_0042', type: 'account', label: 'ACC_0042', score: 0.12, metadata: {} },
        { id: 'CMP_0012', type: 'complaint', label: 'CMP_0012', score: null, metadata: { category: 'UPI_FRAUD', filed_at: '2026-10-01T10:20:00Z' } },
      ],
      edges: [
        {
          id: 'E1',
          source: 'ACC_0042',
          target: 'ACC_0917',
          type: 'transfer',
          txn_id: 'T000100',
          amount_inr: 8500.5,
          timestamp: '2026-10-01T10:10:00Z',
        },
        {
          id: 'E2',
          source: 'ACC_0917',
          target: 'CMP_0012',
          type: 'has_complaint',
          txn_id: null,
          amount_inr: null,
          timestamp: '2026-10-01T10:20:00Z',
        },
      ],
      evidence_path: ['E1'],
    }

    render(<EvidenceGraphCanvas evidence={multiEventEvidence} targetAccountId="ACC_0917" />)

    // Switch to Timeline tab
    const timelineTab = screen.getByTestId('tab-timeline-view')
    expect(timelineTab).toBeInTheDocument()
    fireEvent.click(timelineTab)

    expect(timelineTab).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText(/Chronological Event Timeline/i)).toBeInTheDocument()
    expect(screen.getByText(/2 Timestamped Events/i)).toBeInTheDocument()

    // Event 1: Money Transfer
    expect(screen.getByText(/^MONEY TRANSFER$/i)).toBeInTheDocument()
    expect(screen.getByText(/T000100/)).toBeInTheDocument()
    expect(screen.getByText(/₹8,500.50/)).toBeInTheDocument()
    expect(screen.getByText(/★ KEY TRANSACTION TRAIL/i)).toBeInTheDocument()

    // Event 2: Consumer Complaint
    expect(screen.getByText(/^CONSUMER COMPLAINT$/i)).toBeInTheDocument()
    expect(screen.getByText(/UPI_FRAUD/i)).toBeInTheDocument()

    // Click event to select it and test drawer synchronization
    const eventCard = screen.getByTestId('timeline-event-E1')
    fireEvent.click(eventCard)
    expect(screen.getByRole('region', { name: /Selected Element Details/i })).toBeInTheDocument()
    expect(screen.getByText(/EDGE · TRANSFER/i)).toBeInTheDocument()
  })
})
