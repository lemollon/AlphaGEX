import { dbQuery, botTable, num, int, escapeSql, dteMode } from '@/lib/db'
import { scopeFilter, type LiveBot } from './viewer'
import { LIVE_BOT_LABEL } from './bots'

/**
 * Customer Trade History — the viewer's own CLOSED trades across every strategy
 * they own, scoped through the same ledgerFilter the Live/Performance/Home pages
 * use so the money reconciles across pages. Read-only; realised P&L only, never
 * an open position or a live balance.
 *
 * "Strategy" is deliberately just the bot name (Spark / Flame) per operator —
 * the structure (Iron Condor, etc.) is not shown.
 */

export type OutcomeKind = 'profit' | 'auto' | 'stop' | 'manual' | 'expired' | 'other'

export interface HistoryTrade {
  id: string
  bot: LiveBot
  strategy: string          // bot label only, e.g. "Spark"
  paper: boolean
  underlying: string        // "SPY"
  close_date: string        // YYYY-MM-DD (CT)
  opened_ct: string | null  // "9:48 AM"
  closed_ct: string | null  // "1:42 PM"
  contracts: number
  credit: number | null
  pnl: number
  pnl_pct: number | null    // vs the strategy's starting capital
  outcome: string           // display label
  outcome_kind: OutcomeKind
}

/** Map a raw close_reason to a customer-facing outcome label + kind. */
function outcomeOf(reason: string | null): { label: string; kind: OutcomeKind } {
  const r = (reason ?? '').toLowerCase()
  if (r.startsWith('profit_target')) return { label: 'Profit Target', kind: 'profit' }
  if (r.includes('stop_loss')) return { label: 'Stop Loss', kind: 'stop' }
  if (r.includes('manual') || r.includes('force')) return { label: 'Manual Close', kind: 'manual' }
  if (r.includes('expired')) return { label: 'Expired', kind: 'expired' }
  // eod_cutoff, swing_green_bank, trailing_lockin, broker_*/reconcile* — the
  // system closed it without a manual action.
  if (r) return { label: 'Auto Close', kind: 'auto' }
  return { label: '—', kind: 'other' }
}

function ctTime(v: unknown): string | null {
  if (!v) return null
  const d = new Date(String(v))
  if (isNaN(d.getTime())) return null
  return d.toLocaleTimeString('en-US', { timeZone: 'America/Chicago', hour: 'numeric', minute: '2-digit' })
}
/**
 * Normalise a Postgres date to ISO `YYYY-MM-DD`. The pg driver parses `date` columns into JS Date
 * objects, and `String(date)` is "Wed May 27 2026 …" — slicing that gave "Wed May 27", which is not
 * parseable client-side, so the time filter and chronological sort silently broke. Handle both a
 * Date object (use its local Y/M/D — pg parses a bare date to local midnight) and an ISO string.
 */
function ctDate(v: unknown): string {
  if (!v) return ''
  if (v instanceof Date) {
    if (isNaN(v.getTime())) return ''
    const y = v.getFullYear()
    const m = String(v.getMonth() + 1).padStart(2, '0')
    const d = String(v.getDate()).padStart(2, '0')
    return `${y}-${m}-${d}`
  }
  return String(v).slice(0, 10)
}
const r2 = (v: number) => Math.round(v * 100) / 100

async function loadBotTrades(bot: LiveBot, person: string | null, paper: boolean): Promise<HistoryTrade[]> {
  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const scope = scopeFilter(bot, person)
  const closed = `status IN ('closed', 'expired') AND realized_pnl IS NOT NULL ${dteFilter} ${scope}`

  const [rows, capRows] = await Promise.all([
    dbQuery(
      `SELECT position_id, ticker, contracts, total_credit, realized_pnl, close_reason,
              open_time, close_time,
              to_char((close_time AT TIME ZONE 'America/Chicago')::date, 'YYYY-MM-DD') AS ct_date
       FROM ${botTable(bot, 'positions')}
       WHERE ${closed}
       ORDER BY close_time DESC
       LIMIT 300`,
    ),
    dbQuery(
      `SELECT starting_capital FROM ${botTable(bot, 'paper_account')}
       WHERE is_active = TRUE ${dteFilter} ${scope} ORDER BY id DESC LIMIT 1`,
    ),
  ])
  const startCap = num(capRows[0]?.starting_capital)
  const label = LIVE_BOT_LABEL[bot] ?? bot.toUpperCase()

  return rows
    .filter((r) => r.close_time)
    .map((r): HistoryTrade => {
      const pnl = r2(num(r.realized_pnl))
      const o = outcomeOf(r.close_reason ? String(r.close_reason) : null)
      return {
        id: String(r.position_id),
        bot,
        strategy: label,
        paper,
        underlying: r.ticker ? String(r.ticker) : 'SPY',
        close_date: ctDate(r.ct_date),
        opened_ct: ctTime(r.open_time),
        closed_ct: ctTime(r.close_time),
        contracts: int(r.contracts),
        credit: r.total_credit != null ? r2(num(r.total_credit)) : null,
        pnl,
        pnl_pct: startCap > 0 ? Math.round((pnl / startCap) * 10000) / 100 : null,
        outcome: o.label,
        outcome_kind: o.kind,
      }
    })
}

export async function getCustomerTrades(
  bots: LiveBot[],
  persons: Record<string, string | null> = {},
  paperBots: LiveBot[] = [],
): Promise<HistoryTrade[]> {
  const paperSet = new Set(paperBots)
  const perBot = await Promise.all(
    bots.map((b) => loadBotTrades(b, persons[b] ?? null, paperSet.has(b))),
  )
  return perBot.flat().sort((a, b) => (a.close_date < b.close_date ? 1 : a.close_date > b.close_date ? -1 : 0))
}
