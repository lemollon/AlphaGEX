import { NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { ownsStrategy, hasActiveMembership } from '@/lib/live/membership'
import { customerQuery } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

interface ProfileRow {
  email: string
  first_name: string | null
  last_name: string | null
  email_verified: boolean
  onboarding_step: string | null
  created_at: string
}

/**
 * Who is signed in, plus everything the Account screen's profile card needs (APP-058).
 *
 * The web's /api/auth/customer-me returns only session fields; UX-006 also needs a
 * display name, initials, and a member-since date, so this reads the user row. Same
 * entitlement discipline as the web route: `ok` means SIGNED IN and nothing more —
 * anything gating "may they see the product" must use ownsStrategy/hasMembership,
 * both of which fail closed inside their helpers.
 *
 * verifyEpoch is on: this is the app's session probe, so it is the right place to
 * discover that a password change elsewhere has invalidated this device.
 */
export async function GET() {
  const identity = await getCustomerIdentity({ verifyEpoch: true })
  if (!identity) {
    return NextResponse.json({ ok: false }, { status: 401 })
  }

  const rows = await customerQuery<ProfileRow>(
    `SELECT email, first_name, last_name, email_verified, onboarding_step, created_at
       FROM users WHERE id = $1 LIMIT 1`,
    [identity.customerId],
  )
  const row = rows[0]
  if (!row) return NextResponse.json({ ok: false }, { status: 401 })

  const first = (row.first_name ?? '').trim()
  const last = (row.last_name ?? '').trim()
  const displayName = [first, last].filter(Boolean).join(' ') || row.email
  // Initials fall back to the email's first character so the avatar is never blank.
  const initials =
    ([first[0], last[0]].filter(Boolean).join('') || row.email[0] || '?').toUpperCase()

  return NextResponse.json({
    ok: true,
    ownsStrategy: await ownsStrategy(identity.customerId),
    hasMembership: await hasActiveMembership(identity.customerId),
    customer: {
      id: identity.customerId,
      email: row.email,
      displayName,
      initials,
      firstName: first || null,
      lastName: last || null,
      emailVerified: row.email_verified,
      onboardingStep: row.onboarding_step,
      memberSince: row.created_at,
    },
  })
}
