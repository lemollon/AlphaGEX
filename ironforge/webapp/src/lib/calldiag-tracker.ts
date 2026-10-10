/**
 * CALLDIAG — DB + Tradier orchestration for the IWM 10d/20d call diagonal
 * PAPER sleeve. See lib/calldiag.ts for the pure construction/gate math this
 * drives, and its header for the research this replicates.
 *
 * 🚨 PAPER ONLY IN THIS PR 🚨 — this module never places, closes, or cancels
 * a broker order, on any account, under any CALLDIAG_MODE value (including
 * 'live'). It only calls READ-ONLY quote/chain/history functions
 * (`getOptionExpirations`, `getOptionChainQuotes`, `getOptionQuote`,
 * `getDailyHistory`) and writes rows to its OWN table (calldiag_positions) +
 * decision log (calldiag_decision_log). Leron approved PAPER only
 * (2026-09-27); wiring CALLDIAG_MODE='live' to a real order path is
 * deliberately left for a follow-up PR, not built here — see the mirror
 * proof pattern in afternoon-spread-tracker.ts's own header (no import of
 * any order/cancel/close function tradier.ts exports).
 *
 * CALLDIAG_MODE is the only switch (see getCallDiagMode in lib/calldiag.ts).
 * Unset or anything other than 'paper'/'live' = every exported function here
 * no-ops immediately — no DB read, no Tradier call, no row written. 'live'
 * behaves EXACTLY like 'paper' in this PR (there is no separate order path
 * to gate) — it is accepted only so a later PR can add live order placement
 * without touching this file's mode parsing again.
 *
 * Unlock + sizing: per FLAME account (`resolveEligibleAccounts('flame')`),
 * independently — equity >= CALLDIAG_MIN_EQUITY (default $7,500, env
 * CALLDIAG_MIN_EQUITY) AND that account's own (equity - floor) cushion
 * clears the trade's collateral (evaluateCallDiagCushion, calldiag.ts).
 * Floor/equity are read exactly the way FLINT's own rule R1 reads them
 * (tradier.ts's placeCallSpreadOrderAllAccounts): production floor =
 * getProductionLadderCapital('flame', person).starting; sandbox floor =
 * getOrSeedFlintAccountFloor(person, 'sandbox', ...) — the SAME
 * flint_account_floor table, per the approved spec ("reuse, don't
 * duplicate"). Never more than 1 contract (CD1; CD2's scaled sizing was
 * rejected — see calldiag.ts's header).
 */

import {
  getOptionExpirations,
  getOptionChainQuotes,
  getOptionQuote,
  buildOccSymbol,
  getDailyHistory,
  resolveEligibleAccounts,
  getAllocatedCapitalForAccount,
  getProductionLadderCapital,
  getOrSeedFlintAccountFloor,
} from './tradier'
import { query, dbExecute } from './db'
import {
  CALLDIAG_FRONT_DTE,
  CALLDIAG_BACK_DTE,
  CALLDIAG_MAX_CONTRACTS,
  getCallDiagMode,
  getCallDiagMinEquity,
  isCallDiagUnlocked,
  isCallDiagStandDown,
  computeTrailing5dRealizedVolPct,
  pickCallDiagExpiry,
  buildCallDiagTrade,
  pickCallDiagExitDate,
  computeCallDiagExitPnl,
  evaluateCallDiagCushion,
  type CallDiagBuiltTrade,
  type CallDiagBuildSkipReason,
} from './calldiag'

const TICKER = 'IWM'
const POSITIONS_TABLE = 'calldiag_positions'
const LOG_TABLE = 'calldiag_decision_log'
let _tablesReady = false

async function ensureTables(): Promise<void> {
  if (_tablesReady) return
  await dbExecute(
    `CREATE TABLE IF NOT EXISTS ${POSITIONS_TABLE} (
       id SERIAL PRIMARY KEY,
       person TEXT NOT NULL,
       account_type TEXT NOT NULL,
       front_expiry DATE NOT NULL,
       back_expiry DATE NOT NULL,
       short_strike NUMERIC NOT NULL,
       long_strike NUMERIC NOT NULL,
       short_bid_entry NUMERIC NOT NULL,
       long_ask_entry NUMERIC NOT NULL,
       debit NUMERIC NOT NULL,
       collateral NUMERIC NOT NULL,
       contracts INTEGER NOT NULL DEFAULT 1,
       spot_at_entry NUMERIC,
       em_at_entry NUMERIC,
       cushion_at_entry NUMERIC,
       mode TEXT NOT NULL,
       status TEXT NOT NULL DEFAULT 'open',
       open_date DATE NOT NULL,
       exit_date DATE,
       short_ask_exit NUMERIC,
       long_bid_exit NUMERIC,
       realized_pnl NUMERIC,
       created_at TIMESTAMP NOT NULL DEFAULT NOW(),
       closed_at TIMESTAMP,
       UNIQUE (person, account_type, open_date)
     )`,
  )
  await dbExecute(
    `CREATE TABLE IF NOT EXISTS ${LOG_TABLE} (
       id SERIAL PRIMARY KEY,
       log_date DATE NOT NULL,
       person TEXT,
       account_type TEXT,
       reason TEXT NOT NULL,
       rv5_pct NUMERIC,
       spot NUMERIC,
       created_at TIMESTAMP NOT NULL DEFAULT NOW()
     )`,
  )
  _tablesReady = true
}

