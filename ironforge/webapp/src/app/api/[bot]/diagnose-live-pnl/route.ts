/**
 * SPARK Live-PnL Reconciliation
 *
 *   GET  /api/spark/diagnose-live-pnl   — read-only audit of DB ledger vs Tradier
 *   POST /api/spark/diagnose-live-pnl   — applies reconciliation
 *
 * Why this exists
 * ---------------
 * The SPARK live-trading dashboard derives "Total Trades", "Realized Today",
 * and "Cumulative P&L" from the spark_positions table (account_type='production').
 * If the scanner misses a Tradier fill — order placed but the position INSERT
 * failed, scanner restart between fill and recording, broker_position_gone
 * recovery picking up another bot's fill, etc. — the DB undercounts and the
 * UI numbers go wrong even though the broker is fine.
 *
 * This endpoint compares the Tradier production account (Logan, account_id
 * 6YB71371 today) to spark_positions and surfaces every divergence:
 *   - Tradier filled orders the DB has no row for           (missing_in_db)
 *   - DB rows status='open' that Tradier has no leg for     (extra_in_db)
 *   - Closed DB rows whose realized_pnl disagrees with the
 *     Tradier close fill                                    (pnl_mismatch)
 *
 * Hard rules
 * ----------
 * 1. SPARK-only. Other bots return 400 — the production account is shared
 *    between SPARK and INFERNO via the ironforge_accounts row, but only SPARK
 *    is the production bot per `PRODUCTION_BOT` in lib/tradier.ts.
 * 2. account_type='production' is hard-filtered everywhere. Sandbox rows are
 *    never read or written.
 * 3. INFERNO orders on the same Tradier account are filtered out by leg
 *    expiration (SPARK = expiration > order date, INFERNO = expiration == order
 *    date). Without this filter we'd mis-attribute INFERNO fills to SPARK.
 * 4. POST never deletes a row. It only INSERTs missing positions and UPDATEs
 *    status='open' → status='closed' on rows whose legs the broker no longer
 *    holds, with realized_pnl computed from the actual Tradier exit fill.
 * 5. POST writes a spark_logs row with level='RECONCILE' for every change so
 *    the audit trail is queryable later.
 * 6. POST is idempotent: re-inserts use a deterministic position_id and
 *    ON CONFLICT DO NOTHING; status updates only fire on rows still 'open'.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, num, int, validateBot, CT_TODAY } from '@/lib/db'
import {
  buildOccSymbol,
  isConfigured,
  getProductionAccountsForBot,
  getTradierBalanceDetail,
  getTradierOrders,
  getSandboxAccountPositions,
  PRODUCTION_BOT,
  TradierOrder,
  TradierOrderLeg,
  ProductionAccount,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

// Tradier filled-order lookback for matching against the DB ledger. Ironforge
// scanner ran for SPARK production roughly since mid-April 2026, and the
// production account today (Logan) has a small order volume per day, so a 30d
// window covers every active row and stays well under Tradier's order-history
// page limit. Bump if the spark_positions production set ever ages out beyond
// this window.
const LOOKBACK_DAYS = 30
const LOOKBACK_MS = LOOKBACK_DAYS * 24 * 60 * 60 * 1000

interface ParsedOcc {
  ticker: string
  expiration: string // YYYY-MM-DD
  type: 'P' | 'C'
  strike: number
}

function parseOccSymbol(occ: string): ParsedOcc | null {
  const m = occ.match(/^([A-Z]+)(\d{2})(\d{2})(\d{2})([PC])(\d{8})$/)
  if (!m) return null
  const [, ticker, yy, mm, dd, type, strikeStr] = m
  return {
    ticker,
    expiration: `20${yy}-${mm}-${dd}`,
    type: type as 'P' | 'C',
    strike: parseInt(strikeStr, 10) / 1000,
  }
}

interface ClassifiedOrder {
  kind: 'open' | 'close' | 'unknown'
  ticker: string | null
  expiration: string | null
  strikes: {
    putLong: number
    putShort: number
    callShort: number
    callLong: number
  } | null
  contracts: number | null
  net_price: number | null // per-share, signed (open = credit positive, close = debit positive)
  errors: string[]
}

/**
 * Classify a Tradier order as IC open / close, extract strikes + expiration,
 * and compute the per-share net price from leg fills.
 *
 * For an open IC: 2x sell_to_open + 2x buy_to_open. Net credit (per share) =
 *   short_put_fill + short_call_fill - long_put_fill - long_call_fill
 * For a close IC: 2x buy_to_close + 2x sell_to_close. Net debit (per share) =
 *   long_put_fill + long_call_fill - short_put_fill - short_call_fill
 *
 * We return abs() of the net so both kinds report a positive per-share number.
 */
