import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'
import { isStripeConfigured, cancelSubscription } from '@/lib/billing/stripe'
import { getSnapTrade, isSnapTradeConfigured } from '@/lib/snaptrade'
import { decryptSecret } from '@/lib/crypto/secret-box'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Account deletion request (Google Play requires deletion to be requestable from a
 * public web URL — see /delete-account, which is the page this backs).
 *
 * The shape of this route is deliberate. This database also holds LIVE positions
 * against customers' real brokerage accounts, so an HTTP request never performs the
 * destructive purge. What it does:
 *
 *   1. REFUSES while any position is not in a settled state (see SETTLED_STATUSES).
 *   2. Cancels billing — the customer is leaving; continuing to charge them is the
 *      thing they would rightly be angriest about.
 *   3. Disconnects the brokerage — safe precisely because step 1 proved there is
 *      nothing open behind it.
 *   4. Records the request, with a per-step record of what actually succeeded.
 *
 * The PII purge is a separate reviewed step. Sessions are deliberately NOT revoked
 * here: the customer needs to stay signed in to cancel the request during the grace
 * period, and a purge they cannot call off is not a grace period.
 */

/**
 * Statuses that mean "nothing of this position is live any more".
 *
 * This is an ALLOWLIST, and that direction is the whole point: a status invented
 * later (a new partial-fill or retry state, say) must block deletion until someone
 * has decided it is safe. A denylist would silently let the new state through and
 * delete an account with real money exposed behind it.
 */
const SETTLED_STATUSES = ['closed', 'skipped'] as const

/** How long a request can be called off before the purge is eligible to run. */
const GRACE_PERIOD_DAYS = 14

interface OpenPositionRow {
  status: string
  n: string
}

interface SubRow {
  stripe_subscription_id: string | null
}

interface ConnRow {
  authorization_id: string | null
}

interface UserSnapRow {
  snaptrade_user_id: string | null
  snaptrade_user_secret: string | null
}

export async function GET() {
  const identity = await getCustomerIdentity()
  if (!identity) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'unavailable' }, { status: 503 })
  }

  const rows = await customerQuery<{ status: string; requested_at: string }>(
    `SELECT status, requested_at FROM account_deletion_requests
      WHERE user_id = $1 AND status = 'requested'
      ORDER BY requested_at DESC LIMIT 1`,
    [identity.customerId],
  )
  const open = rows[0] ?? null
  return NextResponse.json({
    ok: true,
    pending: Boolean(open),
    requestedAt: open?.requested_at ?? null,
    gracePeriodDays: GRACE_PERIOD_DAYS,
  })
}

