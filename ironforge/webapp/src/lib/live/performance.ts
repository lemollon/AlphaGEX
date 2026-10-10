import { dbQuery, botTable, num, int, escapeSql, dteMode, CT_TODAY } from '@/lib/db'
import { scopeFilter, resolveAccountMode, type LiveBot } from './viewer'
import { LIVE_BOT_LABEL, LIVE_BOT_ACCENT } from './bots'
import { getSandboxAccountBalances } from '@/lib/tradier'
import {
  sumTradingDayWindow,
  dailyResultBars,
  agentLead,
  cumulativePnlSeries,
  type PnlPoint,
} from './trading-days'

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
  /** Where account_value came from — 'tradier' is the real broker equity. */
  balance_source?: 'tradier' | 'paper_account'
  total_pnl: number
  win_rate: number | null
  trades: number
  /** All-time return on the pooled starting capital, percent. null when no base. */
  return_pct: number | null
  /** Realised P&L over the last 5 / 21 TRADING days, including today
   *  (dev-handoff §6 KPI contract — not a Monday-reset calendar week or a
   *  1st-of-month calendar reset; see trading-days.ts). */
  weekly: number
  monthly: number
  /** Broker buying power (Tradier `option_buying_power`) for a live bot, or the
   *  paper ledger's own `buying_power` column for a paper bot (db-kpi "Capital
   *  available"). Null only when neither source answered. */
  capital_available: number | null
  /** Capital committed to open positions right now — Tradier accountValue minus
   *  capital_available for a live bot, or the paper ledger's own
   *  `collateral_in_use` for a paper bot (db-kpi "Capital available" sub-label). */
  held_for_open_trades: number | null
  /** Realized P&L for today's trading session plus unrealized P&L on anything
   *  still open (db-kpi "Today"). Null only when neither source answered. */
  today_pnl: number | null
  /** This bot's own cumulative-realised equity curve, so the per-strategy
   *  toggle switches the chart, not just the numbers. */
  curve: EquityPoint[]
  /** Last 20 trading days as zero-filled {day, pnl} bars (Daily results chart). */
  daily_bars: Array<{ day: string; pnl: number }>
  /** Agent lead tile: "Days the trade kept its credit: X of Y". Null when the
   *  agent has no closed trade yet. */
  lead: { kept: number; total: number } | null
  /** Cumulative-from-zero P&L series per chart range (dev-handoff: "single
   *  cumulative line from 0", not an equity curve — see cumulativePnlSeries). */
  pnl_ranges: { '1D': PnlPoint[]; '1W': PnlPoint[]; '1M': PnlPoint[]; ALL: PnlPoint[] }
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
    /** Combined last-5 / last-21-trading-day realised P&L (dev-handoff KPIs). */
    weekly: number
    monthly: number
    /** Sum of every owned bot's capital_available/held_for_open_trades/today_pnl.
     *  Null when EVERY bot's own figure is null (nothing real to add); otherwise
     *  missing bots count as 0 so one unreadable source doesn't blank the total. */
    capital_available: number | null
    held_for_open_trades: number | null
    today_pnl: number | null
  }
  equity_curve: EquityPoint[]
  /** Combined last 20 trading days as zero-filled {day, pnl} bars. */
  daily_bars: Array<{ day: string; pnl: number }>
  /** Combined cumulative-from-zero P&L series per chart range. */
  pnl_ranges: { '1D': PnlPoint[]; '1W': PnlPoint[]; '1M': PnlPoint[]; ALL: PnlPoint[] }
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

/** Win rate as a percent, one decimal, or null when there is nothing to divide by.
 *  Shared definition — win = realized_pnl > 0 — so every KPI derived from it (this
 *  page's per-bot/combined win_rate, the mobile Ledger KPI strip) agrees. */
export function winRatePct(wins: number, trades: number): number | null {
  return trades > 0 ? Math.round((wins / trades) * 1000) / 10 : null
}

/** Base per-bot stats before getPerformance enriches with curve + trailing KPIs. */
type BasePerf = Omit<BotPerf, 'return_pct' | 'weekly' | 'monthly' | 'curve' | 'daily_bars' | 'lead' | 'pnl_ranges'>

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

