import { NextRequest, NextResponse } from 'next/server'
import { resolveCustomerUserId } from '@/lib/brokerage/identity'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isTradierOAuthConfigured, buildAuthorizeUrl, tradierPkceEnabled } from '@/lib/tradier-oauth'
import { createOAuthState } from '@/lib/enrollment/oauth-state'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'
import { enqueueCrmEvent } from '@/lib/crm/outbox'
import { mapBrokerageStatusToCrm } from '@/lib/crm/brokerage-status'

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
      // Derived from how the caller authenticated, never from the body — a spoofed
      // flag would aim our post-OAuth redirect at a surface the caller chose.
      client: (await getCustomerIdentity())?.source === 'bearer' ? 'mobile' : 'web',
    })
    const redirectURI = buildAuthorizeUrl(state, codeChallenge)
    const auditRows = await customerQuery<{ id: string }>(
      `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'BROKERAGE_CONNECT_STARTED', $2) RETURNING id`,
      [uid, JSON.stringify({ provider: 'tradier' })],
    ).catch(() => [] as Array<{ id: string }>)

    // Mirror the attempt as a Pending connection, exactly as the SnapTrade start route does.
    // Only SnapTrade emitted this, so a Tradier customer who started a connection and never
    // finished left no trace in the CRM at all — the drop-off the Brokerage Issues view is
    // meant to surface was invisible for the direct-Tradier half of the funnel.
    const auditId = auditRows[0]?.id
    if (auditId) {
      const user = (
        await customerQuery<{ email: string; first_name: string; last_name: string }>(
          `SELECT email, first_name, last_name FROM users WHERE id = $1 LIMIT 1`,
          [uid],
        ).catch(() => [] as Array<{ email: string; first_name: string; last_name: string }>)
      )[0]
      if (user) {
        await enqueueCrmEvent({
          eventId: `brokerage_initiated:${auditId}`,
          eventType: 'crm.brokerage_initiated',
          userId: uid,
          correlationId: `pending:${uid}`,
          payload: {
            email: user.email,
            firstName: user.first_name,
            lastName: user.last_name,
            ironforgeUserId: uid,
            connectionId: `pending:${uid}`,
            connectionStatus: mapBrokerageStatusToCrm('pending').connectionStatus,
            lastAttemptAt: new Date().toISOString(),
            reauthorizationRequired: false,
          },
        })
      }
    }
    return NextResponse.json({ ok: true, redirectURI })
  } catch (e) {
    console.error('[tradier/connect] failed:', e)
    return NextResponse.json({ ok: false, error: 'Something went wrong. Please try again.' }, { status: 500 })
  }
}
