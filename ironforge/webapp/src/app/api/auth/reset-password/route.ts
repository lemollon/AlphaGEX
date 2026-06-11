import { NextRequest, NextResponse } from 'next/server'
import { hashToken, isExpired } from '@/lib/auth/verification-token'
import { hashPassword } from '@/lib/auth/password'
import { checkPassword } from '@/lib/signup-validation'
import { isCustomersDbConfigured, customerQuery, customerTransaction, customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

interface TokenRow {
  id: string
  user_id: string
  expires_at: string
  consumed_at: string | null
}

export async function POST(req: NextRequest) {
  if (!isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'Password reset is temporarily unavailable. Please try again shortly.' },
      { status: 503 },
    )
  }

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  const token = String(body.token ?? '')
  const password = String(body.password ?? '')
  const confirmPassword = String(body.confirmPassword ?? '')

  if (!token) {
    return NextResponse.json({ ok: false, error: 'This reset link is invalid.' }, { status: 400 })
  }
  if (!checkPassword(password).valid) {
    return NextResponse.json(
      { ok: false, error: 'Password does not meet the requirements.' },
      { status: 400 },
    )
  }
  if (password !== confirmPassword) {
    return NextResponse.json({ ok: false, error: 'Passwords do not match.' }, { status: 400 })
  }

  try {
    const rows = await customerQuery<TokenRow>(
      `SELECT id, user_id, expires_at, consumed_at FROM password_reset_tokens WHERE token_hash = $1 LIMIT 1`,
      [hashToken(token)],
    )
    const row = rows[0]
    if (!row || row.consumed_at || isExpired(row.expires_at, new Date())) {
      return NextResponse.json(
        { ok: false, error: 'This reset link is invalid or has expired.' },
        { status: 400 },
      )
    }

    const newHash = await hashPassword(password)
    await customerTransaction(async (run) => {
      await run(`UPDATE users SET password_hash = $1, updated_at = now() WHERE id = $2`, [newHash, row.user_id])
      await run(`UPDATE password_reset_tokens SET consumed_at = now() WHERE id = $1`, [row.id])
    })

    try {
      await customerExecute(
        `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'PASSWORD_RESET', $2)`,
        [row.user_id, JSON.stringify({})],
      )
    } catch { /* best-effort */ }

    return NextResponse.json({ ok: true })
  } catch (e) {
    console.error('[reset-password] failed:', e)
    return NextResponse.json({ ok: false, error: 'Something went wrong. Please try again.' }, { status: 500 })
  }
}
