import { dbQuery, botTable, num, escapeSql, dteMode } from '@/lib/db'
import { ledgerFilter, resolveAccountMode } from './viewer'
import { LIVE_BOT_TAGLINE, type LiveBot } from './bots'

/**
 * PUBLIC track record — the proof surface shown to prospects who have no account.
 *
 * MIRRORS THE LEGACY OPERATOR DASHBOARDS (/spark, /flame). It computes the same
 * stats those pages show — total trades, win rate, realised P&L, profit factor,
 * best/worst, streak — from the same {bot}_positions ledger via ledgerFilter().
 * Because both read one source, the public number and the operator number can
 * never drift apart. (Do NOT derive numbers from the raw /api/{bot}/trades feed;
 * that returns a capped, differently-scoped slice and will disagree with the chart.)
 *
 * Never exposes a live balance, an open position, a control, or per-customer state
 * — only realised P&L on CLOSED trades.
 *
 * Honesty rules on this page:
 *   - Every card carries its real mode. SPARK is the production account (LIVE);
 *     FLAME is paper (SIMULATED). Never render one as the other.
 *   - WIN RATE leads (large samples, sizing-independent, credible). Net P&L and the
 *     equity-curve SHAPE are shown honestly, losing days included.
 *   - No return-on-capital %: both accounts' historical position sizing tracked a
 *     drifting balance rather than a fixed base, so a %-return would be distorted.
 *     Win rate, net dollars, and curve shape are robust to that; a % is not.
 */

/** Featured strategies, in display order. Both mirrored from the legacy dashboards. */
export const PUBLIC_BOTS: readonly LiveBot[] = ['spark', 'flame'] as const

const DISPLAY_NAME: Record<string, string> = { spark: 'SPARK', flame: 'FLAME' }
/** Mascot art key: public/home/{key}-mascot-glow.png */
const MASCOT_KEY: Record<string, 'spark' | 'flame'> = { spark: 'spark', flame: 'flame' }

export interface Stats {
  trades: number
  wins: number
  losses: number
  /** Percent, one decimal. null when no trades. */
  win_rate: number | null
  net_pnl: number
  best_trade: number | null
  worst_trade: number | null
  best_day: number | null
  worst_day: number | null
  green_days: number
  total_days: number
  avg_win: number | null
  avg_loss: number | null
  /** sum(wins) / |sum(losses)|. null when no losses. */
  profit_factor: number | null
  /** Cumulative realised P&L by day. Starts at 0 — NOT a balance. */
  curve: Array<{ t: string; pnl: number }>
}

export interface SalesBot {
  bot: LiveBot
  key: 'spark' | 'flame'
  name: string
  tagline: string
  /** 'live' = production account, 'paper' = simulated. Drives the badge. */
  mode: 'live' | 'paper'
  first_trade: string | null
  /** e.g. "3W" / "2L" — trailing run of same-sign trades. */
  streak: string | null
  allTime: Stats
  windows: { d7: Stats; d30: Stats }
}

export interface PublicTrade {
  date: string
  bot: LiveBot
  name: string
  key: 'spark' | 'flame'
  mode: 'live' | 'paper'
  structure: string | null
  credit: number | null
  outcome: string | null
  pnl: number
}

export interface TrackRecord {
  bots: SalesBot[]
  trades: PublicTrade[]
  generated_at: string
}

function ctDate(v: unknown): string {
  if (v instanceof Date) return v.toISOString().slice(0, 10)
  return v ? String(v).slice(0, 10) : ''
}
function r2(v: number): number {
  return Math.round(v * 100) / 100
}

interface Row {
  ms: number
  ct_date: string
  pnl: number
}

/** Reduce a set of closed trades (already window-filtered) to display stats. */
function statsOf(rows: Row[]): Stats {
  const trades = rows.length
  const winAmts = rows.filter((r) => r.pnl > 0).map((r) => r.pnl)
  const lossAmts = rows.filter((r) => r.pnl < 0).map((r) => r.pnl)
  const wins = winAmts.length
  const losses = lossAmts.length
  const sumWin = winAmts.reduce((a, b) => a + b, 0)
  const sumLoss = lossAmts.reduce((a, b) => a + b, 0)

  const byDay = new Map<string, number>()
  for (const r of rows) byDay.set(r.ct_date, (byDay.get(r.ct_date) ?? 0) + r.pnl)
  const dayKeys = Array.from(byDay.keys()).sort()
  let cum = 0
  let bestDay: number | null = null
  let worstDay: number | null = null
  let green = 0
  const curve = dayKeys.map((k) => {
    const d = r2(byDay.get(k) ?? 0)
    bestDay = bestDay === null || d > bestDay ? d : bestDay
    worstDay = worstDay === null || d < worstDay ? d : worstDay
    if (d > 0) green += 1
    cum = r2(cum + d)
    return { t: k, pnl: cum }
  })

  return {
    trades,
    wins,
    losses,
    win_rate: trades > 0 ? Math.round((wins / trades) * 1000) / 10 : null,
    net_pnl: r2(sumWin + sumLoss),
    best_trade: rows.length ? r2(Math.max(...rows.map((r) => r.pnl))) : null,
    worst_trade: rows.length ? r2(Math.min(...rows.map((r) => r.pnl))) : null,
    best_day: bestDay,
    worst_day: worstDay,
    green_days: green,
    total_days: dayKeys.length,
    avg_win: wins ? r2(sumWin / wins) : null,
    avg_loss: losses ? r2(sumLoss / losses) : null,
    profit_factor: sumLoss !== 0 ? Math.round((sumWin / Math.abs(sumLoss)) * 100) / 100 : null,
    curve,
  }
}

