import { dbQuery, botTable, num, int, escapeSql, dteMode } from '@/lib/db'
import { scopeFilter, type LiveBot } from './viewer'
import { LIVE_BOT_LABEL } from './bots'
import { classifyExitReason, type ExitReasonCode } from './exit-reasons'

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

async function loadBotTrades(
  bot: LiveBot,
  person: string | null,
  paper: boolean,
  isOperator = false,
): Promise<HistoryTrade[]> {
  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const scope = scopeFilter(bot, person, isOperator)
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
  isOperator = false,
): Promise<HistoryTrade[]> {
  const paperSet = new Set(paperBots)
  const perBot = await Promise.all(
    bots.map((b) => loadBotTrades(b, persons[b] ?? null, paperSet.has(b), isOperator)),
  )
  return perBot.flat().sort((a, b) => (a.close_date < b.close_date ? 1 : a.close_date > b.close_date ? -1 : 0))
}

// ---- Cursor pagination (APP-020) ----
//
// The old getCustomerTrades() above is left untouched — it is exercised
// directly by the tenant-isolation security suite and by
// account/trades/TradeHistoryClient.tsx — and still returns a full,
// unpaginated history. Everything below is additive: a second, paginated
// path that /api/live/trades now uses by default.

export interface TradeCursor {
  close_date: string
  id: string
}

/** Opaque page token: base64 of `close_date|id` — the sort key of the last
 *  row on a page, in the exact order the merge query produces. */
export function encodeTradeCursor(c: TradeCursor): string {
  return Buffer.from(`${c.close_date}|${c.id}`, 'utf8').toString('base64')
}

/** Never throws — a missing/tampered/malformed cursor decodes to null, which
 *  callers treat as "start from the newest row" rather than a 500. */
export function decodeTradeCursor(raw: string | null | undefined): TradeCursor | null {
  if (!raw) return null
  try {
    const decoded = Buffer.from(raw, 'base64').toString('utf8')
    const sep = decoded.indexOf('|')
    if (sep < 0) return null
    const close_date = decoded.slice(0, sep)
    const id = decoded.slice(sep + 1)
    return close_date && id ? { close_date, id } : null
  } catch {
    return null
  }
}

interface SortedRow {
  ct_date: string
  position_id: string
}

/**
 * Slice one page out of an array that is ALREADY in `ct_date DESC,
 * position_id DESC` order (the contract loadMergedRows' SQL guarantees via
 * `ORDER BY` on the UNION ALL of every bot's scoped rows). Pure and
 * DB-independent on purpose — the merge itself happens in SQL so a page can
 * never skip or duplicate a row across bots; this function only owns the
 * cursor math, which is what makes that guarantee unit-testable without a
 * live Postgres connection.
 */
export function paginateSorted<T extends SortedRow>(
  rows: T[],
  cursor: TradeCursor | null,
  limit: number,
): { page: T[]; next_cursor: string | null } {
  let from = 0
  if (cursor) {
    from = rows.findIndex(
      (r) => r.ct_date < cursor.close_date || (r.ct_date === cursor.close_date && r.position_id < cursor.id),
    )
    if (from === -1) from = rows.length
  }
  const page = rows.slice(from, from + limit)
  const last = page[page.length - 1]
  const next_cursor =
    last && from + limit < rows.length
      ? encodeTradeCursor({ close_date: last.ct_date, id: last.position_id })
      : null
  return { page, next_cursor }
}

export interface TradesPageFilters {
  limit?: number
  cursor?: string | null
  bot?: LiveBot | null
  days?: 30 | 90 | null
  q?: string | null
}

export interface TradesPage {
  trades: HistoryTrade[]
  next_cursor: string | null
  total: number
}

interface MergedRow {
  bot_key: string
  position_id: string
  ticker: unknown
  contracts: unknown
  total_credit: unknown
  realized_pnl: unknown
  close_reason: string | null
  open_time: unknown
  close_time: unknown
  ct_date: string
}

