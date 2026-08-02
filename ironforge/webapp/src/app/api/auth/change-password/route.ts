import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'
import { verifyPassword, hashPassword } from '@/lib/auth/password'
import { checkPassword } from '@/lib/signup-validation'
import { revokeAllForUser } from '@/lib/auth/mobile-session'

/**
 * Signed-in CUSTOMER password change.
 *
 * This used to read the OPERATOR session and write to `ironforge_users`, while
 * the only page that calls it — /change-password — is a customer screen listed
 * in CUSTOMER_EXACT. So a signed-in customer clicking "Change password" hit a
 * 401 every time and had no way to change their password at all. The ROUTING
 * for that page had already been fixed once (it used to bounce customers to the
 * operator door); the endpoint it posts to had not.
 *
 * It now uses the customer session and the customers database, which is where
 * customer password hashes actually live. Operator password login is gone, so
 * there is no operator caller left to preserve.
 */
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const MIN_LEN = 12

export async function POST(req: NextRequest) {
  try {
    const session = await getCustomerSession()
    if (!session.customerId) {
      return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
    }
    if (!isCustomersDbConfigured()) {
      return NextResponse.json(
        { error: 'Password changes are temporarily unavailable. Please try again shortly.' },
        { status: 503 },
      )
    }

    const body = await req.json().catch(() => ({}) as Record<string, unknown>)
    const currentPassword = String(body.currentPassword || '')
    const newPassword = String(body.newPassword || '')

    // Enforce the SAME strength rules as signup (audit minor): the new password
    // accepted only a length check while signup requires upper/lower/number/special,
    // so a customer could weaken their own password below the standard they signed up at.
    if (!checkPassword(newPassword).valid) {
      return NextResponse.json(
        { error: `New password must be at least ${MIN_LEN} characters and include uppercase, lowercase, a number, and a special character.` },
        { status: 400 },
      )
    }
    if (newPassword === currentPassword) {
      return NextResponse.json(
        { error: 'New password must be different from the current one' },
        { status: 400 },
      )
    }

    const rows = await customerQuery<{ password_hash: string }>(
      `SELECT password_hash FROM users WHERE id = $1 LIMIT 1`,
      [session.customerId],
    )
    const hash = rows[0]?.password_hash
    if (!hash || !(await verifyPassword(currentPassword, hash))) {
      return NextResponse.json({ error: 'Current password is incorrect' }, { status: 400 })
    }

    const newHash = await hashPassword(newPassword)
    await customerExecute(`UPDATE users SET password_hash = $1 WHERE id = $2`, [
      newHash,
      session.customerId,
    ])

    // Changing a password must end every OTHER signed-in session, or the change gives
    // false comfort: someone who logged in on a stolen phone keeps a 60-day refresh
    // token that the password change did nothing to. This also bumps users.token_epoch,
    // which is the only way to kill already-issued stateless access tokens.
    // Best-effort — the password IS changed at this point, so a revocation failure must
    // not turn a successful change into a 500 the customer would retry.
    await revokeAllForUser(session.customerId, 'password_change').catch((e) => {
      console.error('[change-password] mobile revoke failed:', e)
    })

    return NextResponse.json({ ok: true })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