async function loadBot(
  bot: LiveBot,
  person: string | null = null,
  isOperator = false,
): Promise<RawBot> {
  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const prod = scopeFilter(bot, person, isOperator)
  const closed = `status IN ('closed', 'expired') AND realized_pnl IS NOT NULL ${dteFilter} ${prod}`

  const [statRows, capRows, pointRows, todayRealizedRows, latestSnapshotRows] = await Promise.all([
    dbQuery(
      `SELECT COUNT(*) AS trades,
              COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
              COALESCE(SUM(realized_pnl), 0) AS pnl
       FROM ${botTable(bot, 'positions')} WHERE ${closed}`,
    ),
    dbQuery(
      `SELECT starting_capital, buying_power, collateral_in_use
       FROM ${botTable(bot, 'paper_account')}
       WHERE is_active = TRUE ${dteFilter} ${prod} ORDER BY id DESC LIMIT 1`,
    ),
    dbQuery(
      `SELECT (close_time AT TIME ZONE 'America/Chicago')::date AS ct_date, close_time, realized_pnl
       FROM ${botTable(bot, 'positions')} WHERE ${closed} ORDER BY close_time ASC`,
    ),
    // db-kpi "Today": realized P&L for TODAY's session only — a separate sum from
    // the all-time `pnl` above, which the daily_bars/weekly/monthly windows below
    // also need their own trading-day math for, not this plain calendar date.
    dbQuery(
      `SELECT COALESCE(SUM(realized_pnl), 0) AS today_realized_pnl
       FROM ${botTable(bot, 'positions')}
       WHERE status IN ('closed', 'expired') AND realized_pnl IS NOT NULL
         AND (close_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
         ${dteFilter} ${prod}`,
    ),
    dbQuery(
      `SELECT unrealized_pnl FROM ${botTable(bot, 'equity_snapshots')}
       WHERE 1=1 ${dteFilter} ${prod} ORDER BY snapshot_time DESC LIMIT 1`,
    ),
  ])

  const trades = int(statRows[0]?.trades)
  const wins = int(statRows[0]?.wins)
  const pnl = Math.round(num(statRows[0]?.pnl) * 100) / 100

  // ── Account value: the BROKER first, the ledger only as a fallback ──────────
  //
  // This read starting_capital from the paper_account row and reported
  // `starting_capital + pnl` as the account value, never consulting Tradier — while
  // /live resolves the same number from the live broker equity. The two customer pages
  // therefore disagreed about the SAME real-money account: /performance showed
  // $1,233.33 (ledger baseline $1,030.58) against a true Tradier equity of $5,156.18.
  // Both agreed on the P&L; the entire gap was a stale baseline.
  //
  // When the broker answers, its equity IS the account value and the baseline is
  // derived from it (equity − realised P&L) so the pair stays coherent and the return
  // percentage keeps meaning the same thing. Paper bots never consult Tradier.
  const isPaper = resolveAccountMode(bot) === 'paper'
  let startingCapital = num(capRows[0]?.starting_capital)
  let accountValue = Math.round((startingCapital + pnl) * 100) / 100
  let balanceSource: 'tradier' | 'paper_account' = 'paper_account'

  // db-kpi "Capital available" / "Today" — same broker-first, ledger-fallback rule as
  // account value above. Paper's own buying_power/collateral_in_use columns are the
  // real paper ledger (not invented); Tradier's option_buying_power/day_pnl are the
  // real broker fields (see tradier.ts's SandboxAccountBalance — the same ones
  // getLiveSummary's single-bot "Today" KPI already trusts).
  let capitalAvailable: number | null = capRows[0]?.buying_power != null ? num(capRows[0].buying_power) : null
  let heldForOpenTrades: number | null =
    capRows[0]?.collateral_in_use != null ? num(capRows[0].collateral_in_use) : null
  let todayPnl: number | null =
    todayRealizedRows[0] != null
      ? Math.round((num(todayRealizedRows[0].today_realized_pnl) + num(latestSnapshotRows[0]?.unrealized_pnl)) * 100) / 100
      : null

  if (!isPaper) {
    const bals = await getSandboxAccountBalances().catch(() => [])
    const prodBals = bals.filter(
      (b) =>
        b.account_type === 'production' &&
        b.total_equity != null &&
        // Same owner scoping as /live — never sum another customer's account.
        (person == null || b.name === person),
    )
    // Refuse to aggregate for a non-operator, matching getLiveSummary: an honest
    // ledger figure beats a total that silently includes someone else's money.
    const mayUse = prodBals.length === 1 || (isOperator && prodBals.length > 0)
    if (mayUse) {
      accountValue = Math.round(prodBals.reduce((a, b) => a + num(b.total_equity), 0) * 100) / 100
      startingCapital = Math.round((accountValue - pnl) * 100) / 100
      balanceSource = 'tradier'
      capitalAvailable = Math.round(prodBals.reduce((a, b) => a + num(b.option_buying_power), 0) * 100) / 100
      heldForOpenTrades = Math.round(Math.max(0, accountValue - capitalAvailable) * 100) / 100
      todayPnl = Math.round(prodBals.reduce((a, b) => a + num(b.day_pnl) + num(b.unrealized_pnl), 0) * 100) / 100
    } else {
      // Not readable for this viewer — never claim a paper-ledger number for a
      // live bot's capital/today figures.
      capitalAvailable = null
      heldForOpenTrades = null
      todayPnl = null
    }
  }

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
      account_value: accountValue,
      balance_source: balanceSource,
      total_pnl: pnl,
      win_rate: winRatePct(wins, trades),
      trades,
      capital_available: capitalAvailable,
      held_for_open_trades: heldForOpenTrades,
      today_pnl: todayPnl,
    },
    wins,
    points,
  }
}