/** Trailing run of same-sign trades, most-recent first. "3W" / "2L". */
function streakOf(ordered: Row[]): string | null {
  if (!ordered.length) return null
  const last = ordered[ordered.length - 1]
  const sign = last.pnl > 0 ? 1 : last.pnl < 0 ? -1 : 0
  if (sign === 0) return null
  let n = 0
  for (let i = ordered.length - 1; i >= 0; i--) {
    const s = ordered[i].pnl > 0 ? 1 : ordered[i].pnl < 0 ? -1 : 0
    if (s === sign) n++
    else break
  }
  return `${n}${sign > 0 ? 'W' : 'L'}`
}

async function loadBot(bot: LiveBot): Promise<SalesBot> {
  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const closed =
    `status IN ('closed', 'expired') AND realized_pnl IS NOT NULL ${dteFilter} ${ledgerFilter(bot)}`

  // One fetch of every closed trade (spark ~106, flame ~57 — small). All-time and
  // both windows are derived from it, so the lifetime strip matches the legacy
  // /performance page exactly and the toggle needs no refetch.
  const rows = await dbQuery(
    `SELECT close_time,
            (close_time AT TIME ZONE 'America/Chicago')::date AS ct_date,
            realized_pnl
     FROM ${botTable(bot, 'positions')} WHERE ${closed}
     ORDER BY close_time ASC`,
  )
  const all: Row[] = rows
    .filter((r) => r.close_time)
    .map((r) => ({
      ms: new Date(String(r.close_time)).getTime(),
      ct_date: ctDate(r.ct_date),
      pnl: num(r.realized_pnl),
    }))

  const now = Date.now()
  const in30 = all.filter((r) => r.ms >= now - 30 * 864e5)
  const in7 = all.filter((r) => r.ms >= now - 7 * 864e5)

  return {
    bot,
    key: MASCOT_KEY[bot] ?? 'spark',
    name: DISPLAY_NAME[bot] ?? bot.toUpperCase(),
    tagline: LIVE_BOT_TAGLINE[bot],
    mode: resolveAccountMode(bot) === 'production' ? 'live' : 'paper',
    first_trade: all.length ? all[0].ct_date : null,
    streak: streakOf(all),
    allTime: statsOf(all),
    windows: { d7: statsOf(in7), d30: statsOf(in30) },
  }
}

/** "SPY 618/613p 628/633c" from the iron-condor strike columns. */
function structureOf(r: Record<string, unknown>): string | null {
  const ps = num(r.put_short_strike), pl = num(r.put_long_strike)
  const cs = num(r.call_short_strike), cl = num(r.call_long_strike)
  if (!ps && !cs) return null
  const ticker = r.ticker ? String(r.ticker) : 'SPY'
  const parts: string[] = []
  if (ps) parts.push(`${ps}/${pl}p`)
  if (cs) parts.push(`${cs}/${cl}c`)
  return `${ticker} ${parts.join(' ')}`.trim()
}

async function loadTrades(bot: LiveBot, limit: number): Promise<PublicTrade[]> {
  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const rows = await dbQuery(
    `SELECT close_time, ticker,
            put_short_strike, put_long_strike, call_short_strike, call_long_strike,
            total_credit, close_reason, realized_pnl
     FROM ${botTable(bot, 'positions')}
     WHERE status IN ('closed', 'expired') AND realized_pnl IS NOT NULL ${dteFilter} ${ledgerFilter(bot)}
     ORDER BY close_time DESC LIMIT ${limit}`,
  )
  const mode: 'live' | 'paper' = resolveAccountMode(bot) === 'production' ? 'live' : 'paper'
  return rows
    .filter((r) => r.close_time)
    .map((r) => ({
      date: ctDate(r.close_time),
      bot,
      name: DISPLAY_NAME[bot] ?? bot.toUpperCase(),
      key: MASCOT_KEY[bot] ?? 'spark',
      mode,
      structure: structureOf(r),
      credit: r.total_credit != null ? r2(num(r.total_credit)) : null,
      outcome: r.close_reason ? String(r.close_reason) : null,
      pnl: r2(num(r.realized_pnl)),
    }))
}

export async function getTrackRecord(tradeLimit = 16): Promise<TrackRecord> {
  const [bots, tradeLists] = await Promise.all([
    Promise.all(PUBLIC_BOTS.map(loadBot)),
    Promise.all(PUBLIC_BOTS.map((b) => loadTrades(b, tradeLimit))),
  ])
  const trades = tradeLists
    .flat()
    .sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0))
    .slice(0, tradeLimit)
  return { bots, trades, generated_at: new Date().toISOString() }
}
