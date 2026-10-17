/**
 * QUENCH LIVE EXECUTOR — real orders, the fill-quality log, and the
 * assignment guard.
 *
 * Paper tracking stays in lib/afternoon-spread-tracker.ts, which carries a
 * HARD SAFETY RULE and a test asserting it imports no order function. That
 * guarantee is kept intact: live lives here instead. The pure switch/cap/
 * slippage logic is lib/afternoon-spread-live.ts.
 *
 * ── Two lessons from other sleeves are built into the control flow ────────
 *
 * 1. **BROKER FIRST, LEDGER SECOND.** STOKE wrote `status='closed'` before
 *    asking the broker; on 2026-10-15 the buy-back was rejected on all four
 *    accounts while the ledger had booked a loss, SPY settled $0.21 OTM, and
 *    every account had actually KEPT its credit — a ~$205 real-money error
 *    across five rows, unrecoverable because settlement only selects
 *    `status='open'`. Here, nothing is written until an order id exists, and
 *    an EMPTY result from placeQuenchOrderAllAccounts counts as NO ORDER.
 *
 * 2. **SPY OPTIONS ASSIGN — they do not cash-settle.** The backtest scored
 *    settlement as intrinsic against the official close, which is the right
 *    way to score a P&L but is NOT what the broker does. A short leg that
 *    finishes in the money is exercised against us into 100 short shares per
 *    contract. FLAME and STOKE each run an assignment guard for this exact
 *    reason and QUENCH needs its own, so `closeQuenchAtRiskBeforeBell` buys
 *    the short side back in the final minutes when spot is within a buffer of
 *    the short strike. Without it, a defined-risk $1 spread still hands you
 *    an undefined overnight equity position.
 *
 * 🚨 Arms only on AFTERNOON_SPREAD_MODE=live. Every exported function returns
 * immediately — zero DB reads, zero broker calls — under any other value.
 */

import { getQuote, getOptionQuote, buildOccSymbol, placeQuenchOrderAllAccounts } from './tradier'
import { query, dbExecute } from './db'
import {
  downTriggerCallVertical,
  downTriggerFires,
  entryCredit,
  isInTriggerWindow,
  referenceCallStrike,
  referencePutStrike,
  upTriggerFires,
  upTriggerPutVertical,
  type AfternoonSpreadSide,
} from './afternoon-spread'
import {
  clampQuenchContracts,
  fillSlippage,
  getQuenchLiveMode,
  QUENCH_MAX_CONTRACTS,
} from './afternoon-spread-live'

const LIVE_TABLE = 'quench_live_positions'
const FILL_LOG_TABLE = 'quench_fill_log'

/**
 * Buffer, in dollars, inside the short strike that makes a position
 * "at risk" of assignment. Matches FLAME's own reviewed guard buffer of
 * $0.25 (`assignment-guard-buffer-costs-most-of-flame`: a wider buffer
 * closes winners early and costs most of the edge).
 */
export const QUENCH_GUARD_BUFFER = 0.25

let _ready = false

async function ensureTables(): Promise<void> {
  if (_ready) return
  await dbExecute(
    `CREATE TABLE IF NOT EXISTS ${LIVE_TABLE} (
       id SERIAL PRIMARY KEY,
       position_id TEXT NOT NULL,
       trade_date DATE NOT NULL,
       side TEXT NOT NULL,
       right TEXT NOT NULL,
       short_strike NUMERIC NOT NULL,
       long_strike NUMERIC NOT NULL,
       contracts INTEGER NOT NULL,
       quoted_credit NUMERIC NOT NULL,
       filled_credit NUMERIC,
       collateral_required NUMERIC NOT NULL,
       spot_at_entry NUMERIC NOT NULL,
       account_type TEXT NOT NULL,
       person TEXT,
       order_id TEXT NOT NULL,
       status TEXT NOT NULL DEFAULT 'open',
       close_reason TEXT,
       close_price NUMERIC,
       realized_pnl NUMERIC,
       open_time TIMESTAMP NOT NULL DEFAULT NOW(),
       close_time TIMESTAMP,
       UNIQUE (trade_date, side, person, account_type)
     )`,
  )
  await dbExecute(
    `CREATE TABLE IF NOT EXISTS ${FILL_LOG_TABLE} (
       id SERIAL PRIMARY KEY,
       trade_date DATE NOT NULL,
       side TEXT NOT NULL,
       account_name TEXT NOT NULL,
       account_type TEXT NOT NULL,
       order_id TEXT,
       requested_contracts INTEGER NOT NULL,
       filled_contracts INTEGER NOT NULL,
       quoted_credit NUMERIC,
       filled_credit NUMERIC,
       slippage NUMERIC,
       is_close BOOLEAN NOT NULL DEFAULT FALSE,
       note TEXT,
       logged_at TIMESTAMP NOT NULL DEFAULT NOW()
     )`,
  )
  _ready = true
}

