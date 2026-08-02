import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { customerExecute, isCustomersDbConfigured } from '@/lib/customers-db'
import { isExpoPushToken } from '@/lib/push/transport'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Device token registration (APP-033).
 *
 * The owner ALWAYS comes from the authenticated identity, never from the body —
 * APP-045's "never trust client-supplied ownership identifiers", and the shape of bug
 * that would let anyone redirect another customer's notifications to their own phone.
 */
export async function POST(req: NextRequest) {
  const identity = await getCustomerIdentity()
  if (!identity) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'unavailable' }, { status: 503 })
  }

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  const token = String(body.expoPushToken ?? '')
  const platform = String(body.platform ?? '')

  if (!isExpoPushToken(token)) {
    return NextResponse.json({ ok: false, error: 'Invalid push token.' }, { status: 400 })
  }
  if (platform !== 'ios' && platform !== 'android') {
    return NextResponse.json({ ok: false, error: 'Invalid platform.' }, { status: 400 })
  }

  // A physical device that reinstalls under a different login MOVES to the new owner.
  // Without the user_id reassignment the previous owner would keep receiving that
  // handset's notifications — a cross-tenant leak dressed up as a stale row.
  await customerExecute(
    `INSERT INTO push_devices (user_id, expo_push_token, device_id, platform, app_version)
     VALUES ($1, $2, $3, $4, $5)
     ON CONFLICT (expo_push_token) DO UPDATE
       SET user_id = EXCLUDED.user_id,
           device_id = EXCLUDED.device_id,
           platform = EXCLUDED.platform,
           app_version = EXCLUDED.app_version,
           enabled = TRUE,
           disabled_reason = NULL,
           failure_count = 0,
           last_seen_at = now(),
           updated_at = now()`,
    [
      identity.customerId,
      token,
      body.deviceId ? String(body.deviceId).slice(0, 200) : null,
      platform,
      body.appVersion ? String(body.appVersion).slice(0, 32) : null,
    ],
  )

  // Ensure a prefs row exists so the settings screen has something to read.
  await customerExecute(
    `INSERT INTO notification_prefs (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING`,
    [identity.customerId],
  ).catch(() => {})

  return NextResponse.json({ ok: true })
}

/** Unregister on sign-out. Scoped to the caller so B cannot silence A's phone. */
export async function DELETE(req: NextRequest) {
  const identity = await getCustomerIdentity()
  if (!identity) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  const token = String(body.expoPushToken ?? '')
  if (!token) return NextResponse.json({ ok: false, error: 'Token required.' }, { status: 400 })

  await customerExecute(
    `UPDATE push_devices
        SET enabled = FALSE, disabled_reason = 'logout', updated_at = now()
      WHERE expo_push_token = $1 AND user_id = $2`,
    [token, identity.customerId],
  )
  return NextResponse.json({ ok: true })
}
