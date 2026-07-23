import { NextRequest, NextResponse } from 'next/server'
import { publicOrigin } from '@/lib/public-origin'
import { resolveCustomerUserId } from '@/lib/brokerage/identity'
import { getSnapTrade, isSnapTradeConfigured } from '@/lib/snaptrade'
import { encryptSecret, decryptSecret } from '@/lib/crypto/secret-box'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'

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
}

export async function POST(req: NextRequest) {
  const uid = await resolveCustomerUserId(req)
  if (!uid) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })

  // Optional broker slug from the "Choose your broker" dropdown. When present, SnapTrade opens the
  // connection portal directly to that brokerage; when absent, the portal shows the full list.
  let broker: string | undefined
  try {
    const body = (await req.json().catch(() => null)) as { broker?: unknown } | null
    if (body && typeof body.broker === 'string' && body.broker.trim()) broker = body.broker.trim()
  } catch {
    // no/invalid body — fine, fall through to the full-list portal
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
      `SELECT id, snaptrade_user_id, snaptrade_user_secret FROM users WHERE id = $1 LIMIT 1`,
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

    const login = await snaptrade.authentication.loginSnapTradeUser({
      userId: user.id,
      userSecret,
      connectionType: 'trade',
      customRedirect: `${publicOrigin(req)}/api/onboarding/brokerage/callback`,
      ...(broker ? { broker } : {}),
    })
    const redirectURI = (login.data as { redirectURI?: string }).redirectURI
    if (!redirectURI) {
      return NextResponse.json({ ok: false, error: 'Could not start the connection.' }, { status: 502 })
    }

    await customerExecute(
      `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'BROKERAGE_CONNECT_STARTED', $2)`,
      [user.id, JSON.stringify(broker ? { broker } : {})],
    ).catch(() => {})

    return NextResponse.json({ ok: true, redirectURI })
  } catch (e) {
    console.error('[brokerage/connect] failed:', e)
    return NextResponse.json({ ok: false, error: 'Something went wrong. Please try again.' }, { status: 500 })
  }
}
