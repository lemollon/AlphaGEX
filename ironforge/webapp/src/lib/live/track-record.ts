import { dbQuery, botTable, num, int, escapeSql, dteMode } from '@/lib/db'
import { ledgerFilter, resolveAccountMode } from './viewer'
import { LIVE_BOT_LABEL, LIVE_BOT_ACCENT, LIVE_BOT_TAGLINE, type LiveBot } from './bots'

/**
 * PUBLIC track record — the proof surface shown to prospects who have no account.
 *
 * Deliberately narrower than lib/live/performance.ts, which is the signed-in
 * customer's OWN combined history. This module must never expose:
 *   - a live account balance (only realised P&L on closed trades)
 *   - open positions or any control
 *   - any per-customer state
 *
 * It reads the same ledger the customer pages read, via ledgerFilter(), so the
 * public number and the in-app number can never disagree for the same bot.
 *
 * Honest-data rule: every card carries its real mode (`paper` true/false) so a
 * simulated record is never presented as a live one. SPARK is real money today;
 * FLAME is paper. Rendering them side by side without that label would be a
 * performance claim we cannot stand behind.
 */

/** Bots shown publicly. SPARK2 is a migration twin of SPARK (two near-identical
 *  curves confuse more than they prove) and INFERNO is not a customer product. */
export const PUBLIC_BOTS: readonly LiveBot[] = ['spark', 'flame'] as const

export interface PublicBotRecord {
  bot: LiveBot
  label: string
  tagline: string
  accent: 'spark' | 'flame'
  /** true = simulated money. Drives the badge; never omit it in the UI. */
  paper: boolean
  total_pnl: number
  win_rate: number | null
  trades: number
  worst_day: number | null
  best_day: number | null
  max_drawdown: number | null
  first_trade: string | null
  /** Cumulative realised P&L over time. Starts at 0 — NOT an account balance. */
  curve: Array<{ t: string; pnl: number }>
}

export interface PublicTrade {
  date: string
  bot: LiveBot
  label: string
  paper: boolean
  structure: string | null
  credit: number | null
  outcome: string | null
  pnl: number
}

export interface TrackRecord {
  bots: PublicBotRecord[]
  trades: PublicTrade[]
  generated_at: string
}

function ctDate(v: unknown): string {
  if (v instanceof Date) return v.toISOString().slice(0, 10)
  return v ? String(v).slice(0, 10) : ''
}

/** "SPY 618p/613p 628c/633c" from whichever strike columns are populated. */
function structureOf(r: Record<string, unknown>): string | null {
  const sp = num(r.short_put), lp = num(r.long_put)
  const sc = num(r.short_call), lc = num(r.long_call)
  if (!sp && !sc) return null
  const ticker = r.ticker ? String(r.ticker) : 'SPY'
  const parts: string[] = []
  if (sp) parts.push(`${sp}p/${lp || ''}p`)
  if (sc) parts.push(`${sc}c/${lc || ''}c`)
  return `${ticker} ${parts.join(' ')}`.trim()
}

async function loadBot(bot: LiveBot): Promise<PublicBotRecord> {
  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const closed =
    `status IN ('closed', 'expired') AND realized_pnl IS NOT NULL ` +
    `${dteFilter} ${ledgerFilter(bot)}`

  const [statRows, dayRows] = await Promise.all([
    dbQuery(
      `SELECT COUNT(*) AS trades,
              COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
              COALESCE(SUM(realized_pnl), 0) AS pnl,
              MIN(close_time) AS first_trade
       FROM ${botTable(bot, 'positions')} WHERE ${closed}`,
    ),
    dbQuery(
      `SELECT (close_time AT TIME ZONE 'America/Chicago')::date AS ct_date,
              SUM(realized_pnl) AS day_pnl
       FROM ${botTable(bot, 'positions')} WHERE ${closed}
       GROUP BY 1 ORDER BY 1 ASC`,
    ),
  ])

  const trades = int(statRows[0]?.trades)
  const wins = int(statRows[0]?.wins)
  const pnl = Math.round(num(statRows[0]?.pnl) * 100) / 100

  // Cumulative curve + peak-to-trough drawdown on realised P&L.
  let cum = 0
  let peak = 0
  let maxDd: number | null = null
  let worst: number | null = null
  let best: number | null = null
  const curve = dayRows.map((r) => {
    const d = Math.round(num(r.day_pnl) * 100) / 100
    worst = worst === null || d < worst ? d : worst
    best = best === null || d > best ? d : best
    cum = Math.round((cum + d) * 100) / 100
    peak = Math.max(peak, cum)
    const dd = Math.round((cum - peak) * 100) / 100
    maxDd = maxDd === null || dd < maxDd ? dd : maxDd
    return { t: ctDate(r.ct_date), pnl: cum }
  })

  return {
    bot,
    label: LIVE_BOT_LABEL[bot],
    tagline: LIVE_BOT_TAGLINE[bot],
    accent: LIVE_BOT_ACCENT[bot],
    paper: resolveAccountMode(bot) === 'paper',
    total_pnl: pnl,
    win_rate: trades > 0 ? Math.round((wins / trades) * 1000) / 10 : null,
    trades,
    worst_day: worst,
    best_day: best,
    max_drawdown: maxDd,
    first_trade: statRows[0]?.first_trade ? ctDate(statRows[0].first_trade) : null,
    curve,
  }
}

async function loadTrades(bot: LiveBot, limit: number): Promise<PublicTrade[]> {
  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const rows = await dbQuery(
    `SELECT close_time, ticker, short_put, long_put, short_call, long_call,
            net_credit, close_reason, realized_pnl
     FROM ${botTable(bot, 'positions')}
     WHERE status IN ('closed', 'expired') AND realized_pnl IS NOT NULL
       ${dteFilter} ${ledgerFilter(bot)}
     ORDER BY close_time DESC LIMIT ${limit}`,
  )
  const paper = resolveAccountMode(bot) === 'paper'
  return rows
    .filter((r) => r.close_time)
    .map((r) => ({
      date: ctDate(r.close_time),
      bot,
      label: LIVE_BOT_LABEL[bot],
      paper,
      structure: structureOf(r),
      credit: r.net_credit != null ? Math.round(num(r.net_credit) * 100) / 100 : null,
      outcome: r.close_reason ? String(r.close_reason) : null,
      pnl: Math.round(num(r.realized_pnl) * 100) / 100,
    }))
}

export async function getTrackRecord(limit = 25): Promise<TrackRecord> {
  const [bots, tradeLists] = await Promise.all([
    Promise.all(PUBLIC_BOTS.map(loadBot)),
    Promise.all(PUBLIC_BOTS.map((b) => loadTrades(b, limit))),
  ])
  const trades = tradeLists
    .flat()
    .sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0))
    .slice(0, limit)
  return { bots, trades, generated_at: new Date().toISOString() }
}