async function logDecision(
  logDate: string,
  reason: string,
  opts?: { person?: string; accountType?: string; rv5Pct?: number | null; spot?: number | null },
): Promise<void> {
  try {
    await query(
      `INSERT INTO ${LOG_TABLE} (log_date, person, account_type, reason, rv5_pct, spot)
       VALUES ($1,$2,$3,$4,$5,$6)`,
      [logDate, opts?.person ?? null, opts?.accountType ?? null, reason, opts?.rv5Pct ?? null, opts?.spot ?? null],
    )
  } catch (e) {
    console.warn(`[calldiag] decision log failed (non-fatal): ${e instanceof Error ? e.message : String(e)}`)
  }
}

/** Entry window: 09:35 ET = 08:35 CT. A few minutes of slack for scan-interval jitter; idempotent per account via the UNIQUE(person, account_type, open_date) constraint. */
function isInCallDiagEntryWindow(ct: Date): boolean {
  const hhmm = ct.getHours() * 100 + ct.getMinutes()
  return hhmm >= 835 && hhmm <= 839
}

/** Exit window: 15:59 ET = 14:59 CT — the last minute before the close, same convention FLINT/FLAME use for their own EOD/settlement clocks. */
function isInCallDiagExitWindow(ct: Date): boolean {
  const hhmm = ct.getHours() * 100 + ct.getMinutes()
  return hhmm >= 1459
}

interface CallDiagMarketState {
  tradeDate: string
  trade: CallDiagBuiltTrade | CallDiagBuildSkipReason
  rv5Pct: number | null
  standDown: boolean
}

let _marketStateCache: { date: string; value: CallDiagMarketState } | null = null

/**
 * Market-wide state for `tradeDate` — the front/back expiry pick, the built
 * trade (or its skip reason), and the vol stand-down read. Computed ONCE per
 * day (cached), shared by every account's independent per-account gate below
 * — mirrors FLINT's own gamma-upsize decision (evaluateFlintGammaUpsize),
 * a single market-wide read feeding N independent account decisions.
 */
async function getCallDiagMarketState(tradeDate: string): Promise<CallDiagMarketState> {
  if (_marketStateCache && _marketStateCache.date === tradeDate) return _marketStateCache.value

  const expirations = await getOptionExpirations(TICKER)
  const front = pickCallDiagExpiry(expirations, tradeDate, CALLDIAG_FRONT_DTE)
  const back = pickCallDiagExpiry(expirations, tradeDate, CALLDIAG_BACK_DTE)

  let trade: CallDiagBuiltTrade | CallDiagBuildSkipReason
  if (!front || !back || front === back) {
    trade = 'no_expiry'
  } else {
    const [frontQuotes, backQuotes] = await Promise.all([
      getOptionChainQuotes(TICKER, front),
      getOptionChainQuotes(TICKER, back),
    ])
    const backCalls = backQuotes.filter((q) => q.cp === 'C')
    trade = buildCallDiagTrade(front, back, frontQuotes, backCalls)
  }

  // rv5_pct: 5 most recent PRIOR-CLOSE daily % returns of IWM — never today's
  // own not-yet-known close. getDailyHistory returns bars up to and
  // INCLUDING today once the market has printed one, so the 5 returns ending
  // at yesterday's close are history[len-6..len-2] relative to a series that
  // may or may not yet contain today.
  let rv5Pct: number | null = null
  try {
    const hist = await getDailyHistory(TICKER, 20)
    const priorCloses = hist.filter((h) => h.date < tradeDate).map((h) => h.close)
    if (priorCloses.length >= 6) {
      const last6 = priorCloses.slice(-6)
      const returns: number[] = []
      for (let i = 1; i < last6.length; i++) returns.push(last6[i] / last6[i - 1] - 1)
      rv5Pct = computeTrailing5dRealizedVolPct(returns)
    }
  } catch (e) {
    console.warn(`[calldiag] rv5 history read failed (non-fatal, stands down): ${e instanceof Error ? e.message : String(e)}`)
  }
  const standDown = isCallDiagStandDown(rv5Pct)

  const value: CallDiagMarketState = { tradeDate, trade, rv5Pct, standDown }
  _marketStateCache = { date: tradeDate, value }
  return value
}

