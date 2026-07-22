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
  }
  equity_curve: EquityPoint[]
  as_of: string
}

interface RawBot {
  perf: BotPerf
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
  const perfBots = raws.map((r) => r.perf)

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
    },
    equity_curve: curve,
    as_of: new Date().toISOString(),
  }
}
