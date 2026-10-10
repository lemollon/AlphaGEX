import type { LiveEquityPoint, LiveSummary } from '@/api/types'

/**
 * The Forge hero chart's four period series (APP-002 "scrubbable chart"; mobile
 * addendum §2 "Period defs match web exactly").
 *
 * Two real sources feed this, never a fabricated one:
 *   - Today: `LiveSummary.intraday`, the same minute-bucketed equity series the
 *     web dashboard draws — real scanner snapshots, not synthesized.
 *   - Week / Month / Lifetime: `LivePerformance.equity_curve`, built server-side
 *     from actual closed-trade dates (performance.ts's buildCurve). It is NOT
 *     minute-cadence — it only has a point per closed trade — so slicing it by
 *     CALENDAR days is an approximation of the web's 5/21 TRADING-day windows,
 *     not an exact match. That is an honest trade-off (real but coarser data)
 *     rather than inventing intermediate points, which the no-synthetic-data
 *     rule forbids outright.
 */
export type HeroPeriod = 'today' | 'week' | 'month' | 'life'

export interface AccountPoint {
  t: number
  v: number
}

const DAY_MS = 86_400_000
// Calendar-day windows wide enough to comfortably contain 5 and 21 TRADING
// days (weekends/holidays included) without reaching into the next bucket.
const WEEK_CALENDAR_DAYS = 9
const MONTH_CALENDAR_DAYS = 31

export function todaySeries(intraday: LiveSummary['intraday'] | undefined): AccountPoint[] {
  if (!intraday) return []
  return intraday
    .filter((p): p is { timestamp: string; equity: number; pnl?: number | null } => p.equity != null)
    .map((p) => ({ t: new Date(p.timestamp).getTime(), v: p.equity }))
}

function fromEquityCurve(curve: LiveEquityPoint[] | undefined): AccountPoint[] {
  if (!curve) return []
  return curve.map((p) => ({ t: new Date(p.t).getTime(), v: p.equity }))
}

/** Trailing `days` calendar days of an equity curve, ending at its own last point
 *  (not "now") — the curve stops at the last closed trade, and anchoring the
 *  window to "now" would just shrink it toward empty on a quiet week. */
function trailingCalendarDays(curve: AccountPoint[], days: number): AccountPoint[] {
  if (!curve.length) return []
  const end = curve[curve.length - 1].t
  const cutoff = end - days * DAY_MS
  return curve.filter((p) => p.t >= cutoff)
}

export function periodSeries(
  period: HeroPeriod,
  intraday: LiveSummary['intraday'] | undefined,
  equityCurve: LiveEquityPoint[] | undefined,
): AccountPoint[] {
  if (period === 'today') return todaySeries(intraday)
  const curve = fromEquityCurve(equityCurve)
  if (period === 'week') return trailingCalendarDays(curve, WEEK_CALENDAR_DAYS)
  if (period === 'month') return trailingCalendarDays(curve, MONTH_CALENDAR_DAYS)
  return curve
}

export const HERO_PERIOD_LABEL: Record<HeroPeriod, string> = {
  today: 'today',
  week: 'past week',
  month: 'past month',
  life: 'lifetime',
}

export const HERO_PERIOD_TILE_LABEL: Record<HeroPeriod, string> = {
  today: 'Today',
  week: 'Past week',
  month: 'Past month',
  life: 'Lifetime',
}
