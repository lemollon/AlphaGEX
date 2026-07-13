import { NextRequest, NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { normalizeEmail } from '@/lib/signup-validation'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'
import { publicOrigin } from '@/lib/public-origin'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Operator admin bypass: mint a customer session as any user so the operator
 * can reach every customer-gated page and API while developing.
 *
 *   GET /api/ops/impersonate                 → list users to pick from
 *   GET /api/ops/impersonate?email=x@y.com   → become that user, redirect to /home
 *   GET /api/ops/impersonate?email=...&next=/account/trades → custom destination
 *   GET /api/ops/impersonate?clear=true      → drop the impersonated session
 *
 * Requires a valid OPERATOR session (ops login) — customers can never reach
 * this. Every impersonation writes an audit_events row.
 */

interface UserRow {
  id: string
  email: string
  onboarding_step: string
  email_verified: boolean
}

export async function GET(req: NextRequest) {
  const ops = await getSession()

  // Lightweight status probe for the floating AdminBadge — answers for
  // everyone (no 401) but reveals nothing unless an operator session exists.
  if (req.nextUrl.searchParams.get('status') === 'true') {
    if (!ops.userId) return NextResponse.json({ ok: true, operator: false })
    const session = await getCustomerSession()
    return NextResponse.json({
      ok: true,
      operator: true,
      impersonating: session.customerId ? { email: session.email ?? null } : null,
    })
  }

  if (!ops.userId) {
    return NextResponse.json({ ok: false, error: 'Operator session required.' }, { status: 401 })
  }
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'Customers DB not configured.' }, { status: 503 })
  }

  const url = req.nextUrl
  const session = await getCustomerSession()

  if (url.searchParams.get('clear') === 'true') {
    session.destroy()
    return NextResponse.json({ ok: true, cleared: true })
  }

  const email = normalizeEmail(url.searchParams.get('email') ?? '')

  if (!email) {
    // No target: show the roster so the operator can pick.
    const users = await customerQuery<UserRow>(
      `SELECT id, email, onboarding_step, email_verified FROM users ORDER BY created_at DESC LIMIT 50`,
    )
    return NextResponse.json({
      ok: true,
      usage: 'GET /api/ops/impersonate?email=<pick one below>[&next=/home] | ?clear=true to stop',
      currentlyImpersonating: session.customerId ? { customerId: session.customerId, email: session.email } : null,
      users: users.map((u) => ({ email: u.email, onboardingStep: u.onboarding_step, verified: u.email_verified })),
    })
  }

  const rows = await customerQuery<UserRow>(
    `SELECT id, email, onboarding_step, email_verified FROM users WHERE email = $1 LIMIT 1`,
    [email],
  )
  const user = rows[0]
  if (!user) {
    return NextResponse.json({ ok: false, error: `No customer with email ${email}.` }, { status: 404 })
  }

  session.customerId = user.id
  session.email = user.email
  session.emailVerified = true
  session.onboardingStep = user.onboarding_step
  await session.save()

  try {
    await customerExecute(
      `INSERT INTO audit_events (user_id, event_type, ip_address, user_agent, metadata)
       VALUES ($1, $2, $3, $4, $5)`,
      [
        user.id,
        'ADMIN_IMPERSONATE',
        req.headers.get('x-forwarded-for')?.split(',')[0]?.trim() ?? null,
        req.headers.get('user-agent'),
        JSON.stringify({ operator: ops.username ?? ops.userId }),
      ],
    )
  } catch (e) {
    console.error('[impersonate] audit failed:', e)
  }

  const next = url.searchParams.get('next') ?? '/home'
  // Only allow same-site relative destinations; build on the public origin so
  // the redirect works on Render (nextUrl.origin is the internal bind address).
  const dest = next.startsWith('/') && !next.startsWith('//') ? next : '/home'
  return NextResponse.redirect(new URL(dest, publicOrigin(req)))
}
