import { NextRequest, NextResponse } from 'next/server'
import { publicOrigin } from '@/lib/public-origin'
import { resolveCustomerUserId } from '@/lib/brokerage/identity'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isTastytradeOAuthConfigured, buildAuthorizeUrl, tastytradePkceEnabled } from '@/lib/tastytrade-oauth'
import { createOAuthState } from '@/lib/enrollment/oauth-state'
import { isCustomersDbConfigured, customerExecute } from '@/lib/customers-db'
import { legalCompleteForOpenEnrollment } from '@/lib/enrollment/service'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Starts a tastytrade connection — the direct OAuth lane (tastytrade is also reachable today
 * through SnapTrade; see onboarding/brokerage/brokerages/route.ts). Mirrors
 * onboarding/brokerage/tradier/connect/route.ts exactly; the only structural difference is that
 * tastytrade's authorize/token endpoints both require an explicit redirect_uri, which Tradier's
 * app-level config doesn't.
 *
 * Until tastytrade approves the pending trusted-third-party request (sent 2026-08-12), this will
 * only work for the single tastytrade account the OAuth app itself belongs to — every other
 * customer's authorize attempt will be rejected by tastytrade, not by us.
 */
export async function POST(req: NextRequest) {
  const uid = await resolveCustomerUserId(req)
  if (!uid) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })

  let returnTo: 'enroll' | undefined
  try {
    const body = (await req.json().catch(() => null)) as { return_to?: unknown } | null
    if (body?.return_to === 'enroll') returnTo = 'enroll'
  } catch {
    /* default onboarding */
  }

  if (!isTastytradeOAuthConfigured() || !isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'tastytrade connection is temporarily unavailable. Please try again shortly.' },
      { status: 503 },
    )
  }

  if (!(await legalCompleteForOpenEnrollment(uid))) {
    return NextResponse.json(
      { ok: false, error: 'Please review and accept the required agreements before connecting a brokerage.' },
      { status: 409 },
    )
  }

  try {
    // oauth-state.ts owns PKCE generation/storage generically (it's provider-agnostic, not
    // Tradier-specific despite living next to the first provider that used it) — the verifier
    // never leaves the server, same guarantee as the Tradier lane.
    const { state, codeChallenge } = await createOAuthState({
      userId: uid,
      brokerCode: 'tastytrade',
      pkce: tastytradePkceEnabled(),
      returnTo,
      client: (await getCustomerIdentity())?.source === 'bearer' ? 'mobile' : 'web',
    })

    const redirectUri = `${publicOrigin(req)}/api/onboarding/brokerage/tastytrade/callback`
    const redirectURI = buildAuthorizeUrl(state, redirectUri, codeChallenge)
    await customerExecute(
      `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'BROKERAGE_CONNECT_STARTED', $2)`,
      [uid, JSON.stringify({ provider: 'tastytrade' })],
    ).catch(() => {})
    return NextResponse.json({ ok: true, redirectURI })
  } catch (e) {
    console.error('[tastytrade/connect] failed:', e)
    return NextResponse.json({ ok: false, error: 'Something went wrong. Please try again.' }, { status: 500 })
  }
}
