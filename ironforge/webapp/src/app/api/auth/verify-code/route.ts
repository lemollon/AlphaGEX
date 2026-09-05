import { NextRequest, NextResponse } from 'next/server'
import { isValidEmail, normalizeEmail } from '@/lib/signup-validation'
import { hashCode, isExpired, MAX_CODE_ATTEMPTS } from '@/lib/auth/verification-token'
import {
  isCustomersDbConfigured,
  customerQuery,
  customerExecute,
  customerTransaction,
} from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * 6-digit code counterpart to GET /api/auth/verify (mobile enrollment follow-up,
 * 9/5). Same success side-effects as the link (users.email_verified/
 * account_status/onboarding_step), but returns JSON instead of a redirect — the
 * mobile client is a bearer API, not a browser, so there is no cookie session to
 * mint here. The caller signs in separately via POST /api/auth/mobile/login once
 * this returns ok.
 *
 * The code and the link token are rotated TOGETHER (see resend-verification) and
 * live on the same email_verification_tokens row, but are consumed independently:
 * a code guess never marks the link token consumed, and vice versa — either path
 * alone is sufficient proof of control of the email.
 */

// Lightweight in-memory rate limit (per instance), same shape as
// community/assist and support/chat's local limiters — this endpoint accepts a
// short numeric code, so it is the one auth route where abuse-damping earns its
// keep beyond the per-code 5-attempt cap below.
const HITS = new Map<string, number[]>()
const WINDOW_MS = 5 * 60_000
const MAX_PER_WINDOW = 20

function rateLimited(key: string): boolean {
  const now = Date.now()
  const arr = (HITS.get(key) ?? []).filter((t) => now - t < WINDOW_MS)
  arr.push(now)
  HITS.set(key, arr)
  return arr.length > MAX_PER_WINDOW
}

interface TokenRow {
  id: string
  user_id: string
  code_hash: string | null
  code_expires_at: string | null
  code_attempts: number
}

function clientIp(req: NextRequest): string | null {
  const xff = req.headers.get('x-forwarded-for')
  return xff ? xff.split(',')[0].trim() : null
}

async function audit(userId: string, eventType: string, req: NextRequest, metadata: Record<string, unknown>) {
  try {
    await customerExecute(
      `INSERT INTO audit_events (user_id, event_type, ip_address, user_agent, metadata)
       VALUES ($1, $2, $3, $4, $5)`,
      [userId, eventType, clientIp(req), req.headers.get('user-agent'), JSON.stringify(metadata)],
    )
  } catch (e) {
    console.error('[verify-code] audit write failed:', eventType, e)
  }
}

export async function POST(req: NextRequest) {
  if (!isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'Verification is temporarily unavailable. Please try again shortly.' },
      { status: 503 },
    )
  }

  const body = (await req.json().catch(() => ({}))) as { email?: unknown; code?: unknown }
  const email = normalizeEmail(String(body.email ?? ''))
  const code = String(body.code ?? '').trim()

  if (!isValidEmail(email)) {
    return NextResponse.json({ ok: false, error: 'Enter a valid email address.' }, { status: 400 })
  }
  if (!/^\d{6}$/.test(code)) {
    return NextResponse.json({ ok: false, error: 'Enter the 6-digit code from your email.' }, { status: 400 })
  }
  if (rateLimited(email)) {
    return NextResponse.json({ ok: false, error: 'Too many attempts — wait a few minutes and try again.' }, { status: 429 })
  }

  try {
    const users = await customerQuery<{ id: string; onboarding_step: string | null }>(
      `SELECT id, onboarding_step FROM users WHERE email = $1 LIMIT 1`,
      [email],
    )
    const user = users[0]
    // Never reveal whether the email exists — same generic failure either way.
    const invalidOrExpired = () =>
      NextResponse.json({ ok: false, code: 'invalid_code', error: 'Invalid or expired code.' }, { status: 400 })

    if (!user) return invalidOrExpired()

    const rows = await customerQuery<TokenRow>(
      `SELECT id, user_id, code_hash, code_expires_at, code_attempts
         FROM email_verification_tokens
        WHERE user_id = $1 AND code_hash IS NOT NULL AND consumed_at IS NULL
        ORDER BY created_at DESC LIMIT 1`,
      [user.id],
    )
    const row = rows[0]
    if (!row || !row.code_hash || !row.code_expires_at) return invalidOrExpired()
    if (isExpired(row.code_expires_at, new Date())) return invalidOrExpired()
    if (row.code_attempts >= MAX_CODE_ATTEMPTS) {
      return NextResponse.json(
        { ok: false, code: 'code_locked', error: 'Too many incorrect attempts — request a new code.' },
        { status: 410 },
      )
    }

    if (hashCode(code, user.id) !== row.code_hash) {
      const attempts = row.code_attempts + 1
      await customerExecute(
        `UPDATE email_verification_tokens SET code_attempts = $1 WHERE id = $2`,
        [attempts, row.id],
      )
      if (attempts >= MAX_CODE_ATTEMPTS) {
        return NextResponse.json(
          { ok: false, code: 'code_locked', error: 'Too many incorrect attempts — request a new code.' },
          { status: 410 },
        )
      }
      return NextResponse.json(
        {
          ok: false,
          code: 'invalid_code',
          error: `Incorrect code. ${MAX_CODE_ATTEMPTS - attempts} attempt${MAX_CODE_ATTEMPTS - attempts === 1 ? '' : 's'} left.`,
        },
        { status: 400 },
      )
    }

    await customerTransaction(async (run) => {
      await run(
        `UPDATE users
            SET email_verified = TRUE,
                account_status = 'email_verified',
                onboarding_step = 'email_verified',
                updated_at = now()
          WHERE id = $1`,
        [user.id],
      )
      await run(
        `UPDATE email_verification_tokens SET consumed_at = now() WHERE id = $1`,
        [row.id],
      )
    })

    await audit(user.id, 'EMAIL_VERIFIED', req, { token_id: row.id, method: 'code' })

    return NextResponse.json({ ok: true })
  } catch (e) {
    console.error('[verify-code] failed:', e)
    return NextResponse.json({ ok: false, error: 'Something went wrong. Please try again.' }, { status: 500 })
  }
}
