/**
 * PAPER-ONLY RESEARCH TRACKER — DB + Tradier orchestration for the "dynamic
 * hedge V2" lead. See lib/afternoon-spread.ts for the pure trigger/strike/
 * settlement math this drives, and the research docs cited there.
 *
 * 🚨 HARD SAFETY RULE 🚨 — this module NEVER places, closes, or cancels an
 * order anywhere: no Tradier sandbox, no production, no env flag. It only
 * calls READ-ONLY quote/history functions (`getQuote`, `getOptionQuote`,
 * `getDailyHistory`, `buildOccSymbol`) and writes rows to its OWN table
 * (afternoon_spread_ledger). There is no code path from this file to a real
 * order — see __tests__/afternoon-spread-tracker.test.ts's "imports no order
 * functions" assertion, the same proof PR #3074 gave for blaze/flare's paper
 * executors (neither imports `placeIcOrderAllAccounts`, `canPlaceLiveOrders`,
 * or `resolveEligibleAccounts`). This file imports none of those, plus none
 * of the other order/cancel/close-position functions tradier.ts exports
 * (`placeHedgePutSpread`, `closeIcOrderAllAccounts`, `cancelSandboxOrder`,
 * `emergencyCloseSandboxPositions`, `closeOrphanSandboxPositions`,
 * `closeAllSandboxPositions`) — see the test's full blocklist.
 *
 * AFTERNOON_SPREAD_PAPER=on is the only switch (see getAfternoonSpreadPaperMode
 * in lib/afternoon-spread.ts). Unset or anything else = off: every exported
 * function here no-ops immediately — no DB read, no Tradier call, no row
 * written.
 */

import { getQuote, getOptionQuote, buildOccSymbol, getDailyHistory } from './tradier'
import { query, dbExecute } from './db'
import {
  AfternoonSpreadGateTag,
  AfternoonSpreadLedgerRow,
  AfternoonSpreadSide,
  AfternoonSpreadStatus,
  AfternoonSpreadTotals,
  callVerticalIntrinsic,
  downTriggerCallVertical,
  downTriggerFires,
  entryCredit,
  getAfternoonSpreadPaperMode,
  isInTriggerWindow,
  putVerticalIntrinsic,
  referenceCallStrike,
  referencePutStrike,
  settlementPnl,
  summarizeAfternoonSpreadLedger,
  tagGate,
  upTriggerFires,
  upTriggerPutVertical,
} from './afternoon-spread'

const TABLE = 'afternoon_spread_ledger'
let _tableReady = false

async function ensureTable(): Promise<void> {
  if (_tableReady) return
  await dbExecute(
    `CREATE TABLE IF NOT EXISTS ${TABLE} (
       id SERIAL PRIMARY KEY,
       trade_date DATE NOT NULL,
       side TEXT NOT NULL,
       trigger_minute TIMESTAMP NOT NULL,
       spot NUMERIC NOT NULL,
       short_strike NUMERIC NOT NULL,
       long_strike NUMERIC NOT NULL,
       short_bid NUMERIC,
       short_ask NUMERIC,
       long_bid NUMERIC,
       long_ask NUMERIC,
       credit NUMERIC,
       vix_ratio NUMERIC,
       gate_tag TEXT NOT NULL,
       close_price NUMERIC,
       realized_pnl NUMERIC,
       status TEXT NOT NULL DEFAULT 'tracked',
       skip_reason TEXT,
       created_at TIMESTAMP NOT NULL DEFAULT NOW(),
       UNIQUE (trade_date, side)
     )`,
  )
  _tableReady = true
}

/** Central Time HHMM S0 is captured at — the spec's "SPY spot at 13:05 CT". */
const S0_CAPTURE_HHMM = 1305

const SESSION_TABLE = 'afternoon_spread_session'
let _sessionTableReady = false

async function ensureSessionTable(): Promise<void> {
  if (_sessionTableReady) return
  await dbExecute(
    `CREATE TABLE IF NOT EXISTS ${SESSION_TABLE} (
       trade_date DATE PRIMARY KEY,
       s0 NUMERIC NOT NULL,
       p NUMERIC NOT NULL,
       c NUMERIC NOT NULL,
       captured_at TIMESTAMP NOT NULL DEFAULT NOW()
     )`,
  )
  _sessionTableReady = true
}

