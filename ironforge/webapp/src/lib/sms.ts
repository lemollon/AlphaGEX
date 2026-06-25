/**
 * SMS alert delivery via Twilio. Mirrors lib/email.ts: guarded by env vars, a
 * no-op (skipped) when unset, so it's safe to call unconditionally alongside the
 * email sender. Used to also push the vol-regime alerts to the operator's phone.
 *
 * Required env (set on the `ironforge` Render service):
 *   TWILIO_ACCOUNT_SID   — Twilio account SID (starts "AC...")
 *   TWILIO_AUTH_TOKEN    — Twilio auth token
 *   TWILIO_FROM_NUMBER   — your Twilio number in E.164 (e.g. +15551234567)
 *   ALERT_SMS_TO         — destination phone(s) in E.164, comma-separated
 */
export function isSmsConfigured(): boolean {
  return !!(
    process.env.TWILIO_ACCOUNT_SID &&
    process.env.TWILIO_AUTH_TOKEN &&
    process.env.TWILIO_FROM_NUMBER &&
    process.env.ALERT_SMS_TO
  )
}

export function smsRecipients(): string[] {
  return (process.env.ALERT_SMS_TO || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

export interface VolAlertSmsParams {
  signalKey: string
  direction?: string | null
  reason: 'early-warning' | 'confirmed'
  headline?: string | null
  vix?: number | null
  vix3m?: number | null
}

export interface SmsResult {
  sent: boolean
  skipped?: boolean
  error?: string
}

/** Send a short vol-alert SMS to every ALERT_SMS_TO recipient via Twilio. */
export async function sendVolAlertSms(p: VolAlertSmsParams): Promise<SmsResult> {
  if (!isSmsConfigured()) return { sent: false, skipped: true }
  const sid = process.env.TWILIO_ACCOUNT_SID as string
  const token = process.env.TWILIO_AUTH_TOKEN as string
  const from = process.env.TWILIO_FROM_NUMBER as string

  const tag = p.reason === 'early-warning' ? 'EARLY WARN' : 'ALERT'
  const name = p.signalKey.replace(/_/g, ' ')
  const dir = p.direction ? ` (${p.direction})` : ''
  const vixStr =
    typeof p.vix === 'number' && typeof p.vix3m === 'number'
      ? ` VIX ${p.vix.toFixed(1)}/${p.vix3m.toFixed(1)}`
      : ''
  // Keep it to one SMS segment-ish; Twilio splits longer bodies automatically.
  const body = `IronForge ${tag}: ${name}${dir}.${p.headline ? ' ' + p.headline : ''}${vixStr}`.slice(0, 320)

  const auth = Buffer.from(`${sid}:${token}`).toString('base64')
  const errors: string[] = []
  for (const to of smsRecipients()) {
    try {
      const res = await fetch(`https://api.twilio.com/2010-04-01/Accounts/${sid}/Messages.json`, {
        method: 'POST',
        headers: {
          Authorization: `Basic ${auth}`,
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: new URLSearchParams({ From: from, To: to, Body: body }).toString(),
      })
      if (!res.ok) {
        const detail = await res.text().catch(() => '')
        errors.push(`${to}: Twilio ${res.status} ${detail.slice(0, 140)}`)
      }
    } catch (e) {
      errors.push(`${to}: ${e instanceof Error ? e.message : 'send failed'}`)
    }
  }
  return errors.length ? { sent: false, error: errors.join('; ') } : { sent: true }
}
