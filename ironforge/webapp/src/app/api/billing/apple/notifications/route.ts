import { NextRequest, NextResponse } from 'next/server'
import { VerificationException } from '@apple/app-store-server-library'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'
import { getAppleVerifier } from '@/lib/billing/apple/verifier'
import { planFor } from '@/lib/billing/apple-products'
import { statusForNotification } from '@/lib/billing/apple/notification-status'
import { upsertSubscription, emitMembershipEvent } from '@/lib/billing/membership-sync'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * POST /api/billing/apple/notifications — PUBLIC, no auth. This is App Store Server
 * Notifications V2 — Apple is the caller, not a signed-in customer, the same shape as
 * /api/billing/webhook is for Stripe. Register this URL in App Store Connect
 * (Production AND Sandbox notification URLs).
 *
 * Body: { signedPayload: string }.
 *
 * Apple retries on any non-2xx response indefinitely, so per Apple's own contract: 401 is
 * reserved for "the signature itself didn't verify" (a real attack or a misconfigured
 * cert — retrying won't help, but 401 is what Apple's docs say to send). Everything AFTER
 * a successful verify acks 200, including notification types we don't act on and users we
 * can't identify — there is nothing about "we don't recognise this" that a retry fixes.
 */
export async function POST(req: NextRequest) {
  let body: any
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ ok: false, error: 'bad payload' }, { status: 400 })
  }
  const signedPayload = typeof body?.signedPayload === 'string' ? body.signedPayload : null
  if (!signedPayload) return NextResponse.json({ ok: false, error: 'missing signedPayload' }, { status: 400 })

  const verifier = getAppleVerifier()
  let notification
  try {
    notification = await verifier.verifyAndDecodeNotification(signedPayload)
  } catch (e) {
    if (e instanceof VerificationException) {
      return NextResponse.json({ ok: false, error: 'invalid signature' }, { status: 401 })
    }
    console.error('[billing/apple/notifications] verifier error:', e)
    return NextResponse.json({ ok: false, error: 'verification failed' }, { status: 401 })
  }

  const notificationType = String(notification.notificationType ?? '')

  // TEST is Apple's own "Send Test Notification" button in App Store Connect — a
  // connectivity check with no transaction data to act on.
  if (notificationType === 'TEST') {
    return NextResponse.json({ ok: true, noop: true })
  }
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: true, stored: false })
  }

  // Everything from here down: signature already verified, so we ALWAYS ack 200 — an
  // unhandled type, an unknown user, or an internal error all just get logged. See the
  // route comment for why this differs from the Stripe webhook's 500-to-retry pattern.
  try {
    const signedTransactionInfo = notification.data?.signedTransactionInfo
    if (!signedTransactionInfo) {
      console.warn(`[billing/apple/notifications] ${notificationType} — no signedTransactionInfo, ack + skip`)
      return NextResponse.json({ ok: true, skipped: true })
    }
    const transaction = await verifier.verifyAndDecodeTransaction(signedTransactionInfo)
    const signedRenewalInfo = notification.data?.signedRenewalInfo
    const renewal = signedRenewalInfo ? await verifier.verifyAndDecodeRenewalInfo(signedRenewalInfo) : null

    const status = statusForNotification({
      notificationType,
      expiresDateMs: transaction.expiresDate,
      revocationDate: transaction.revocationDate,
      gracePeriodExpiresMs: renewal?.gracePeriodExpiresDate,
    })
    if (!status) {
      console.warn(`[billing/apple/notifications] unhandled type ${notificationType} — ack, no-op`)
      return NextResponse.json({ ok: true, unhandled: true })
    }

    const plan = planFor(transaction.productId ?? '')
    if (!plan) {
      console.warn(`[billing/apple/notifications] unknown productId ${transaction.productId} — ack, no-op`)
      return NextResponse.json({ ok: true, unhandled: true })
    }

    // Locate the user: appAccountToken first (it IS the user id we mint), else whoever
    // already owns this originalTransactionId from a prior /verify call.
    let userId: string | null = null
    if (transaction.appAccountToken) {
      const rows = await customerQuery<{ id: string }>(`SELECT id FROM users WHERE id = $1 LIMIT 1`, [
        transaction.appAccountToken,
      ])
      userId = rows[0]?.id ?? null
    }
    if (!userId && transaction.originalTransactionId) {
      const rows = await customerQuery<{ user_id: string }>(
        `SELECT user_id FROM customer_bot_subscriptions WHERE apple_original_transaction_id = $1 LIMIT 1`,
        [transaction.originalTransactionId],
      )
      userId = rows[0]?.user_id ?? null
    }
    if (!userId) {
      console.warn(
        `[billing/apple/notifications] ${notificationType} — no known user for originalTransactionId ${transaction.originalTransactionId}, ack + skip`,
      )
      return NextResponse.json({ ok: true, unknownUser: true })
    }

    for (const bot of plan.bots) {
      await upsertSubscription({
        userId,
        bot,
        status,
        provider: 'apple',
        appleOriginalTransactionId: transaction.originalTransactionId ?? null,
        currentPeriodEnd:
          typeof transaction.expiresDate === 'number' ? new Date(transaction.expiresDate).toISOString() : null,
        priceLookupKey: plan.lookupKey,
      })
    }

    // Idempotency key: Apple's own notificationUUID is unique per notification, so a
    // redelivered notification (Apple retries on non-2xx) inserts nothing twice.
    await emitMembershipEvent({
      eventId: `apple:${notification.notificationUUID ?? transaction.originalTransactionId}:${notificationType}`,
      eventType: status === 'canceled' ? 'crm.membership_canceled' : 'crm.subscription_active',
      userId,
      bots: plan.bots,
      bundle: plan.bundle,
      status,
    })

    return NextResponse.json({ ok: true })
  } catch (e) {
    console.error('[billing/apple/notifications] handler error (acking anyway):', e)
    return NextResponse.json({ ok: true, error: 'handled with warning' })
  }
}