function toHistoryTrade(
  bot: LiveBot,
  r: {
    position_id: unknown
    ticker: unknown
    contracts: unknown
    total_credit: unknown
    realized_pnl: unknown
    close_reason: string | null
    open_time: unknown
    close_time: unknown
    ct_date: string
  },
  paper: boolean,
  startCap: number,
): HistoryTrade {
  const pnl = r2(num(r.realized_pnl))
  const o = outcomeOf(r.close_reason ? String(r.close_reason) : null)
  return {
    id: String(r.position_id),
    bot,
    strategy: LIVE_BOT_LABEL[bot] ?? bot.toUpperCase(),
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
}

/**
 * ONE SQL statement — a UNION ALL of every target bot's identically-scoped
 * SELECT, ordered by the exact key paginateSorted expects. Doing the merge
 * here (not by concatenating two JS arrays) is what makes cross-bot
 * pagination correct: two bots' closed-trade counts can differ, so a fixed
 * per-bot page size would eventually misalign which bot's next row is
 * "newest".
 */
async function loadMergedRows(
  bots: LiveBot[],
  persons: Record<string, string | null>,
  isOperator: boolean,
  filters: { bot: LiveBot | null; days: 30 | 90 | null; q: string | null },
): Promise<MergedRow[]> {
  const targetBots = filters.bot ? bots.filter((b) => b === filters.bot) : bots
  if (targetBots.length === 0) return []

  const subqueries = targetBots.map((bot) => {
    const dte = dteMode(bot)
    const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
    const scope = scopeFilter(bot, persons[bot] ?? null, isOperator)
    const daysFilter = filters.days ? `AND close_time >= NOW() - INTERVAL '${int(filters.days)} days'` : ''
    const label = LIVE_BOT_LABEL[bot] ?? bot.toUpperCase()
    const qFilter = filters.q
      ? `AND (ticker ILIKE '%${escapeSql(filters.q)}%' OR close_reason ILIKE '%${escapeSql(filters.q)}%' ` +
        `OR '${escapeSql(label)}' ILIKE '%${escapeSql(filters.q)}%' ` +
        `OR to_char((close_time AT TIME ZONE 'America/Chicago')::date, 'YYYY-MM-DD') ILIKE '%${escapeSql(filters.q)}%')`
      : ''
    return `SELECT '${bot}' AS bot_key, position_id, ticker, contracts, total_credit, realized_pnl, close_reason,
              open_time, close_time,
              to_char((close_time AT TIME ZONE 'America/Chicago')::date, 'YYYY-MM-DD') AS ct_date
            FROM ${botTable(bot, 'positions')}
            WHERE status IN ('closed', 'expired') AND realized_pnl IS NOT NULL ${dteFilter} ${scope} ${daysFilter} ${qFilter}`
  })

  const sql =
    subqueries.length === 1
      ? `${subqueries[0]} ORDER BY ct_date DESC, position_id DESC`
      : `SELECT * FROM (${subqueries.join(' UNION ALL ')}) merged ORDER BY ct_date DESC, position_id DESC`

  return dbQuery<MergedRow>(sql)
}

/** Starting capital per bot — needed for pnl_pct, kept as a second small
 *  query (one per target bot) rather than joined into the UNION so the
 *  merge query above stays a single homogeneous column set. */
async function loadStartCaps(
  bots: LiveBot[],
  persons: Record<string, string | null>,
  isOperator: boolean,
): Promise<Map<LiveBot, number>> {
  const entries = await Promise.all(
    bots.map(async (bot) => {
      const dte = dteMode(bot)
      const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
      const scope = scopeFilter(bot, persons[bot] ?? null, isOperator)
      const rows = await dbQuery<{ starting_capital: unknown }>(
        `SELECT starting_capital FROM ${botTable(bot, 'paper_account')}
         WHERE is_active = TRUE ${dteFilter} ${scope} ORDER BY id DESC LIMIT 1`,
      )
      return [bot, num(rows[0]?.starting_capital)] as const
    }),
  )
  return new Map(entries)
}

/**
 * Paginated, filterable trade history — GET /api/live/trades' primary path.
 * `total` counts every row matching the filters (pre-cursor), for the
 * mobile "X of TOTAL trades" line.
 */
export async function getCustomerTradesPage(
  bots: LiveBot[],
  persons: Record<string, string | null> = {},
  paperBots: LiveBot[] = [],
  isOperator = false,
  filters: TradesPageFilters = {},
): Promise<TradesPage> {
  const limit = Math.min(Math.max(1, int(filters.limit) || 50), 200)
  const botFilter = filters.bot && bots.includes(filters.bot) ? filters.bot : null
  const days = filters.days === 30 || filters.days === 90 ? filters.days : null
  const q = filters.q?.trim() || null

  const rawRows = await loadMergedRows(bots, persons, isOperator, { bot: botFilter, days, q })
  if (rawRows.length === 0) return { trades: [], next_cursor: null, total: 0 }

  const cursor = decodeTradeCursor(filters.cursor)
  const { page, next_cursor } = paginateSorted(rawRows, cursor, limit)

  const targetBots = botFilter ? [botFilter] : bots
  const paperSet = new Set(paperBots)
  const startCapByBot = await loadStartCaps(targetBots, persons, isOperator)

  const trades = page.map((r) => {
    const bot = r.bot_key as LiveBot
    return toHistoryTrade(bot, r, paperSet.has(bot), startCapByBot.get(bot) ?? 0)
  })

  return { trades, next_cursor, total: rawRows.length }
}

// ---- Trade detail (APP-019, APP-022) ----

export interface TradeLeg {
  side: 'buy' | 'sell'
  right: 'put' | 'call'
  strike: number
  expiry: string
  qty: number
}

export interface TradeLifecycleEntry {
  at_ct: string
  event: string
  note: string | null
}

export interface TradeDetail {
  legs: TradeLeg[] | null
  entry_at_ct: string | null
  credit: number | null
  buying_power_used: number | null
  current_pnl: number | null
  lifecycle: TradeLifecycleEntry[] | null
  exit_reason_code: ExitReasonCode | null
  exit_reason_text: string | null
  monitoring_message: string | null
}

export interface TradeDetailResponse {
  trade: HistoryTrade
  detail: TradeDetail
}

/** "Sep 3, 2:14 PM CT" — date+time, unlike ctTime()'s time-only label, for
 *  fields (entry time, lifecycle timestamps) that need to disambiguate day. */
function ctDateTime(v: unknown): string | null {
  if (!v) return null
  const d = new Date(String(v))
  if (isNaN(d.getTime())) return null
  const label = d.toLocaleString('en-US', {
    timeZone: 'America/Chicago',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
  return `${label} CT`
}

/** Every scanner-internal CLOSE_TRIGGER reason this codebase writes (see
 *  scanner.ts) mapped to a member-safe label. Unknown/future reasons fall
 *  through to a generic line rather than ever surfacing the raw keyword. */
const CLOSE_TRIGGER_LABELS: Record<string, string> = {
  PT: 'Profit target reached',
  STOP_LOSS: 'Stop loss triggered',
  EOD_CUTOFF: 'End-of-day close triggered',
  DATA_FEED_FAILURE: 'Data issue triggered a close',
  TRAILING_LOCKIN: 'Profit lock-in triggered',
}

/**
 * Turn one `{bot}_logs` row into a curated lifecycle label, or null if this
 * log level has no customer-facing meaning. The raw `message` column is
 * scanner shorthand (e.g. "PT_FIRED pos=... cost_to_close_last=0.4200") and
 * must never reach a customer — only the matched, fixed label may.
 */
export function classifyLifecycleEvent(level: string, message: string): string | null {
  switch (level) {
    case 'TRADE_OPEN':
      return 'Position opened'
    case 'TRADE_CLOSE':
      return 'Position closed'
    case 'SWING_HOLD':
      return 'Held open overnight'
    case 'CLOSE_TRIGGER': {
      const m = /^([A-Z_]+)_FIRED\b/.exec(message)
      const key = m?.[1] ?? ''
      return CLOSE_TRIGGER_LABELS[key] ?? 'Exit condition detected'
    }
    default:
      return null
  }
}

/**
 * ONE closed trade's full detail, scoped exactly like getCustomerTradesPage —
 * tries each bot the viewer owns in turn and returns the first match, so a
 * foreign or unknown id naturally falls through to null (the route maps
 * that to 404). `id` is user-controlled (a URL path segment) and is always
 * passed as a bound parameter, never interpolated.
 */
export async function getCustomerTradeDetail(
  id: string,
  bots: LiveBot[],
  persons: Record<string, string | null> = {},
  paperBots: LiveBot[] = [],
  isOperator = false,
): Promise<TradeDetailResponse | null> {
  const paperSet = new Set(paperBots)

  for (const bot of bots) {
    const dte = dteMode(bot)
    const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
    const scope = scopeFilter(bot, persons[bot] ?? null, isOperator)

    const rows = await dbQuery<{
      position_id: unknown
      ticker: unknown
      expiration: unknown
      put_short_strike: unknown
      put_long_strike: unknown
      call_short_strike: unknown
      call_long_strike: unknown
      contracts: unknown
      total_credit: unknown
      collateral_required: unknown
      realized_pnl: unknown
      close_reason: string | null
      open_time: unknown
      close_time: unknown
      ct_date: string
    }>(
      `SELECT position_id, ticker, expiration, put_short_strike, put_long_strike,
              call_short_strike, call_long_strike, contracts, total_credit,
              collateral_required, realized_pnl, close_reason, open_time, close_time,
              to_char((close_time AT TIME ZONE 'America/Chicago')::date, 'YYYY-MM-DD') AS ct_date
       FROM ${botTable(bot, 'positions')}
       WHERE position_id = $1 AND status IN ('closed', 'expired') AND realized_pnl IS NOT NULL ${dteFilter} ${scope}
       LIMIT 1`,
      [id],
    )
    const r = rows[0]
    if (!r) continue

    const startCapByBot = await loadStartCaps([bot], persons, isOperator)
    const trade = toHistoryTrade(bot, r, paperSet.has(bot), startCapByBot.get(bot) ?? 0)

    const expiration =
      (r.expiration as { toISOString?: () => string } | null)?.toISOString?.()?.slice(0, 10) ||
      (r.expiration ? String(r.expiration).slice(0, 10) : '')
    const { put_short_strike: ps, put_long_strike: pl, call_short_strike: cs, call_long_strike: cl } = r
    const legs: TradeLeg[] | null =
      ps != null && pl != null && cs != null && cl != null
        ? [
            { side: 'buy', right: 'put', strike: num(pl), expiry: expiration, qty: int(r.contracts) },
            { side: 'sell', right: 'put', strike: num(ps), expiry: expiration, qty: int(r.contracts) },
            { side: 'sell', right: 'call', strike: num(cs), expiry: expiration, qty: int(r.contracts) },
            { side: 'buy', right: 'call', strike: num(cl), expiry: expiration, qty: int(r.contracts) },
          ]
        : null

    const logRows = await dbQuery<{ log_time: unknown; level: string | null; message: string | null }>(
      `SELECT log_time, level, message
       FROM ${botTable(bot, 'logs')}
       WHERE message LIKE '%' || $1 || '%' ${dteFilter}
       ORDER BY log_time ASC
       LIMIT 30`,
      [id],
    )
    const lifecycleEntries: TradeLifecycleEntry[] = []
    for (const lr of logRows) {
      const event = classifyLifecycleEvent(String(lr.level ?? ''), String(lr.message ?? ''))
      const at = ctDateTime(lr.log_time)
      if (event && at) lifecycleEntries.push({ at_ct: at, event, note: null })
    }

    const exit = classifyExitReason(r.close_reason)

    return {
      trade,
      detail: {
        legs,
        entry_at_ct: ctDateTime(r.open_time),
        credit: r.total_credit != null ? r2(num(r.total_credit)) : null,
        buying_power_used: r.collateral_required != null ? r2(num(r.collateral_required)) : null,
        current_pnl: r.realized_pnl != null ? r2(num(r.realized_pnl)) : null,
        lifecycle: lifecycleEntries.length > 0 ? lifecycleEntries : null,
        exit_reason_code: exit.code,
        exit_reason_text: exit.text,
        // No per-position "latest monitoring message" is ever persisted — the
        // Live page's check_line is a computed-today string for the OPEN
        // position state machine (state.ts), not a column on this closed
        // row, so there is nothing here to source it from.
        monitoring_message: null,
      },
    }
  }

  return null
}
