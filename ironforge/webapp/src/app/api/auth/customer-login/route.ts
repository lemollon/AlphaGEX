import { NextRequest, NextResponse } from 'next/server'
import { verifyPassword } from '@/lib/auth/password'
import { normalizeEmail } from '@/lib/signup-validation'
import { classifyLoginAttempt, TIMING_DUMMY_HASH } from '@/lib/auth/customer-auth'
import { nextRouteForOnboarding } from '@/lib/auth/onboarding-route'
import { getCustomerSession } from '@/lib/auth/customer-session'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

interface UserRow {
  id: string
  password_hash: string
  email_verified: boolean
  onboarding_step: string
}

function clientIp(req: NextRequest): string | null {
  const xff = req.headers.get('x-forwarded-for')
  return xff ? xff.split(',')[0].trim() : null
}

async function audit(userId: string | null, eventType: string, req: NextRequest, metadata: Record<string, unknown>) {
  try {
    await customerExecute(
      `INSERT INTO audit_events (user_id, event_type, ip_address, user_agent, metadata)
       VALUES ($1, $2, $3, $4, $5)`,
      [userId, eventType, clientIp(req), req.headers.get('user-agent'), JSON.stringify(metadata)],
    )
  } catch (e) {
    console.error('[customer-login] audit failed:', eventType, e)
  }
}

export async function POST(req: NextRequest) {
  if (!isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'Sign-in is temporarily unavailable. Please try again shortly.' },
      { status: 503 },
    )
  }

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  const email = normalizeEmail(String(body.email ?? ''))
  const password = String(body.password ?? '')
  if (!email || !password) {
    return NextResponse.json({ ok: false, error: 'Email and password are required.' }, { status: 400 })
  }

  try {
    const rows = await customerQuery<UserRow>(
      `SELECT id, password_hash, email_verified, onboarding_step FROM users WHERE email = $1 LIMIT 1`,
      [email],
    )
    const user = rows[0]
    // Always run a bcrypt compare (dummy hash on miss) to equalize timing.
    const passwordOk = await verifyPassword(password, user?.password_hash ?? TIMING_DUMMY_HASH)

    const outcome = classifyLoginAttempt({
      userExists: !!user,
      passwordOk,
      emailVerified: !!user?.email_verified,
    })

    if (outcome === 'invalid_credentials') {
      return NextResponse.json(
        { ok: false, code: 'invalid_credentials', error: 'Invalid email or password.' },
        { status: 401 },
      )
    }
    if (outcome === 'email_unverified') {
      await audit(user!.id, 'LOGIN_BLOCKED_UNVERIFIED', req, {})
      return NextResponse.json(
        { ok: false, code: 'email_unverified', error: 'Please verify your email before signing in.' },
        { status: 403 },
      )
    }

    const session = await getCustomerSession()
    session.customerId = user!.id
    session.email = email
    session.emailVerified = true
    session.onboardingStep = user!.onboarding_step
    await session.save()

    void customerExecute(`UPDATE users SET last_login_at = now() WHERE id = $1`, [user!.id]).catch(() => {})
    await audit(user!.id, 'CUSTOMER_LOGIN', req, {})

    return NextResponse.json({ ok: true, next: nextRouteForOnboarding(user!.onboarding_step) })
  } catch (e) {
    console.error('[customer-login] failed:', e)
    return NextResponse.json({ ok: false, error: 'Something went wrong. Please try again.' }, { status: 500 })
  }
}
