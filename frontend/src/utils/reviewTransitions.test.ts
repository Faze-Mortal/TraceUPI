import { describe, it, expect } from 'vitest'
import {
  isAllowedTransition,
  getDisallowedTransitionReason,
  ALLOWED_REVIEW_TRANSITIONS,
  ALL_REVIEW_STATUSES,
} from './reviewTransitions'

describe('Contract v1.2 Review Transitions State Machine (§9.1)', () => {
  it('correctly validates all allowed edges defined in Contract v1.2', () => {
    // OPEN -> INVESTIGATING, CONFIRMED_FRAUD, DISMISSED_BENIGN
    expect(isAllowedTransition('OPEN', 'INVESTIGATING')).toBe(true)
    expect(isAllowedTransition('OPEN', 'CONFIRMED_FRAUD')).toBe(true)
    expect(isAllowedTransition('OPEN', 'DISMISSED_BENIGN')).toBe(true)

    // INVESTIGATING -> CONFIRMED_FRAUD, DISMISSED_BENIGN
    expect(isAllowedTransition('INVESTIGATING', 'CONFIRMED_FRAUD')).toBe(true)
    expect(isAllowedTransition('INVESTIGATING', 'DISMISSED_BENIGN')).toBe(true)

    // CONFIRMED_FRAUD -> INVESTIGATING (Reopen)
    expect(isAllowedTransition('CONFIRMED_FRAUD', 'INVESTIGATING')).toBe(true)

    // DISMISSED_BENIGN -> INVESTIGATING (Reopen)
    expect(isAllowedTransition('DISMISSED_BENIGN', 'INVESTIGATING')).toBe(true)
  })

  it('correctly rejects disallowed transitions', () => {
    // Same status transitions
    for (const status of ALL_REVIEW_STATUSES) {
      expect(isAllowedTransition(status, status)).toBe(false)
    }

    // Direct transition between terminal decisions without reopening
    expect(isAllowedTransition('CONFIRMED_FRAUD', 'DISMISSED_BENIGN')).toBe(false)
    expect(isAllowedTransition('DISMISSED_BENIGN', 'CONFIRMED_FRAUD')).toBe(false)

    // Reverting active decisions to OPEN
    expect(isAllowedTransition('INVESTIGATING', 'OPEN')).toBe(false)
    expect(isAllowedTransition('CONFIRMED_FRAUD', 'OPEN')).toBe(false)
    expect(isAllowedTransition('DISMISSED_BENIGN', 'OPEN')).toBe(false)
  })

  it('provides descriptive explanations for disallowed transitions', () => {
    expect(getDisallowedTransitionReason('OPEN', 'OPEN')).toContain('already in OPEN')
    expect(getDisallowedTransitionReason('CONFIRMED_FRAUD', 'DISMISSED_BENIGN')).toContain(
      'Cannot transition directly from CONFIRMED_FRAUD to DISMISSED_BENIGN'
    )
    expect(getDisallowedTransitionReason('DISMISSED_BENIGN', 'CONFIRMED_FRAUD')).toContain(
      'Cannot transition directly from DISMISSED_BENIGN to CONFIRMED_FRAUD'
    )
    expect(getDisallowedTransitionReason('INVESTIGATING', 'OPEN')).toContain(
      'cannot be reverted to OPEN'
    )
    expect(getDisallowedTransitionReason('CONFIRMED_FRAUD', 'OPEN')).toContain(
      'cannot transition back to OPEN'
    )
  })

  it('ALLOWED_REVIEW_TRANSITIONS contains the exact 7 valid directed edges', () => {
    let edgeCount = 0
    for (const [, targets] of Object.entries(ALLOWED_REVIEW_TRANSITIONS)) {
      edgeCount += targets.length
    }
    // OPEN: 3, INVESTIGATING: 2, CONFIRMED_FRAUD: 1, DISMISSED_BENIGN: 1 -> 7 edges
    expect(edgeCount).toBe(7)
  })
})