/**
 * The forward fill record — the reason this ships at 1 lot at all. Every
 * order writes one row per account whether or not a price came back, because
 * an unlogged fill is indistinguishable from a fill that never happened, and
 * "could the backtest's bid/ask convention actually be achieved" is the only
 * question that licenses raising the size later.
 */
async function logFill(row: {
  tradeDate: string
  side: AfternoonSpreadSide
  accountName: string
  accountType: string
  orderId: string | null
  requested: number
  filled: number
  quotedCredit: number | null
  filledCredit: number | null
  isClose: boolean
  note?: string | null
}): Promise<void> {
  await query(
    `INSERT INTO ${FILL_LOG_TABLE} (
       trade_date, side, account_name, account_type, order_id,
       requested_contracts, filled_contracts, quoted_credit, filled_credit,
       slippage, is_close, note
     ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)`,
    [
      row.tradeDate, row.side, row.accountName, row.accountType, row.orderId,
      row.requested, row.filled, row.quotedCredit, row.filledCredit,
      fillSlippage(row.quotedCredit, row.filledCredit), row.isClose, row.note ?? null,
    ],
  ).catch((e) => {
    // A logging failure must never take a trading cycle down, but it must be
    // loud: this table is the entire evidence base for a future size change.
    console.error(`[quench] FILL LOG WRITE FAILED (${row.side} ${row.accountName}): ${e instanceof Error ? e.message : e}`)
  })
}

/**
 * One live entry tick. Mirrors the paper tracker's trigger logic exactly —
 * same session anchors, same window, same buffer — and differs only in
 * placing a real order and recording the order id.
 *
 * Returns a short log string, or '' when nothing happened (mode off, outside
 * the window, both sides already fired, or no quote).
 */
export async function runQuenchLiveTick(ct: Date): Promise<string> {
  if (!getQuenchLiveMode()) return ''
  await ensureTables()

  const tradeDate = ct.toISOString().slice(0, 10)
  const hhmm = ct.getHours() * 100 + ct.getMinutes()
  if (!isInTriggerWindow(hhmm)) return ''

  // Session anchors come from the paper tracker's own session table so the
  // live and paper sleeves can never disagree about which strikes were being
  // watched on a given day.
  const session = await query<{ p: string | number; c: string | number }>(
    `SELECT p, c FROM afternoon_spread_session WHERE trade_date = $1`,
    [tradeDate],
  )
  if (session.length === 0) return ''
  const p = Number(session[0].p)
  const c = Number(session[0].c)

  const already = await query<{ side: string }>(
    `SELECT DISTINCT side FROM ${LIVE_TABLE} WHERE trade_date = $1`,
    [tradeDate],
  )
  const fired = new Set(already.map((r) => r.side))
  if (fired.has('down_call') && fired.has('up_put')) return ''

  const q = await getQuote('SPY')
  const spot = q?.last ?? 0
  if (!(spot > 0)) return ''

  const out: string[] = []
  if (!fired.has('down_call') && downTriggerFires(spot, p, QUENCH_GUARD_BUFFER * 2)) {
    out.push(await fireLiveSide('down_call', ct, tradeDate, spot))
  }
  if (!fired.has('up_put') && upTriggerFires(spot, c, QUENCH_GUARD_BUFFER * 2)) {
    out.push(await fireLiveSide('up_put', ct, tradeDate, spot))
  }

  const said = out.filter(Boolean)
  return said.length ? `QUENCH-LIVE[${said.join(' ')}]` : ''
}