/**
 * P and C are fixed for the whole day off S0 — the spot AT 13:05 CT — per
 * spec, never off the current, evolving minute's spot (that would make P/C
 * chase spot and the down/up triggers could never fire). Captured once,
 * idempotently (`ON CONFLICT DO NOTHING` + a re-read so every caller sees
 * the SAME p/c even if two ticks raced), the first tick at or after 13:05 CT
 * each trading day. Returns null before 13:05 CT, or when no row exists yet
 * and no live quote is available to create one.
 */
async function captureSessionIfDue(ct: Date, tradeDate: string): Promise<{ p: number; c: number } | null> {
  const existing = await query<{ p: string | number; c: string | number }>(
    `SELECT p, c FROM ${SESSION_TABLE} WHERE trade_date = $1`,
    [tradeDate],
  )
  if (existing.length > 0) return { p: Number(existing[0].p), c: Number(existing[0].c) }

  const hhmm = ct.getHours() * 100 + ct.getMinutes()
  if (hhmm < S0_CAPTURE_HHMM) return null

  const q = await getQuote('SPY')
  const s0 = q?.last ?? 0
  if (!(s0 > 0)) return null

  const p = referencePutStrike(s0)
  const c = referenceCallStrike(s0)
  await query(
    `INSERT INTO ${SESSION_TABLE} (trade_date, s0, p, c) VALUES ($1,$2,$3,$4)
     ON CONFLICT (trade_date) DO NOTHING`,
    [tradeDate, s0, p, c],
  )

  const after = await query<{ p: string | number; c: string | number }>(
    `SELECT p, c FROM ${SESSION_TABLE} WHERE trade_date = $1`,
    [tradeDate],
  )
  if (after.length === 0) return null
  return { p: Number(after[0].p), c: Number(after[0].c) }
}

/**
 * FLAME's own VIX decay gate ratio for `tradeDate` (prior VIX close / max VIX
 * close of the trailing 20 sessions) — `scanner.ts`'s own `vixDecayCheck`
 * against its own `VIX_DECAY_CEILING.flame`, dynamically imported to avoid a
 * circular import (scanner.ts calls INTO this tracker each cycle; this
 * tracker only reads scanner.ts's already-exported, side-effect-free gate
 * check, never the reverse at module-load time — same pattern tradier.ts
 * already uses to reach `loadProductionConfigFor` in scanner.ts). A read
 * failure returns null — the caller tags that gate_skip, same as an
 * elevated ratio, never a guess.
 */
async function readFlameVixRatio(tradeDate: string): Promise<number | null> {
  try {
    const { vixDecayCheck, VIX_DECAY_CEILING } = await import('./scanner')
    const check = await vixDecayCheck(tradeDate, VIX_DECAY_CEILING.flame)
    return check.ratio
  } catch {
    return null
  }
}

/**
 * Official close for `dateStr`, mirroring scanner.ts's `settleExpiredPositions`
 * exactly: daily-history bar for that date first, live last-quote fallback
 * only for same-day settlement before the history endpoint has the bar yet.
 * Never a 15:55-15:59 window max/min — a single point value, same as FLAME.
 */
async function getOfficialClose(ticker: string, dateStr: string): Promise<number | null> {
  try {
    const hist = await getDailyHistory(ticker, 10)
    const bar = hist.find((h) => h.date === dateStr)
    if (bar && bar.close > 0) return bar.close
  } catch {
    /* fall through to the live quote */
  }
  const q = await getQuote(ticker)
  return q?.last && q.last > 0 ? q.last : null
}

/**
 * One paper-tracking tick. Called from scanner.ts's FLAME cycle once per
 * minute (the scanner's own scan interval), so this function itself only
 * has to: capture today's S0/P/C session on the first eligible tick at or
 * after 13:05 CT, check the 13:10-14:45 CT trigger window, and check the
 * "already fired today" set — no timer of its own. Returns a short log
 * string, or '' when nothing happened (mode off, before 13:05 CT, outside
 * the trigger window, or both sides already fired).
 */
