/**
 * XSP_SWAP (R4) persistence — the internal (master-book) XSP legs live in
 * their OWN table, `xsp_swap_legs`, deliberately NOT inside `{bot}_positions`.
 *
 * Why a separate table rather than a row in the existing positions table:
 * every downstream function that reads `{bot}_positions` (closeAtRiskBeforeBell,
 * closePosition, settleExpiredPositions, the watchdog, position-monitor,
 * equity/collateral math) assumes "one row = one guardable, actively-managed
 * SPY spread". XSP is cash-settled, European-style, and by design gets NO
 * assignment guard and NO active management — it is opened once and left to
 * settle. Keeping it out of `{bot}_positions` means every one of those
 * existing, real-money functions is UNCHANGED by this feature (the guard
 * literally cannot see an XSP leg, because it never queries this table) —
 * see xsp-swap.ts's header for the same point made about the pure decision
 * engine. The host leg's OWN row in `{bot}_positions` already carries the
 * REDUCED contract count (n_spy, not n_host) once a swap applies, so every
 * existing SPY-side calculation (collateral, guard, settle, equity) is
 * correct with zero code changes there.
 *
 * Auto-create on first use, matching fast-start-db.ts / tradier.ts's existing
 * migration style — no separate migration runner.
 */
import { query, dbExecute } from './db'
import {
  isXspTicker,
  xspSettlementValueFromSpxClose,
  xspSpreadSettlementValue,
  xspSettlementPnl,
} from './xsp-swap'

export type XspSwapLegAccountType = 'production' | 'sandbox' | 'customer'

export interface XspSwapLegInput {
  bot: string
  /** The HOST leg's own position_id (in `{bot}_positions` for production/sandbox, or
   *  the master's positionId for the customer mirror) — the XSP leg's own id is derived
   *  as `${hostPositionId}-XSP-{accountType}-{accountName}` so multiple accounts opening
   *  the same master signal never collide. */
  hostPositionId: string
  accountType: XspSwapLegAccountType
  accountName: string
  expiration: string // YYYY-MM-DD
  putShortStrike: number
  putLongStrike: number
  contracts: number
  creditPerContract: number
  orderId: string | null
  fillPrice: number | null
  /** Informational only — settlement is keyed by (bot, expiration), never dte_mode. */
  dteMode?: string | null
}

async function ensureXspSwapLegsTable(): Promise<void> {
  await dbExecute(
    `CREATE TABLE IF NOT EXISTS xsp_swap_legs (
       id BIGSERIAL PRIMARY KEY,
       leg_id TEXT NOT NULL UNIQUE,
       bot TEXT NOT NULL,
       host_position_id TEXT NOT NULL,
       account_type TEXT NOT NULL,
       account_name TEXT NOT NULL,
       ticker TEXT NOT NULL DEFAULT 'XSP',
       expiration DATE NOT NULL,
       put_short_strike NUMERIC NOT NULL,
       put_long_strike NUMERIC NOT NULL,
       contracts INTEGER NOT NULL,
       credit_per_contract NUMERIC NOT NULL,
       order_id TEXT,
       fill_price NUMERIC,
       status TEXT NOT NULL DEFAULT 'open',
       settle_close NUMERIC,
       settle_value NUMERIC,
       settle_pnl NUMERIC,
       dte_mode TEXT,
       opened_at TIMESTAMP NOT NULL DEFAULT NOW(),
       settled_at TIMESTAMP
     )`,
  )
}

/** Deterministic id: one row per (host leg, account) — safe to call more than once
 *  with the same inputs (e.g. a retried scan cycle) via ON CONFLICT DO NOTHING. */
export function xspSwapLegId(hostPositionId: string, accountType: XspSwapLegAccountType, accountName: string): string {
  const safeName = accountName.toLowerCase().replace(/[^a-z0-9]/g, '')
  return `${hostPositionId}-XSP-${accountType}-${safeName}`
}

/** Records a filled XSP leg. Idempotent per (hostPositionId, accountType, accountName). */
export async function insertXspSwapLeg(input: XspSwapLegInput): Promise<string> {
  await ensureXspSwapLegsTable()
  const legId = xspSwapLegId(input.hostPositionId, input.accountType, input.accountName)
  await dbExecute(
    `INSERT INTO xsp_swap_legs (
       leg_id, bot, host_position_id, account_type, account_name, ticker, expiration,
       put_short_strike, put_long_strike, contracts, credit_per_contract, order_id,
       fill_price, status, dte_mode
     ) VALUES ($1,$2,$3,$4,$5,'XSP',$6,$7,$8,$9,$10,$11,$12,'open',$13)
     ON CONFLICT (leg_id) DO NOTHING`,
    [legId, input.bot, input.hostPositionId, input.accountType, input.accountName, input.expiration,
     input.putShortStrike, input.putLongStrike, input.contracts, input.creditPerContract,
     input.orderId, input.fillPrice, input.dteMode ?? null],
  )
  return legId
}

