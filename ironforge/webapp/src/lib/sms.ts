/**
 * Phone alert delivery for vol-regime alerts. Mirrors lib/email.ts: each channel
 * is guarded by env vars and a no-op (skipped) when unset, so it's safe to call
 * unconditionally alongside the email sender. Channels (any subset may be on):
 *
 *   ntfy push (instant, free — the operator subscribes to the topic in the ntfy app)
 *     ALERT_NTFY_TOPIC       — ntfy.sh topic name (treat as a secret; anyone who
 *                              knows it can send pushes to the subscriber)
 *
 *   Carrier email-to-SMS gateway (true SMS, no Twilio; delivery can lag minutes)
 *     ALERT_SMS_GATEWAY_TO   — gateway address(es), comma-separated, e.g.
 *                              5551234567@vtext.com. Sends a plain-text email via
 *                              the existing Resend config (RESEND_API_KEY/EMAIL_FROM).
 *
 *   Twilio SMS
 *     TWILIO_ACCOUNT_SID     — Twilio account SID (starts "AC...")
 *     TWILIO_AUTH_TOKEN      — Twilio auth token
 *     TWILIO_FROM_NUMBER     — your Twilio number in E.164 (e.g. +15551234567)
 *     ALERT_SMS_TO           — destination phone(s) in E.164, comma-separated
 */
import { isEmailConfigured } from './email'

const RESEND_ENDPOINT = 'https://api.resend.com/emails'

export function isTwilioConfigured(): boolean {
  return !!(
    process.env.TWILIO_ACCOUNT_SID &&
    process.env.TWILIO_AUTH_TOKEN &&
    process.env.TWILIO_FROM_NUMBER &&
    process.env.ALERT_SMS_TO
  )
}

export function isNtfyConfigured(): boolean {
  return !!process.env.ALERT_NTFY_TOPIC
}

export function isSmsGatewayConfigured(): boolean {
  return !!(process.env.ALERT_SMS_GATEWAY_TO && isEmailConfigured())
}

/** True when at least one phone channel is configured. */
export function isSmsConfigured(): boolean {
  return isTwilioConfigured() || isNtfyConfigured() || isSmsGatewayConfigured()
}

export function smsRecipients(): string[] {
  return (process.env.ALERT_SMS_TO || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

export function smsGatewayRecipients(): string[] {
  return (process.env.ALERT_SMS_GATEWAY_TO || '')
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

function alertBody(p: VolAlertSmsParams): string {
  const tag = p.reason === 'early-warning' ? 'EARLY WARN' : 'ALERT'
  const name = p.signalKey.replace(/_/g, ' ')
  const dir = p.direction ? ` (${p.direction})` : ''
  const vixStr =
    typeof p.vix === 'number' && typeof p.vix3m === 'number'
      ? ` VIX ${p.vix.toFixed(1)}/${p.vix3m.toFixed(1)}`
      : ''
  // Keep it to one SMS segment-ish; Twilio splits longer bodies automatically.
  return `IronForge ${tag}: ${name}${dir}.${p.headline ? ' ' + p.headline : ''}${vixStr}`.slice(0, 320)
}

async function sendViaTwilio(body: string): Promise<string[]> {
  const sid = process.env.TWILIO_ACCOUNT_SID as string
  const token = process.env.TWILIO_AUTH_TOKEN as string
  const from = process.env.TWILIO_FROM_NUMBER as string
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
        errors.push(`twilio ${to}: ${res.status} ${detail.slice(0, 140)}`)
      }
    } catch (e) {
      errors.push(`twilio ${to}: ${e instanceof Error ? e.message : 'send failed'}`)
    }
  }
  return errors
}

async function sendViaNtfy(p: VolAlertSmsParams, body: string): Promise<string[]> {
  const topic = process.env.ALERT_NTFY_TOPIC as string
  try {
    const res = await fetch(`https://ntfy.sh/${encodeURIComponent(topic)}`, {
      method: 'POST',
      headers: {
        Title: `IronForge ${p.reason === 'early-warning' ? 'early warning' : 'vol alert'}: ${p.signalKey.replace(/_/g, ' ')}`,
        Priority: p.reason === 'confirmed' ? 'high' : 'default',
        Tags: p.reason === 'confirmed' ? 'rotating_light' : 'warning',
      },
      body,
    })
    if (!res.ok) {
      const detail = await res.text().catch(() => '')
      return [`ntfy: ${res.status} ${detail.slice(0, 140)}`]
    }
    return []
  } catch (e) {
    return [`ntfy: ${e instanceof Error ? e.message : 'send failed'}`]
  }
}

/** Plain-text email to a carrier SMS gateway (vtext.com etc.) via Resend. */
async function sendViaSmsGateway(p: VolAlertSmsParams, body: string): Promise<string[]> {
  try {
    const res = await fetch(RESEND_ENDPOINT, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: process.env.EMAIL_FROM,
        to: smsGatewayRecipients(),
        // Gateways render subject + body; keep the subject minimal.
        subject: `IronForge ${p.reason === 'early-warning' ? 'early warn' : 'alert'}`,
        text: body,
      }),
    })
    if (!res.ok) {
      const detail = await res.text().catch(() => '')
      return [`sms-gateway: Resend ${res.status} ${detail.slice(0, 140)}`]
    }
    return []
  } catch (e) {
    return [`sms-gateway: ${e instanceof Error ? e.message : 'send failed'}`]
  }
}

/**
 * Push a short vol-alert to the operator's phone over every configured channel
 * (ntfy push, carrier SMS gateway, Twilio). Sent if at least one channel
 * delivered; failures from the others are aggregated into `error`.
 */
export async function sendVolAlertSms(p: VolAlertSmsParams): Promise<SmsResult> {
  if (!isSmsConfigured()) return { sent: false, skipped: true }
  const body = alertBody(p)
  const errors: string[] = []
  let delivered = 0

  const channels: Array<[boolean, () => Promise<string[]>]> = [
    [isNtfyConfigured(), () => sendViaNtfy(p, body)],
    [isSmsGatewayConfigured(), () => sendViaSmsGateway(p, body)],
    [isTwilioConfigured(), () => sendViaTwilio(body)],
  ]
  for (const [on, send] of channels) {
    if (!on) continue
    const errs = await send()
    if (errs.length === 0) delivered++
    errors.push(...errs)
  }

  if (delivered > 0) return errors.length ? { sent: true, error: errors.join('; ') } : { sent: true }
  return { sent: false, error: errors.join('; ') || 'no channel delivered' }
}
