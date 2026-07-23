import { dbQuery, botTable, num, int, escapeSql, dteMode } from '@/lib/db'
import { scopeFilter, resolveAccountMode, type LiveBot } from './viewer'
import { LIVE_BOT_LABEL, LIVE_BOT_ACCENT } from './bots'

/**
 * Customer Performance page payload — the viewer's all-time history, COMBINED
 * across every bot they own (per the chosen "combined only, no per-bot
 * drill-down" model). Scoped through the same ledgerFilter the Live/Home pages
 * use, so the money reconciles across pages. Honest-data rules: null when a stat
 * can't be computed, never fabricated.
 */

export interface BotPerf {
  bot: LiveBot
  label: string
  accent: 'spark' | 'flame'
  paper: boolean
  starting_capital: number
  account_value: number
  total_pnl: number
  win_rate: number | null
  trades: number
  /** All-time return on the pooled starting capital, percent. null when no base. */
  return_pct: number | null
  /** Realised P&L over the trailing 7 / 30 days (the Wealth-Snapshot KPIs,
   *  now shown on Performance and switchable per strategy). */
  weekly: number
  monthly: number
  /** This bot's own cumulative-realised equity curve, so the per-strategy
   *  toggle switches the chart, not just the numbers. */
  curve: EquityPoint[]
}

export interface EquityPoint {
  t: string
  equity: number
}

export interface PerformanceData {
  bots: BotPerf[]
  combined: {
    starting_capital: number
    account_value: number
    total_pnl: number
    total_return_pct: number | null
    win_rate: number | null
    total_trades: number
    wins: number
    losses: number
    best_day: number | null
    /** Combined trailing 7 / 30-day realised P&L (Wealth-Snapshot KPIs). */
    weekly: number
    monthly: number
  }
  equity_curve: EquityPoint[]
  as_of: string
}

/** Build a cumulative-realised equity curve from dated P&L points on top of a base. */
function buildCurve(points: Array<{ t: number; pnl: number }>, base: number): EquityPoint[] {
  const sorted = [...points].sort((a, b) => a.t - b.t)
  const r2 = (v: number) => Math.round(v * 100) / 100
  const out: EquityPoint[] = []
  let run = 0
  for (const p of sorted) {
    run += p.pnl
    out.push({ t: new Date(p.t).toISOString(), equity: r2(base + run) })
  }
  if (out.length) out.unshift({ t: new Date(sorted[0].t).toISOString(), equity: r2(base) })
  return out
}

/** Sum P&L of points whose timestamp is within the trailing `days`. */
function trailing(points: Array<{ t: number; pnl: number }>, days: number, nowMs: number): number {
  const cut = nowMs - days * 86_400_000
  const s = points.reduce((a, p) => (p.t >= cut ? a + p.pnl : a), 0)
  return Math.round(s * 100) / 100
}

/** Base per-bot stats before getPerformance enriches with curve + trailing KPIs. */
type BasePerf = Omit<BotPerf, 'return_pct' | 'weekly' | 'monthly' | 'curve'>

interface RawBot {
  perf: BasePerf
  wins: number
  /** Per-closed-trade points for the combined equity curve + best-day grouping. */
  points: Array<{ t: number; day: string; pnl: number }>
}

function ctDate(v: unknown): string {
  if (v instanceof Date) return v.toISOString().slice(0, 10)
  return v ? String(v).slice(0, 10) : ''
}