function classifyIcOrder(legs: TradierOrderLeg[], orderQty: number | null): ClassifiedOrder {
  const errors: string[] = []
  if (legs.length !== 4) {
    return {
      kind: 'unknown',
      ticker: null,
      expiration: null,
      strikes: null,
      contracts: null,
      net_price: null,
      errors: [`expected 4 legs, got ${legs.length}`],
    }
  }
  const parsed = legs.map(l => ({
    leg: l,
    p: l.option_symbol ? parseOccSymbol(l.option_symbol) : null,
  }))
  if (parsed.some(p => !p.p)) {
    errors.push('one or more leg OCC symbols failed to parse')
    return {
      kind: 'unknown',
      ticker: null,
      expiration: null,
      strikes: null,
      contracts: null,
      net_price: null,
      errors,
    }
  }
  const tickers = new Set(parsed.map(p => p.p!.ticker))
  const exps = new Set(parsed.map(p => p.p!.expiration))
  if (tickers.size !== 1) errors.push(`mixed tickers: ${Array.from(tickers).join(',')}`)
  if (exps.size !== 1) errors.push(`mixed expirations: ${Array.from(exps).join(',')}`)
  if (errors.length > 0) {
    return {
      kind: 'unknown',
      ticker: null,
      expiration: null,
      strikes: null,
      contracts: null,
      net_price: null,
      errors,
    }
  }

  const puts = parsed.filter(p => p.p!.type === 'P').sort((a, b) => a.p!.strike - b.p!.strike)
  const calls = parsed.filter(p => p.p!.type === 'C').sort((a, b) => a.p!.strike - b.p!.strike)
  if (puts.length !== 2 || calls.length !== 2) {
    errors.push(`not an IC: ${puts.length} puts, ${calls.length} calls`)
    return {
      kind: 'unknown',
      ticker: null,
      expiration: null,
      strikes: null,
      contracts: null,
      net_price: null,
      errors,
    }
  }

  const strikes = {
    putLong: puts[0].p!.strike,
    putShort: puts[1].p!.strike,
    callShort: calls[0].p!.strike,
    callLong: calls[1].p!.strike,
  }

  const sides = parsed.map(p => (p.leg.side || '').toLowerCase())
  const opens = sides.filter(s => s.includes('open')).length
  const closes = sides.filter(s => s.includes('close')).length
  let kind: 'open' | 'close' | 'unknown' = 'unknown'
  if (opens === 4) kind = 'open'
  else if (closes === 4) kind = 'close'

  // Per-leg contracts (Tradier reports each leg's qty separately; for an IC
  // every leg should match). Use the first non-null leg quantity, fall back
  // to the parent order qty.
  const legQtys = legs.map(l => l.exec_quantity ?? l.quantity).filter((q): q is number => q != null)
  const contracts = legQtys.length > 0 ? Math.max(...legQtys.map(Math.abs)) : (orderQty != null ? Math.abs(orderQty) : null)

  // Net per-share. Sell legs add to net; buy legs subtract. abs() so both
  // open (net credit) and close (net debit) report positive numbers.
  let signedNet = 0
  let allHaveFills = true
  for (const p of parsed) {
    const fp = p.leg.last_fill_price
    if (fp == null) { allHaveFills = false; break }
    const side = (p.leg.side || '').toLowerCase()
    if (side.includes('sell')) signedNet += fp
    else if (side.includes('buy')) signedNet -= fp
    else { allHaveFills = false; break }
  }
  const net_price = allHaveFills ? Math.round(Math.abs(signedNet) * 10000) / 10000 : null

  return { kind, ticker: parsed[0].p!.ticker, expiration: parsed[0].p!.expiration, strikes, contracts, net_price, errors }
}

interface DbProdRow {
  position_id: string
  status: string
  person: string
  contracts: number
  total_credit: number
  spread_width: number
  realized_pnl: number | null
  close_reason: string | null
  open_time: string
  close_time: string | null
  open_date: string | null
  expiration: string
  put_short_strike: number
  put_long_strike: number
  call_short_strike: number
  call_long_strike: number
  sandbox_order_id: string | null
  sandbox_close_order_id: string | null
  open_order_id: number | null
  close_order_id: number | null
}

function extractOrderId(jsonStr: string | null): number | null {
  if (!jsonStr) return null
  try {
    const parsed = JSON.parse(jsonStr) as Record<string, { order_id?: number | string | null }>
    for (const v of Object.values(parsed)) {
      const id = v?.order_id
      if (id == null) continue
      const n = typeof id === 'number' ? id : parseInt(String(id), 10)
      if (Number.isFinite(n)) return n
    }
  } catch { /* not JSON or unexpected shape */ }
  return null
}

async function fetchProdLedgerRows(): Promise<DbProdRow[]> {
  const rows = await dbQuery(
    `SELECT position_id, status, person, contracts, total_credit, spread_width,
            realized_pnl, close_reason,
            open_time, close_time, open_date, expiration,
            put_short_strike, put_long_strike, call_short_strike, call_long_strike,
            sandbox_order_id, sandbox_close_order_id
     FROM spark_positions
     WHERE account_type = 'production'
       AND COALESCE(open_time, NOW()) >= NOW() - INTERVAL '${LOOKBACK_DAYS} days'
     ORDER BY open_time DESC`,
  )
  return rows.map((r: any): DbProdRow => {
    const expIso = r.expiration instanceof Date
      ? r.expiration.toISOString().slice(0, 10)
      : String(r.expiration ?? '').slice(0, 10)
    return {
      position_id: String(r.position_id),
      status: String(r.status ?? 'unknown'),
      person: String(r.person ?? ''),
      contracts: int(r.contracts),
      total_credit: num(r.total_credit),
      spread_width: num(r.spread_width),
      realized_pnl: r.realized_pnl == null ? null : num(r.realized_pnl),
      close_reason: r.close_reason ?? null,
      open_time: r.open_time instanceof Date ? r.open_time.toISOString() : (r.open_time != null ? String(r.open_time) : ''),
      close_time: r.close_time instanceof Date ? r.close_time.toISOString() : (r.close_time != null ? String(r.close_time) : null),
      open_date: r.open_date instanceof Date ? r.open_date.toISOString().slice(0, 10) : (r.open_date != null ? String(r.open_date).slice(0, 10) : null),
      expiration: expIso,
      put_short_strike: num(r.put_short_strike),
      put_long_strike: num(r.put_long_strike),
      call_short_strike: num(r.call_short_strike),
      call_long_strike: num(r.call_long_strike),
      sandbox_order_id: r.sandbox_order_id ?? null,
      sandbox_close_order_id: r.sandbox_close_order_id ?? null,
      open_order_id: extractOrderId(r.sandbox_order_id ?? null),
      close_order_id: extractOrderId(r.sandbox_close_order_id ?? null),
    }
  })
}