export async function POST(req: NextRequest) {
  // Cookie OR mobile bearer, so this works identically from the app and the web.
  const identity = await getCustomerIdentity()
  if (!identity) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'unavailable' }, { status: 503 })
  }
  const userId = identity.customerId

  try {
    // ── Guard: refuse while anything is still live ────────────────────────────
    // Checked BEFORE the request row is written, so a blocked attempt leaves no
    // trace suggesting a deletion is under way.
    const openRows = await customerQuery<OpenPositionRow>(
      `SELECT status, COUNT(*)::text AS n
         FROM customer_positions
        WHERE user_id = $1 AND status <> ALL($2::text[])
        GROUP BY status`,
      [userId, SETTLED_STATUSES as unknown as string[]],
    )
    if (openRows.length > 0) {
      const total = openRows.reduce((acc, r) => acc + Number(r.n), 0)
      return NextResponse.json(
        {
          ok: false,
          error: 'open_positions',
          message:
            `You still have ${total} position${total === 1 ? '' : 's'} that ${total === 1 ? 'is' : 'are'} not settled. ` +
            `Close ${total === 1 ? 'it' : 'them'} before requesting deletion, so nothing is left running in your brokerage account.`,
          positions: openRows.map((r) => ({ status: r.status, count: Number(r.n) })),
        },
        { status: 409 },
      )
    }

    // ── Idempotency ───────────────────────────────────────────────────────────
    // A double-tap must not cancel billing twice or produce a second open request
    // (the partial unique index would reject it anyway — this returns the honest
    // answer instead of a 500).
    const existing = await customerQuery<{ id: string; requested_at: string }>(
      `SELECT id, requested_at FROM account_deletion_requests
        WHERE user_id = $1 AND status = 'requested' LIMIT 1`,
      [userId],
    )
    if (existing[0]) {
      return NextResponse.json({
        ok: true,
        alreadyRequested: true,
        requestedAt: existing[0].requested_at,
        gracePeriodDays: GRACE_PERIOD_DAYS,
      })
    }

    const steps: Record<string, string> = {}

    // ── Cancel billing ────────────────────────────────────────────────────────
    if (isStripeConfigured()) {
      const subs = await customerQuery<SubRow>(
        `SELECT stripe_subscription_id FROM customer_bot_subscriptions
          WHERE user_id = $1 AND stripe_subscription_id IS NOT NULL
            AND status NOT IN ('canceled', 'incomplete_expired')`,
        [userId],
      )
      let cancelled = 0
      for (const s of subs) {
        if (!s.stripe_subscription_id) continue
        try {
          await cancelSubscription(s.stripe_subscription_id)
          cancelled += 1
        } catch (e) {
          // Recorded, not swallowed. A subscription still billing after a deletion
          // request is a money problem someone has to see.
          steps[`billing_error_${s.stripe_subscription_id}`] =
            e instanceof Error ? e.message : String(e)
        }
      }
      steps.billing = `cancelled ${cancelled}/${subs.length}`
    } else {
      steps.billing = 'stripe not configured'
    }

    // ── Disconnect the brokerage ──────────────────────────────────────────────
    // Safe because the guard above proved there is nothing open behind it.
    if (isSnapTradeConfigured()) {
      const userRows = await customerQuery<UserSnapRow>(
        `SELECT snaptrade_user_id, snaptrade_user_secret FROM users WHERE id = $1 LIMIT 1`,
        [userId],
      )
      const u = userRows[0]
      const conns = await customerQuery<ConnRow>(
        `SELECT authorization_id FROM brokerage_connections
          WHERE user_id = $1 AND status = 'active' AND authorization_id IS NOT NULL`,
        [userId],
      )
      if (u?.snaptrade_user_id && u.snaptrade_user_secret && conns.length > 0) {
        const snaptrade = getSnapTrade()
        const userSecret = decryptSecret(u.snaptrade_user_secret)
        let removed = 0
        for (const c of conns) {
          if (!c.authorization_id) continue
          try {
            await snaptrade.connections.removeBrokerageAuthorization({
              authorizationId: c.authorization_id,
              userId: u.snaptrade_user_id,
              userSecret,
            })
            await customerExecute(
              `UPDATE brokerage_connections SET status = 'removed', updated_at = now()
                WHERE user_id = $1 AND authorization_id = $2`,
              [userId, c.authorization_id],
            )
            removed += 1
          } catch (e) {
            steps[`brokerage_error_${c.authorization_id}`] =
              e instanceof Error ? e.message : String(e)
          }
        }
        await customerExecute(
          `UPDATE users SET brokerage_connected = FALSE, updated_at = now()
            WHERE id = $1
              AND NOT EXISTS (
                SELECT 1 FROM brokerage_connections bc
                 WHERE bc.user_id = $1 AND bc.status = 'active')`,
          [userId],
        ).catch(() => {})
        steps.brokerage = `removed ${removed}/${conns.length}`
      } else {
        steps.brokerage = 'no active connection'
      }
    } else {
      steps.brokerage = 'snaptrade not configured'
    }

    // ── Record the request ────────────────────────────────────────────────────
    const inserted = await customerQuery<{ id: string; requested_at: string }>(
      `INSERT INTO account_deletion_requests
         (user_id, status, steps_json, requested_ip, requested_user_agent)
       VALUES ($1, 'requested', $2, $3, $4)
       ON CONFLICT DO NOTHING
       RETURNING id, requested_at`,
      [
        userId,
        JSON.stringify(steps),
        req.headers.get('x-forwarded-for'),
        req.headers.get('user-agent'),
      ],
    )
    // ON CONFLICT DO NOTHING returns no row if the partial unique index fired,
    // which means a concurrent request won the race. Verifying by re-reading STATE
    // rather than trusting the write is the rule here — an INSERT that wrote
    // nothing must not be reported as success.
    if (!inserted[0]) {
      const now = await customerQuery<{ requested_at: string }>(
        `SELECT requested_at FROM account_deletion_requests
          WHERE user_id = $1 AND status = 'requested' LIMIT 1`,
        [userId],
      )
      if (!now[0]) {
        return NextResponse.json(
          { ok: false, error: 'Could not record the request. Please try again.' },
          { status: 500 },
        )
      }
      return NextResponse.json({
        ok: true,
        alreadyRequested: true,
        requestedAt: now[0].requested_at,
        gracePeriodDays: GRACE_PERIOD_DAYS,
      })
    }

    await customerExecute(
      `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'ACCOUNT_DELETION_REQUESTED', $2)`,
      [userId, JSON.stringify(steps)],
    ).catch(() => {})

    return NextResponse.json({
      ok: true,
      requestedAt: inserted[0].requested_at,
      gracePeriodDays: GRACE_PERIOD_DAYS,
      steps,
    })
  } catch (e) {
    console.error('[account/deletion-request] failed:', e)
    return NextResponse.json({ ok: false, error: 'Something went wrong.' }, { status: 500 })
  }
}

/** Calls off a pending request during the grace period. */
export async function DELETE() {
  const identity = await getCustomerIdentity()
  if (!identity) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'unavailable' }, { status: 503 })
  }

  const n = await customerExecute(
    `UPDATE account_deletion_requests
        SET status = 'cancelled', cancelled_at = now()
      WHERE user_id = $1 AND status = 'requested'`,
    [identity.customerId],
  )
  if (n === 0) {
    return NextResponse.json({ ok: false, error: 'no_pending_request' }, { status: 404 })
  }
  await customerExecute(
    `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'ACCOUNT_DELETION_CANCELLED', $2)`,
    [identity.customerId, JSON.stringify({})],
  ).catch(() => {})
  // Deliberately does NOT restore the cancelled subscription or the removed
  // brokerage connection — neither is ours to re-create, and silently resubscribing
  // someone would be worse than making them do it themselves. /delete-account says so.
  return NextResponse.json({ ok: true, cancelled: true })
}
