import { NextRequest, NextResponse } from 'next/server'
import { publicOrigin } from '@/lib/public-origin'
import { resolveCustomerUserId } from '@/lib/brokerage/identity'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isOptionsCapable } from '@/lib/brokerage/providers'
import { createOAuthState } from '@/lib/enrollment/oauth-state'
import { getSnapTrade, isSnapTradeConfigured } from '@/lib/snaptrade'
import { encryptSecret, decryptSecret } from '@/lib/crypto/secret-box'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'
import { enqueueCrmEvent } from '@/lib/crm/outbox'
import { mapBrokerageStatusToCrm } from '@/lib/crm/brokerage-status'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Starts a brokerage connection. Idempotently registers the customer as a SnapTrade user
 * (userId = our users.id), stores the returned userSecret ENCRYPTED, then mints a hosted
 * Connection Portal redirect URL (trade-enabled) and hands it back to the client. The broker
 * login / 2FA / OTP all happen on SnapTrade's portal — we never see credentials.
 */

interface UserRow {
  id: string
  snaptrade_user_id: string | null
  snaptrade_user_secret: string | null
  email: string
  first_name: string
  last_name: string
}

export async function POST(req: NextRequest) {
  const uid = await resolveCustomerUserId(req)
  if (!uid) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })

  // Optional broker slug from the "Choose your broker" dropdown. When present, SnapTrade opens the
  // connection portal directly to that brokerage; when absent, the portal shows the full list.
  // return_to: which surface initiated this ('enroll' funnel vs legacy onboarding) — an
  // allowlisted literal carried on our own callback URL, never a caller-supplied URL.
  let broker: string | undefined
  let returnTo: 'enroll' | undefined
  try {
    const body = (await req.json().catch(() => null)) as { broker?: unknown; return_to?: unknown } | null
    if (body && typeof body.broker === 'string' && body.broker.trim()) broker = body.broker.trim()
    if (body?.return_to === 'enroll') returnTo = 'enroll'
  } catch {
    // no/invalid body — fine, fall through to the full-list portal
  }

  // APP-041 provider allowlist, ENFORCED at the API boundary. The curated list already
  // existed but only filtered the dropdown, while this route passed the client-supplied
  // slug straight through to SnapTrade — so a caller could connect a crypto exchange the
  // bot can never trade in, and only find out later.
  if (broker && !isOptionsCapable(broker)) {
    return NextResponse.json(
      { ok: false, error: 'That brokerage is not supported for options trading.' },
      { status: 400 },
    )
  }

  if (!isSnapTradeConfigured() || !isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'Brokerage connection is temporarily unavailable. Please try again shortly.' },
      { status: 503 },
    )
  }

  try {
    const snaptrade = getSnapTrade()
    const rows = await customerQuery<UserRow>(
      `SELECT id, snaptrade_user_id, snaptrade_user_secret, email, first_name, last_name
         FROM users WHERE id = $1 LIMIT 1`,
      [uid],
    )
    const user = rows[0]
    if (!user) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })

    let userSecret: string
    if (user.snaptrade_user_id && user.snaptrade_user_secret) {
      userSecret = decryptSecret(user.snaptrade_user_secret)
    } else {
      const reg = await snaptrade.authentication.registerSnapTradeUser({ userId: user.id })
      userSecret = reg.data.userSecret as string
      await customerExecute(
        `UPDATE users SET snaptrade_user_id = $2, snaptrade_user_secret = $3, updated_at = now() WHERE id = $1`,
        [user.id, user.id, encryptSecret(userSecret)],
      )
    }

    // Single-use server-side state, the same record the Tradier flow already uses.
    //
    // THIS IS WHAT MAKES THE MOBILE FLOW POSSIBLE. The callback previously resolved the
    // member from a COOKIE, and an ASWebAuthenticationSession / Custom Tab has its own
    // cookie jar — so the callback simply failed for the app. Carrying an opaque state
    // instead binds the callback to the initiating member with no cookie at all.
    //
    // The state rides our own customRedirect as a query param. That is proven to survive
    // SnapTrade's redirect: the existing production flow already carries `return_to` the
    // same way.
    const identity = await getCustomerIdentity()
    const client = identity?.source === 'bearer' ? 'mobile' : 'web'
    const { state } = await createOAuthState({
      userId: user.id,
      brokerCode: 'snaptrade',
      // SnapTrade's Connection Portal is not an OAuth2 authorize endpoint, so PKCE does
      // not apply. The binding here is the single-use state plus the server-held
      // userSecret. Tradier, which IS a real OAuth2 flow, carries PKCE separately.
      pkce: false,
      returnTo,
      client,
    })

    const redirectUrl = new URL(`${publicOrigin(req)}/api/onboarding/brokerage/callback`)
    if (returnTo) redirectUrl.searchParams.set('return_to', returnTo)
    redirectUrl.searchParams.set('state', state)

    const login = await snaptrade.authentication.loginSnapTradeUser({
      userId: user.id,
      userSecret,
      connectionType: 'trade',
      customRedirect: redirectUrl.toString(),
      ...(broker ? { broker } : {}),
    })
    const redirectURI = (login.data as { redirectURI?: string }).redirectURI
    if (!redirectURI) {
      return NextResponse.json({ ok: false, error: 'Could not start the connection.' }, { status: 502 })
    }

    const auditRows = await customerQuery<{ id: string }>(
      `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'BROKERAGE_CONNECT_STARTED', $2) RETURNING id`,
      [user.id, JSON.stringify(broker ? { broker } : {})],
    ).catch(() => [] as Array<{ id: string }>)

    // Mirror the attempt into the CRM as the Pending connection record. No brokerage_connections
    // row exists yet — that's created at the callback — so connectionId is a stable placeholder
    // per attempt (the audit row this same request just wrote), keyed the same way an eventual
    // real connection would be.
    const auditId = auditRows[0]?.id
    if (auditId) {
      await enqueueCrmEvent({
        eventId: `brokerage_initiated:${auditId}`,
        eventType: 'crm.brokerage_initiated',
        userId: user.id,
        correlationId: `pending:${user.id}`,
        payload: {
          email: user.email,
          firstName: user.first_name,
          lastName: user.last_name,
          ironforgeUserId: user.id,
          connectionId: `pending:${user.id}`,
          connectionStatus: mapBrokerageStatusToCrm('pending').connectionStatus,
          lastAttemptAt: new Date().toISOString(),
          reauthorizationRequired: false,
        },
      })
    }

    return NextResponse.json({ ok: true, redirectURI })
  } catch (e) {
    console.error('[brokerage/connect] failed:', e)
    return NextResponse.json({ ok: false, error: 'Something went wrong. Please try again.' }, { status: 500 })
  }
}
