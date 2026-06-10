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
