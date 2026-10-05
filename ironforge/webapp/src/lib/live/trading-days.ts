import { isMarketHoliday } from '@/lib/market-calendar'
import { getCTNow } from '@/lib/pt-tiers'

/**
 * Trading-day windows for the customer dashboard KPIs (dev-handoff §6: "Past
 * week" = last 5 trading days including today, "Past month" = last 21 trading
 * days including today — NOT a Monday-reset calendar week or a 1st-of-month
 * calendar reset, which is what `/api/live/performance` shipped with before
 * this fix).
 *
 * A "trading day" here is any NYSE weekday that is not a full-closure holiday
 * (half-days still count — the session happened, just shorter).
 *
 * `isMarketHoliday()` reads the LOCAL getFullYear/getMonth/getDate fields off
 * whatever Date it's given (it was written for the scanner's CT-local `Date`
 * objects). This module stays self-consistent with that contract by doing all
 * of its own date-key building with the matching LOCAL getters/constructor —
 * it never mixes in UTC fields — so the weekday/holiday read always lines up
 * with the same calendar date being walked.
 */

function localKey(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${dd}`
}

/**
 * Returns the last `n` trading-day date keys (YYYY-MM-DD, ascending, oldest
 * first) ending on `asOf` (inclusive, even when `asOf` itself lands on a
 * weekend/holiday — the window just starts counting from the prior one).
 */
export function lastNTradingDays(n: number, asOf: Date = getCTNow()): string[] {
  const out: string[] = []
  const cur = new Date(asOf.getFullYear(), asOf.getMonth(), asOf.getDate())
  // Hard cap so a bad holiday table (or n <= 0) can never spin forever.
  let guard = n * 4 + 30
  while (out.length < n && guard-- > 0) {
    const dow = cur.getDay() // 0 = Sun, 6 = Sat
    if (dow !== 0 && dow !== 6 && !isMarketHoliday(cur)) {
      out.unshift(localKey(cur))
    }
    cur.setDate(cur.getDate() - 1)
  }
  return out
}

/** Sum `{day, pnl}` points whose `day` falls within the last `n` trading days. */
export function sumTradingDayWindow(
  points: Array<{ day: string; pnl: number }>,
  n: number,
  asOf: Date = getCTNow(),
): number {
  const window = new Set(lastNTradingDays(n, asOf))
  const s = points.reduce((a, p) => (window.has(p.day) ? a + p.pnl : a), 0)
  return Math.round(s * 100) / 100
}

export interface PnlPoint { t: string; pnl: number }

/**
 * Cumulative-from-zero realized-P&L series for the dashboard's 1D/1W/1M/All
 * chart (dev-handoff: "single cumulative line from 0"). This is deliberately
 * NOT an equity curve — every range restarts at zero, so a 1W view shows the
 * week's P&L shape, not the account's whole balance history. `n = null` means
 * "All" (every closed-trade point, no window).
 */
export function cumulativePnlSeries(
  points: Array<{ t: number; day: string; pnl: number }>,
  n: number | null,
  asOf: Date = getCTNow(),
): PnlPoint[] {
  const filtered = n == null
    ? points
    : (() => {
        const window = new Set(lastNTradingDays(n, asOf))
        return points.filter((p) => window.has(p.day))
      })()
  const sorted = [...filtered].sort((a, b) => a.t - b.t)
  const out: PnlPoint[] = []
  let run = 0
  for (const p of sorted) {
    run += p.pnl
    out.push({ t: new Date(p.t).toISOString(), pnl: Math.round(run * 100) / 100 })
  }
  return out
}

/**
 * Last `n` trading days as `{day, pnl}` bars for the "Daily results" chart —
 * zero-filled for sessions with no closed trade, so the chart always has
 * exactly `n` bars (dev-handoff: "last 20 trading days").
 */
export function dailyResultBars(
  points: Array<{ day: string; pnl: number }>,
  n: number,
  asOf: Date = getCTNow(),
): Array<{ day: string; pnl: number }> {
  const days = lastNTradingDays(n, asOf)
  const byDay = new Map<string, number>()
  for (const p of points) byDay.set(p.day, (byDay.get(p.day) ?? 0) + p.pnl)
  return days.map((day) => ({ day, pnl: Math.round((byDay.get(day) ?? 0) * 100) / 100 }))
}

/**
 * Agent lead tile (dev-handoff): "Days the trade kept its credit: X of Y" —
 * winning trading days ÷ total trading days the agent actually traded, since
 * its first trade. Only counts days present in `points` (days the agent had
 * at least one closed trade), not every calendar trading day since.
 */
export function agentLead(points: Array<{ day: string; pnl: number }>): { kept: number; total: number } | null {
  if (points.length === 0) return null
  const byDay = new Map<string, number>()
  for (const p of points) byDay.set(p.day, (byDay.get(p.day) ?? 0) + p.pnl)
  const total = byDay.size
  const kept = Array.from(byDay.values()).filter((v) => v > 0).length
  return { kept, total }
}
