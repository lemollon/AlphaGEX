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
 *   Discord webhook (rich embed + @here ping)
 *     ALERT_DISCORD_WEBHOOK  — full Discord webhook URL
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

export function isDiscordConfigured(): boolean {
  return !!process.env.ALERT_DISCORD_WEBHOOK
}

/** True when at least one phone channel is configured. */
export function isSmsConfigured(): boolean {
  return isTwilioConfigured() || isNtfyConfigured() || isSmsGatewayConfigured() || isDiscordConfigured()
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
  /** Optional extras used by the Discord embed. */
  message?: string | null
  vvix?: number | null
  proximity?: number | null
  regimeLabel?: string | null
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

const IRONFORGE_ICON = 'https://ironforge.trade/apple-touch-icon.png'

/** Rich Discord embed + @here ping so it lands loud in the phone's notifications. */
async function sendViaDiscord(p: VolAlertSmsParams): Promise<string[]> {
  const url = process.env.ALERT_DISCORD_WEBHOOK as string
  const isEarly = p.reason === 'early-warning'
  const bullish = (p.direction || '').toLowerCase().includes('bull')
  const dirEmoji = bullish ? '🟢📈' : '🔴📉'
  const color = isEarly ? 0xf59e0b : bullish ? 0x22c55e : 0xef4444
  const name = p.signalKey.replace(/_/g, ' ')
  const dir = p.direction ? ` (${p.direction})` : ''
  const kicker = isEarly ? 'EARLY WARNING' : 'CONFIRMED SIGNAL'
  const ratio =
    typeof p.vix === 'number' && typeof p.vix3m === 'number' && p.vix3m
      ? (p.vix / p.vix3m).toFixed(3)
      : null
  const fields: Array<{ name: string; value: string; inline: boolean }> = []
  if (typeof p.vix === 'number' && typeof p.vix3m === 'number') {
    fields.push({
      name: 'VIX / VIX3M',
      value: `${p.vix.toFixed(2)} / ${p.vix3m.toFixed(2)}${ratio ? ` (ratio ${ratio})` : ''}`,
      inline: true,
    })
  }
  if (typeof p.vvix === 'number') fields.push({ name: 'VVIX', value: p.vvix.toFixed(0), inline: true })
  if (typeof p.proximity === 'number') fields.push({ name: 'Proximity', value: `${(p.proximity * 100).toFixed(0)}%`, inline: true })
  if (p.regimeLabel) fields.push({ name: 'Regime', value: p.regimeLabel.replace(/_/g, ' '), inline: true })
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: 'IronForge',
        avatar_url: IRONFORGE_ICON,
        content: `@here ${dirEmoji} **IronForge ${isEarly ? 'EARLY WARN' : 'VOL ALERT'}: ${name}${dir}**${p.headline ? ` — ${p.headline}` : ''}`,
        allowed_mentions: { parse: ['everyone'] },
        embeds: [
          {
            title: `${dirEmoji} ${name}${dir} — ${kicker}`,
            description: `${p.headline ? `**${p.headline}**` : ''}${p.message ? `\n${p.message}` : ''}`,
            color,
            thumbnail: { url: IRONFORGE_ICON },
            fields,
            footer: {
              text: `IronForge volatility-regime monitor • ${isEarly ? 'tripped, not yet confirmed' : 'sustained and confirmed'}`,
            },
            timestamp: new Date().toISOString(),
          },
        ],
      }),
    })
    if (!res.ok) {
      const detail = await res.text().catch(() => '')
      return [`discord: ${res.status} ${detail.slice(0, 140)}`]
    }
    return []
  } catch (e) {
    return [`discord: ${e instanceof Error ? e.message : 'send failed'}`]
  }
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
 * (Discord embed, ntfy push, carrier SMS gateway, Twilio). Sent if at least one channel
 * delivered; failures from the others are aggregated into `error`.
 */