interface AccountReport {
  person: string
  account_id: string | null
  account_loaded: boolean
  tradier_balance: {
    total_equity: number | null
    option_buying_power: number | null
    open_pl: number | null
    close_pl: number | null
  } | null
  tradier_orders: {
    filled_total_lookback: number
    filled_today: number
    spark_filled_total_lookback: number
    spark_filled_today: number
    inferno_filled_total_lookback: number
    open_orders_total: number
  }
  tradier_open_legs: {
    total_legs: number
    by_expiration: Record<string, number>
    spark_open_legs_estimate: number
  }
  db_ledger: {
    rows_lookback: number
    open_rows: number
    rows_opened_today: number
    rows_closed_today: number
    today_realized_pnl_usd: number
    alltime_realized_pnl_usd: number
  }
  mismatches: Mismatch[]
}

type Mismatch =
  | {
      kind: 'missing_in_db'
      tradier_order_id: number | string
      transaction_date: string | null
      ic_kind: 'open' | 'close' | 'unknown'
      strikes: { putLong: number; putShort: number; callShort: number; callLong: number } | null
      expiration: string | null
      contracts: number | null
      net_price_per_share: number | null
      proposed_position_id: string
      proposed_action: 'insert' | 'attach_close' | 'manual_review'
      attach_to_position_id?: string
      reasoning: string
    }
  | {
      kind: 'extra_in_db'
      db_position_id: string
      person: string
      expiration: string
      strikes: { putLong: number; putShort: number; callShort: number; callLong: number }
      contracts: number
      total_credit: number
      proposed_action: 'mark_closed' | 'manual_review'
      proposed_close_price: number | null
      proposed_realized_pnl: number | null
      matched_close_order_id: number | null
      reasoning: string
    }
  | {
      kind: 'pnl_mismatch'
      db_position_id: string
      db_realized_pnl: number
      expected_realized_pnl: number
      diff_usd: number
      matched_close_order_id: number | null
      reasoning: string
    }

interface DiagnosticReport {
  bot: 'SPARK'
  generated_at: string
  ct_today: string
  account_type: 'production'
  tradier_connected: boolean
  lookback_days: number
  accounts: AccountReport[]
  totals: {
    accounts_inspected: number
    total_mismatches: number
    missing_in_db: number
    extra_in_db: number
    pnl_mismatch: number
  }
  summary: string
}

/**
 * Build the diagnostic report for one production account. Pulls Tradier
 * balances, filled orders (lookback window), open positions; pulls the DB's
 * production rows for the same person; cross-references both directions and
 * emits Mismatch entries.
 */
