import { NextRequest, NextResponse } from 'next/server'
import { resolveEmberOwner } from '@/lib/ember-entitlement'
import { getEmberEquityCurve, type EmberEquityPeriod } from '@/lib/ember-trades'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const PERIODS: EmberEquityPeriod[] = ['day', 'week', 'month', 'year', 'all']

/**
 * GET /api/ember/equity-curve?period=day|week|month|year|all — Ember's
 * performance chart data, for the signed-in customer who owns Ember. Same
 * 403-not-401 reasoning as /api/ember/status and /api/ember/trades.
 *
 * Built entirely from ember_trades' own realized `pnl` — see
 * lib/ember-trades.ts's getEmberEquityCurve() header comment for why this is
 * cumulative REALIZED P&L, not an account balance (Ember's pipeline has no
 * equity_snapshots table and no starting_capital; REFLEX's live Robinhood
 * total_value is never synced into this webapp today).
 */
export async function GET(req: NextRequest) {
  const owner = await resolveEmberOwner()
  if (!owner) {
    return NextResponse.json({ ok: false, error: 'not entitled to Ember', points: [], period_pnl: null }, { status: 403 })
  }
  const periodParam = req.nextUrl.searchParams.get('period')
  const period: EmberEquityPeriod = PERIODS.includes(periodParam as EmberEquityPeriod) ? (periodParam as EmberEquityPeriod) : 'day'
  try {
    const curve = await getEmberEquityCurve(period)
    return NextResponse.json({ ok: true, period, points: curve.points, period_pnl: curve.period_pnl })
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    return NextResponse.json({ ok: false, error: msg, points: [], period_pnl: null }, { status: 500 })
  }
}