export async function sendVolAlertSms(p: VolAlertSmsParams): Promise<SmsResult> {
  if (!isSmsConfigured()) return { sent: false, skipped: true }
  const body = alertBody(p)
  const errors: string[] = []
  let delivered = 0

  const channels: Array<[boolean, () => Promise<string[]>]> = [
    [isDiscordConfigured(), () => sendViaDiscord(p)],
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

/* ------------------------------------------------------------------ */
/*  Generic operational push — the watchdog and the trade heartbeat     */
/* ------------------------------------------------------------------ */

/**
 * PUSH AN OPS ALERT TO THE OPERATOR'S PHONE.
 *
 * 🚨 THIS EXISTS BECAUSE `@here` DOES NOT PUSH TO A PHONE. A whole family of
 * IronForge alerts landed in a Discord channel nobody was looking at, and the
 * standing fix — "get the Discord user ID so `<@id>` can ping" — was never done.
 *
 * It also was not necessary: `ALERT_NTFY_TOPIC` has been configured on this service
 * the whole time, and ntfy is an actual phone push. The Discord embed stays (it is
 * the readable record); this is the part that wakes someone up.
 *
 * Deliberately NOT routed through the Discord channel here — `postOpsAlert` in
 * ./discord already posts the embed, and duplicating it would double every alert.
 *
 * Best-effort and never throws: an alert path that can take down the thing it is
 * alerting about is worse than no alert.
 */
export async function sendOpsPush(args: {
  title: string
  body: string
  /** 'critical' pushes at high priority so it breaks through a quiet phone. */
  severity: 'info' | 'critical'
}): Promise<SmsResult> {
  const anyPhoneChannel =
    isNtfyConfigured() || isSmsGatewayConfigured() || isTwilioConfigured()
  if (!anyPhoneChannel) {
    console.warn(
      '[sms] no phone channel configured (ALERT_NTFY_TOPIC / ALERT_SMS_GATEWAY_TO / ' +
      'TWILIO_*) — an ops alert is going out with NO phone push.',
    )
    return { sent: false, skipped: true }
  }

  const body = `IronForge: ${args.title}\n${args.body}`.slice(0, 320)
  const errors: string[] = []
  const reached: string[] = []
  let delivered = 0

  if (isNtfyConfigured()) {
    const topic = process.env.ALERT_NTFY_TOPIC as string
    try {
      const res = await fetch(`https://ntfy.sh/${encodeURIComponent(topic)}`, {
        method: 'POST',
        headers: {
          Title: `IronForge: ${args.title}`.slice(0, 200),
          Priority: args.severity === 'critical' ? 'high' : 'default',
          Tags: args.severity === 'critical' ? 'rotating_light' : 'wrench',
        },
        body,
      })
      if (res.ok) { delivered++; reached.push('ntfy') }
      else errors.push(`ntfy: ${res.status} ${(await res.text().catch(() => '')).slice(0, 140)}`)
    } catch (e) {
      errors.push(`ntfy: ${e instanceof Error ? e.message : 'send failed'}`)
    }
  }

  // Only a CRITICAL alert is worth an SMS segment or a Twilio charge. An FYI that
  // the watchdog healed something belongs on the push channel and in Discord.
  if (args.severity === 'critical') {
    const params: VolAlertSmsParams = {
      signalKey: args.title,
      reason: 'confirmed',
      headline: args.body.slice(0, 200),
    }
    if (isSmsGatewayConfigured()) {
      const errs = await sendViaSmsGateway(params, body)
      if (errs.length === 0) { delivered++; reached.push('sms_gateway') }
      errors.push(...errs)
    }
    if (isTwilioConfigured()) {
      const errs = await sendViaTwilio(body)
      if (errs.length === 0) { delivered++; reached.push('twilio') }
      errors.push(...errs)
    }
  }

  // 🚨 SAY WHERE IT WENT, AND SAY IT AFTER THE SEND — not before.
  //
  // This used to be silent on success, so after the fact there was NO way to answer
  // "what channel did that alert go to". Same shape as the bug this whole alerting
  // path exists to catch: an outcome nobody read back. `reached` is built from the
  // RESPONSES, not from which channels were configured, so it reports delivery
  // rather than intent.
  if (delivered > 0) {
    console.log(
      `[sms] ops push [${args.severity}] "${args.title}" delivered via ` +
      `${reached.join(', ')}${errors.length ? ` (also failed: ${errors.join('; ')})` : ''}`,
    )
    return errors.length ? { sent: true, error: errors.join('; ') } : { sent: true }
  }
  console.error(
    `[sms] *** OPS PUSH NOT DELIVERED *** [${args.severity}] "${args.title}" — ` +
    `${errors.join('; ') || 'no channel delivered'}`,
  )
  return { sent: false, error: errors.join('; ') || 'no channel delivered' }
}