async function buildAccountReport(
  account: ProductionAccount,
  ledgerRows: DbProdRow[],
  ctTodayStr: string,
  ctNowMs: number,
): Promise<AccountReport> {
  const personRows = ledgerRows.filter(r => r.person === account.name)

  // Account is configured but Tradier returned no accountId — skip Tradier
  // calls so we don't hard-fail the route. The DB-side numbers still render.
  if (!account.accountId) {
    return {
      person: account.name,
      account_id: null,
      account_loaded: false,
      tradier_balance: null,
      tradier_orders: {
        filled_total_lookback: 0,
        filled_today: 0,
        spark_filled_total_lookback: 0,
        spark_filled_today: 0,
        inferno_filled_total_lookback: 0,
        open_orders_total: 0,
      },
      tradier_open_legs: { total_legs: 0, by_expiration: {}, spark_open_legs_estimate: 0 },
      db_ledger: dbLedgerStats(personRows, ctTodayStr),
      mismatches: [{
        kind: 'missing_in_db',
        tradier_order_id: 'n/a',
        transaction_date: null,
        ic_kind: 'unknown',
        strikes: null,
        expiration: null,
        contracts: null,
        net_price_per_share: null,
        proposed_position_id: '',
        proposed_action: 'manual_review',
        reasoning: `Tradier accountId for ${account.name} did not resolve — cannot fetch broker state. Check ironforge_accounts.account_id and Tradier API key validity (use /api/spark/diagnose-production).`,
      }],
    }
  }

  // ── Tradier balance ──────────────────────────────────────────────────
  const balance = await getTradierBalanceDetail(account.apiKey, account.accountId, account.baseUrl)
  const tradierBalance = balance ? {
    total_equity: balance.total_equity,
    option_buying_power: balance.option_buying_power,
    open_pl: balance.open_pl,
    close_pl: balance.close_pl,
  } : null

  // ── Tradier filled orders (lookback) + open orders ───────────────────
  let allFilled: TradierOrder[] = []
  let allOpen: TradierOrder[] = []
  try {
    allFilled = await getTradierOrders(account.apiKey, account.accountId, account.baseUrl, 'filled')
  } catch { /* leave empty */ }
  try {
    allOpen = await getTradierOrders(account.apiKey, account.accountId, account.baseUrl, 'open')
  } catch { /* leave empty */ }

  const cutoffMs = ctNowMs - LOOKBACK_MS
  const filledRecent = allFilled.filter(o => {
    const ts = o.transaction_date ? Date.parse(o.transaction_date) : NaN
    return Number.isFinite(ts) && ts >= cutoffMs
  })

  // Classify each filled order. Determine SPARK vs INFERNO by leg expiration:
  // SPARK = expiration > order date, INFERNO = expiration == order date.
  const classified: Array<{
    order: TradierOrder
    classification: ClassifiedOrder
    bot_inferred: 'spark' | 'inferno' | 'unknown'
    tx_ct_date: string | null
  }> = filledRecent.map(o => {
    const c = classifyIcOrder(o.legs, o.quantity)
    const txTs = o.transaction_date ? Date.parse(o.transaction_date) : NaN
    const txCtDate = Number.isFinite(txTs) ? ctDateString(new Date(txTs)) : null
    let botInferred: 'spark' | 'inferno' | 'unknown' = 'unknown'
    if (c.expiration && txCtDate) {
      if (c.expiration > txCtDate) botInferred = 'spark'
      else if (c.expiration === txCtDate) botInferred = 'inferno'
    }
    return { order: o, classification: c, bot_inferred: botInferred, tx_ct_date: txCtDate }
  })

  const sparkClassified = classified.filter(c => c.bot_inferred === 'spark' && c.classification.kind !== 'unknown')
  const filledTodayCount = classified.filter(c => c.tx_ct_date === ctTodayStr).length
  const sparkFilledTodayCount = sparkClassified.filter(c => c.tx_ct_date === ctTodayStr).length
  const infernoFilledCount = classified.filter(c => c.bot_inferred === 'inferno').length

  // ── Tradier open legs ────────────────────────────────────────────────
  let openPositions: Array<{ symbol: string; quantity: number; cost_basis: number; market_value: number; gain_loss: number }> = []
  try {
    openPositions = await getSandboxAccountPositions(account.apiKey, undefined, account.baseUrl)
  } catch { /* leave empty */ }
  const nonZeroLegs = openPositions.filter(p => p.quantity !== 0)
  const legsByExp: Record<string, number> = {}
  let sparkOpenLegsEstimate = 0
  for (const p of nonZeroLegs) {
    const parsed = parseOccSymbol(p.symbol)
    if (!parsed) continue
    legsByExp[parsed.expiration] = (legsByExp[parsed.expiration] ?? 0) + 1
    if (parsed.expiration > ctTodayStr) sparkOpenLegsEstimate++
  }

  // ── Match Tradier orders against DB rows ─────────────────────────────
  // Build lookup maps from DB.
  const dbByOpenOrderId = new Map<number, DbProdRow>()
  const dbByCloseOrderId = new Map<number, DbProdRow>()
  for (const row of personRows) {
    if (row.open_order_id != null) dbByOpenOrderId.set(row.open_order_id, row)
    if (row.close_order_id != null) dbByCloseOrderId.set(row.close_order_id, row)
  }

  const mismatches: Mismatch[] = []

  // Pass 1: Tradier orders with no matching DB row (missing_in_db).
  for (const c of sparkClassified) {
    const orderIdNum = typeof c.order.id === 'number' ? c.order.id : parseInt(String(c.order.id), 10)
    if (!Number.isFinite(orderIdNum)) continue

    if (c.classification.kind === 'open' && !dbByOpenOrderId.has(orderIdNum)) {
      // Untracked OPEN fill — propose to insert a new spark_positions row.
      const proposedPosId = `SPARK-RECON-${orderIdNum}-prod-${account.name.toLowerCase().replace(/[^a-z0-9]/g, '')}`
      mismatches.push({
        kind: 'missing_in_db',
        tradier_order_id: orderIdNum,
        transaction_date: c.order.transaction_date,
        ic_kind: 'open',
        strikes: c.classification.strikes,
        expiration: c.classification.expiration,
        contracts: c.classification.contracts,
        net_price_per_share: c.classification.net_price,
        proposed_position_id: proposedPosId,
        proposed_action: c.classification.strikes && c.classification.contracts && c.classification.expiration
          ? 'insert'
          : 'manual_review',
        reasoning:
          `Tradier filled OPEN order ${orderIdNum} on ${c.tx_ct_date ?? '?'} (exp ${c.classification.expiration ?? '?'}) ` +
          `${c.classification.contracts ?? '?'} contracts net $${c.classification.net_price ?? '?'} per share — ` +
          `no spark_positions row references this order_id.`,
      })
      continue
    }

    if (c.classification.kind === 'close' && !dbByCloseOrderId.has(orderIdNum)) {
      // Untracked CLOSE fill. We try to attach it to the matching OPEN position
      // — same person + same expiration + same strikes + status='open'. If we
      // find one, propose attach_close. Otherwise manual_review.
      const candidate = personRows.find(r =>
        r.status === 'open'
        && r.expiration === c.classification.expiration
        && r.put_short_strike === c.classification.strikes?.putShort
        && r.put_long_strike === c.classification.strikes?.putLong
        && r.call_short_strike === c.classification.strikes?.callShort
        && r.call_long_strike === c.classification.strikes?.callLong,
      )
      mismatches.push({
        kind: 'missing_in_db',
        tradier_order_id: orderIdNum,
        transaction_date: c.order.transaction_date,
        ic_kind: 'close',
        strikes: c.classification.strikes,
        expiration: c.classification.expiration,
        contracts: c.classification.contracts,
        net_price_per_share: c.classification.net_price,
        proposed_position_id: candidate?.position_id ?? '',
        proposed_action: candidate ? 'attach_close' : 'manual_review',
        attach_to_position_id: candidate?.position_id,
        reasoning: candidate
          ? `Tradier CLOSE order ${orderIdNum} matches open spark_positions row ${candidate.position_id} ` +
            `but the DB row has no sandbox_close_order_id pointer to this fill.`
          : `Tradier CLOSE order ${orderIdNum} has no matching open spark_positions row — manual review.`,
      })
    }
  }

  // Pass 2: DB rows with status='open' that Tradier has no leg for (extra_in_db).
  for (const row of personRows) {
    if (row.status !== 'open') continue

    const expectedLegs = [
      buildOccSymbol('SPY', row.expiration, row.put_short_strike, 'P'),
      buildOccSymbol('SPY', row.expiration, row.put_long_strike, 'P'),
      buildOccSymbol('SPY', row.expiration, row.call_short_strike, 'C'),
      buildOccSymbol('SPY', row.expiration, row.call_long_strike, 'C'),
    ]
    const tradierHasAnyLeg = expectedLegs.some(occ => nonZeroLegs.some(p => p.symbol === occ))
    if (tradierHasAnyLeg) continue // broker still holds at least one leg — leave alone

    // Look for a matching CLOSE fill in Tradier order history that we can
    // attribute to this position (same expiration + strikes, kind='close',
    // transaction_date >= row.open_time).
    const openTimeMs = row.open_time ? Date.parse(row.open_time) : NaN
    const matchingClose = sparkClassified.find(c =>
      c.classification.kind === 'close'
      && c.classification.expiration === row.expiration
      && c.classification.strikes?.putShort === row.put_short_strike
      && c.classification.strikes?.putLong === row.put_long_strike
      && c.classification.strikes?.callShort === row.call_short_strike
      && c.classification.strikes?.callLong === row.call_long_strike
      && (() => {
        const ts = c.order.transaction_date ? Date.parse(c.order.transaction_date) : NaN
        return Number.isFinite(openTimeMs) && Number.isFinite(ts) && ts >= openTimeMs
      })(),
    )

    let proposedClose: number | null = null
    let proposedPnl: number | null = null
    if (matchingClose && matchingClose.classification.net_price != null) {
      proposedClose = matchingClose.classification.net_price
      // realized_pnl = (entry_credit - cost_to_close) * 100 * contracts
      // Cap cost_to_close at spread_width (max loss)
      const cappedCost = Math.min(Math.max(0, proposedClose), row.spread_width || (row.put_short_strike - row.put_long_strike))
      proposedPnl = Math.round((row.total_credit - cappedCost) * 100 * row.contracts * 100) / 100
    }

    const matchOrderId = matchingClose
      ? (typeof matchingClose.order.id === 'number'
          ? matchingClose.order.id
          : parseInt(String(matchingClose.order.id), 10))
      : null

    mismatches.push({
      kind: 'extra_in_db',
      db_position_id: row.position_id,
      person: row.person,
      expiration: row.expiration,
      strikes: {
        putLong: row.put_long_strike,
        putShort: row.put_short_strike,
        callShort: row.call_short_strike,
        callLong: row.call_long_strike,
      },
      contracts: row.contracts,
      total_credit: row.total_credit,
      proposed_action: matchingClose ? 'mark_closed' : 'manual_review',
      proposed_close_price: proposedClose,
      proposed_realized_pnl: proposedPnl,
      matched_close_order_id: Number.isFinite(matchOrderId as number) ? (matchOrderId as number) : null,
      reasoning: matchingClose
        ? `DB row is status='open' but Tradier has none of the 4 legs. A matching CLOSE fill ` +
          `(order ${matchOrderId}, ${matchingClose.order.transaction_date ?? '?'}) is in order history.`
        : `DB row is status='open' but Tradier has none of the 4 legs and no matching CLOSE fill ` +
          `was found in the ${LOOKBACK_DAYS}-day order history. Manual review required — do NOT auto-close.`,
    })
  }

  // Pass 3: closed DB rows whose realized_pnl disagrees with the matched
  // Tradier close fill (pnl_mismatch). $1.00 tolerance covers rounding.
  for (const row of personRows) {
    if (row.status !== 'closed' && row.status !== 'expired') continue
    if (row.realized_pnl == null) continue
    if (row.close_order_id == null) continue
    const matched = sparkClassified.find(c =>
      c.classification.kind === 'close'
      && (typeof c.order.id === 'number' ? c.order.id : parseInt(String(c.order.id), 10)) === row.close_order_id,
    )
    if (!matched || matched.classification.net_price == null) continue
    const cappedCost = Math.min(
      Math.max(0, matched.classification.net_price),
      row.spread_width || (row.put_short_strike - row.put_long_strike),
    )
    const expectedPnl = Math.round((row.total_credit - cappedCost) * 100 * row.contracts * 100) / 100
    const diff = Math.round((row.realized_pnl - expectedPnl) * 100) / 100
    if (Math.abs(diff) >= 1.0) {
      mismatches.push({
        kind: 'pnl_mismatch',
        db_position_id: row.position_id,
        db_realized_pnl: row.realized_pnl,
        expected_realized_pnl: expectedPnl,
        diff_usd: diff,
        matched_close_order_id: row.close_order_id,
        reasoning:
          `Closed row records realized_pnl=$${row.realized_pnl} but Tradier close order ${row.close_order_id} ` +
          `at $${matched.classification.net_price}/share implies P&L=$${expectedPnl} (Δ $${diff}).`,
      })
    }
  }

  return {
    person: account.name,
    account_id: account.accountId,
    account_loaded: true,
    tradier_balance: tradierBalance,
    tradier_orders: {
      filled_total_lookback: filledRecent.length,
      filled_today: filledTodayCount,
      spark_filled_total_lookback: sparkClassified.length,
      spark_filled_today: sparkFilledTodayCount,
      inferno_filled_total_lookback: infernoFilledCount,
      open_orders_total: allOpen.length,
    },
    tradier_open_legs: {
      total_legs: nonZeroLegs.length,
      by_expiration: legsByExp,
      spark_open_legs_estimate: sparkOpenLegsEstimate,
    },
    db_ledger: dbLedgerStats(personRows, ctTodayStr),
    mismatches,
  }
}

