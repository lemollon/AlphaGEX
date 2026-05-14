/**
 * BLAZE Directional Chart — historical GEX snapshots for time-varying
 * wall/flip overlays. Backed by blaze_gex_history, written every scan
 * cycle by blaze/scanner.ts.writeGexHistory().
 *
 * Query params:
 *   since: ISO timestamp (default: start of today in CT)
 *   limit: max rows (default: 500, max: 2000)
 *
 * Response shape:
 *   {
 *     snapshots: [
 *       { time, spot, vix, net_gex, call_wall, put_wall, flip_point, regime },
 *       ...
 *     ]
 *   }
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, num } from '@/lib/db'

export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  const url = req.nextUrl
  const sinceParam = url.searchParams.get('since')
  const limitRaw = parseInt(url.searchParams.get('limit') || '500', 10)
  const limit = Number.isFinite(limitRaw) ? Math.max(10, Math.min(2000, limitRaw)) : 500

  // Default = midnight CT today (covers the active RTH session + after-hours
  // snapshots taken before market open).
  const sinceClause = sinceParam
    ? `AND snapshot_time >= '${sinceParam.replace(/'/g, "''")}'::timestamptz`
    : `AND (snapshot_time AT TIME ZONE 'America/Chicago')::date = (NOW() AT TIME ZONE 'America/Chicago')::date`

  try {
    const rows = await dbQuery(
      `SELECT snapshot_time, spot_price, vix, net_gex,
              call_wall, put_wall, flip_point, regime
       FROM blaze_gex_history
       WHERE 1=1 ${sinceClause}
       ORDER BY snapshot_time ASC
       LIMIT ${limit}`,
    )
    return NextResponse.json({
      snapshots: rows.map(r => ({
        time: r.snapshot_time,
        spot: num(r.spot_price),
        vix: num(r.vix),
        net_gex: num(r.net_gex),
        call_wall: num(r.call_wall),
        put_wall: num(r.put_wall),
        flip_point: num(r.flip_point),
        regime: r.regime || 'NEUTRAL',
      })),
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    // Treat missing-table as "no data yet" instead of 500 — the table is
    // auto-created on first scan, and a brand-new deploy may briefly serve
    // requests before the scanner has run its first cycle.
    if (/relation .* does not exist/i.test(msg)) {
      return NextResponse.json({ snapshots: [], note: 'table_not_created_yet' })
    }
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