export async function runAfternoonSpreadTick(ct: Date): Promise<string> {
  if (!getAfternoonSpreadPaperMode()) return ''

  await ensureTable()
  await ensureSessionTable()

  const tradeDate = ct.toISOString().slice(0, 10)

  // P and C are fixed off S0 (13:05 CT) for the whole day — capture (or
  // fetch the already-captured) session first. Before 13:05 CT, or on a
  // day the capture quote never arrived, there is nothing to compare
  // against yet.
  const session = await captureSessionIfDue(ct, tradeDate)
  if (!session) return ''

  const hhmm = ct.getHours() * 100 + ct.getMinutes()
  if (!isInTriggerWindow(hhmm)) return ''

  const already = await query<{ side: string }>(
    `SELECT side FROM ${TABLE} WHERE trade_date = $1`,
    [tradeDate],
  )
  const fired = new Set(already.map((r) => r.side))
  if (fired.has('down_call') && fired.has('up_put')) return ''

  const q = await getQuote('SPY')
  const spot = q?.last ?? 0
  if (!(spot > 0)) return ''

  const out: string[] = []
  if (!fired.has('down_call') && downTriggerFires(spot, session.p)) {
    out.push(await fireSide('down_call', ct, tradeDate, spot))
  }
  if (!fired.has('up_put') && upTriggerFires(spot, session.c)) {
    out.push(await fireSide('up_put', ct, tradeDate, spot))
  }

  const said = out.filter(Boolean)
  return said.length ? `afternoon-spread[${said.join(' ')}]` : ''
}

async function fireSide(
  side: AfternoonSpreadSide,
  ct: Date,
  tradeDate: string,
  spot: number,
): Promise<string> {
  const { short, long } = side === 'down_call' ? downTriggerCallVertical(spot) : upTriggerPutVertical(spot)
  const optType: 'C' | 'P' = side === 'down_call' ? 'C' : 'P'

  const vixRatio = await readFlameVixRatio(tradeDate)
  const gateTag = tagGate(vixRatio)

  const [shortQ, longQ] = await Promise.all([
    getOptionQuote(buildOccSymbol('SPY', tradeDate, short, optType)),
    getOptionQuote(buildOccSymbol('SPY', tradeDate, long, optType)),
  ])

  if (!shortQ || !longQ) {
    await insertRow({
      side, ct, tradeDate, spot, short, long, gateTag, vixRatio,
      status: 'skipped', skipReason: 'quote_missing',
    })
    return `${side}=skip:quote_missing`
  }

  const credit = entryCredit(shortQ.bid, longQ.ask)
  const legs = { shortBid: shortQ.bid, shortAsk: shortQ.ask, longBid: longQ.bid, longAsk: longQ.ask }

  if (credit == null) {
    await insertRow({
      side, ct, tradeDate, spot, short, long, gateTag, vixRatio, ...legs,
      status: 'skipped', skipReason: 'credit_non_positive',
    })
    return `${side}=skip:credit<=0`
  }

  await insertRow({
    side, ct, tradeDate, spot, short, long, gateTag, vixRatio, ...legs,
    credit, status: 'tracked',
  })
  return `${side}=tracked@${credit.toFixed(2)}`
}

async function insertRow(row: {
  side: AfternoonSpreadSide
  ct: Date
  tradeDate: string
  spot: number
  short: number
  long: number
  gateTag: AfternoonSpreadGateTag
  vixRatio: number | null
  shortBid?: number
  shortAsk?: number
  longBid?: number
  longAsk?: number
  credit?: number
  status: AfternoonSpreadStatus
  skipReason?: string
}): Promise<void> {
  await query(
    `INSERT INTO ${TABLE} (
       trade_date, side, trigger_minute, spot, short_strike, long_strike,
       short_bid, short_ask, long_bid, long_ask, credit, vix_ratio, gate_tag,
       status, skip_reason
     ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
     ON CONFLICT (trade_date, side) DO NOTHING`,
    [
      row.tradeDate, row.side, row.ct, row.spot, row.short, row.long,
      row.shortBid ?? null, row.shortAsk ?? null, row.longBid ?? null, row.longAsk ?? null,
      row.credit ?? null, row.vixRatio, row.gateTag,
      row.status, row.skipReason ?? null,
    ],
  )
}