function dbLedgerStats(rows: DbProdRow[], ctTodayStr: string): AccountReport['db_ledger'] {
  const ctDate = (iso: string | null): string | null =>
    iso ? ctDateString(new Date(iso)) : null
  let openRows = 0
  let openedToday = 0
  let closedToday = 0
  let todayPnl = 0
  let alltimePnl = 0
  for (const r of rows) {
    if (r.status === 'open') openRows++
    if (ctDate(r.open_time) === ctTodayStr) openedToday++
    if (ctDate(r.close_time) === ctTodayStr) {
      closedToday++
      if (r.realized_pnl != null) todayPnl += r.realized_pnl
    }
    if ((r.status === 'closed' || r.status === 'expired') && r.realized_pnl != null) {
      alltimePnl += r.realized_pnl
    }
  }
  return {
    rows_lookback: rows.length,
    open_rows: openRows,
    rows_opened_today: openedToday,
    rows_closed_today: closedToday,
    today_realized_pnl_usd: Math.round(todayPnl * 100) / 100,
    alltime_realized_pnl_usd: Math.round(alltimePnl * 100) / 100,
  }
}

function ctDateString(d: Date): string {
  // Render a date as YYYY-MM-DD in America/Chicago, no DST-handling shortcuts.
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Chicago',
    year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(d)
  const y = parts.find(p => p.type === 'year')?.value
  const m = parts.find(p => p.type === 'month')?.value
  const day = parts.find(p => p.type === 'day')?.value
  return `${y}-${m}-${day}`
}

