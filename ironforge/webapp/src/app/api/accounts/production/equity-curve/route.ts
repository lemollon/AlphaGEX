import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, num, escapeSql, CT_TODAY } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * GET /api/accounts/production/equity-curve
 *
 * Returns the equity curve for a specific production (Tradier) account.
 * Built from production_equity_snapshots saved every scan cycle.
 *
 * Query params:
 *   - person (required): Account name (e.g., "Logan", "User")
 *   - period: "1d" | "1w" | "1m" | "3m" | "all" (default: "all")
 *   - mode: "historical" | "intraday" (default: "historical")
 */
export async function GET(req: NextRequest) {
  const personParam = req.nextUrl.searchParams.get('person')
  if (!personParam) {
    return NextResponse.json({ error: 'person parameter required' }, { status: 400 })
  }

  const period = req.nextUrl.searchParams.get('period') || 'all'
  const mode = req.nextUrl.searchParams.get('mode') || 'historical'

  try {
    const person = escapeSql(personParam)

    if (mode === 'intraday') {
      // Today's snapshots (1-minute granularity from scan cycles)
      const rows = await dbQuery(
        `SELECT snapshot_time, total_equity, option_buying_power,
                day_pnl, unrealized_pnl, open_positions, note
         FROM production_equity_snapshots
         WHERE person = $1
           AND (snapshot_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
         ORDER BY snapshot_time ASC`,
        [personParam],
      )

      const snapshots = rows.map((r) => ({
        timestamp: r.snapshot_time,
        total_equity: num(r.total_equity),
        option_buying_power: num(r.option_buying_power),
        day_pnl: num(r.day_pnl),
        unrealized_pnl: num(r.unrealized_pnl),
        open_positions: parseInt(r.open_positions) || 0,
        note: r.note,
      }))

      return NextResponse.json({
        person: personParam,
        mode: 'intraday',
        snapshots,
        snapshot_count: snapshots.length,
      })
    }

    // Historical mode: one snapshot per 5-minute window (downsample to avoid huge payloads)
    let dateFilter = ''
    if (period !== 'all') {
      const days = period === '1d' ? 1 : period === '1w' ? 7 : period === '1m' ? 30 : period === '3m' ? 90 : 0
      if (days > 0) {
        dateFilter = `AND snapshot_time >= NOW() - INTERVAL '${days} days'`
      }
    }

    const rows = await dbQuery(
      `SELECT
         date_trunc('hour', snapshot_time) +
           (EXTRACT(minute FROM snapshot_time)::int / 5) * INTERVAL '5 minutes' AS bucket,
         AVG(total_equity) AS total_equity,
         AVG(option_buying_power) AS option_buying_power,
         AVG(day_pnl) AS day_pnl,
         AVG(unrealized_pnl) AS unrealized_pnl,
         MAX(open_positions) AS open_positions
       FROM production_equity_snapshots
       WHERE person = $1 ${dateFilter}
       GROUP BY bucket
       ORDER BY bucket ASC`,
      [personParam],
    )

    const curve = rows.map((r) => ({
      timestamp: r.bucket,
      total_equity: Math.round(num(r.total_equity) * 100) / 100,
      option_buying_power: Math.round(num(r.option_buying_power) * 100) / 100,
      day_pnl: Math.round(num(r.day_pnl) * 100) / 100,
      unrealized_pnl: Math.round(num(r.unrealized_pnl) * 100) / 100,
      open_positions: parseInt(r.open_positions) || 0,
    }))

    return NextResponse.json({
      person: personParam,
      mode: 'historical',
      period,
      curve,
      data_points: curve.length,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
