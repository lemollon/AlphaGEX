/**
 * KINDLE orphan re-open — remediation for the 2026-06-25 failed-close orphans.
 *
 * When a production close FAILED at the broker (before the close-path fix), the DB
 * marked the position CLOSED while it stayed OPEN at Tradier — an orphan that would
 * expire and risk an assignment fee. This re-opens such orphans (production
 * positions closed in the DB whose expiration is still in the FUTURE) so the
 * scanner's monitor manages + CLOSES them at the broker before expiry (the close
 * path now reaches 6YB70795). closeIcOrderAllAccounts checks the real Tradier
 * quantity, so re-opening a position that's genuinely already closed is a safe
 * no-op (0 qty → nothing to close).
 *
 * GET  — list orphan candidates (read-only).
 * POST — re-open them (status=open, clear close fields).
 * Scoped to KINDLE production positions only. Places no orders itself.
 */
import { NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, CT_TODAY } from '@/lib/db'

export const dynamic = 'force-dynamic'

const SELECT_ORPHANS = `
  SELECT position_id, expiration, put_short_strike, put_long_strike,
         call_short_strike, call_long_strike, contracts, total_credit, close_reason
  FROM ${botTable('kindle', 'positions')}
  WHERE COALESCE(account_type,'sandbox') = 'production'
    AND status = 'closed'
    AND expiration > ${CT_TODAY}`

export async function GET() {
  const rows = await dbQuery(SELECT_ORPHANS)
  return NextResponse.json({
    ok: true,
    preview: true,
    orphan_candidates: rows,
    note: 'POST to re-open these so the monitor closes them at the broker before expiry.',
  })
}

export async function POST() {
  const rows = await dbQuery(SELECT_ORPHANS)
  if (rows.length === 0) {
    return NextResponse.json({ ok: true, reopened: 0, message: 'No future-dated closed production orphans to re-open.' })
  }
  await dbExecute(
    `UPDATE ${botTable('kindle', 'positions')}
       SET status = 'open',
           close_time = NULL,
           close_price = NULL,
           realized_pnl = NULL,
           close_reason = NULL,
           sandbox_close_order_id = NULL,
           updated_at = NOW()
     WHERE COALESCE(account_type,'sandbox') = 'production'
       AND status = 'closed'
       AND expiration > ${CT_TODAY}`,
  )
  return NextResponse.json({
    ok: true,
    reopened: rows.length,
    positions: (rows as Array<Record<string, unknown>>).map(r => r.position_id),
    message: `Re-opened ${rows.length} orphan(s). The scanner monitor will now close them at 6YB70795 before expiry (close path fixed). KINDLE can stay paused — closes are pause-exempt.`,
  })
}