async function fireLiveSide(
  side: AfternoonSpreadSide,
  ct: Date,
  tradeDate: string,
  spot: number,
): Promise<string> {
  const { short, long } = side === 'down_call' ? downTriggerCallVertical(spot) : upTriggerPutVertical(spot)
  const right: 'C' | 'P' = side === 'down_call' ? 'C' : 'P'

  const [shortQ, longQ] = await Promise.all([
    getOptionQuote(buildOccSymbol('SPY', tradeDate, short, right)),
    getOptionQuote(buildOccSymbol('SPY', tradeDate, long, right)),
  ])
  if (!shortQ || !longQ) return `${side}=skip:quote_missing`

  // The backtest's convention, byte for byte: sell the short at the BID, buy
  // the long at the ASK. A non-positive credit skips rather than being
  // floored — the same rule the paper sleeve applies.
  const credit = entryCredit(shortQ.bid, longQ.ask)
  if (credit == null) return `${side}=skip:credit<=0`

  const clamp = clampQuenchContracts(QUENCH_MAX_CONTRACTS)
  if (clamp.contracts < 1) return `${side}=skip:${clamp.reason ?? 'bad_size'}`
  const contracts = clamp.contracts

  const positionId = `QUENCH-${tradeDate}-${side}`
  const placed = await placeQuenchOrderAllAccounts(
    'SPY', tradeDate, short, long, right, contracts, credit, positionId,
  )

  // EMPTY MEANS NO ORDER. Writing a ledger row here would repeat STOKE's
  // 2026-10-15 failure in a new sleeve.
  const keys = Object.keys(placed)
  if (keys.length === 0) {
    await logFill({
      tradeDate, side, accountName: 'n/a', accountType: 'n/a', orderId: null,
      requested: contracts, filled: 0, quotedCredit: credit, filledCredit: null,
      isClose: false, note: 'no account accepted the order',
    })
    return `${side}=no_order_placed`
  }

  const width = Math.abs(long - short)
  for (const key of keys) {
    const info = placed[key]
    const [person, acctType] = key.split(':')
    const filled = info.fill_price ?? null
    await logFill({
      tradeDate, side, accountName: person, accountType: acctType, orderId: String(info.order_id),
      requested: contracts, filled: info.contracts, quotedCredit: credit, filledCredit: filled,
      isClose: false,
    })
    await query(
      `INSERT INTO ${LIVE_TABLE} (
         position_id, trade_date, side, right, short_strike, long_strike, contracts,
         quoted_credit, filled_credit, collateral_required, spot_at_entry,
         account_type, person, order_id, status
       ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,'open')
       ON CONFLICT (trade_date, side, person, account_type) DO NOTHING`,
      [
        positionId, tradeDate, side, right, short, long, info.contracts,
        credit, filled, Math.max(0, (width - (filled ?? credit)) * 100) * info.contracts,
        spot, acctType, person, String(info.order_id),
      ],
    )
  }
  return `${side}=live@${credit.toFixed(2)}x${keys.length}acct`
}

/**
 * Assignment guard. SPY options are physically settled, so a short leg left
 * in the money is exercised against the account into 100 short shares per
 * contract. This buys the spread back in the final minutes whenever spot sits
 * within QUENCH_GUARD_BUFFER of the short strike.
 *
 * Ordering is deliberate and is the whole lesson of the 2026-10-15 STOKE
 * incident: the broker is asked FIRST, and a row is only marked closed once
 * an order id comes back. A rejected buy-back leaves the row OPEN so
 * settlement books the outcome that actually happened.
 */
