import React, { useState, useMemo, useRef } from 'react'
import type { EdgeType, Evidence, EvidenceEdge, EvidenceNode, NodeType } from '../types/api'
import { computeDeterministicGraphLayout } from './graphLayout'

interface EvidenceGraphCanvasProps {
  evidence: Evidence | null
  targetAccountId?: string
  className?: string
}

type SelectedElement =
  | { type: 'node'; data: EvidenceNode }
  | { type: 'edge'; data: EvidenceEdge }
  | null

function getNodeColor(
  type: NodeType,
  score: number | null = null,
  isTarget: boolean = false,
  metadata?: Record<string, unknown>
): { fill: string; stroke: string; text: string } {
  if (isTarget) {
    const isHigh = score !== null && score >= 0.8
    return {
      fill: isHigh ? '#35221F' : '#352B1E',
      stroke: isHigh ? '#C65B4A' : '#D4A15A',
      text: '#EAE7DF',
    }
  }

  if (type === 'account') {
    if (score !== null && score >= 0.8) {
      return { fill: '#35221F', stroke: '#C65B4A', text: '#C65B4A' }
    }
    if (score !== null && score >= 0.5) {
      return { fill: '#352B1E', stroke: '#D4A15A', text: '#D4A15A' }
    }
    if (metadata?.verified) {
      return { fill: '#222D23', stroke: '#6E8F72', text: '#6E8F72' }
    }
    if (metadata?.is_linked) {
      return { fill: '#22251F', stroke: '#8A8F85', text: '#A7A89E' }
    }
    return { fill: '#1A1C19', stroke: '#6B6F67', text: '#A7A89E' }
  }

  if (type === 'device') {
    return { fill: '#22251F', stroke: '#8A8F85', text: '#A7A89E' }
  }

  if (type === 'merchant') {
    return { fill: '#1A1C19', stroke: '#8A8F85', text: '#A7A89E' }
  }

  if (type === 'complaint') {
    return { fill: '#35221F', stroke: '#C65B4A', text: '#C65B4A' }
  }

  return { fill: '#1A1C19', stroke: '#6B6F67', text: '#EAE7DF' }
}

function getEdgeColor(type: EdgeType, isPath: boolean, isSelected: boolean, isHighRiskPath: boolean = false): string {
  if (isSelected) return '#EAE7DF'
  if (isPath) return isHighRiskPath ? '#C65B4A' : '#D4A15A'
  switch (type) {
    case 'transfer':
      return '#3A3F37'
    case 'uses_device':
      return '#8A8F85'
    case 'merchant_profile':
      return '#8A8F85'
    case 'has_complaint':
      return '#C65B4A'
    default:
      return '#3A3F37'
  }
}

