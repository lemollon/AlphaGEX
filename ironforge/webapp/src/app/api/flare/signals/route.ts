import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, num, int } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * GET /api/flare/signals
 *
 * FLARE-specific override of the generic /api/[bot]/signals route.
 *
 * FLARE is a directional vertical-debit bot — its scanner does NOT write to the
 * IC-shaped `flare_signals` table (which stays empty). Every scan outcome
 * (TRADE / NO_TRADE / SKIP / ERROR / RISK_FORCE_CLOSE) is logged to `flare_logs`
 * via insertSignalActivity(). The generic route reads `flare_signals`, so the
 * dashboard Signals tab was permanently blank and the operator had no visibility
 * into WHY FLARE wasn't trading. This route reads the real feed (flare_logs) and
 * maps it into the Signal shape the SignalsTable component expects.
 *
 * The reason/detail string carries the actionable info, e.g.:
 *   "regime=EXTREME_NEGATIVE spot=737.55 cw=750 pw=737"   (NO_TRADE)
 *   "dir_cooldown_call"                                    (SKIP)
 *   "max_concurrent_call=20/20"                            (SKIP)
 *   "gex_stale:gex snapshot age=274.2s > 90s"              (SKIP)
 *   "RISK_FORCE_CLOSE call x4 pnl=-694.00 cooldown_45min"  (TRADE/force-close)
 */
export async function GET(req: NextRequest) {
  const url = new URL(req.url)
  const limit = Math.min(Math.max(1, int(url.searchParams.get('limit')) || 60), 200)
  const offset = Math.max(0, int(url.searchParams.get('offset')) || 0)

  try {
    const rows = await dbQuery(
      `SELECT id, log_time, level, message, details
         FROM flare_logs
        WHERE message IN ('TRADE', 'NO_TRADE', 'SKIP', 'ERROR')
        ORDER BY log_time DESC
        LIMIT ${limit} OFFSET ${offset}`,
    )

    const signals = rows.map((r) => {
      const details: string = r.details || ''
      // Pull whatever structured fields the scanner embedded in the detail string.
      const spot = /spot=([\d.]+)/.exec(details)?.[1]
      const regime = /regime=([A-Z_]+)/.exec(details)?.[1]
      const executed = r.message === 'TRADE'
      // For the Reason column: prefix the outcome unless the detail already says it.
      const reason =
        r.message === 'TRADE' ? details : `${r.message}: ${details}`
      return {
        id: int(r.id),
        signal_time: r.log_time || null,
        spot_price: spot ? num(spot) : 0,
        vix: 0,
        expected_move: 0,
        call_wall: num(/cw=([\d.]+)/.exec(details)?.[1]),
        put_wall: num(/pw=([\d.]+)/.exec(details)?.[1]),
        gex_regime: regime || null,
        // Directional bot — no IC strikes on a scan row.
        put_short: 0,
        put_long: 0,
        call_short: 0,
        call_long: 0,
        total_credit: 0,
        confidence: 0,
        was_executed: executed,
        skip_reason: reason,
        reasoning: details,
        wings_adjusted: false,
        dte_mode: '0DTE',
      }
    })

    return NextResponse.json({ signals })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ signals: [], error: msg }, { status: 200 })
  }
}