/**
 * Settle every open ('tracked', has a credit) row whose trade date's close
 * is available. Called every cycle, same as scanner.ts's own
 * `settleExpiredPositions` — a no-op most minutes, and it only looks at
 * rows this tracker itself wrote, so it can never touch FLAME's or any
 * other bot's ledger.
 */
export async function settleAfternoonSpreadExpired(ct: Date): Promise<string> {
  if (!getAfternoonSpreadPaperMode()) return ''

  const hhmm = ct.getHours() * 100 + ct.getMinutes()
  if (hhmm < 1500) return '' // wait for the actual close, same convention as scanner.ts

  await ensureTable()

  const todayStr = ct.toISOString().slice(0, 10)
  const rows = await query<{
    id: number
    trade_date: string | Date
    side: string
    short_strike: string | number
    long_strike: string | number
    credit: string | number
  }>(
    `SELECT id, trade_date, side, short_strike, long_strike, credit
       FROM ${TABLE}
      WHERE status = 'tracked' AND credit IS NOT NULL AND trade_date <= $1`,
    [todayStr],
  )
  if (rows.length === 0) return ''

  const out: string[] = []
  for (const r of rows) {
    const exp = (r.trade_date as any)?.toISOString?.()?.slice(0, 10) || String(r.trade_date).slice(0, 10)
    const close = await getOfficialClose('SPY', exp)
    if (close == null) {
      out.push(`${r.id}=no_settle_price`)
      continue
    }
    const short = Number(r.short_strike)
    const long = Number(r.long_strike)
    const credit = Number(r.credit)
    const intrinsic = r.side === 'down_call'
      ? callVerticalIntrinsic(close, short, long)
      : putVerticalIntrinsic(close, short, long)
    const pnl = settlementPnl(credit, intrinsic, 1)
    await dbExecute(
      `UPDATE ${TABLE} SET status = 'settled', close_price = $1, realized_pnl = $2 WHERE id = $3`,
      [close, pnl, r.id],
    )
    out.push(`${r.id}=settled@${pnl.toFixed(2)}`)
  }
  return out.length ? `afternoon-spread settle[${out.join(' ')}]` : ''
}

/* ------------------------------------------------------------------ */
/*  Operator visibility — read-only.                                   */
/* ------------------------------------------------------------------ */

export async function getAfternoonSpreadLedger(limit = 2000): Promise<AfternoonSpreadLedgerRow[]> {
  await ensureTable()
  const rows = await query<AfternoonSpreadLedgerRow & { trade_date: string }>(
    `SELECT trade_date::text AS trade_date, side, trigger_minute, spot,
            short_strike, long_strike, short_bid, short_ask, long_bid, long_ask,
            credit, vix_ratio, gate_tag, close_price, realized_pnl, status, skip_reason
       FROM ${TABLE}
      ORDER BY trade_date DESC, id DESC
      LIMIT $1`,
    [limit],
  )
  return rows
}

/**
 * Ledger + running totals by side and by gate tag, month-to-date and
 * all-time, for the operator-only visibility route
 * (app/api/afternoon-spread/route.ts). Month boundary is computed off the
 * server's UTC clock against the CT `trade_date` string — a few hours of
 * slack right at a month boundary is acceptable for an operator dashboard,
 * not a P&L-critical calculation.
 */
export async function getAfternoonSpreadSummary(): Promise<{
  ledger: AfternoonSpreadLedgerRow[]
  totals: { all_time: AfternoonSpreadTotals; month_to_date: AfternoonSpreadTotals }
}> {
  const ledger = await getAfternoonSpreadLedger()
  const allTime = summarizeAfternoonSpreadLedger(ledger)
  const monthStart = `${new Date().toISOString().slice(0, 7)}-01`
  const monthToDate = summarizeAfternoonSpreadLedger(ledger.filter((r) => r.trade_date >= monthStart))
  return { ledger: ledger.slice(0, 500), totals: { all_time: allTime, month_to_date: monthToDate } }
}