async function buildReport(): Promise<DiagnosticReport> {
  const ctNow = new Date()
  const ctNowMs = ctNow.getTime()
  const ctTodayStr = ctDateString(ctNow)

  const ledgerRows = await fetchProdLedgerRows()

  const accounts = await getProductionAccountsForBot(PRODUCTION_BOT)
  const accountReports: AccountReport[] = []
  for (const acct of accounts) {
    accountReports.push(await buildAccountReport(acct, ledgerRows, ctTodayStr, ctNowMs))
  }

  const allMismatches = accountReports.flatMap(a => a.mismatches)
  const missingCount = allMismatches.filter(m => m.kind === 'missing_in_db').length
  const extraCount = allMismatches.filter(m => m.kind === 'extra_in_db').length
  const pnlCount = allMismatches.filter(m => m.kind === 'pnl_mismatch').length

  const summary = (() => {
    if (accounts.length === 0) {
      return 'No production accounts loaded for SPARK. Either the production-pause flag is set or no ironforge_accounts row matches type=production AND bot ILIKE %SPARK%. Use /api/spark/diagnose-production for the gate breakdown.'
    }
    if (allMismatches.length === 0) {
      return `No mismatches across ${accounts.length} production account(s). DB ledger and Tradier order history agree within tolerance.`
    }
    return `${allMismatches.length} mismatch(es) across ${accounts.length} account(s): ` +
      `${missingCount} missing_in_db (Tradier fills DB doesn't track), ` +
      `${extraCount} extra_in_db (DB rows status='open' with no broker legs), ` +
      `${pnlCount} pnl_mismatch (closed rows whose realized_pnl disagrees with Tradier exit fill).`
  })()

  return {
    bot: 'SPARK',
    generated_at: new Date().toISOString(),
    ct_today: ctTodayStr,
    account_type: 'production',
    tradier_connected: isConfigured(),
    lookback_days: LOOKBACK_DAYS,
    accounts: accountReports,
    totals: {
      accounts_inspected: accounts.length,
      total_mismatches: allMismatches.length,
      missing_in_db: missingCount,
      extra_in_db: extraCount,
      pnl_mismatch: pnlCount,
    },
    summary,
  }
}

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (bot !== PRODUCTION_BOT) {
    return NextResponse.json(
      { error: `diagnose-live-pnl is ${PRODUCTION_BOT.toUpperCase()}-only — production accounts only exist for the production bot.` },
      { status: 400 },
    )
  }
  if (!isConfigured()) {
    return NextResponse.json({ error: 'Tradier not configured' }, { status: 503 })
  }
  try {
    const report = await buildReport()
    return NextResponse.json(report)
  } catch (err: unknown) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    )
  }
}

interface ApplyChange {
  kind: 'inserted_position' | 'attached_close' | 'marked_closed' | 'pnl_corrected' | 'skipped'
  position_id: string
  detail: string
}

/**
 * Build the column list + parameters for a missing_in_db OPEN insert.
 * Mirrors the canonical SPARK production INSERT in lib/scanner.ts (line 2792)
 * exactly, with these substitutions for fields the broker can't tell us:
 *   - underlying_at_entry / vix_at_entry / expected_move = 0  (unknown, post-hoc)
 *   - oracle_* fields = 0 / 'RECONCILE' / '[]' / false (no advisor record)
 *   - put_order_id / call_order_id = 'RECONCILE'
 *   - sandbox_order_id  = JSON wrapping the Tradier order_id we're attributing
 *   - status = 'open'  (Pass 2 / a separate close fill will mark it closed)
 *   - person + account_type = the Tradier account holder + 'production'
 */
