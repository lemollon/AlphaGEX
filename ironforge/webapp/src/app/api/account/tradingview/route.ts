import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * TradingView indicator perk (7/30): members provide the TradingView username that
 * invite-only script access is granted to.
 *
 * GET  → { username, granted } for the signed-in customer.
 * POST → { username } stores it, RESETS granted_at (access follows the username), and
 *        pings the operator over ntfy so the grant happens in the TradingView UI.
 *        The grant itself is manual for now; /api/ops/tradingview-grants tracks it.
 *
 * Usernames are TradingView handles, not secrets — but they are still customer data:
 * validated to a safe charset, never interpolated into markup, audit-logged on change.
 */

const USERNAME_RE = /^[A-Za-z0-9_.-]{2,40}$/

async function notifyOperator(username: string, email: string | null): Promise<void> {
  const topic = process.env.ALERT_NTFY_TOPIC
  if (!topic) return
  try {
    await fetch(`https://ntfy.sh/${encodeURIComponent(topic)}`, {
      method: 'POST',
      headers: { Title: 'IronForge: TradingView grant needed', Tags: 'chart_with_upwards_trend' },
      body: `Grant invite-only script access to TradingView user "${username}"${email ? ` (member ${email})` : ''}, then mark it granted via /api/ops/tradingview-grants.`,
    })
  } catch {
    // Best-effort: the ops list is the durable record; the push is a convenience.
  }
}

export async function GET() {
  const session = await getCustomerSession()
  if (!session.customerId) return NextResponse.json({ ok: false }, { status: 401 })
  if (!isCustomersDbConfigured()) return NextResponse.json({ ok: true, username: null, granted: false })

  const rows = await customerQuery<{ tradingview_username: string | null; tradingview_granted_at: string | null }>(
    `SELECT tradingview_username, tradingview_granted_at FROM users WHERE id = $1 LIMIT 1`,
    [session.customerId],
  )
  return NextResponse.json({
    ok: true,
    username: rows[0]?.tradingview_username ?? null,
    granted: Boolean(rows[0]?.tradingview_granted_at),
  })
}

export async function POST(req: NextRequest) {
  const session = await getCustomerSession()
  if (!session.customerId) return NextResponse.json({ ok: false }, { status: 401 })
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'Temporarily unavailable.' }, { status: 503 })
  }

  try {
    const body = (await req.json().catch(() => ({}))) as { username?: unknown }
    const username = typeof body.username === 'string' ? body.username.trim() : ''
    if (!USERNAME_RE.test(username)) {
      return NextResponse.json(
        { ok: false, error: 'Enter your TradingView username (letters, numbers, dot, dash or underscore).' },
        { status: 422 },
      )
    }

    const rows = await customerQuery<{ email: string | null; tradingview_username: string | null }>(
      `SELECT email, tradingview_username FROM users WHERE id = $1 LIMIT 1`,
      [session.customerId],
    )
    const user = rows[0]
    if (!user) return NextResponse.json({ ok: false }, { status: 401 })

    const unchanged = user.tradingview_username === username
    if (!unchanged) {
      // granted_at RESETS: access was granted to the OLD handle; the new one starts over.
      await customerExecute(
        `UPDATE users SET tradingview_username = $2, tradingview_granted_at = NULL, updated_at = now()
          WHERE id = $1`,
        [session.customerId, username],
      )
      await customerExecute(
        `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'TRADINGVIEW_USERNAME_SET', $2)`,
        [session.customerId, JSON.stringify({ username })],
      ).catch(() => {})
      await notifyOperator(username, user.email)
    }

    return NextResponse.json({ ok: true, username, granted: false })
  } catch (e) {
    console.error('[account/tradingview] failed:', e)
    return NextResponse.json({ ok: false, error: 'Something went wrong. Please try again.' }, { status: 500 })
  }
}
