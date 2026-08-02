import { NextRequest, NextResponse } from 'next/server'
import { rotateRefreshToken } from '@/lib/auth/mobile-session'
import { MOBILE_SESSION_POLICY } from '@/lib/auth/mobile-policy'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Exchange a refresh token for a new pair. Single-use: the presented token is dead
 * afterwards (MOBILE_SESSION_POLICY.rotateRefreshOnUse).
 *
 * Every failure returns 401 with a machine-readable `code` so the app can tell
 * "refresh again" from "send the user back to the password screen" — but the codes
 * describe the TOKEN, never the account, so an attacker holding a stolen token learns
 * nothing about whether the user exists or is still a customer.
 */
export async function POST(req: NextRequest) {
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  const refreshToken = String(body.refreshToken ?? '')
  if (!refreshToken) {
    return NextResponse.json({ ok: false, code: 'invalid', error: 'Refresh token required.' }, { status: 400 })
  }

  const result = await rotateRefreshToken(refreshToken, {
    deviceId: body.deviceId ? String(body.deviceId).slice(0, 200) : null,
    platform: body.platform ? String(body.platform).slice(0, 32) : null,
    appVersion: body.appVersion ? String(body.appVersion).slice(0, 32) : null,
    userAgent: req.headers.get('user-agent'),
  })

  if ('error' in result) {
    if (result.error === 'unconfigured') {
      return NextResponse.json(
        { ok: false, code: 'unavailable', error: 'Temporarily unavailable.' },
        { status: 503 },
      )
    }
    // reuse → the token was already rotated, so it leaked; every device in that family
    // has been signed out and the access-token epoch bumped. The app must re-login.
    return NextResponse.json(
      { ok: false, code: result.error, error: 'Please sign in again.' },
      { status: 401 },
    )
  }

  return NextResponse.json({ ok: true, ...result, policy: MOBILE_SESSION_POLICY })
}