function buildInsertSql(
  positionId: string,
  expiration: string,
  strikes: { putLong: number; putShort: number; callShort: number; callLong: number },
  contracts: number,
  netCredit: number,
  person: string,
  tradierOrderId: number,
  txDate: string | null,
): { sql: string; params: any[] } {
  const spreadWidth = Math.round((strikes.putShort - strikes.putLong) * 100) / 100
  const halfCredit = Math.round((netCredit / 2) * 10000) / 10000
  const collateral = Math.max(0, (spreadWidth - netCredit) * 100) * contracts
  const maxProfit = netCredit * 100 * contracts
  const sandboxJson = JSON.stringify({
    [`${person}:production`]: {
      order_id: tradierOrderId,
      contracts,
      fill_price: netCredit,
      account_type: 'production',
      _reconciled: true,
      _tx_date: txDate,
    },
  })
  const sql = `INSERT INTO spark_positions (
      position_id, ticker, expiration,
      put_short_strike, put_long_strike, put_credit,
      call_short_strike, call_long_strike, call_credit,
      contracts, spread_width, total_credit, max_loss, max_profit,
      collateral_required,
      underlying_at_entry, vix_at_entry, expected_move,
      call_wall, put_wall, gex_regime,
      flip_point, net_gex,
      oracle_confidence, oracle_win_probability, oracle_advice,
      oracle_reasoning, oracle_top_factors, oracle_use_gex_walls,
      wings_adjusted, original_put_width, original_call_width,
      put_order_id, call_order_id,
      sandbox_order_id,
      status, open_time, open_date, dte_mode, person, account_type
    ) VALUES (
      $1, 'SPY', $2, $3, $4, $5, $6, $7, $8, $9,
      $10, $11, $12, $13, $14, 0, 0, 0,
      0, 0, 'UNKNOWN',
      0, 0,
      0, 0, 'RECONCILE',
      'Inserted by /api/spark/diagnose-live-pnl POST', '[]', false,
      false, $10, $10,
      'RECONCILE', 'RECONCILE',
      $15,
      'open', COALESCE($16::timestamptz, NOW()), ${CT_TODAY}, '1DTE', $17, 'production'
    )
    ON CONFLICT (position_id) DO NOTHING`
  const params = [
    positionId,                // $1
    expiration,                // $2
    strikes.putShort,          // $3
    strikes.putLong,           // $4
    halfCredit,                // $5
    strikes.callShort,         // $6
    strikes.callLong,          // $7
    halfCredit,                // $8
    contracts,                 // $9
    spreadWidth,               // $10  (also passed as original_put/call_width)
    netCredit,                 // $11  (total_credit)
    collateral,                // $12  (max_loss = collateral)
    maxProfit,                 // $13
    collateral,                // $14  (collateral_required = max_loss)
    sandboxJson,               // $15
    txDate,                    // $16  (open_time, NULL → NOW())
    person,                    // $17
  ]
  return { sql, params }
}

async function applyReconciliation(report: DiagnosticReport): Promise<{
  changes: ApplyChange[]
  errors: Array<{ where: string; error: string }>
}> {
  const changes: ApplyChange[] = []
  const errors: Array<{ where: string; error: string }> = []

  // ── Apply inserts first (least risky — just adds rows) ──────────────
  for (const acct of report.accounts) {
    for (const m of acct.mismatches) {
      if (m.kind !== 'missing_in_db') continue

      if (m.proposed_action === 'insert') {
        if (!m.strikes || !m.expiration || !m.contracts || m.net_price_per_share == null) {
          changes.push({
            kind: 'skipped',
            position_id: m.proposed_position_id,
            detail: `insert skipped — incomplete order data (strikes=${!!m.strikes}, exp=${!!m.expiration}, contracts=${m.contracts}, net=${m.net_price_per_share})`,
          })
          continue
        }
        try {
          const { sql, params } = buildInsertSql(
            m.proposed_position_id,
            m.expiration,
            m.strikes,
            m.contracts,
            m.net_price_per_share,
            acct.person,
            typeof m.tradier_order_id === 'number'
              ? m.tradier_order_id
              : parseInt(String(m.tradier_order_id), 10),
            m.transaction_date,
          )
          const affected = await dbExecute(sql, params)
          changes.push({
            kind: affected > 0 ? 'inserted_position' : 'skipped',
            position_id: m.proposed_position_id,
            detail: affected > 0
              ? `Inserted from Tradier order ${m.tradier_order_id} (${m.contracts}x @ $${m.net_price_per_share}/share, exp ${m.expiration})`
              : `INSERT no-op — position_id already exists (idempotent re-run)`,
          })
        } catch (err: unknown) {
          errors.push({
            where: `insert ${m.proposed_position_id}`,
            error: err instanceof Error ? err.message : String(err),
          })
        }
        continue
      }

      if (m.proposed_action === 'attach_close' && m.attach_to_position_id) {
        // Untracked CLOSE fill that pairs with an existing OPEN position. Patch
        // the row's sandbox_close_order_id pointer + mark it closed with the
        // realized_pnl computed from the actual exit fill.
        const target = await dbQuery(
          `SELECT contracts, total_credit, spread_width, put_short_strike, put_long_strike
           FROM spark_positions
           WHERE position_id = $1 AND account_type = 'production' AND status = 'open'
           LIMIT 1`,
          [m.attach_to_position_id],
        )
        if (target.length === 0) {
          changes.push({
            kind: 'skipped',
            position_id: m.attach_to_position_id,
            detail: 'attach_close skipped — position no longer status=open (race or already reconciled)',
          })
          continue
        }
        const t = target[0]
        const tContracts = int(t.contracts)
        const tCredit = num(t.total_credit)
        const tSpreadWidth = num(t.spread_width) || (num(t.put_short_strike) - num(t.put_long_strike))
        const closePrice = m.net_price_per_share ?? 0
        const cappedCost = Math.min(Math.max(0, closePrice), tSpreadWidth)
        const realizedPnl = Math.round((tCredit - cappedCost) * 100 * tContracts * 100) / 100
        const closeJson = JSON.stringify({
          [`${acct.person}:production`]: {
            order_id: m.tradier_order_id,
            contracts: m.contracts,
            fill_price: closePrice,
            account_type: 'production',
            _reconciled: true,
            _tx_date: m.transaction_date,
          },
        })
        try {
          const affected = await dbExecute(
            `UPDATE spark_positions
             SET status = 'closed',
                 close_time = COALESCE($1::timestamptz, NOW()),
                 close_price = $2,
                 close_reason = 'reconcile_attached_close',
                 realized_pnl = $3,
                 sandbox_close_order_id = $4,
                 updated_at = NOW()
             WHERE position_id = $5 AND status = 'open' AND account_type = 'production'`,
            [m.transaction_date, closePrice, realizedPnl, closeJson, m.attach_to_position_id],
          )
          changes.push({
            kind: affected > 0 ? 'attached_close' : 'skipped',
            position_id: m.attach_to_position_id,
            detail: affected > 0
              ? `Marked closed from Tradier order ${m.tradier_order_id}: close_price=$${closePrice}, realized_pnl=$${realizedPnl}`
              : 'attach_close UPDATE affected 0 rows (race condition)',
          })
        } catch (err: unknown) {
          errors.push({
            where: `attach_close ${m.attach_to_position_id}`,
            error: err instanceof Error ? err.message : String(err),
          })
        }
      }
    }
  }

  // ── Apply mark_closed for extra_in_db rows where we have an exit fill ──
  for (const acct of report.accounts) {
    for (const m of acct.mismatches) {
      if (m.kind !== 'extra_in_db') continue
      if (m.proposed_action !== 'mark_closed') continue
      if (m.proposed_close_price == null || m.proposed_realized_pnl == null) continue

      const closeJson = JSON.stringify({
        [`${m.person}:production`]: {
          order_id: m.matched_close_order_id,
          contracts: m.contracts,
          fill_price: m.proposed_close_price,
          account_type: 'production',
          _reconciled: true,
          _matched_via: 'extra_in_db_pass',
        },
      })
      try {
        const affected = await dbExecute(
          `UPDATE spark_positions
           SET status = 'closed',
               close_time = NOW(),
               close_price = $1,
               close_reason = 'reconcile_orphan_db_row',
               realized_pnl = $2,
               sandbox_close_order_id = $3,
               updated_at = NOW()
           WHERE position_id = $4 AND status = 'open' AND account_type = 'production'`,
          [m.proposed_close_price, m.proposed_realized_pnl, closeJson, m.db_position_id],
        )
        changes.push({
          kind: affected > 0 ? 'marked_closed' : 'skipped',
          position_id: m.db_position_id,
          detail: affected > 0
            ? `Marked closed via matched Tradier exit ${m.matched_close_order_id}: close_price=$${m.proposed_close_price}, realized_pnl=$${m.proposed_realized_pnl}`
            : 'mark_closed UPDATE affected 0 rows (race condition)',
        })
      } catch (err: unknown) {
        errors.push({
          where: `mark_closed ${m.db_position_id}`,
          error: err instanceof Error ? err.message : String(err),
        })
      }
    }
  }

  // ── Apply pnl correction (closed rows whose realized_pnl disagrees) ──
  for (const acct of report.accounts) {
    for (const m of acct.mismatches) {
      if (m.kind !== 'pnl_mismatch') continue
      try {
        const affected = await dbExecute(
          `UPDATE spark_positions
           SET realized_pnl = $1,
               updated_at = NOW()
           WHERE position_id = $2 AND account_type = 'production'`,
          [m.expected_realized_pnl, m.db_position_id],
        )
        changes.push({
          kind: affected > 0 ? 'pnl_corrected' : 'skipped',
          position_id: m.db_position_id,
          detail: affected > 0
            ? `realized_pnl ${m.db_realized_pnl} → ${m.expected_realized_pnl} (diff $${m.diff_usd}) from Tradier order ${m.matched_close_order_id}`
            : 'pnl correction UPDATE affected 0 rows',
        })
      } catch (err: unknown) {
        errors.push({
          where: `pnl_correction ${m.db_position_id}`,
          error: err instanceof Error ? err.message : String(err),
        })
      }
    }
  }

  return { changes, errors }
}

