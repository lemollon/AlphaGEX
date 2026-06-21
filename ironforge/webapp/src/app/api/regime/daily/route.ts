import { NextRequest, NextResponse } from 'next/server'
import { dbQuery } from '@/lib/db'
import { ensureRegimeDailyTable } from '@/lib/volAlerts.server'

export const dynamic = 'force-dynamic'

/**
 * IronForge's OWN daily regime history (replaces the empty AlphaGEX-proxied
 * `/api/volatility/history`). One row per CT trading day: latched regime, the
 * sticky daily hedge decision, and (once backfilled) the realized next-day move.
 * This is the backtestable record for the regime→loss / hedge-trigger analysis.
 */
export async function GET(req: NextRequest) {
  const daysParam = req.nextUrl.searchParams.get('days')
  const days = daysParam && Number.isFinite(Number(daysParam)) ? Math.min(Number(daysParam), 400) : 120
  try {
    await ensureRegimeDailyTable()
    const rows = await dbQuery(
      `SELECT ct_date, regime_label, active_signals, vix, vvix, vix3m,
              hedge_flagged, hedge_reasons, first_flagged_at,
              realized_spy_ret, realized_vix_chg, updated_at
         FROM regime_daily
        WHERE ct_date >= (NOW() AT TIME ZONE 'America/Chicago')::date - ($1::int)
        ORDER BY ct_date DESC`,
      [days],
    )
    return NextResponse.json({ rows })
  } catch (err: unknown) {
    return NextResponse.json({ error: err instanceof Error ? err.message : String(err) }, { status: 500 })
  }
}