/**
 * Per-account (floor, equity) — EXACTLY the same read FLINT's rule R1 uses
 * (tradier.ts's placeCallSpreadOrderAllAccounts): production floor =
 * getProductionLadderCapital('flame', person).starting; sandbox floor =
 * getOrSeedFlintAccountFloor (the SAME flint_account_floor table CallDiag
 * was told to reuse, not duplicate). null on any unreadable leg — the caller
 * must skip, never guess a real-money gate input.
 */
async function getCallDiagAccountLedger(
  person: string,
  isProd: boolean,
): Promise<{ floor: number | null; equity: number | null }> {
  const allocated = await getAllocatedCapitalForAccount(person, isProd ? 'production' : 'sandbox')
  const equity = allocated?.equity ?? null
  if (isProd) {
    const ladderCap = await getProductionLadderCapital('flame', person)
    return { floor: ladderCap?.starting ?? null, equity }
  }
  const floor = await getOrSeedFlintAccountFloor(person, 'sandbox', null, equity)
  return { floor, equity }
}

/**
 * One entry tick, called from scanner.ts's FLAME cycle every scan minute.
 * No-ops outside CALLDIAG_MODE paper/live, outside the 08:35-08:39 CT (09:35
 * ET) entry window, or once every eligible account already has a row for
 * today. Returns a short log string, or '' when nothing happened.
 */
export async function runCallDiagEntryTick(ct: Date): Promise<string> {
  const mode = getCallDiagMode()
  if (mode === 'off') return ''
  if (!isInCallDiagEntryWindow(ct)) return ''

  await ensureTables()
  const tradeDate = ct.toISOString().slice(0, 10)

  const market = await getCallDiagMarketState(tradeDate)
  if (typeof market.trade === 'string') {
    await logDecision(tradeDate, `skip:${market.trade}`, { rv5Pct: market.rv5Pct })
    return `calldiag=skip:${market.trade}`
  }
  const trade = market.trade

  // EDGE-DECAY PAUSE. Blocks every real (account-tagged) entry below while
  // CallDiag is paused on a CUSUM alarm (EDGE_DECAY_MODE=enforce). CallDiag
  // has no separate always-on paper book to reuse as the shadow stream the
  // way FLINT does (every calldiag_positions row here is already virtual —
  // "PAPER ONLY IN THIS PR", see this file's header — but pausing them is
  // still the correct test of "would this have helped," per the RESULT
  // file's own measurement), so instead of writing the real per-account
  // rows, ONE hypothetical shadow trade is recorded for today into
  // edge_decay_shadow_trades — settled by settleCallDiagEdgeDecayShadow
  // above using the exact same market data already resolved for `trade`.
  // No-ops false with zero DB access unless mode is exactly 'enforce'.
  try {
    const { isEdgeDecayPaused, recordEdgeDecayShadowEntry } = await import('./edge-decay')
    if (await isEdgeDecayPaused('calldiag')) {
      await recordEdgeDecayShadowEntry('calldiag', {
        tradeDate, ticker: TICKER, frontExpiry: trade.front, backExpiry: trade.back,
        shortStrike: trade.shortStrike, longStrike: trade.longStrike,
        shortBidEntry: trade.shortBid, longAskEntry: trade.longAsk, contracts: CALLDIAG_MAX_CONTRACTS,
      })
      await logDecision(tradeDate, 'skip:edge_decay_paused', { rv5Pct: market.rv5Pct, spot: trade.spot })
      return 'calldiag:paused(edge_decay)'
    }
  } catch (e) {
    console.warn(`[edge-decay] CallDiag pause check failed (non-fatal, trading continues): ${e instanceof Error ? e.message : String(e)}`)
  }

  const accounts = await resolveEligibleAccounts('flame')
  const out: string[] = []
  for (const acct of accounts) {
    const isProd = acct.type === 'production'
    const accountType = isProd ? 'production' : 'sandbox'

    const already = await query<{ cnt: string }>(
      `SELECT COUNT(*) AS cnt FROM ${POSITIONS_TABLE} WHERE person = $1 AND account_type = $2 AND open_date = $3`,
      [acct.name, accountType, tradeDate],
    )
    if (Number(already[0]?.cnt) >= 1) continue

    const { floor, equity } = await getCallDiagAccountLedger(acct.name, isProd)

    if (!isCallDiagUnlocked(equity, getCallDiagMinEquity())) {
      await logDecision(tradeDate, `skip:locked_below_${getCallDiagMinEquity()}`, { person: acct.name, accountType })
      continue
    }
    if (market.standDown) {
      await logDecision(tradeDate, 'skip:gate_standdown', {
        person: acct.name, accountType, rv5Pct: market.rv5Pct, spot: trade.spot,
      })
      out.push(`${acct.name}:gate_standdown`)
      continue
    }
    const gate = evaluateCallDiagCushion(equity, floor, trade.collateral)
    if (!gate.eligible) {
      await logDecision(tradeDate, gate.reason ?? 'skip:calldiag_profit_cushion(unreadable)', { person: acct.name, accountType })
      continue
    }

    await query(
      `INSERT INTO ${POSITIONS_TABLE} (
         person, account_type, front_expiry, back_expiry, short_strike, long_strike,
         short_bid_entry, long_ask_entry, debit, collateral, contracts, spot_at_entry,
         em_at_entry, cushion_at_entry, mode, status, open_date
       ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,'open',$16)
       ON CONFLICT (person, account_type, open_date) DO NOTHING`,
      [
        acct.name, accountType, trade.front, trade.back, trade.shortStrike, trade.longStrike,
        trade.shortBid, trade.longAsk, trade.debit, trade.collateral, CALLDIAG_MAX_CONTRACTS,
        trade.spot, trade.em, gate.cushion, mode,
        tradeDate,
      ],
    )
    await logDecision(tradeDate, 'opened', { person: acct.name, accountType, rv5Pct: market.rv5Pct, spot: trade.spot })
    out.push(`${acct.name}:opened@${trade.shortStrike}/${trade.longStrike}`)
  }

  return out.length ? `calldiag[${out.join(' ')}]` : ''
}

