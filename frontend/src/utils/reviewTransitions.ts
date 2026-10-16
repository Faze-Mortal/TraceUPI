import type { ReviewStatus } from '../types/api'

export const ALLOWED_REVIEW_TRANSITIONS: Record<ReviewStatus, readonly ReviewStatus[]> = {
  OPEN: ['INVESTIGATING', 'CONFIRMED_FRAUD', 'DISMISSED_BENIGN'],
  INVESTIGATING: ['CONFIRMED_FRAUD', 'DISMISSED_BENIGN'],
  CONFIRMED_FRAUD: ['INVESTIGATING'],
  DISMISSED_BENIGN: ['INVESTIGATING'],
}

export const ALL_REVIEW_STATUSES: readonly ReviewStatus[] = [
  'OPEN',
  'INVESTIGATING',
  'CONFIRMED_FRAUD',
  'DISMISSED_BENIGN',
]

/**
 * Returns true if transition from current to target is allowed by Contract v1.2 §9.1.
 */
export function isAllowedTransition(current: ReviewStatus, target: ReviewStatus): boolean {
  if (current === target) return false
  return ALLOWED_REVIEW_TRANSITIONS[current]?.includes(target) ?? false
}

/**
 * Returns explanatory text for why a transition is disallowed under Contract v1.2.
 */
export function getDisallowedTransitionReason(current: ReviewStatus, target: ReviewStatus): string {
  if (current === target) {
    return `Alert is already in ${current} status.`
  }
  if (current === 'CONFIRMED_FRAUD' && target === 'DISMISSED_BENIGN') {
    return `Cannot transition directly from CONFIRMED_FRAUD to DISMISSED_BENIGN. You must first reopen the alert to INVESTIGATING.`
  }
  if (current === 'DISMISSED_BENIGN' && target === 'CONFIRMED_FRAUD') {
    return `Cannot transition directly from DISMISSED_BENIGN to CONFIRMED_FRAUD. You must first reopen the alert to INVESTIGATING.`
  }
  if (current === 'INVESTIGATING' && target === 'OPEN') {
    return `An alert under active investigation cannot be reverted to OPEN. Conclude with CONFIRMED_FRAUD or DISMISSED_BENIGN.`
  }
  if (target === 'OPEN') {
    return `Active review decisions cannot transition back to OPEN. Under Contract v1.2, status resets to OPEN only when a pipeline rerun detects evidence divergence.`
  }
  return `Transition from ${current} to ${target} is not permitted by the Contract v1.2 review state machine.`
}
