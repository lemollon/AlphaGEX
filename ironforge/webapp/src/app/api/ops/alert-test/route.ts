import { NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { isPublicMode } from '@/lib/auth/access'
import {
  isNtfyConfigured,
  isSmsGatewayConfigured,
  isTwilioConfigured,
  isDiscordConfigured,
  sendOpsPush,
} from '@/lib/sms'

/**
 * DOES AN OPS ALERT ACTUALLY REACH A PHONE, ON THE SERVICE THAT RAISES IT?
 *
 * 🚨 THE CHANNELS ARE PER-SERVICE, AND THE OLD TEST ROUTE WAS ON THE WRONG ONE.
 * `/api/sms-test` is classified operator-only, so it is reachable on
 * ironforge-legacy — which has NO alert env vars at all (`sms_configured: false`).
 * The alert vars (`ALERT_NTFY_TOPIC`, `ALERT_SMS_GATEWAY_TO`,
 * `ALERT_DISCORD_WEBHOOK`) live on **ironforge-customer**, which is also where the
 * scanner runs. So the one test you could actually run was testing a service that
 * never alerts, and it reported "no channel configured" while the real alerting
 * service was fully wired. Same shape as every other per-service trap here — see
 * `flame-live-armed-on-the-wrong-service`.
 *
 * This route lives under `/api/ops/`, a SHARED prefix, so it is served on BOTH
 * deployments and can finally answer the question on the service that matters.
 *
 *   GET  /api/ops/alert-test  → which channels does THIS service have? Booleans
 *                               only — never a topic, number, or key. No auth: it
 *                               reveals nothing a caller could use.
 *   POST /api/ops/alert-test  → send a real push through sendOpsPush.
 *                               Operator session required (it messages a human).
 *                               Body: { "severity": "info" | "critical" }
 *                               Default "critical", because that is the path that
 *                               has to work when something is actually wrong.
 */
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function channels() {
  return {
    ntfy: isNtfyConfigured(),
    sms_gateway: isSmsGatewayConfigured(),
    twilio: isTwilioConfigured(),
    discord_webhook: isDiscordConfigured(),
    /** `@here` does not push; only `<@id>` does. Unset = a CRITICAL Discord post is silent. */
    discord_user_id: !!process.env.DISCORD_ALERT_USER_ID?.trim(),
  }
}

/** True when at least one channel can actually wake someone up. Discord alone cannot. */
function canReachAPhone(): boolean {
  return isNtfyConfigured() || isSmsGatewayConfigured() || isTwilioConfigured()
}

export async function GET() {
  const c = channels()
  return NextResponse.json({
    service: process.env.RENDER_SERVICE_NAME ?? null,
    surface: process.env.IRONFORGE_MODE ?? 'both',
    channels: c,
    reaches_a_phone: canReachAPhone(),
    // The distinction that took this long to notice: a Discord webhook is a RECORD,
    // not an alert. Saying "configured" for a webhook-only service is how a family of
    // alerts sat unread in a channel.
    note: canReachAPhone()
      ? 'At least one push channel is live on this service.'
      : 'NO push channel on this service. A CRITICAL alert here would be silent — ' +
        'a Discord webhook alone posts to a channel, it does not wake anyone.',
  })
}

export async function POST(req: Request) {
  if (!isPublicMode()) {
    const ops = await getSession()
    if (!ops.userId) {
      return NextResponse.json({ ok: false, error: 'Operator session required.' }, { status: 401 })
    }
  }

  let severity: 'info' | 'critical' = 'critical'
  try {
    const body = await req.json()
    if (body?.severity === 'info') severity = 'info'
  } catch { /* empty body → critical */ }

  if (!canReachAPhone()) {
    return NextResponse.json({
      ok: false,
      sent: false,
      channels: channels(),
      error:
        'No push channel on this service — set ALERT_NTFY_TOPIC (or ALERT_SMS_GATEWAY_TO / TWILIO_*). ' +
        'Note these are PER-SERVICE: having them on another IronForge service does not help this one.',
    })
  }

  const res = await sendOpsPush({
    title: `alert test (${severity})`,
    body:
      'If this reached your phone, the watchdog and the "has not traded" heartbeat ' +
      'can reach you too. Nothing is wrong.',
    severity,
  })

  return NextResponse.json({ ok: res.sent, ...res, severity, channels: channels() })
}
