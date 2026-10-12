import { NextRequest, NextResponse } from 'next/server'
import { VerificationException } from '@apple/app-store-server-library'
import { isCustomersDbConfigured, customerExecute, customerQuery } from '@/lib/customers-db'
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
 * cert — retrying won't help, but 401 is what Apple's docs say to send). A notification we
 * understood and legitimately have nothing to do with (an unhandled type, an unrecognised
 * productId, a user we can't identify) acks 200 — there is nothing about "we don't
 * recognise this" that a retry fixes. But a genuine handler failure (a transient DB blip
 * while writing the row) now returns 500 so Apple retries with backoff, same dead-letter
 * pattern as /api/billing/webhook (audit C5) — this used to ack 200 on ANY error, which
 * permanently dropped a lost REFUND/EXPIRED/REVOKE with nothing to self-heal it (nothing
 * else in this codebase expires a row by current_period_end; status is the only thing read).
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
  const notificationUUID = typeof notification.notificationUUID === 'string' ? notification.notificationUUID : null

  // TEST is Apple's own "Send Test Notification" button in App Store Connect — a
  // connectivity check with no transaction data to act on. Never touches a row, so it's
  // exempt from the dedupe/dead-letter table below.
  if (notificationType === 'TEST') {
    return NextResponse.json({ ok: true, noop: true })
  }
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: true, stored: false })
  }

  // Replay/dedupe guard + dead-letter (mirrors /api/billing/webhook's stripe_webhook_events
  // pattern, audit C5): the INSERT is the processing claim. A redelivery of an
  // ALREADY-PROCESSED notification (Apple retries on non-2xx) is ack'd without re-running
  // the handler. A redelivery of a notification whose PRIOR attempt failed (processed_at
  // still NULL, error set) is processed again — that's the retry actually working.
  if (notificationUUID) {
    const inserted = await customerExecute(
      `INSERT INTO apple_notification_events (notification_uuid, notification_type) VALUES ($1, $2)
       ON CONFLICT (notification_uuid) DO NOTHING`,
      [notificationUUID, notificationType],
    ).catch(() => 1) // if the guard table itself is unavailable, fall through and process
    if (inserted === 0) {
      const prior = await customerQuery<{ processed_at: string | null }>(
        `SELECT processed_at FROM apple_notification_events WHERE notification_uuid = $1 LIMIT 1`,
        [notificationUUID],
      ).catch(() => [] as Array<{ processed_at: string | null }>)
      if (prior[0]?.processed_at) {
        return NextResponse.json({ ok: true, duplicate: true })
      }
    }
  }

  const markProcessed = async () => {
    if (notificationUUID) {
      await customerExecute(
        `UPDATE apple_notification_events SET processed_at = now() WHERE notification_uuid = $1`,
        [notificationUUID],
      ).catch(() => {})
    }
  }

  try {
    const signedTransactionInfo = notification.data?.signedTransactionInfo
    if (!signedTransactionInfo) {
      console.warn(`[billing/apple/notifications] ${notificationType} — no signedTransactionInfo, ack + skip`)
      await markProcessed()
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
      await markProcessed()
      return NextResponse.json({ ok: true, unhandled: true })
    }

    const plan = planFor(transaction.productId ?? '')
    if (!plan) {
      console.warn(`[billing/apple/notifications] unknown productId ${transaction.productId} — ack, no-op`)
      await markProcessed()
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
      await markProcessed()
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

    // DID_CHANGE_RENEWAL_PREF + subtype UPGRADE: the customer switched, with IMMEDIATE
    // effect, to a different product in the SAME subscription group (apple-products.ts —
    // "ONE subscription group ... a customer can only ever hold one active tier at a
    // time on iOS"). The transaction above already reflects the NEW product; nothing in
    // this payload names the OLD one, so retire it by elimination: any OTHER bot this
    // same user owns via Apple that is NOT part of the new plan is the product being
    // replaced. (DOWNGRADE is deliberately excluded — it takes effect at the next renewal,
    // not now, so the old product's row is still genuinely active and must not be touched
    // here; the eventual DID_RENEW/EXPIRED on it will settle it when the switch lands.)
    if (notificationType === 'DID_CHANGE_RENEWAL_PREF' && notification.subtype === 'UPGRADE') {
      const keep = new Set(plan.bots)
      const owned = await customerQuery<{ bot: string }>(
        `SELECT bot FROM customer_bot_subscriptions
          WHERE user_id = $1 AND provider = 'apple' AND status IN ('trialing', 'active', 'past_due')`,
        [userId],
      )
      for (const row of owned) {
        if (keep.has(row.bot)) continue
        console.warn(
          `[billing/apple/notifications] DID_CHANGE_RENEWAL_PREF/UPGRADE — retiring old product's bot=${row.bot} for user=${userId} in favor of ${plan.bots.join('+')}`,
        )
        await upsertSubscription({
          userId,
          bot: row.bot,
          status: 'canceled',
          provider: 'apple',
          currentPeriodEnd: null,
        })
        await emitMembershipEvent({
          eventId: `apple:${notification.notificationUUID ?? transaction.originalTransactionId}:${notificationType}:downgrade:${row.bot}`,
          eventType: 'crm.membership_canceled',
          userId,
          bots: [row.bot],
          bundle: false,
          status: 'canceled',
        })
      }
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

    await markProcessed()
    return NextResponse.json({ ok: true })
  } catch (e) {
    // Genuine handler failure (transient DB blip, unexpected throw) — NOT a legitimate
    // no-op, which always returns 200 above. Record the failure on the dead-letter row and
    // return 500 so Apple retries with backoff; see the route comment for why this differs
    // from this handler's old "ack 200 on any error" behavior.
    const msg = e instanceof Error ? e.message : String(e)
    console.error('[billing/apple/notifications] handler error:', e)
    if (notificationUUID) {
      await customerExecute(
        `UPDATE apple_notification_events SET error = $2, processed_at = NULL WHERE notification_uuid = $1`,
        [notificationUUID, msg.slice(0, 500)],
      ).catch(() => {})
    }
    return NextResponse.json({ ok: false, error: 'handler failed — will retry' }, { status: 500 })
  }
}
