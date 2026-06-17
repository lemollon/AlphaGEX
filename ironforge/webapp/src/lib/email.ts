/**
 * Transactional email via Resend (sub-project D).
 *
 * Guarded by RESEND_API_KEY + EMAIL_FROM. When unset, sends are skipped (no-op)
 * so the app runs fine before email is wired — mirrors the customers-db guard.
 * Swappable: only this module talks to the provider's HTTP API.
 */

const RESEND_ENDPOINT = 'https://api.resend.com/emails'

export function isEmailConfigured(): boolean {
  return !!(process.env.RESEND_API_KEY && process.env.EMAIL_FROM)
}

export interface SendResult {
  sent: boolean
  skipped?: boolean
  error?: string
}

function esc(s: string): string {
  return s.replace(/[<>&]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[c] as string))
}

function verificationHtml(firstName: string, verifyUrl: string): string {
  const name = firstName ? esc(firstName) : 'there'
  return `<!doctype html><html><body style="margin:0;background:#0B0B0D;font-family:Arial,Helvetica,sans-serif;color:#e5e5e5">
  <div style="max-width:480px;margin:0 auto;padding:32px 24px">
    <h1 style="font-size:20px;color:#ffffff;margin:0 0 8px">Confirm your email</h1>
    <p style="color:#a3a3a3;font-size:14px;line-height:1.6">Hi ${name}, welcome to IronForge. Confirm your email address to continue setting up your account.</p>
    <p style="margin:28px 0">
      <a href="${esc(verifyUrl)}" style="display:inline-block;background:#E8531F;color:#ffffff;text-decoration:none;font-weight:bold;font-size:14px;padding:12px 24px;border-radius:6px">Verify email</a>
    </p>
    <p style="color:#737373;font-size:12px;line-height:1.6">If the button does not work, paste this link into your browser:<br>${esc(verifyUrl)}</p>
    <p style="color:#525252;font-size:11px;margin-top:28px">This link expires in 24 hours. If you did not create an IronForge account, you can ignore this email.</p>
  </div></body></html>`
}

export async function sendVerificationEmail(params: {
  to: string
  verifyUrl: string
  firstName: string
}): Promise<SendResult> {
  if (!isEmailConfigured()) return { sent: false, skipped: true }
  try {
    const res = await fetch(RESEND_ENDPOINT, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: process.env.EMAIL_FROM,
        to: params.to,
        subject: 'Verify your IronForge email',
        html: verificationHtml(params.firstName, params.verifyUrl),
      }),
    })
    if (!res.ok) {
      const detail = await res.text().catch(() => '')
      return { sent: false, error: `Resend ${res.status}: ${detail.slice(0, 200)}` }
    }
    return { sent: true }
  } catch (e) {
    return { sent: false, error: e instanceof Error ? e.message : 'send failed' }
  }
}

function resetHtml(firstName: string, resetUrl: string): string {
  const name = firstName ? esc(firstName) : 'there'
  return `<!doctype html><html><body style="margin:0;background:#0B0B0D;font-family:Arial,Helvetica,sans-serif;color:#e5e5e5">
  <div style="max-width:480px;margin:0 auto;padding:32px 24px">
    <h1 style="font-size:20px;color:#ffffff;margin:0 0 8px">Reset your password</h1>
    <p style="color:#a3a3a3;font-size:14px;line-height:1.6">Hi ${name}, we received a request to reset your IronForge password. Click below to choose a new one.</p>
    <p style="margin:28px 0">
      <a href="${esc(resetUrl)}" style="display:inline-block;background:#E8531F;color:#ffffff;text-decoration:none;font-weight:bold;font-size:14px;padding:12px 24px;border-radius:6px">Reset password</a>
    </p>
    <p style="color:#737373;font-size:12px;line-height:1.6">If the button does not work, paste this link into your browser:<br>${esc(resetUrl)}</p>
    <p style="color:#525252;font-size:11px;margin-top:28px">This link expires in 1 hour. If you did not request a password reset, you can safely ignore this email.</p>
  </div></body></html>`
}

export async function sendPasswordResetEmail(params: {
  to: string
  resetUrl: string
  firstName: string
}): Promise<SendResult> {
  if (!isEmailConfigured()) return { sent: false, skipped: true }
  try {
    const res = await fetch(RESEND_ENDPOINT, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: process.env.EMAIL_FROM,
        to: params.to,
        subject: 'Reset your IronForge password',
        html: resetHtml(params.firstName, params.resetUrl),
      }),
    })
    if (!res.ok) {
      const detail = await res.text().catch(() => '')
      return { sent: false, error: `Resend ${res.status}: ${detail.slice(0, 200)}` }
    }
    return { sent: true }
  } catch (e) {
    return { sent: false, error: e instanceof Error ? e.message : 'send failed' }
  }
}

/* ------------------------------------------------------------------ */
/*  Operator vol-regime alert email                                    */
/* ------------------------------------------------------------------ */

/** Default operator recipient when OPS_ALERT_EMAILS is unset. */
const DEFAULT_OPS_EMAIL = 'shairan2016@gmail.com'

