import { NextRequest, NextResponse } from 'next/server'
import { verifyPassword } from '@/lib/auth/password'
import { TIMING_DUMMY_HASH } from '@/lib/auth/customer-auth'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { signStepUpToken } from '@/lib/auth/mobile-token'
import { currentEpoch } from '@/lib/auth/mobile-session'
import { MOBILE_SESSION_POLICY } from '@/lib/auth/mobile-policy'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Step-up re-authentication (APP-010): trade a valid session + the account password for
 * a short-lived step-up token, required by MOBILE_SESSION_POLICY.stepUpActions.
 *
 * Biometrics unlock the stored refresh token on-device; they are NOT accepted here.
 * A fingerprint proves the phone's owner is present, not that the account holder
 * authorised a money-moving action — for that we want the password.
 */
export async function POST(req: NextRequest) {
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'Temporarily unavailable.' }, { status: 503 })
  }

  // Plain access token is enough to ASK; the password is what actually elevates.
  const identity = await getCustomerIdentity({ verifyEpoch: true })
  if (!identity || identity.source !== 'bearer') {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  const password = String(body.password ?? '')
  if (!password) {
    return NextResponse.json({ ok: false, error: 'Password is required.' }, { status: 400 })
  }

  const rows = await customerQuery<{ password_hash: string }>(
    `SELECT password_hash FROM users WHERE id = $1 LIMIT 1`,
    [identity.customerId],
  )
  // Dummy-hash compare on a missing row keeps the timing flat, as in customer-login.
  const ok = await verifyPassword(password, rows[0]?.password_hash ?? TIMING_DUMMY_HASH)
  if (!ok) {
    await customerExecute(
      `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'MOBILE_STEPUP_FAILED', $2)`,
      [identity.customerId, JSON.stringify({})],
    ).catch(() => {})
    return NextResponse.json(
      { ok: false, code: 'invalid_credentials', error: 'Incorrect password.' },
      { status: 401 },
    )
  }

  const epoch = await currentEpoch(identity.customerId)
  const stepUpToken = await signStepUpToken(identity.customerId, epoch)

  await customerExecute(
    `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'MOBILE_STEPUP', $2)`,
    [identity.customerId, JSON.stringify({ action: body.action ?? null })],
  ).catch(() => {})

  return NextResponse.json({
    ok: true,
    stepUpToken,
    expiresInSec: MOBILE_SESSION_POLICY.stepUpTtlSec,
  })
}
