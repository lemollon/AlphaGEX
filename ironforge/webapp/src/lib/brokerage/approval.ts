/**
 * Pure decision helpers for the per-trade approval flow (sub-project: brokerage connection).
 *
 * COMPLIANCE INVARIANT: an order may only be placed against a customer's connected brokerage
 * after an explicit, unexpired approval. This module is the single source of truth for that
 * decision so it is unit-testable without SnapTrade or a DB. Keep it pure — no I/O.
 *
 * v1 is per-trade approval ONLY (the lane SnapTrade permits for non-registered apps). There is
 * deliberately NO path here that authorizes placement without a customer decision.
 */

export type ApprovalStatus =
  | 'pending'
  | 'approved'
  | 'placed'
  | 'failed'
  | 'expired'
  | 'declined'

/** What the approve-route is allowed to do with an approval row, given its current state + time. */
export type ApprovalAction = 'place' | 'expired' | 'invalid'

/**
 * Decide whether a customer's "Approve" tap may proceed to placing the order.
 * - 'place'   → the row is pending and still within its window; the route may call placeOrder.
 * - 'expired' → the window lapsed; the route must mark it expired and refuse.
 * - 'invalid' → already decided/placed/failed/declined; the tap is a no-op (idempotent guard).
 */
export function decideApproval(p: {
  status: ApprovalStatus
  now: Date
  expiresAt: Date
}): ApprovalAction {
  if (p.status !== 'pending') return 'invalid'
  if (p.now.getTime() >= p.expiresAt.getTime()) return 'expired'
  return 'place'
}

/** True only for the one state that authorizes a real order. Used as a belt-and-suspenders guard. */
export function isPlaceable(status: ApprovalStatus, now: Date, expiresAt: Date): boolean {
  return decideApproval({ status, now, expiresAt }) === 'place'
}