async function loadBot(bot: LiveBot, person: string | null = null): Promise<RawBot> {
  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const prod = scopeFilter(bot, person)
  const closed = `status IN ('closed', 'expired') AND realized_pnl IS NOT NULL ${dteFilter} ${prod}`

  const [statRows, capRows, pointRows] = await Promise.all([
    dbQuery(
      `SELECT COUNT(*) AS trades,
              COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
              COALESCE(SUM(realized_pnl), 0) AS pnl
       FROM ${botTable(bot, 'positions')} WHERE ${closed}`,
    ),
    dbQuery(
      `SELECT starting_capital FROM ${botTable(bot, 'paper_account')}
       WHERE is_active = TRUE ${dteFilter} ${prod} ORDER BY id DESC LIMIT 1`,
    ),
    dbQuery(
      `SELECT (close_time AT TIME ZONE 'America/Chicago')::date AS ct_date, close_time, realized_pnl
       FROM ${botTable(bot, 'positions')} WHERE ${closed} ORDER BY close_time ASC`,
    ),
  ])

  const trades = int(statRows[0]?.trades)
  const wins = int(statRows[0]?.wins)
  const pnl = Math.round(num(statRows[0]?.pnl) * 100) / 100
  const startingCapital = num(capRows[0]?.starting_capital)

  const points = pointRows
    .filter((r) => r.close_time)
    .map((r) => ({ t: new Date(r.close_time as string).getTime(), day: ctDate(r.ct_date), pnl: num(r.realized_pnl) }))
    .filter((p) => !isNaN(p.t))

  return {
    perf: {
      bot,
      label: LIVE_BOT_LABEL[bot],
      accent: LIVE_BOT_ACCENT[bot],
      paper: resolveAccountMode(bot) === 'paper',
      starting_capital: startingCapital,
      account_value: Math.round((startingCapital + pnl) * 100) / 100,
      total_pnl: pnl,
      win_rate: trades > 0 ? Math.round((wins / trades) * 1000) / 10 : null,
      trades,
    },
    wins,
    points,
  }
}

export async function getPerformance(
  bots: LiveBot[],
  persons: Record<string, string | null> = {},
): Promise<PerformanceData> {
  const raws = await Promise.all(bots.map((b) => loadBot(b, persons[b] ?? null)))
  const nowMs = Date.now()
  // Enrich each bot with its own curve + trailing KPIs so the per-strategy
  // toggle on the Performance page switches the chart and the income tiles.
  const perfBots = raws.map((r) => ({
    ...r.perf,
    return_pct: r.perf.starting_capital > 0
      ? Math.round((r.perf.total_pnl / r.perf.starting_capital) * 10000) / 100
      : null,
    weekly: trailing(r.points, 7, nowMs),
    monthly: trailing(r.points, 30, nowMs),
    curve: buildCurve(r.points, r.perf.starting_capital),
  }))

  const round2 = (v: number) => Math.round(v * 100) / 100
  const startingCapital = round2(perfBots.reduce((s, b) => s + b.starting_capital, 0))
  const totalPnl = round2(perfBots.reduce((s, b) => s + b.total_pnl, 0))
  const totalTrades = perfBots.reduce((s, b) => s + b.trades, 0)
  const wins = raws.reduce((s, r) => s + r.wins, 0)

  // Combined best day: sum same CT-date P&L across ALL the viewer's bots, take the max.
  const byDay = new Map<string, number>()
  for (const r of raws) {
    for (const p of r.points) {
      if (!p.day) continue
      byDay.set(p.day, (byDay.get(p.day) ?? 0) + p.pnl)
    }
  }
  const bestDay = byDay.size ? round2(Math.max(...Array.from(byDay.values()))) : null

  // Combined equity curve: merge every bot's closed trades by close time, run a
  // cumulative sum on top of the pooled starting capital.
  const all = raws.flatMap((r) => r.points).sort((a, b) => a.t - b.t)
  const curve: EquityPoint[] = []
  let run = 0
  for (const p of all) {
    run += p.pnl
    curve.push({ t: new Date(p.t).toISOString(), equity: round2(startingCapital + run) })
  }
  if (curve.length) curve.unshift({ t: new Date(all[0].t).toISOString(), equity: round2(startingCapital) })

  return {
    bots: perfBots,
    combined: {
      starting_capital: startingCapital,
      account_value: round2(startingCapital + totalPnl),
      total_pnl: totalPnl,
      total_return_pct: startingCapital > 0 ? Math.round((totalPnl / startingCapital) * 10000) / 100 : null,
      win_rate: totalTrades > 0 ? Math.round((wins / totalTrades) * 1000) / 10 : null,
      total_trades: totalTrades,
      wins,
      losses: totalTrades - wins,
      best_day: bestDay,
      weekly: round2(perfBots.reduce((s, b) => s + b.weekly, 0)),
      monthly: round2(perfBots.reduce((s, b) => s + b.monthly, 0)),
    },
    equity_curve: curve,
    as_of: new Date().toISOString(),
  }
}