export async function closeQuenchAtRiskBeforeBell(ct: Date, endHHMM: number): Promise<string> {
  if (!getQuenchLiveMode()) return ''
  const hhmm = ct.getHours() * 100 + ct.getMinutes()
  if (hhmm < endHHMM - 3) return ''
  await ensureTables()

  const tradeDate = ct.toISOString().slice(0, 10)
  const rows = await query<{
    position_id: string
    side: string
    right: string
    short_strike: string | number
    long_strike: string | number
    contracts: number
    quoted_credit: string | number
    filled_credit: string | number | null
    person: string | null
    account_type: string
  }>(
    `SELECT position_id, side, right, short_strike, long_strike, contracts,
            quoted_credit, filled_credit, person, account_type
       FROM ${LIVE_TABLE}
      WHERE status = 'open' AND trade_date = $1`,
    [tradeDate],
  )
  if (rows.length === 0) return ''

  const q = await getQuote('SPY')
  const spot = q?.last ?? 0
  if (!(spot > 0)) return ''

  const out: string[] = []
  for (const r of rows) {
    const short = Number(r.short_strike)
    const long = Number(r.long_strike)
    const width = Math.abs(long - short)

    // At risk = spot has reached the short strike's side of the buffer.
    const atRisk = r.right === 'C'
      ? spot >= short - QUENCH_GUARD_BUFFER
      : spot <= short + QUENCH_GUARD_BUFFER
    if (!atRisk) continue

    // Fail-safe worst case: assume the full width until a real quote says better.
    let costToClose = width
    try {
      const [sQ, lQ] = await Promise.all([
        getOptionQuote(buildOccSymbol('SPY', tradeDate, short, r.right as 'C' | 'P')),
        getOptionQuote(buildOccSymbol('SPY', tradeDate, long, r.right as 'C' | 'P')),
      ])
      if (sQ && lQ) costToClose = Math.min(Math.max(0, sQ.ask - lQ.bid), width)
    } catch { /* keep the fail-safe */ }

    if (!r.person) {
      console.error(`[quench] GUARD SKIPPED ${r.position_id}: no person on a ${r.account_type} row — refusing to guess the account. Left OPEN.`)
      out.push(`${r.position_id}=no_person_left_open`)
      continue
    }

    const placed = await placeQuenchOrderAllAccounts(
      'SPY', tradeDate, short, long, r.right as 'C' | 'P', r.contracts, costToClose,
      r.position_id, { close: true, targetPerson: r.person },
    )
    const closedKeys = Object.keys(placed)
    await logFill({
      tradeDate, side: r.side as AfternoonSpreadSide, accountName: r.person,
      accountType: r.account_type, orderId: closedKeys.length ? String(placed[closedKeys[0]].order_id) : null,
      requested: r.contracts, filled: closedKeys.length ? placed[closedKeys[0]].contracts : 0,
      quotedCredit: costToClose, filledCredit: closedKeys.length ? placed[closedKeys[0]].fill_price ?? null : null,
      isClose: true, note: closedKeys.length ? null : 'guard buy-back placed no order',
    })

    if (closedKeys.length === 0) {
      console.error(
        `[quench] GUARD placed NO close order for ${r.position_id} (${r.person}, ${r.account_type}) — ` +
        `row left OPEN so settlement books the real outcome. ASSIGNMENT RISK: reconcile the broker account.`,
      )
      out.push(`${r.position_id}=broker_close_failed_left_open`)
      continue
    }

    const entry = Number(r.filled_credit ?? r.quoted_credit)
    const realizedPnl = Math.round((entry - costToClose) * 100 * r.contracts * 100) / 100
    await dbExecute(
      `UPDATE ${LIVE_TABLE}
          SET status = 'closed', close_reason = 'assignment_guard', close_price = $1,
              realized_pnl = $2, close_time = NOW()
        WHERE position_id = $3 AND person = $4 AND account_type = $5 AND status = 'open'`,
      [costToClose, realizedPnl, r.position_id, r.person, r.account_type],
    )
    out.push(`${r.position_id}=guarded@${spot.toFixed(2)}`)
  }
  return out.length ? `QUENCH guard[${out.join(' ')}]` : ''
}

/**
 * Fill-quality summary — the forward evidence that decides whether QUENCH may
 * ever trade more than one lot. Read this, not a backtest, before changing
 * QUENCH_MAX_CONTRACTS.
 */
export async function getQuenchFillQuality(): Promise<{
  orders: number
  withPrice: number
  medianSlippage: number | null
  metConvention: number
  worseThanQuoted: number
}> {
  await ensureTables()
  const rows = await query<{ slippage: string | number | null }>(
    `SELECT slippage FROM ${FILL_LOG_TABLE} WHERE is_close = FALSE AND order_id IS NOT NULL`,
  )
  const slips = rows.map((r) => (r.slippage == null ? null : Number(r.slippage))).filter((v): v is number => v != null)
  slips.sort((a, b) => a - b)
  return {
    orders: rows.length,
    withPrice: slips.length,
    medianSlippage: slips.length ? slips[Math.floor(slips.length / 2)] : null,
    metConvention: slips.filter((s) => s >= -0.01).length,
    worseThanQuoted: slips.filter((s) => s < -0.01).length,
  }
}
