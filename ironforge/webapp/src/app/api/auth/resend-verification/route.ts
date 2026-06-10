import { NextRequest, NextResponse } from 'next/server'
import { isValidEmail, normalizeEmail } from '@/lib/signup-validation'
import { generateToken, TOKEN_TTL_MS } from '@/lib/auth/verification-token'
import { sendVerificationEmail } from '@/lib/email'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Resend the email-verification link (sub-project D).
 * Always returns a generic { ok: true } for a valid-format email so the endpoint
 * cannot be used to enumerate which addresses have accounts.
 */

interface UserRow {
  id: string
  first_name: string
  email_verified: boolean
}

function maskEmail(email: string): string {
  const [local, domain] = email.split('@')
  return domain ? `${local.slice(0, 1)}***@${domain}` : '***'
}

export async function POST(req: NextRequest) {
  let body: { email?: string }
  try {
    body = (await req.json()) as { email?: string }
  } catch {
    return NextResponse.json({ ok: false, error: 'Invalid request body.' }, { status: 400 })
  }

  if (!isValidEmail(String(body.email ?? ''))) {
    return NextResponse.json({ ok: false, error: 'Enter a valid email address.' }, { status: 400 })
  }
  if (!isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'Verification is temporarily unavailable. Please try again shortly.' },
      { status: 503 },
    )
  }

  const email = normalizeEmail(String(body.email))

  try {
    const rows = await customerQuery<UserRow>(
      `SELECT id, first_name, email_verified FROM users WHERE email = $1 LIMIT 1`,
      [email],
    )
    const user = rows[0]
    if (user && !user.email_verified) {
      const { raw, hash } = generateToken()
      const expiresAt = new Date(Date.now() + TOKEN_TTL_MS).toISOString()
      await customerExecute(
        `INSERT INTO email_verification_tokens (user_id, token_hash, expires_at) VALUES ($1,$2,$3)`,
        [user.id, hash, expiresAt],
      )
      const verifyUrl = `${req.nextUrl.origin}/api/auth/verify?token=${encodeURIComponent(raw)}`
      const emailRes = await sendVerificationEmail({
        to: email,
        verifyUrl,
        firstName: user.first_name || '',
      })
      if (emailRes.sent) {
        try {
          await customerExecute(
            `INSERT INTO audit_events (user_id, event_type, ip_address, user_agent, metadata)
             VALUES ($1,$2,$3,$4,$5)`,
            [
              user.id,
              'EMAIL_VERIFICATION_SENT',
              req.headers.get('x-forwarded-for')?.split(',')[0].trim() ?? null,
              req.headers.get('user-agent'),
              JSON.stringify({ email_masked: maskEmail(email), resend: true }),
            ],
          )
        } catch (e) {
          console.error('[resend] audit write failed:', e)
        }
      }
    }
  } catch (e) {
    // Never reveal internal state to the caller; log for ops.
    console.error('[resend] failed:', e)
  }

  return NextResponse.json({ ok: true })
}
