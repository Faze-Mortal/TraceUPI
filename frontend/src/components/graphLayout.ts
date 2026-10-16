import type { EvidenceEdge, EvidenceNode } from '../types/api'

export interface Point {
  x: number
  y: number
}

export interface GraphLayoutResult {
  positions: Record<string, Point>
  width: number
  height: number
}

/**
 * Computes deterministic 2D positions for evidence graph nodes.
 * Anchors the target account at the center and cleanly separates:
 * - Incoming transfer senders (left sector)
 * - Outgoing transfer receivers (right sector)
 * - Associated devices (top sector)
 * - Merchants (bottom-right sector)
 * - Complaints (bottom-left sector)
 * Followed by gentle deterministic relaxation with collision prevention.
 * Fully deterministic: zero Math.random() calls.
 */
export function computeDeterministicGraphLayout(
  nodes: EvidenceNode[],
  edges: EvidenceEdge[],
  targetAccountId?: string,
  width = 880,
  height = 560
): GraphLayoutResult {
  const positions: Record<string, Point> = {}

  if (nodes.length === 0) {
    return { positions, width, height }
  }

  const cx = width / 2
  const cy = height / 2

  // Single node edge-case
  if (nodes.length === 1) {
    positions[nodes[0].id] = { x: cx, y: cy }
    return { positions, width, height }
  }

  // Determine target node ID
  const targetId =
    targetAccountId && nodes.some((n) => n.id === targetAccountId)
      ? targetAccountId
      : nodes[0].id

  // Adjacency and relationship mapping
  const incomingSenders = new Set<string>()
  const outgoingReceivers = new Set<string>()
  const devices = new Set<string>()
  const merchants = new Set<string>()
  const complaints = new Set<string>()
  const secondaryNodes = new Set<string>()

  // Classify direct edges with target
  for (const e of edges) {
    if (e.target === targetId && e.type === 'transfer') {
      incomingSenders.add(e.source)
    } else if (e.source === targetId && e.type === 'transfer') {
      outgoingReceivers.add(e.target)
    } else if (e.type === 'uses_device') {
      if (e.source === targetId) devices.add(e.target)
      else if (e.target === targetId) devices.add(e.source)
    } else if (e.type === 'merchant_profile') {
      if (e.source === targetId) merchants.add(e.target)
      else if (e.target === targetId) merchants.add(e.source)
    } else if (e.type === 'has_complaint') {
      if (e.source === targetId) complaints.add(e.target)
      else if (e.target === targetId) complaints.add(e.source)
    }
  }

  // Classify by node type if not captured by direct edge
  for (const n of nodes) {
    if (n.id === targetId) continue
    if (
      !incomingSenders.has(n.id) &&
      !outgoingReceivers.has(n.id) &&
      !devices.has(n.id) &&
      !merchants.has(n.id) &&
      !complaints.has(n.id)
    ) {
      if (n.type === 'device') {
        devices.add(n.id)
      } else if (n.type === 'merchant') {
        merchants.add(n.id)
      } else if (n.type === 'complaint') {
        complaints.add(n.id)
      } else {
        secondaryNodes.add(n.id)
      }
    }
  }

  // Pin target node at center
  positions[targetId] = { x: cx, y: cy }

  // Helper for angular fan distribution
  const placeArc = (
    nodeList: string[],
    startAngleRad: number,
    endAngleRad: number,
    radius: number
  ) => {
    const list = [...nodeList].sort()
    const count = list.length
    if (count === 0) return

    if (count === 1) {
      const mid = (startAngleRad + endAngleRad) / 2
      positions[list[0]] = {
        x: cx + radius * Math.cos(mid),
        y: cy + radius * Math.sin(mid),
      }
      return
    }

    const step = (endAngleRad - startAngleRad) / (count - 1)
    list.forEach((id, idx) => {
      const angle = startAngleRad + step * idx
      positions[id] = {
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
      }
    })
  }

  // 1. Devices: Top sector (-140° to -40°)
  placeArc(
    Array.from(devices),
    (-140 * Math.PI) / 180,
    (-40 * Math.PI) / 180,
    180
  )

  // 2. Incoming transfer senders: Left sector (125° to 235°)
  placeArc(
    Array.from(incomingSenders),
    (130 * Math.PI) / 180,
    (230 * Math.PI) / 180,
    210
  )

  // 3. Outgoing transfer receivers: Right sector (-50° to 50°)
  placeArc(
    Array.from(outgoingReceivers),
    (-50 * Math.PI) / 180,
    (50 * Math.PI) / 180,
    210
  )

  // 4. Complaints: Bottom-left sector (95° to 135°)
  placeArc(
    Array.from(complaints),
    (95 * Math.PI) / 180,
    (135 * Math.PI) / 180,
    190
  )

  // 5. Merchants: Bottom-right sector (45° to 85°)
  placeArc(
    Array.from(merchants),
    (45 * Math.PI) / 180,
    (85 * Math.PI) / 180,
    190
  )

  // 6. Secondary (2-hop) nodes: Outer ring radius 280
  const secondaryList = Array.from(secondaryNodes).sort()
  if (secondaryList.length > 0) {
    const step = (2 * Math.PI) / secondaryList.length
    secondaryList.forEach((id, idx) => {
      const angle = idx * step
      positions[id] = {
        x: cx + 270 * Math.cos(angle),
        y: cy + 270 * Math.sin(angle),
      }
    })
  }

  // Fallback for any unplaced nodes
  for (const n of nodes) {
    if (!positions[n.id]) {
      positions[n.id] = { x: cx + 150, y: cy + 150 }
    }
  }

  // Force relaxation with anti-overlap collision prevention (40 iterations)
  const idealDist = 120
  const iterations = 40

  for (let iter = 0; iter < iterations; iter++) {
    const temp = (1 - iter / iterations) * 8
    const forces: Record<string, { fx: number; fy: number }> = {}

    for (const n of nodes) {
      forces[n.id] = { fx: 0, fy: 0 }
    }

    // Node-node collision repulsion
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const id1 = nodes[i].id
        const id2 = nodes[j].id
        const p1 = positions[id1]
        const p2 = positions[id2]
        const dx = p1.x - p2.x
        const dy = p1.y - p2.y
        const distSq = dx * dx + dy * dy
        const d = Math.max(0.1, Math.sqrt(distSq))

        // Strong repulsion if nodes are closer than 130px
        if (d < 140) {
          const repForce = (idealDist * idealDist) / d
          const fx = (dx / d) * repForce
          const fy = (dy / d) * repForce

          forces[id1].fx += fx
          forces[id1].fy += fy
          forces[id2].fx -= fx
          forces[id2].fy -= fy
        }
      }
    }

    // Edge spring constraint
    for (const e of edges) {
      const p1 = positions[e.source]
      const p2 = positions[e.target]
      if (!p1 || !p2) continue

      const dx = p1.x - p2.x
      const dy = p1.y - p2.y
      const d = Math.max(0.1, Math.sqrt(dx * dx + dy * dy))

      if (d > 220) {
        const attForce = (d - 180) * 0.05
        const fx = (dx / d) * attForce
        const fy = (dy / d) * attForce

        forces[e.source].fx -= fx
        forces[e.source].fy -= fy
        forces[e.target].fx += fx
        forces[e.target].fy += fy
      }
    }

    // Apply displacements, keeping target node strictly centered
    for (const n of nodes) {
      if (n.id === targetId) continue
      const f = forces[n.id]
      const fMag = Math.sqrt(f.fx * f.fx + f.fy * f.fy)
      if (fMag > 0.001) {
        const step = Math.min(temp, fMag)
        positions[n.id].x += (f.fx / fMag) * step
        positions[n.id].y += (f.fy / fMag) * step
      }

      // Safe margin bounds
      positions[n.id].x = Math.max(70, Math.min(width - 70, positions[n.id].x))
      positions[n.id].y = Math.max(60, Math.min(height - 60, positions[n.id].y))
    }
  }

  return { positions, width, height }
}
