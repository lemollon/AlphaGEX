import { NextRequest, NextResponse } from 'next/server'
import { VerificationException } from '@apple/app-store-server-library'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'
import { getAppleVerifier, APPLE_IAP_BUNDLE_ID } from '@/lib/billing/apple/verifier'
import { evaluateTransaction } from '@/lib/billing/apple/verify-logic'
import { upsertSubscription, emitMembershipEvent } from '@/lib/billing/membership-sync'
import { buildMembershipResponse } from '@/lib/billing/membership'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * POST /api/billing/apple/verify — the mobile app's ONE call after StoreKit hands it a
 * signed transaction: on first purchase, on restore, and on every launch's "did anything
 * change" refresh. Auth'd (mobile bearer or web cookie, via getCustomerIdentity — same as
 * membership/route.ts).
 *
 * Body: { jws: string } — the StoreKit 2 signedTransaction JWS from the device.
 *
 * Ownership: a transaction with `appAccountToken` set to someone else's user id is refused
 * outright (403) — that is the App Review–relevant "don't let purchase device B grant
 * account A" case. A transaction with NO appAccountToken (an older purchase, or a restore
 * predating this field) is trusted for whichever account already owns its
 * originalTransactionId, or accepted fresh if nobody does yet.
 *
 * Writes through lib/billing/membership-sync — the SAME upsertSubscription/
 * emitMembershipEvent the Stripe webhook uses — so a customer's provider (stripe vs apple)
 * is the only thing that differs about how they got here.
 */
export async function POST(req: NextRequest) {
  const identity = await getCustomerIdentity()
  if (!identity?.customerId) return NextResponse.json({ ok: false }, { status: 401 })

  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'billing not configured' }, { status: 503 })
  }

  let body: any
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ ok: false, error: 'bad payload' }, { status: 400 })
  }
  const jws = typeof body?.jws === 'string' ? body.jws : null
  if (!jws) return NextResponse.json({ ok: false, error: 'missing jws' }, { status: 400 })

  let decoded
  try {
    decoded = await getAppleVerifier().verifyAndDecodeTransaction(jws)
  } catch (e) {
    if (e instanceof VerificationException) {
      return NextResponse.json({ ok: false, error: 'invalid signature' }, { status: 401 })
    }
    console.error('[billing/apple/verify] verifier error:', e)
    return NextResponse.json({ ok: false, error: 'verification failed' }, { status: 401 })
  }

  try {
    // Who (if anyone) already owns this originalTransactionId — needed for the
    // no-appAccountToken ownership branch in evaluateTransaction.
    let existingOwnerUserId: string | null = null
    if (decoded.originalTransactionId) {
      const rows = await customerQuery<{ user_id: string }>(
        `SELECT user_id FROM customer_bot_subscriptions WHERE apple_original_transaction_id = $1 LIMIT 1`,
        [decoded.originalTransactionId],
      )
      existingOwnerUserId = rows[0]?.user_id ?? null
    }

    const result = evaluateTransaction(decoded, {
      bundleId: APPLE_IAP_BUNDLE_ID,
      userId: identity.customerId,
      existingOwnerUserId,
    })

    if (!result.ok) {
      return NextResponse.json({ ok: false, error: result.error }, { status: result.status })
    }

    for (const bot of result.plan.bots) {
      await upsertSubscription({
        userId: identity.customerId,
        bot,
        status: result.status,
        provider: 'apple',
        appleOriginalTransactionId: result.originalTransactionId,
        currentPeriodEnd: result.expiresDateIso,
        priceLookupKey: result.plan.lookupKey,
      })
    }

    // Idempotency key: same jws -> same Apple-signed `signedDate` -> same eventId, so a
    // device re-POSTing the same transaction on every app launch never double-fires CRM.
    await emitMembershipEvent({
      eventId: `apple:${result.originalTransactionId}:${decoded.signedDate ?? 0}`,
      eventType: result.status === 'active' ? 'crm.subscription_active' : 'crm.membership_canceled',
      userId: identity.customerId,
      bots: result.plan.bots,
      bundle: result.plan.bundle,
      status: result.status,
    })

    return NextResponse.json(await buildMembershipResponse(identity.customerId))
  } catch (e) {
    console.error('[billing/apple/verify] handler error:', e)
    return NextResponse.json({ ok: false, error: 'could not record purchase' }, { status: 500 })
  }
}
