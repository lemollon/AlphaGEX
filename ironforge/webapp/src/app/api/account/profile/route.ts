import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * PUT /api/account/profile — change the signed-in customer's display name.
 *
 * APP-058 ("Edit Profile") had no endpoint at all, which is why the mobile Account screen
 * shipped without the row: a chevron that opens a screen that cannot save is worse than
 * no chevron.
 *
 * SCOPE IS NAME ONLY, deliberately. APP-058 also describes changing the email address,
 * but the same sentence requires uniqueness validation, step-up reauthentication and a
 * verification round-trip before the new address becomes the login — that is a flow, not
 * a field, and half of it silently shipped is an account-takeover vector. An email in the
 * body is rejected explicitly rather than ignored, so a client cannot believe it worked.
 *
 * Name is not a security boundary here: it is display text, the session already proves who
 * is asking, and nothing authorizes off it.
 */
const MAX_LEN = 60

/**
 * Strip control characters, collapse whitespace, keep everything a real name contains.
 *
 * Filtered by CODE POINT rather than a regex class on purpose. A literal control-character
 * class is invisible in source (and does not survive a round-trip through most editors),
 * while the range that looks correct at a glance — space through hyphen — actually deletes
 * apostrophes and hyphens, quietly turning O'Neill into ONeill and Smith-Jones into
 * SmithJones.
 */
function cleanName(raw: unknown): string | null {
  if (typeof raw !== 'string') return null
  const stripped = Array.from(raw)
    .filter((ch) => {
      const c = ch.codePointAt(0) ?? 0
      return c >= 0x20 && c !== 0x7f
    })
    .join('')
    .replace(/\s+/g, ' ')
    .trim()
  if (!stripped || stripped.length > MAX_LEN) return null
  return stripped
}

export async function PUT(req: NextRequest) {
  // verifyEpoch: a profile write mutates the account, so a revocation that happened inside
  // the access token's 15-minute life must be honoured.
  const identity = await getCustomerIdentity({ verifyEpoch: true })
  const customerId = identity?.customerId ?? null
  if (!customerId) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })

  if (!isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'Profile changes are temporarily unavailable. Please try again shortly.' },
      { status: 503 },
    )
  }

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>

  if ('email' in body) {
    return NextResponse.json(
      {
        ok: false,
        error:
          'Changing your email address is not supported here. It has to be verified before it becomes your login — contact support.',
      },
      { status: 400 },
    )
  }

  const firstName = cleanName(body.firstName)
  const lastName = cleanName(body.lastName)
  if (!firstName || !lastName) {
    return NextResponse.json(
      { ok: false, error: `First and last name are required, each up to ${MAX_LEN} characters.` },
      { status: 400 },
    )
  }

  try {
    const rows = await customerQuery<{ first_name: string; last_name: string }>(
      `UPDATE users SET first_name = $2, last_name = $3, updated_at = now()
        WHERE id = $1
        RETURNING first_name, last_name`,
      [customerId, firstName, lastName],
    )
    // RETURNING is the check, not a driver rowCount that can lie: no row back means the id
    // matched nothing and nothing was written.
    const row = rows[0]
    if (!row) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })

    await customerExecute(
      `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'PROFILE_UPDATED', $2)`,
      [customerId, JSON.stringify({ fields: ['first_name', 'last_name'] })],
    ).catch(() => {})

    const displayName = `${row.first_name} ${row.last_name}`.trim()
    const initials =
      (row.first_name.charAt(0) + row.last_name.charAt(0)).toUpperCase() || displayName.charAt(0)

    return NextResponse.json({
      ok: true,
      profile: { firstName: row.first_name, lastName: row.last_name, displayName, initials },
    })
  } catch (e) {
    console.error('[account/profile] failed:', e)
    return NextResponse.json({ ok: false, error: 'Could not save your profile.' }, { status: 500 })
  }
}
