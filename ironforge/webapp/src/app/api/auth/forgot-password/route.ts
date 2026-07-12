import { NextRequest, NextResponse } from 'next/server'
import { normalizeEmail } from '@/lib/signup-validation'
import { generateToken } from '@/lib/auth/verification-token'
import { sendPasswordResetEmail } from '@/lib/email'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const RESET_TTL_MS = 60 * 60 * 1000 // 1 hour

interface UserRow {
  id: string
  first_name: string
  email: string
}

/** Always returns { ok: true } — never reveals whether an account exists. */
export async function POST(req: NextRequest) {
  const ok = () => NextResponse.json({ ok: true })

  if (!isCustomersDbConfigured()) return ok()

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  const email = normalizeEmail(String(body.email ?? ''))
  if (!email) return ok()

  try {
    const rows = await customerQuery<UserRow>(
      `SELECT id, first_name, email FROM users WHERE email = $1 LIMIT 1`,
      [email],
    )
    const user = rows[0]
    if (user) {
      const { raw, hash } = generateToken()
      const expiresAt = new Date(Date.now() + RESET_TTL_MS).toISOString()
      await customerExecute(
        `INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) VALUES ($1, $2, $3)`,
        [user.id, hash, expiresAt],
      )
      const resetUrl = `${req.nextUrl.origin}/reset-password?token=${encodeURIComponent(raw)}`
      try {
        const emailRes = await sendPasswordResetEmail({ to: user.email, resetUrl, firstName: user.first_name })
        if (emailRes.skipped) {
          console.warn('[forgot-password] reset email SKIPPED (RESEND_API_KEY/EMAIL_FROM unset)')
        } else if (emailRes.error) {
          console.error('[forgot-password] reset email failed:', emailRes.error)
        }
      } catch (e) {
        console.error('[forgot-password] email send threw:', e)
      }
      try {
        await customerExecute(
          `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'PASSWORD_RESET_REQUESTED', $2)`,
          [user.id, JSON.stringify({})],
        )
      } catch { /* best-effort */ }
    }
    return ok()
  } catch (e) {
    console.error('[forgot-password] failed:', e)
    return ok() // still enumeration-safe on internal error
  }
}
