import { NextRequest, NextResponse } from 'next/server'
import { resolveCustomerUserId } from '@/lib/brokerage/identity'
import { isTradierOAuthConfigured, signState, buildAuthorizeUrl } from '@/lib/tradier-oauth'
import { isCustomersDbConfigured, customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Starts a Tradier connection. Signs a CSRF state carrying the customer id and returns Tradier's
 * OAuth authorize URL. The actual broker login happens on Tradier; we get a code back at the
 * tradier/callback route. (Tradier is a second provider — SnapTrade doesn't support it.)
 */
export async function POST(req: NextRequest) {
  const uid = await resolveCustomerUserId(req)
  if (!uid) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })

  if (!isTradierOAuthConfigured() || !isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'Tradier connection is temporarily unavailable. Please try again shortly.' },
      { status: 503 },
    )
  }

  try {
    const redirectURI = buildAuthorizeUrl(signState(uid))
    await customerExecute(
      `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'BROKERAGE_CONNECT_STARTED', $2)`,
      [uid, JSON.stringify({ provider: 'tradier' })],
    ).catch(() => {})
    return NextResponse.json({ ok: true, redirectURI })
  } catch (e) {
    console.error('[tradier/connect] failed:', e)
    return NextResponse.json({ ok: false, error: 'Something went wrong. Please try again.' }, { status: 500 })
  }
}
