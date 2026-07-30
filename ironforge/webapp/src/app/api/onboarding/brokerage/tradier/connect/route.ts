import { NextRequest, NextResponse } from 'next/server'
import { resolveCustomerUserId } from '@/lib/brokerage/identity'
import { isTradierOAuthConfigured, buildAuthorizeUrl, tradierPkceEnabled } from '@/lib/tradier-oauth'
import { createOAuthState } from '@/lib/enrollment/oauth-state'
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

  // Which surface initiated this (legacy onboarding vs the /enroll funnel). Stored on
  // the OAuth state so the callback lands the customer back where they started.
  let returnTo: 'enroll' | undefined
  try {
    const body = (await req.json().catch(() => null)) as { return_to?: unknown } | null
    if (body?.return_to === 'enroll') returnTo = 'enroll'
  } catch {
    /* default onboarding */
  }

  if (!isTradierOAuthConfigured() || !isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'Tradier connection is temporarily unavailable. Please try again shortly.' },
      { status: 503 },
    )
  }

  try {
    // Single-use, server-side state (§8). Replaces the stateless HMAC token, which
    // could not be made one-time: a stateless token is valid every time it is
    // presented, so a replayed callback replayed the whole exchange.
    const { state, codeChallenge } = await createOAuthState({
      userId: uid,
      brokerCode: 'tradier',
      pkce: tradierPkceEnabled(),
      returnTo,
    })
    const redirectURI = buildAuthorizeUrl(state, codeChallenge)
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
