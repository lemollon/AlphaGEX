/**
 * Pure accept/reject logic for a decoded StoreKit 2 transaction, split out of the
 * /api/billing/apple/verify route so it's testable without a mocked Next.js request or a
 * real Apple signature. The route's ONLY job past this point is: call the verifier, call
 * this, act on the result.
 */

import { planFor, type AppleProduct } from '@/lib/billing/apple-products'

/** The subset of JWSTransactionDecodedPayload this logic reads. */
export interface DecodedTransactionLike {
  bundleId?: string
  productId?: string
  appAccountToken?: string
  originalTransactionId?: string
  expiresDate?: number
  revocationDate?: number
}

export interface EvaluateTransactionOptions {
  /** APPLE_IAP_BUNDLE_ID — required to match the decoded transaction's bundleId. */
  bundleId: string
  /** The authenticated caller's user id. */
  userId: string
  /** user_id already on file for this originalTransactionId, if any row exists. */
  existingOwnerUserId?: string | null
  now?: number
}

export type VerifyRejectionReason = 'bad_bundle' | 'unknown_product' | 'invalid_transaction' | 'foreign_transaction'

export interface VerifyRejection {
  ok: false
  status: 400 | 403
  error: VerifyRejectionReason
}

export interface VerifyAcceptance {
  ok: true
  plan: AppleProduct
  productId: string
  originalTransactionId: string
  status: 'active' | 'canceled'
  /** ISO string for current_period_end, or null when Apple sent no expiresDate. */
  expiresDateIso: string | null
}

export function evaluateTransaction(
  decoded: DecodedTransactionLike,
  opts: EvaluateTransactionOptions,
): VerifyRejection | VerifyAcceptance {
  const now = opts.now ?? Date.now()

  if (decoded.bundleId !== opts.bundleId) {
    return { ok: false, status: 400, error: 'bad_bundle' }
  }
  if (!decoded.productId || !decoded.originalTransactionId) {
    return { ok: false, status: 400, error: 'invalid_transaction' }
  }
  const plan = planFor(decoded.productId)
  if (!plan) {
    return { ok: false, status: 400, error: 'unknown_product' }
  }

  // Ownership: appAccountToken === user id OR the row already on file for this
  // originalTransactionId belongs to this same user. Reject 403 the moment the token is
  // SET and points at someone else — that is the one unambiguous "not yours" signal.
  if (decoded.appAccountToken) {
    if (decoded.appAccountToken !== opts.userId) {
      return { ok: false, status: 403, error: 'foreign_transaction' }
    }
  } else if (opts.existingOwnerUserId && opts.existingOwnerUserId !== opts.userId) {
    return { ok: false, status: 403, error: 'foreign_transaction' }
  }

  const status: 'active' | 'canceled' =
    !decoded.revocationDate && typeof decoded.expiresDate === 'number' && decoded.expiresDate > now
      ? 'active'
      : 'canceled'

  return {
    ok: true,
    plan,
    productId: decoded.productId,
    originalTransactionId: decoded.originalTransactionId,
    status,
    expiresDateIso: typeof decoded.expiresDate === 'number' ? new Date(decoded.expiresDate).toISOString() : null,
  }
}
