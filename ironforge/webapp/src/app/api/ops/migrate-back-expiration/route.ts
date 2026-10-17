import { NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { isPublicMode } from '@/lib/auth/access'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * ANVIL's one blocker: add `customer_positions.back_expiration`.
 *
 *   GET  /api/ops/migrate-back-expiration  → read-only: does the column exist?
 *   POST /api/ops/migrate-back-expiration  → apply it
 *
 * WHY THIS IS A ROUTE AND NOT A SCRIPT. The customers database
 * (`ironforge-customers`, dpg-d8eeek740ujc73dh446g-a) has an EMPTY IP allow
 * list, so nothing outside Render can reach it — a local psql or a migration
 * script cannot run, by design. The deployed service already holds the
 * credential and sits inside the network, so per ironforge/CLAUDE.md's hard
 * rule ("ALL diagnostic tools, fix scripts, and backend operations MUST be
 * implemented as API routes") this is the only supported path. Opening the
 * allow list to a laptop would be a worse answer to the same problem.
 *
 * WHY ANVIL NEEDS IT. Every other structure the customer mirror places stamps
 * ONE expiration on every leg, and `customer_positions` has exactly one
 * `expiration` column to match. A diagonal's short and long legs expire on
 * DIFFERENT dates, so with one column the back leg can neither be recorded nor
 * later closed — a position sized and opened as a diagonal would be invisible
 * to its own close path. That is why `mirrorAnvilOpenToCustomers` and both
 * dispatch sites in customer-executor/executor.ts throw fail-closed today
 * rather than placing a single-expiry vertical that merely resembles the
 * intended trade.
 *
 * ── Safety of this specific DDL ───────────────────────────────────────────
 *
 * `ADD COLUMN ... DATE NULL` with no default and no constraint is the safest
 * shape Postgres offers: it is a catalog-only change, rewrites no rows, takes
 * no long lock, and leaves every existing row and every existing query
 * untouched (a NULL back_expiration reads exactly like today's absent column
 * for all three current strategies — main, flint, xsp). It is additive and
 * reversible with DROP COLUMN.
 *
 * It is written `IF NOT EXISTS` so re-running it is a no-op rather than an
 * error, and the GET is provided so the state can be read before anything is
 * changed. Approved by Leron 2026-10-17 ("i approve ANVIL the migration").
 *
 * 🚨 Applying this does NOT arm ANVIL. The column is a prerequisite; the
 * mirror stays gated behind CUSTOMER_ANVIL (default off) and still needs its
 * fail-closed guards lifted deliberately, in a reviewed change, once the
 * column exists.
 */

const TABLE = 'customer_positions'
const COLUMN = 'back_expiration'

async function requireOperator(): Promise<{ ok: true; who: string } | { ok: false; res: NextResponse }> {
  if (isPublicMode()) return { ok: true, who: 'public-mode' }
  const ops = await getSession()
  if (!ops.userId) {
    return { ok: false, res: NextResponse.json({ ok: false, error: 'Operator session required.' }, { status: 401 }) }
  }
  return { ok: true, who: ops.username ?? String(ops.userId) }
}

/** The one fact that decides everything: is the column already there? */
async function columnExists(): Promise<boolean> {
  const rows = await customerQuery<{ column_name: string }>(
    `SELECT column_name
       FROM information_schema.columns
      WHERE table_name = $1 AND column_name = $2`,
    [TABLE, COLUMN],
  )
  return rows.length > 0
}

export async function GET() {
  const auth = await requireOperator()
  if (!auth.ok) return auth.res

  if (!isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'CUSTOMERS_DATABASE_URL is not configured on this service.' },
      { status: 503 },
    )
  }

  try {
    const exists = await columnExists()
    return NextResponse.json({
      ok: true,
      table: TABLE,
      column: COLUMN,
      exists,
      applied: exists,
      ddl: `ALTER TABLE ${TABLE} ADD COLUMN IF NOT EXISTS ${COLUMN} DATE NULL`,
      next: exists
        ? 'Column present. ANVIL is unblocked at the schema level; it remains gated behind CUSTOMER_ANVIL and its fail-closed guards.'
        : 'Column absent. POST to this route to add it. Nothing has been changed by this GET.',
    })
  } catch (e: unknown) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : String(e) },
      { status: 500 },
    )
  }
}

export async function POST() {
  const auth = await requireOperator()
  if (!auth.ok) return auth.res

  if (!isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'CUSTOMERS_DATABASE_URL is not configured on this service.' },
      { status: 503 },
    )
  }

  try {
    const before = await columnExists()
    if (before) {
      return NextResponse.json({
        ok: true,
        changed: false,
        table: TABLE,
        column: COLUMN,
        by: auth.who,
        note: 'Already present — nothing was altered.',
      })
    }

    await customerExecute(
      `ALTER TABLE ${TABLE} ADD COLUMN IF NOT EXISTS ${COLUMN} DATE NULL`,
    )

    // Verify by re-reading the catalog rather than trusting that the statement
    // returned without error: a migration that reports success it did not
    // achieve is the failure mode this whole session has been about.
    const after = await columnExists()
    if (!after) {
      return NextResponse.json(
        {
          ok: false,
          changed: false,
          error: 'ALTER TABLE returned without error but the column is still absent. Nothing to rely on here — investigate before retrying.',
        },
        { status: 500 },
      )
    }

    console.log(`[ops] customer_positions.${COLUMN} added by ${auth.who} — ANVIL schema blocker cleared.`)
    return NextResponse.json({
      ok: true,
      changed: true,
      table: TABLE,
      column: COLUMN,
      by: auth.who,
      verified: true,
      note:
        'Column added and verified in information_schema. This does NOT arm ANVIL: the mirror is still ' +
        'gated behind CUSTOMER_ANVIL (default off) and still throws fail-closed until those guards are ' +
        'lifted in a reviewed change.',
    })
  } catch (e: unknown) {
    return NextResponse.json(
      { ok: false, changed: false, error: e instanceof Error ? e.message : String(e) },
      { status: 500 },
    )
  }
}