export const EvidenceGraphCanvas: React.FC<EvidenceGraphCanvasProps> = ({
  evidence,
  targetAccountId,
  className = '',
}) => {
  const [activeTab, setActiveTab] = useState<'canvas' | 'table' | 'timeline'>('canvas')
  const [selectedElement, setSelectedElement] = useState<SelectedElement>(null)
  const [isPathHighlightActive, setIsPathHighlightActive] = useState<boolean>(true)
  const [showAllEdgeAmounts, setShowAllEdgeAmounts] = useState<boolean>(false)
  const [zoomLevel, setZoomLevel] = useState<number>(1)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  const nodes = evidence?.nodes || []
  const edges = evidence?.edges || []
  const evidencePath = evidence?.evidence_path || []

  // Fast lookup set for evidence path edges
  const pathEdgeSet = useMemo(() => new Set(evidencePath), [evidencePath])

  // Nodes in evidence path
  const pathNodeSet = useMemo(() => {
    const set = new Set<string>()
    for (const e of edges) {
      if (pathEdgeSet.has(e.id)) {
        set.add(e.source)
        set.add(e.target)
      }
    }
    return set
  }, [edges, pathEdgeSet])

  // Extract and chronologically sort all timestamped transfer and complaint events
  const timelineEvents = useMemo(() => {
    const list: Array<{
      id: string
      edgeId: string | null
      nodeId: string | null
      timestamp: string
      date: Date
      type: 'transfer' | 'complaint'
      source: string
      target: string
      amountInr: number | null
      txnId: string | null
      isKeyTrail: boolean
      category?: string
    }> = []

    for (const edge of edges) {
      if (edge.timestamp) {
        const isKeyTrail = pathEdgeSet.has(edge.id)
        if (edge.type === 'transfer') {
          list.push({
            id: edge.id,
            edgeId: edge.id,
            nodeId: null,
            timestamp: edge.timestamp,
            date: new Date(edge.timestamp),
            type: 'transfer',
            source: edge.source,
            target: edge.target,
            amountInr: edge.amount_inr,
            txnId: edge.txn_id,
            isKeyTrail,
          })
        } else if (edge.type === 'has_complaint') {
          const compNode = nodes.find((n) => n.type === 'complaint' && (n.id === edge.target || n.id === edge.source))
          const category = (compNode?.metadata?.category as string) || 'Consumer Grievance'
          list.push({
            id: edge.id,
            edgeId: edge.id,
            nodeId: compNode?.id || null,
            timestamp: edge.timestamp,
            date: new Date(edge.timestamp),
            type: 'complaint',
            source: edge.source,
            target: edge.target,
            amountInr: null,
            txnId: null,
            category,
            isKeyTrail: false,
          })
        }
      }
    }

    // Also check complaint nodes if they have filed_at timestamp and weren't in edges
    for (const node of nodes) {
      if (node.type === 'complaint' && node.metadata?.filed_at) {
        const filedAt = String(node.metadata.filed_at)
        const alreadyInList = list.some((item) => item.target === node.id || item.nodeId === node.id)
        if (!alreadyInList) {
          list.push({
            id: node.id,
            edgeId: null,
            nodeId: node.id,
            timestamp: filedAt,
            date: new Date(filedAt),
            type: 'complaint',
            source: targetAccountId || 'ACCOUNT',
            target: node.id,
            amountInr: null,
            txnId: null,
            category: (node.metadata.category as string) || 'Consumer Grievance',
            isKeyTrail: false,
          })
        }
      }
    }

    return list.sort((a, b) => a.date.getTime() - b.date.getTime())
  }, [edges, nodes, pathEdgeSet, targetAccountId])

  // Compute deterministic layout with clean sector separation
  const { positions, width, height } = useMemo(() => {
    return computeDeterministicGraphLayout(nodes, edges, targetAccountId, 880, 560)
  }, [nodes, edges, targetAccountId])

  // Handle zoom
  const handleZoomIn = () => setZoomLevel((z) => Math.min(2.0, Number((z + 0.2).toFixed(1))))
  const handleZoomOut = () => setZoomLevel((z) => Math.max(0.6, Number((z - 0.2).toFixed(1))))
  const handleZoomReset = () => {
    setZoomLevel(1)
    setSelectedElement(null)
  }

  if (!evidence || nodes.length === 0) {
    return (
      <div className={`evidence-canvas-empty ${className}`} role="region" aria-label="Evidence Graph Area">
        <div className="canvas-empty-state">
          <svg viewBox="0 0 24 24" width="44" height="44" fill="none" stroke="var(--color-text-muted, #7B7F76)" strokeWidth="1.5">
            <circle cx="18" cy="5" r="3" />
            <circle cx="6" cy="12" r="3" />
            <circle cx="18" cy="19" r="3" />
            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
            <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
          </svg>
          <h3 className="empty-title">No Graph Evidence Available</h3>
          <p className="empty-subtitle">
            Select an alert from the queue to view its entity connections, money trail, and shared devices.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className={`evidence-graph-container ${className}`} role="region" aria-label="Interactive Evidence Graph">
      {/* Plain-English Explanation Banner */}
      <div className="graph-explanation-banner" role="region" aria-label="Investigation Scope Guidance">
        <div className="explanation-title-row">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="var(--brand-terracotta, #A56F58)" strokeWidth="2" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
          <strong className="explanation-title">Account-Level Alert &amp; Connected Evidence Subgraph</strong>
        </div>
        <p className="explanation-text">
          This alert is evaluated at the <strong>account level</strong> for main account <strong className="font-mono text-amber">{targetAccountId}</strong>.
          The graph visualizes 2-hop connected transactions, shared devices, and consumer complaints to assist human triage.
          Connected counterparties and highlighted key transaction trails provide contextual investigative leads—they do <strong>not</strong> prove wrongdoing, criminal guilt, or legal liability.
        </p>
      </div>

      {/* Canvas Toolbar with Plain-English Controls */}
      <div className="graph-toolbar">
        <div className="tab-toggle-group" role="tablist" aria-label="Graph View Mode">
          <button
            type="button"
            role="tab"
            id="tab-canvas-view"
            aria-selected={activeTab === 'canvas'}
            aria-controls="panel-canvas-view"
            className={`btn-tab ${activeTab === 'canvas' ? 'active' : ''}`}
            onClick={() => setActiveTab('canvas')}
          >
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <circle cx="18" cy="5" r="3" />
              <circle cx="6" cy="12" r="3" />
              <circle cx="18" cy="19" r="3" />
              <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
              <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
            </svg>
            Interactive Map
          </button>
          <button
            type="button"
            role="tab"
            id="tab-table-view"
            aria-selected={activeTab === 'table'}
            aria-controls="panel-table-view"
            className={`btn-tab ${activeTab === 'table' ? 'active' : ''}`}
            onClick={() => setActiveTab('table')}
          >
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
            Accessible Table View
          </button>
          <button
            type="button"
            role="tab"
            id="tab-timeline-view"
            data-testid="tab-timeline-view"
            aria-selected={activeTab === 'timeline'}
            aria-controls="panel-timeline-view"
            className={`btn-tab ${activeTab === 'timeline' ? 'active' : ''}`}
            onClick={() => setActiveTab('timeline')}
          >
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            Chronological Timeline ({timelineEvents.length})
          </button>
        </div>

        {activeTab === 'canvas' && (
          <div className="graph-actions-group">
            {/* Key Transaction Trail Toggle */}
            <button
              type="button"
              className={`btn-tool font-mono ${isPathHighlightActive ? 'active' : ''}`}
              onClick={() => setIsPathHighlightActive(!isPathHighlightActive)}
              title="Highlight the suspicious key transaction trail across accounts"
              aria-pressed={isPathHighlightActive}
              aria-label={`Key transaction trail Evidence Path (${evidencePath.length})`}
            >
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
              </svg>
              Key transaction trail (Evidence Path: {evidencePath.length})
            </button>

            {/* Toggle All Edge Amounts: Progressive Disclosure */}
            <button
              type="button"
              className={`btn-tool font-mono ${showAllEdgeAmounts ? 'active' : ''}`}
              onClick={() => setShowAllEdgeAmounts(!showAllEdgeAmounts)}
              title="Show transaction amount tags on all edges (normally shown only on key trail or selected edge)"
              aria-pressed={showAllEdgeAmounts}
            >
              {showAllEdgeAmounts ? 'Hide Extra Amounts' : 'Show All Amounts'}
            </button>

            {/* Zoom Controls */}
            <div className="zoom-controls">
              <button
                type="button"
                className="btn-zoom"
                onClick={handleZoomIn}
                aria-label="Zoom in graph"
                title="Zoom In"
              >
                +
              </button>
              <span className="zoom-indicator font-mono">{Math.round(zoomLevel * 100)}%</span>
              <button
                type="button"
                className="btn-zoom"
                onClick={handleZoomOut}
                aria-label="Zoom out graph"
                title="Zoom Out"
              >
                -
              </button>
              <button
                type="button"
                className="btn-zoom-reset font-mono"
                onClick={handleZoomReset}
                title="Reset zoom and center view"
              >
                Reset
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Graph Telemetry Banner */}
      <div className="graph-meta-banner font-mono">
        <span className="meta-item">Nodes: {nodes.length}/25</span>
        <span className="meta-item">Edges: {edges.length}/60</span>
        <span className="meta-item">Path: {evidencePath.length}/10 hops</span>
        {evidencePath.length === 0 && (
          <span className="meta-tag-warning">No contiguous path (isolated features)</span>
        )}
        <span className="meta-tip text-muted">
          Tip: Click any node or transfer line to inspect full details below.
        </span>
      </div>

      {/* Main Tab Panels */}
      {activeTab === 'canvas' ? (
        <div id="panel-canvas-view" role="tabpanel" aria-labelledby="tab-canvas-view" className="canvas-wrapper">
          <svg
            ref={svgRef}
            viewBox={`0 0 ${width} ${height}`}
            className="graph-svg"
            role="img"
            aria-label="Heterogeneous Evidence Subgraph Canvas"
            onClick={(e) => {
              if (e.target === svgRef.current) {
                setSelectedElement(null)
              }
            }}
          >
            <defs>
              {/* Arrowheads for different edge types */}
              <marker id="arrow-transfer" viewBox="0 0 10 10" refX="28" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 1 L 10 5 L 0 9 z" fill="#3A3F37" />
              </marker>
              <marker id="arrow-path" viewBox="0 0 10 10" refX="28" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#D4A15A" />
              </marker>
              <marker id="arrow-merchant" viewBox="0 0 10 10" refX="28" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 1 L 10 5 L 0 9 z" fill="#8A8F85" />
              </marker>
              <marker id="arrow-selected" viewBox="0 0 10 10" refX="28" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#EAE7DF" />
              </marker>
              <marker id="arrow-complaint" viewBox="0 0 10 10" refX="28" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 1 L 10 5 L 0 9 z" fill="#C65B4A" />
              </marker>

              {/* Restrained subtle glow for key trail */}
              <filter id="path-glow" x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="2.5" result="blur" />
                <feComposite in="SourceGraphic" in2="blur" operator="over" />
              </filter>
            </defs>

            {/* Transform Container with Zoom */}
            <g transform={`translate(${width * (1 - zoomLevel) / 2}, ${height * (1 - zoomLevel) / 2}) scale(${zoomLevel})`}>
              {/* Edges Layer */}
              <g className="edges-layer" aria-label="Graph Edges">
                {edges.map((edge) => {
                  const p1 = positions[edge.source]
                  const p2 = positions[edge.target]
                  if (!p1 || !p2) return null

                  const isPath = pathEdgeSet.has(edge.id)
                  const isSelected = selectedElement?.type === 'edge' && selectedElement.data.id === edge.id
                  const isDimmed = isPathHighlightActive && !isPath && evidencePath.length > 0 && !isSelected
                  const isIncidentEdge = hoveredNodeId ? (edge.source === hoveredNodeId || edge.target === hoveredNodeId) : false
                  const isHoverDimmed = hoveredNodeId ? !isIncidentEdge : false

                  const color = getEdgeColor(edge.type, isPath, isSelected)
                  const strokeWidth = isSelected ? 3.5 : isIncidentEdge ? 2.5 : isPath && isPathHighlightActive ? 2.4 : 1.2
                  const isDashed = edge.type === 'uses_device' || edge.type === 'has_complaint'

                  // Arrowhead selection
                  let markerEnd = 'url(#arrow-transfer)'
                  if (isSelected) markerEnd = 'url(#arrow-selected)'
                  else if (isPath && isPathHighlightActive) markerEnd = 'url(#arrow-path)'
                  else if (edge.type === 'merchant_profile') markerEnd = 'url(#arrow-merchant)'
                  else if (edge.type === 'has_complaint') markerEnd = 'url(#arrow-complaint)'

                  // Midpoint for amount tag
                  const midX = (p1.x + p2.x) / 2
                  const midY = (p1.y + p2.y) / 2

                  // Progressive disclosure: only show amount tag if on key trail, selected, or explicitly enabled
                  const shouldShowAmount =
                    edge.amount_inr !== null &&
                    (showAllEdgeAmounts || isSelected || (isPath && isPathHighlightActive))

                  const edgeOpacity = isHoverDimmed ? 0.12 : isDimmed ? 0.25 : isIncidentEdge ? 1 : isPath ? 0.95 : 0.55

                  return (
                    <g
                      key={edge.id}
                      className={`edge-group ${isSelected ? 'selected' : ''}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        setSelectedElement({ type: 'edge', data: edge })
                      }}
                      tabIndex={0}
                      role="button"
                      aria-label={`Edge ${edge.id}: ${edge.source} to ${edge.target}, Type: ${edge.type}`}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          setSelectedElement({ type: 'edge', data: edge })
                        }
                      }}
                    >
                      <line
                        x1={p1.x}
                        y1={p1.y}
                        x2={p2.x}
                        y2={p2.y}
                        stroke={color}
                        strokeWidth={strokeWidth}
                        strokeDasharray={isDashed ? '5 4' : undefined}
                        opacity={edgeOpacity}
                        markerEnd={markerEnd}
                        filter={isPath && isPathHighlightActive ? 'url(#path-glow)' : undefined}
                      />

                      {/* Wide invisible hitbox for easy clickability */}
                      <line
                        x1={p1.x}
                        y1={p1.y}
                        x2={p2.x}
                        y2={p2.y}
                        stroke="transparent"
                        strokeWidth={16}
                      />

                      {/* Edge Amount Badge (Displayed primarily on key trail, selected, or when toggled) */}
                      {shouldShowAmount && (
                        <g transform={`translate(${midX}, ${midY})`}>
                          <rect
                            x="-32"
                            y="-9"
                            width="64"
                            height="18"
                            rx="4"
                            fill="#1A1C19"
                            stroke={color}
                            strokeWidth={isSelected ? '2' : '1'}
                            opacity={isDimmed ? 0.3 : 0.95}
                          />
                          <text
                            x="0"
                            y="3"
                            textAnchor="middle"
                            fill={color}
                            fontSize="9"
                            fontFamily="var(--font-mono)"
                            fontWeight="700"
                            opacity={isDimmed ? 0.3 : 1}
                          >
                            Rs {Math.round(edge.amount_inr!).toLocaleString()}
                          </text>
                        </g>
                      )}
                    </g>
                  )
                })}
              </g>

              {/* Nodes Layer */}
              <g className="nodes-layer" aria-label="Graph Nodes">
                {nodes.map((node) => {
                  const p = positions[node.id]
                  if (!p) return null

                  const isTarget = node.id === targetAccountId
                  const isPath = pathNodeSet.has(node.id)
                  const isSelected = selectedElement?.type === 'node' && selectedElement.data.id === node.id
                  const isDimmed = isPathHighlightActive && !isPath && !isTarget && evidencePath.length > 0 && !isSelected

                  const style = getNodeColor(node.type, node.score, isTarget, node.metadata)
                  const nodeRadius = isTarget ? 25 : 18

                  return (
                    <g
                      key={node.id}
                      transform={`translate(${p.x}, ${p.y})`}
                      className={`node-group ${isSelected ? 'selected' : ''}`}
                      onMouseEnter={() => setHoveredNodeId(node.id)}
                      onMouseLeave={() => setHoveredNodeId(null)}
                      onClick={(e) => {
                        e.stopPropagation()
                        setSelectedElement({ type: 'node', data: node })
                      }}
                      tabIndex={0}
                      role="button"
                      aria-label={`Node ${node.id}: ${node.type}, Score: ${node.score ?? 'null'}`}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          setSelectedElement({ type: 'node', data: node })
                        }
                      }}
                    >
                      {/* Target Account Distinctive Halo */}
                      {isTarget && (
                        <circle
                          r={nodeRadius + 6}
                          fill="none"
                          stroke="#D4A15A"
                          strokeWidth="1.5"
                          strokeDasharray="4 3"
                          opacity={0.8}
                        />
                      )}

                      {/* Explicit Selected Ring (clear off-white outline) */}
                      {isSelected && (
                        <circle
                          r={nodeRadius + 5}
                          fill="none"
                          stroke="#EAE7DF"
                          strokeWidth="2.5"
                          strokeDasharray="3 2"
                        />
                      )}

                      {/* Node Shape By Entity Type */}
                      {node.type === 'merchant' ? (
                        <rect
                          x={-nodeRadius}
                          y={-nodeRadius}
                          width={nodeRadius * 2}
                          height={nodeRadius * 2}
                          transform="rotate(45)"
                          fill={style.fill}
                          stroke={style.stroke}
                          strokeWidth={isTarget || isSelected ? 3 : 2}
                          opacity={isDimmed ? 0.35 : 1}
                        />
                      ) : node.type === 'device' ? (
                        <rect
                          x={-nodeRadius}
                          y={-nodeRadius + 3}
                          width={nodeRadius * 2}
                          height={nodeRadius * 1.5}
                          rx="4"
                          fill={style.fill}
                          stroke={style.stroke}
                          strokeWidth={isSelected ? 3 : 2}
                          opacity={isDimmed ? 0.35 : 1}
                        />
                      ) : (
                        <circle
                          r={nodeRadius}
                          fill={style.fill}
                          stroke={style.stroke}
                          strokeWidth={isTarget || isSelected ? 3 : 2}
                          opacity={isDimmed ? 0.35 : 1}
                        />
                      )}

                      {/* Node Label / ID */}
                      <text
                        x="0"
                        y={node.score !== null ? -2 : 4}
                        textAnchor="middle"
                        fill={isTarget ? '#EAE7DF' : style.text}
                        fontSize={isTarget ? '10.5' : '9.5'}
                        fontWeight="700"
                        fontFamily="var(--font-mono)"
                        opacity={isDimmed ? 0.35 : 1}
                      >
                        {node.id}
                      </text>

                      {/* Risk Score for Accounts */}
                      {node.score !== null && (
                        <text
                          x="0"
                          y="10"
                          textAnchor="middle"
                          fill={node.score >= 0.8 ? '#C65B4A' : '#D4A15A'}
                          fontSize="8"
                          fontFamily="var(--font-mono)"
                          fontWeight="600"
                          opacity={isDimmed ? 0.35 : 1}
                        >
                          {node.score.toFixed(2)}
                        </text>
                      )}

                      {/* Clear Entity Role Tag Below Node */}
                      <text
                        x="0"
                        y={nodeRadius + 14}
                        textAnchor="middle"
                        fill={isTarget ? '#D4A15A' : '#7B7F76'}
                        fontSize="8"
                        fontFamily="var(--font-mono)"
                        fontWeight={isTarget ? '700' : '500'}
                        opacity={isDimmed ? 0.25 : 0.9}
                      >
                        {isTarget ? 'TARGET ACCOUNT' : node.type.toUpperCase()}
                      </text>
                    </g>
                  )
                })}
              </g>
            </g>
          </svg>
        </div>
      ) : activeTab === 'table' ? (
        /* Accessible Table Alternative */
        <div id="panel-table-view" role="tabpanel" aria-labelledby="tab-table-view" className="table-view-wrapper">
          <div className="table-section">
            <h4 className="table-section-title">1. Graph Entities ({nodes.length} Nodes)</h4>
            <div className="table-scroll-container">
              <table className="accessible-graph-table" aria-label="Evidence Graph Nodes Table">
                <thead>
                  <tr>
                    <th scope="col">Entity ID</th>
                    <th scope="col">Entity Type</th>
                    <th scope="col">Label</th>
                    <th scope="col">Risk Score</th>
                    <th scope="col">In Key Trail</th>
                  </tr>
                </thead>
                <tbody>
                  {nodes.map((node) => (
                    <tr
                      key={node.id}
                      className={node.id === targetAccountId ? 'row-target' : ''}
                      onClick={() => setSelectedElement({ type: 'node', data: node })}
                    >
                      <td className="font-mono text-strong">{node.id}</td>
                      <td>
                        <span className={`type-chip type-${node.type}`}>{node.type}</span>
                      </td>
                      <td className="font-mono">{node.label}</td>
                      <td className="font-mono">
                        {node.score !== null ? node.score.toFixed(4) : '—'}
                      </td>
                      <td className="font-mono">
                        {pathNodeSet.has(node.id) ? (
                          <span className="badge-path-yes">YES</span>
                        ) : (
                          'No'
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="table-section">
            <h4 className="table-section-title">2. Financial Transfers & Edges ({edges.length} Edges)</h4>
            <div className="table-scroll-container">
              <table className="accessible-graph-table" aria-label="Evidence Graph Edges Table">
                <thead>
                  <tr>
                    <th scope="col">Connection ID</th>
                    <th scope="col">Type</th>
                    <th scope="col">From &rarr; To</th>
                    <th scope="col">Amount (INR)</th>
                    <th scope="col">Txn ID</th>
                    <th scope="col">In Key Trail</th>
                  </tr>
                </thead>
                <tbody>
                  {edges.map((edge) => (
                    <tr
                      key={edge.id}
                      className={pathEdgeSet.has(edge.id) ? 'row-path' : ''}
                      onClick={() => setSelectedElement({ type: 'edge', data: edge })}
                    >
                      <td className="font-mono text-strong">{edge.id}</td>
                      <td className="font-mono">{edge.type}</td>
                      <td className="font-mono">
                        {edge.source} &rarr; {edge.target}
                      </td>
                      <td className="font-mono inr-highlight">
                        {edge.amount_inr !== null ? `Rs ${edge.amount_inr.toLocaleString()}` : '—'}
                      </td>
                      <td className="font-mono">{edge.txn_id || '—'}</td>
                      <td className="font-mono">
                        {pathEdgeSet.has(edge.id) ? (
                          <span className="badge-path-yes">YES</span>
                        ) : (
                          'No'
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {evidencePath.length > 0 && (
            <div className="table-section">
              <h4 className="table-section-title">3. Traceable Evidence Path Walk ({evidencePath.length} Hops)</h4>
              <ol className="path-ordered-list font-mono">
                {evidencePath.map((edgeId, idx) => {
                  const edge = edges.find((e) => e.id === edgeId)
                  return (
                    <li key={edgeId} className="path-step-item">
                      <span className="step-num">Hop {idx + 1}:</span>
                      <strong className="step-edge">{edgeId}</strong>
                      {edge ? (
                        <span>
                          [{edge.type}] {edge.source} &rarr; {edge.target}
                          {edge.amount_inr !== null ? ` (Rs ${edge.amount_inr.toLocaleString()})` : ''}
                        </span>
                      ) : (
                        <span>Referenced Edge</span>
                      )}
                    </li>
                  )
                })}
              </ol>
            </div>
          )}
        </div>
      ) : (
        /* Chronological Timeline Alternative */
        <div id="panel-timeline-view" role="tabpanel" aria-labelledby="tab-timeline-view" className="timeline-view-wrapper">
          <div className="timeline-header-bar font-mono">
            <div>
              <h4 className="timeline-title font-sans">Chronological Event Timeline</h4>
              <p className="timeline-subtitle font-sans">
                Chronological sequence of all participating transactions and consumer complaints. Click any event to inspect its attributes or locate it on the map.
              </p>
            </div>
            <div className="timeline-stats">
              <span className="stats-pill">{timelineEvents.length} Timestamped Events</span>
              {edges.length > timelineEvents.length && (
                <span className="stats-excluded-note text-muted" title="Uses-device and static associations do not carry timestamps per Contract v1.1">
                  ({edges.length - timelineEvents.length} non-transaction links omitted)
                </span>
              )}
            </div>
          </div>

          {timelineEvents.length === 0 ? (
            <div className="timeline-empty-box">
              <p>No timestamped transaction or complaint events available for this alert subgraph.</p>
              <p className="text-muted font-mono" style={{ fontSize: '0.78rem' }}>
                Note: Non-transaction edges (e.g. device associations) do not carry timestamps under Contract v1.1 and are displayed in the Interactive Map and Table View.
              </p>
            </div>
          ) : (
            <div className="timeline-events-list" role="feed" aria-label="Chronological Transaction Events">
              {timelineEvents.map((evt, idx) => {
                const isSelected = selectedElement?.data?.id === evt.id
                return (
                  <article
                    key={evt.id}
                    id={`timeline-event-${evt.id}`}
                    data-testid={`timeline-event-${evt.id}`}
                    className={`timeline-event-card ${evt.type} ${evt.isKeyTrail ? 'is-key-trail' : ''} ${
                      isSelected ? 'is-selected' : ''
                    }`}
                    onClick={() => {
                      if (evt.edgeId) {
                        const edge = edges.find((e) => e.id === evt.edgeId)
                        if (edge) setSelectedElement({ type: 'edge', data: edge })
                      } else if (evt.nodeId) {
                        const node = nodes.find((n) => n.id === evt.nodeId)
                        if (node) setSelectedElement({ type: 'node', data: node })
                      }
                    }}
                    tabIndex={0}
                  >
                    <div className="event-marker-column" aria-hidden="true">
                      <span className="event-marker-dot" />
                      <span className="event-marker-line" />
                    </div>

                    <div className="event-card-content">
                      <div className="event-card-header">
                        <div className="event-time-group font-mono">
                          <span className="event-time-badge">
                            {evt.date.toUTCString().replace('GMT', 'UTC')}
                          </span>
                          <span className="event-hop-badge">Event #{idx + 1}</span>
                          {evt.isKeyTrail && (
                            <span className="badge-key-trail-tag font-mono">
                              ★ KEY TRANSACTION TRAIL
                            </span>
                          )}
                        </div>
                        <span className={`event-type-chip type-${evt.type} font-mono`}>
                          {evt.type === 'transfer' ? 'MONEY TRANSFER' : 'CONSUMER COMPLAINT'}
                        </span>
                      </div>

                      <div className="event-card-body">
                        {evt.type === 'transfer' ? (
                          <div className="event-transfer-flow font-mono">
                            <span className={`account-badge ${evt.source === targetAccountId ? 'is-target' : ''}`}>
                              {evt.source} {evt.source === targetAccountId && '(Target Under Review)'}
                            </span>
                            <span className="transfer-arrow-icon" aria-hidden="true">&rarr;</span>
                            <span className={`account-badge ${evt.target === targetAccountId ? 'is-target' : ''}`}>
                              {evt.target} {evt.target === targetAccountId && '(Target Under Review)'}
                            </span>
                            {evt.amountInr !== null && (
                              <span className="event-amount inr-highlight">
                                ₹{evt.amountInr.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                              </span>
                            )}
                          </div>
                        ) : (
                          <div className="event-complaint-flow font-mono">
                            <span className="complaint-icon" aria-hidden="true">📋</span>
                            <span>Consumer complaint against <strong>{evt.source}</strong>: {evt.category}</span>
                          </div>
                        )}

                        <div className="event-card-footer font-mono">
                          {evt.txnId && <span>Txn ID: <strong>{evt.txnId}</strong></span>}
                          <span>Connection ID: <strong>{evt.id}</strong></span>
                          <button
                            type="button"
                            className="btn-locate-map font-mono"
                            onClick={(e) => {
                              e.stopPropagation()
                              if (evt.edgeId) {
                                const edge = edges.find((edgeItem) => edgeItem.id === evt.edgeId)
                                if (edge) setSelectedElement({ type: 'edge', data: edge })
                              }
                              setActiveTab('canvas')
                            }}
                            title="Locate this connection on the interactive map"
                          >
                            View on Map &rarr;
                          </button>
                        </div>
                      </div>
                    </div>
                  </article>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Contextual Inspector Drawer */}
      {selectedElement && (
        <div className="subgraph-inspector-card" role="region" aria-label="Selected Element Details">
          <div className="inspector-card-header">
            <span className="element-badge font-mono">
              {selectedElement.type === 'node'
                ? `NODE · ${selectedElement.data.type.toUpperCase()}`
                : `EDGE · ${selectedElement.data.type.toUpperCase()}`}
            </span>
            <button
              type="button"
              className="btn-close-card"
              onClick={() => setSelectedElement(null)}
              aria-label="Close inspector"
            >
              &times;
            </button>
          </div>

          {selectedElement.type === 'node' ? (
            <div className="inspector-card-body font-mono">
              <div className="card-row">
                <span className="card-key">Entity ID:</span>
                <span className="card-val text-strong">{selectedElement.data.id}</span>
              </div>
              <div className="card-row">
                <span className="card-key">Entity Type:</span>
                <span className="card-val">{selectedElement.data.type}</span>
              </div>
              {selectedElement.data.score !== null && (
                <div className="card-row">
                  <span className="card-key">Investigative Risk Score:</span>
                  <span className="card-val score-highlight">
                    {selectedElement.data.score.toFixed(4)}
                  </span>
                </div>
              )}
              {selectedElement.data.id === targetAccountId && (
                <div className="card-row">
                  <span className="card-key">Role:</span>
                  <span className="card-val text-amber">Main Account Under Review</span>
                </div>
              )}
              {Object.keys(selectedElement.data.metadata).length > 0 && (
                <div className="card-row">
                  <span className="card-key">Attributes:</span>
                  <span className="card-val">
                    {JSON.stringify(selectedElement.data.metadata)}
                  </span>
                </div>
              )}
              <p className="card-help-text">
                Note: Risk scores prioritize accounts for review and do not represent a calibrated percentage probability of fraud.
              </p>
            </div>
          ) : (
            <div className="inspector-card-body font-mono">
              <div className="card-row">
                <span className="card-key">Connection ID:</span>
                <span className="card-val text-strong">{selectedElement.data.id}</span>
              </div>
              <div className="card-row">
                <span className="card-key">Direction:</span>
                <span className="card-val">
                  {selectedElement.data.source} &rarr; {selectedElement.data.target}
                </span>
              </div>
              {selectedElement.data.amount_inr !== null && (
                <div className="card-row">
                  <span className="card-key">Amount:</span>
                  <span className="card-val inr-highlight">
                    Rs {selectedElement.data.amount_inr.toLocaleString()}
                  </span>
                </div>
              )}
              {selectedElement.data.txn_id && (
                <div className="card-row">
                  <span className="card-key">Transaction ID:</span>
                  <span className="card-val">{selectedElement.data.txn_id}</span>
                </div>
              )}
              {selectedElement.data.timestamp && (
                <div className="card-row">
                  <span className="card-key">Timestamp:</span>
                  <span className="card-val">{selectedElement.data.timestamp}</span>
                </div>
              )}
              <div className="card-row">
                <span className="card-key">Part of Key Trail:</span>
                <span className="card-val">
                  {pathEdgeSet.has(selectedElement.data.id)
                    ? 'YES (Flagged Hop)'
                    : 'NO (Contextual Connection)'}
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Plain-English Visual Legend & Guide */}
      <div className="graph-legend-container font-mono" role="region" aria-label="Graph Visual Legend">
        <div className="legend-title font-sans">Graph Symbol Guide:</div>
        <div className="legend-items-grid font-sans">
          <div className="legend-item">
            <span className="legend-swatch node-target" aria-hidden="true" />
            <div className="legend-text">
              <strong className="legend-name">Target Account ({targetAccountId})</strong>
              <span className="legend-desc">Account under review (amber outline &amp; focus halo)</span>
            </div>
          </div>
          <div className="legend-item">
            <span className="legend-swatch node-account" aria-hidden="true" />
            <div className="legend-text">
              <strong className="legend-name">Connected Accounts</strong>
              <span className="legend-desc">Sender or receiver accounts in 2-hop neighborhood (neutral grey)</span>
            </div>
          </div>
          <div className="legend-item">
            <span className="legend-swatch edge-transfer" aria-hidden="true" />
            <div className="legend-text">
              <strong className="legend-name">Directed Money Transfers</strong>
              <span className="legend-desc">Low-emphasis grey arrow indicates flow of money (sender &rarr; receiver)</span>
            </div>
          </div>
          <div className="legend-item">
            <span className="legend-swatch edge-key-trail" aria-hidden="true" />
            <div className="legend-text">
              <strong className="legend-name">Key Transaction Trail</strong>
              <span className="legend-desc">Highlighted suspicious transaction walk (amber route)</span>
            </div>
          </div>
          <div className="legend-item">
            <span className="legend-swatch node-device" aria-hidden="true" />
            <div className="legend-text">
              <strong className="legend-name">Shared Devices</strong>
              <span className="legend-desc">Hardware/phones associated with multiple sender accounts (muted grey)</span>
            </div>
          </div>
          <div className="legend-item">
            <span className="legend-swatch node-merchant" aria-hidden="true" />
            <div className="legend-text">
              <strong className="legend-name">Merchants &amp; Aggregators</strong>
              <span className="legend-desc">Commercial endpoints or cash-out aggregators (muted grey)</span>
            </div>
          </div>
          <div className="legend-item">
            <span className="legend-swatch node-complaint" aria-hidden="true" />
            <div className="legend-text">
              <strong className="legend-name">Consumer Complaints</strong>
              <span className="legend-desc">Fraud grievances registered by victim accounts (red flag)</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