/**
 * One exit tick, called every scan minute from 14:59 CT (15:59 ET) on. Closes
 * every open position whose front expiry's exit day (the last session
 * strictly before that expiry — pickCallDiagExitDate) is TODAY. A trading-day
 * calendar is built from IWM's own recent daily-history dates plus today (if
 * today itself is a session) — good enough to answer "is today the day
 * before front expiry" without a dedicated market-calendar table.
 */
export async function runCallDiagExitTick(ct: Date): Promise<string> {
  const mode = getCallDiagMode()
  if (mode === 'off') return ''
  if (!isInCallDiagExitWindow(ct)) return ''

  await ensureTables()
  const today = ct.toISOString().slice(0, 10)

  const open = await query<{
    id: number
    person: string
    account_type: string
    front_expiry: string | Date
    back_expiry: string | Date
    short_strike: string | number
    long_strike: string | number
    short_bid_entry: string | number
    long_ask_entry: string | number
    open_date: string | Date
  }>(`SELECT id, person, account_type, front_expiry, back_expiry, short_strike, long_strike,
             short_bid_entry, long_ask_entry, open_date
        FROM ${POSITIONS_TABLE} WHERE status = 'open'`)

  let calendar: string[] | null = null
  const out: string[] = []
  for (const p of open) {
    const openDate = (p.open_date as any)?.toISOString?.()?.slice(0, 10) || String(p.open_date).slice(0, 10)
    const frontExpiry = (p.front_expiry as any)?.toISOString?.()?.slice(0, 10) || String(p.front_expiry).slice(0, 10)
    const backExpiry = (p.back_expiry as any)?.toISOString?.()?.slice(0, 10) || String(p.back_expiry).slice(0, 10)

    if (!calendar) {
      const hist = await getDailyHistory(TICKER, 60)
      const days = new Set(hist.map((h) => h.date))
      days.add(today)
      calendar = Array.from(days).sort()
    }
    const exitDate = pickCallDiagExitDate(calendar, openDate, frontExpiry)
    if (exitDate !== today) continue

    const [shortQ, longQ] = await Promise.all([
      getOptionQuote(buildOccSymbol(TICKER, frontExpiry, Number(p.short_strike), 'C')),
      getOptionQuote(buildOccSymbol(TICKER, backExpiry, Number(p.long_strike), 'C')),
    ])
    if (!shortQ || !longQ) {
      await logDecision(today, 'skip:no_quote', { person: p.person, accountType: p.account_type })
      out.push(`${p.person}:no_quote`)
      continue
    }

    const pnl = computeCallDiagExitPnl(
      Number(p.short_bid_entry), Number(p.long_ask_entry), shortQ.ask, longQ.bid,
    )
    await dbExecute(
      `UPDATE ${POSITIONS_TABLE}
          SET status = 'closed', exit_date = $1, short_ask_exit = $2, long_bid_exit = $3,
              realized_pnl = $4, closed_at = NOW()
        WHERE id = $5`,
      [today, shortQ.ask, longQ.bid, pnl, p.id],
    )
    await logDecision(today, 'closed', { person: p.person, accountType: p.account_type })
    // EDGE-DECAY: feed this closed trade's per-contract pnl into CallDiag's own
    // CUSUM. No-ops with zero DB access when EDGE_DECAY_MODE is unset — see
    // lib/edge-decay.ts. Never allowed to affect the trading path.
    try {
      const { recordEdgeDecayClose } = await import('./edge-decay')
      await recordEdgeDecayClose('calldiag', pnl / Math.max(1, CALLDIAG_MAX_CONTRACTS))
    } catch (e) {
      console.warn(`[edge-decay] CallDiag exit hook failed (non-fatal): ${e instanceof Error ? e.message : String(e)}`)
    }
    out.push(`${p.person}:closed@${pnl.toFixed(2)}`)
  }

  await settleCallDiagEdgeDecayShadow(today)

  return out.length ? `calldiag exit[${out.join(' ')}]` : ''
}