export async function getPerformance(
  bots: LiveBot[],
  persons: Record<string, string | null> = {},
  isOperator = false,
): Promise<PerformanceData> {
  const raws = await Promise.all(bots.map((b) => loadBot(b, persons[b] ?? null, isOperator)))
  const asOf = new Date()
  // Enrich each bot with its own curve + trailing KPIs so the per-strategy
  // toggle on the Performance page switches the chart and the income tiles.
  // "Past week"/"Past month" are 5/21 TRADING days (dev-handoff §6), not a
  // calendar week or calendar month.
  const perfBots = raws.map((r) => ({
    ...r.perf,
    return_pct: r.perf.starting_capital > 0
      ? Math.round((r.perf.total_pnl / r.perf.starting_capital) * 10000) / 100
      : null,
    weekly: sumTradingDayWindow(r.points, 5, asOf),
    monthly: sumTradingDayWindow(r.points, 21, asOf),
    curve: buildCurve(r.points, r.perf.starting_capital),
    daily_bars: dailyResultBars(r.points, 20, asOf),
    lead: agentLead(r.points),
    pnl_ranges: {
      '1D': cumulativePnlSeries(r.points, 1, asOf),
      '1W': cumulativePnlSeries(r.points, 5, asOf),
      '1M': cumulativePnlSeries(r.points, 21, asOf),
      ALL: cumulativePnlSeries(r.points, null, asOf),
    },
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

  // Sum each nullable per-bot figure, but only when AT LEAST ONE bot actually
  // answered — all-null in means all-null out, never a fabricated $0.00 total.
  const sumNullable = (vals: Array<number | null>): number | null =>
    vals.every((v) => v == null) ? null : round2(vals.reduce((s: number, v) => s + (v ?? 0), 0))
  const capitalAvailable = sumNullable(perfBots.map((b) => b.capital_available))
  const heldForOpenTrades = sumNullable(perfBots.map((b) => b.held_for_open_trades))
  const todayPnl = sumNullable(perfBots.map((b) => b.today_pnl))

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

  const combinedPoints = all.map((p) => ({ t: p.t, day: p.day, pnl: p.pnl }))

  return {
    bots: perfBots,
    combined: {
      starting_capital: startingCapital,
      account_value: round2(startingCapital + totalPnl),
      total_pnl: totalPnl,
      total_return_pct: startingCapital > 0 ? Math.round((totalPnl / startingCapital) * 10000) / 100 : null,
      win_rate: winRatePct(wins, totalTrades),
      total_trades: totalTrades,
      wins,
      losses: totalTrades - wins,
      best_day: bestDay,
      // Combined weekly/monthly are the SUM of each bot's own trading-day
      // window, not a window recomputed on the merged points — two bots can
      // trade on different days, so "the last 5 trading days" isn't a single
      // shared set across them the way it is for a single bot.
      weekly: round2(perfBots.reduce((s, b) => s + b.weekly, 0)),
      monthly: round2(perfBots.reduce((s, b) => s + b.monthly, 0)),
      capital_available: capitalAvailable,
      held_for_open_trades: heldForOpenTrades,
      today_pnl: todayPnl,
    },
    equity_curve: curve,
    daily_bars: dailyResultBars(combinedPoints, 20, asOf),
    pnl_ranges: {
      '1D': cumulativePnlSeries(combinedPoints, 1, asOf),
      '1W': cumulativePnlSeries(combinedPoints, 5, asOf),
      '1M': cumulativePnlSeries(combinedPoints, 21, asOf),
      ALL: cumulativePnlSeries(combinedPoints, null, asOf),
    },
    as_of: new Date().toISOString(),
  }
}