interface OpenXspSwapLegRow {
  leg_id: string
  bot: string
  host_position_id: string
  account_type: string
  account_name: string
  expiration: unknown
  put_short_strike: string | number
  put_long_strike: string | number
  contracts: string | number
  credit_per_contract: string | number
}

function dateStr(v: unknown): string {
  const d = v as { toISOString?: () => string } | null | undefined
  return d?.toISOString?.()?.slice(0, 10) || String(v).slice(0, 10)
}

/**
 * Settle every OPEN xsp_swap_legs row for `bot` whose expiration is today or earlier,
 * from the OFFICIAL SPX close (never SPY's own close — a different series). `getSpxClose`
 * is injected so this stays testable without a network/DB dependency on tradier.ts; the
 * scanner wires it to `getDailyHistory('SPX', lookback)`, the same "daily bar for the
 * expiration date" convention settle-watchdog.ts already uses for the SPY side, just
 * pointed at the index ticker instead.
 *
 * NEVER invents a price: a missing SPX close for that date leaves the row open and logs
 * a warning — same "no close means no settle" guard as settle-watchdog.ts.
 */
export async function settleXspSwapLegsForBot(
  bot: string,
  todayCT: string,
  getSpxClose: (expiration: string) => Promise<number | null>,
): Promise<{ settled: number; unsettled: number }> {
  await ensureXspSwapLegsTable()
  const rows = await query<OpenXspSwapLegRow>(
    `SELECT leg_id, bot, host_position_id, account_type, account_name, expiration,
            put_short_strike, put_long_strike, contracts, credit_per_contract
       FROM xsp_swap_legs
      WHERE bot = $1 AND status = 'open' AND expiration <= $2`,
    [bot, todayCT],
  )
  let settled = 0
  let unsettled = 0
  const closeCache = new Map<string, number | null>()
  for (const r of rows) {
    const exp = dateStr(r.expiration)
    if (!closeCache.has(exp)) {
      let c: number | null = null
      try { c = await getSpxClose(exp) } catch { c = null }
      closeCache.set(exp, c)
    }
    const spxClose = closeCache.get(exp) ?? null
    const settleXsp = spxClose != null ? xspSettlementValueFromSpxClose(spxClose) : null
    const value = settleXsp != null
      ? xspSpreadSettlementValue(Number(r.put_short_strike), Number(r.put_long_strike), settleXsp)
      : null
    if (value == null) {
      unsettled++
      console.warn(
        `[xsp-swap-db] ${bot.toUpperCase()} leg ${r.leg_id}: no usable SPX close for ${exp} — ` +
        `holds open, unsettled (never inventing a price).`,
      )
      continue
    }
    const pnl = xspSettlementPnl(Number(r.credit_per_contract), value, Number(r.contracts))
    await dbExecute(
      `UPDATE xsp_swap_legs
          SET status = 'settled', settle_close = $2, settle_value = $3, settle_pnl = $4, settled_at = NOW()
        WHERE leg_id = $1 AND status = 'open'`,
      [r.leg_id, spxClose, value, pnl],
    )
    settled++
    console.log(
      `[xsp-swap-db] ${bot.toUpperCase()} leg ${r.leg_id} SETTLED: spx_close=${spxClose} ` +
      `(xsp=${settleXsp?.toFixed(2)}) value=$${value.toFixed(2)} pnl=$${pnl.toFixed(2)}`,
    )
  }
  return { settled, unsettled }
}

/** For reporting/reconciliation UI — never used by the guard (XSP legs never enter it). */
export async function getOpenXspSwapLegs(bot: string): Promise<OpenXspSwapLegRow[]> {
  await ensureXspSwapLegsTable()
  return query<OpenXspSwapLegRow>(
    `SELECT leg_id, bot, host_position_id, account_type, account_name, expiration,
            put_short_strike, put_long_strike, contracts, credit_per_contract
       FROM xsp_swap_legs WHERE bot = $1 AND status = 'open'`,
    [bot],
  )
}

// Re-exported so callers that only touch the DB layer don't also need to import
// xsp-swap.ts directly for this one guard check.
export { isXspTicker }