/**
 * EDGE-DECAY SHADOW SETTLEMENT — closes any open `edge_decay_shadow_trades`
 * rows for CallDiag using the SAME real-market quote-based pnl calc as the
 * real exit tick above. These rows only exist while CallDiag is paused on a
 * CUSUM alarm (see runCallDiagEntryTick) — they are hypothetical (no real
 * account, no capital at risk) and exist solely to score the 10-trade resume
 * block the RESULT file's rule calls for. Simplification, disclosed: settles
 * at/after front_expiry rather than replicating pickCallDiagExitDate's
 * day-before-expiry calendar walk — a real position's exit timing precision
 * does not matter for a trade that was never actually placed.
 */
async function settleCallDiagEdgeDecayShadow(today: string): Promise<void> {
  try {
    const { getEdgeDecayMode, getOpenEdgeDecayShadowTrades, settleEdgeDecayShadowTrade } = await import('./edge-decay')
    if (getEdgeDecayMode() === 'off') return // zero DB access — byte-for-byte unchanged when unset
    const open = await getOpenEdgeDecayShadowTrades('calldiag')
    for (const s of open) {
      const frontExpiry = s.front_expiry
      if (frontExpiry > today) continue
      const [shortQ, longQ] = await Promise.all([
        getOptionQuote(buildOccSymbol(TICKER, frontExpiry, Number(s.short_strike), 'C')),
        getOptionQuote(buildOccSymbol(TICKER, s.back_expiry, Number(s.long_strike), 'C')),
      ])
      if (!shortQ || !longQ) continue
      const pnl = computeCallDiagExitPnl(Number(s.short_bid_entry), Number(s.long_ask_entry), shortQ.ask, longQ.bid)
      await settleEdgeDecayShadowTrade(s.id, 'calldiag', {
        shortAskExit: shortQ.ask, longBidExit: longQ.bid, realizedPnl: pnl, contracts: Number(s.contracts) || 1,
      })
    }
  } catch (e) {
    console.warn(`[edge-decay] CallDiag shadow settlement failed (non-fatal): ${e instanceof Error ? e.message : String(e)}`)
  }
}

/* ------------------------------------------------------------------ */
/*  Operator visibility — read-only.                                   */
/* ------------------------------------------------------------------ */

export async function getCallDiagPositions(limit = 2000) {
  await ensureTables()
  return query(
    `SELECT person, account_type, front_expiry::text, back_expiry::text, short_strike, long_strike,
            short_bid_entry, long_ask_entry, debit, collateral, contracts, spot_at_entry, em_at_entry,
            cushion_at_entry, mode, status, open_date::text, exit_date::text, short_ask_exit,
            long_bid_exit, realized_pnl
       FROM ${POSITIONS_TABLE}
      ORDER BY open_date DESC, id DESC
      LIMIT $1`,
    [limit],
  )
}

export async function getCallDiagDecisionLog(limit = 2000) {
  await ensureTables()
  return query(
    `SELECT log_date::text, person, account_type, reason, rv5_pct, spot
       FROM ${LOG_TABLE}
      ORDER BY log_date DESC, id DESC
      LIMIT $1`,
    [limit],
  )
}