export async function POST(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (bot !== PRODUCTION_BOT) {
    return NextResponse.json(
      { error: `diagnose-live-pnl is ${PRODUCTION_BOT.toUpperCase()}-only — production accounts only exist for the production bot.` },
      { status: 400 },
    )
  }
  if (!isConfigured()) {
    return NextResponse.json({ error: 'Tradier not configured' }, { status: 503 })
  }
  try {
    const report = await buildReport()
    const { changes, errors } = await applyReconciliation(report)

    // Tally what actually got applied so the spark_logs entry is searchable.
    const tally = changes.reduce<Record<string, number>>((acc, c) => {
      acc[c.kind] = (acc[c.kind] ?? 0) + 1
      return acc
    }, {})

    try {
      await dbExecute(
        `INSERT INTO spark_logs (log_time, level, message, details, dte_mode, account_type)
         VALUES (NOW(), 'RECONCILE', $1, $2, '1DTE', 'production')`,
        [
          `diagnose-live-pnl POST: ` +
          `${tally.inserted_position ?? 0} inserted, ` +
          `${tally.attached_close ?? 0} attached_close, ` +
          `${tally.marked_closed ?? 0} marked_closed, ` +
          `${tally.pnl_corrected ?? 0} pnl_corrected, ` +
          `${tally.skipped ?? 0} skipped, ` +
          `${errors.length} errors`,
          JSON.stringify({
            source: 'diagnose-live-pnl-post',
            tally,
            changes,
            errors,
            report_summary: report.summary,
            report_totals: report.totals,
          }),
        ],
      )
    } catch (logErr: unknown) {
      // Best-effort log; don't fail the response if spark_logs INSERT errors.
      errors.push({
        where: 'spark_logs RECONCILE entry',
        error: logErr instanceof Error ? logErr.message : String(logErr),
      })
    }

    return NextResponse.json({
      bot: 'SPARK',
      account_type: 'production',
      generated_at: new Date().toISOString(),
      report_summary: report.summary,
      report_totals: report.totals,
      apply_tally: tally,
      changes,
      errors,
    })
  } catch (err: unknown) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    )
  }
}