/**
 * Operator alert recipients, from OPS_ALERT_EMAILS (comma-separated). Falls back
 * to the default operator address so a fresh deploy still reaches someone. These
 * are the OPERATOR's inboxes — not a customer's — so the default is intentional.
 */
export function volAlertRecipients(): string[] {
  const raw = (process.env.OPS_ALERT_EMAILS || DEFAULT_OPS_EMAIL)
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
  return raw.length > 0 ? raw : [DEFAULT_OPS_EMAIL]
}

export interface VolAlertEmailParams {
  signalKey: string
  direction: string | null
  /** 'confirmed' (sustained, actionable) or 'early-warning' (tripped, pre-confirm). */
  reason: 'confirmed' | 'early-warning'
  headline: string | null
  message: string | null
  regimeLabel: string | null
  vix: number | null
  vix3m: number | null
  vvix: number | null
  proximity: number | null
  /** Optional override; defaults to volAlertRecipients(). */
  to?: string[]
}

function num(n: number | null | undefined, digits = 2): string {
  return typeof n === 'number' && Number.isFinite(n) ? n.toFixed(digits) : '—'
}

function volAlertHtml(p: VolAlertEmailParams): string {
  const isEarly = p.reason === 'early-warning'
  const accent = isEarly ? '#F59E0B' : '#E8531F'
  const kicker = isEarly ? 'EARLY WARNING — pre-confirmation' : 'CONFIRMED SIGNAL'
  const name = esc(p.signalKey.replace(/_/g, ' '))
  const dir = p.direction ? esc(p.direction) : ''
  const ratio =
    typeof p.vix === 'number' && typeof p.vix3m === 'number' && p.vix3m
      ? (p.vix / p.vix3m).toFixed(3)
      : '—'
  return `<!doctype html><html><body style="margin:0;background:#0B0B0D;font-family:Arial,Helvetica,sans-serif;color:#e5e5e5">
  <div style="max-width:520px;margin:0 auto;padding:32px 24px">
    <p style="margin:0 0 4px;font-size:11px;letter-spacing:2px;color:${accent};font-weight:bold">${kicker}</p>
    <h1 style="font-size:20px;color:#ffffff;margin:0 0 4px;text-transform:capitalize">${name}${dir ? ` <span style="color:#a3a3a3;font-size:14px">(${dir})</span>` : ''}</h1>
    ${p.headline ? `<p style="color:#ffffff;font-size:15px;font-weight:bold;margin:12px 0 4px">${esc(p.headline)}</p>` : ''}
    ${p.message ? `<p style="color:#a3a3a3;font-size:13px;line-height:1.6;margin:8px 0">${esc(p.message)}</p>` : ''}
    <table style="width:100%;border-collapse:collapse;margin:20px 0;font-size:13px">
      <tr><td style="padding:6px 0;color:#737373">Regime</td><td style="padding:6px 0;color:#e5e5e5;text-align:right">${esc((p.regimeLabel || '—').replace(/_/g, ' '))}</td></tr>
      <tr><td style="padding:6px 0;color:#737373">VIX / VIX3M</td><td style="padding:6px 0;color:#e5e5e5;text-align:right">${num(p.vix)} / ${num(p.vix3m)} (ratio ${ratio})</td></tr>
      <tr><td style="padding:6px 0;color:#737373">VVIX</td><td style="padding:6px 0;color:#e5e5e5;text-align:right">${num(p.vvix, 0)}</td></tr>
      <tr><td style="padding:6px 0;color:#737373">Proximity to trigger</td><td style="padding:6px 0;color:#e5e5e5;text-align:right">${p.proximity != null ? `${(p.proximity * 100).toFixed(0)}%` : '—'}</td></tr>
    </table>
    <p style="color:#525252;font-size:11px;line-height:1.6;margin-top:8px">IronForge volatility-regime monitor. ${isEarly ? 'This signal has tripped its trigger but is not yet debounce-confirmed — treat as a heads-up, not a committed signal.' : 'This signal is sustained and confirmed.'}</p>
  </div></body></html>`
}

/**
 * Send an operator vol-regime alert via Resend. No-op (skipped) when email isn't
 * configured, mirroring the other senders. Caller decides WHEN to send (escalation
 * + cooldown live in volAlerts); this only renders + delivers.
 */
export async function sendVolAlertEmail(params: VolAlertEmailParams): Promise<SendResult> {
  if (!isEmailConfigured()) return { sent: false, skipped: true }
  const to = params.to && params.to.length > 0 ? params.to : volAlertRecipients()
  const tag = params.reason === 'early-warning' ? 'Early warning' : 'Alert'
  const subject = `IronForge ${tag}: ${params.signalKey.replace(/_/g, ' ')}${params.direction ? ` (${params.direction})` : ''}`
  try {
    const res = await fetch(RESEND_ENDPOINT, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: process.env.EMAIL_FROM,
        to,
        subject,
        html: volAlertHtml(params),
      }),
    })
    if (!res.ok) {
      const detail = await res.text().catch(() => '')
      return { sent: false, error: `Resend ${res.status}: ${detail.slice(0, 200)}` }
    }
    return { sent: true }
  } catch (e) {
    return { sent: false, error: e instanceof Error ? e.message : 'send failed' }
  }
}
