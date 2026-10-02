/**
 * FLAME v2 — SPY 0DTE CALL credit spread order/ledger orchestration.
 * FLAME_V2_CALL_SPREAD_MODE (see flags.ts) gates everything here:
 *   off     — this module does nothing (no DB, no quote, no order).
 *   shadow  — (default) the decision is computed and logged by
 *             flame-v2/engine.ts's flameCallSpreadDecision; THIS module still
 *             writes a paper ledger row (own table, flame_v2_call_positions)
 *             so the shadow record exists to review, but places no order.
 *   live    — same paper ledger row, PLUS a real order via
 *             placeFlameV2CallSpreadOrder IF canPlaceLiveOrders('flame') is
 *             also true (the real-money arm switch, independent of this
 *             flag — see tradier.ts isFlameLiveArmed).
 *
 * Own table, own guard, own settle pass — this NEVER reads or writes
 * flame_positions / flame_paper_account (FLAME's EBB put-spread ledger), so a
 * bug here cannot corrupt the put side's accounting. See math.ts's
 * callSpreadStrikes/callSpreadTier/callSpreadContracts for the pure sizing
 * formula and callGuardShouldClose for the mirrored assignment-guard test
 * this module's guard tick reuses.
 *
 * SAFETY INVARIANT (matches engine.ts): every exported function here is
 * wrapped so it can NEVER throw into the scan tick. A bug must degrade to
 * "logged, no order, no behavior change" — scanner.ts also wraps every call
 * site in its own try/catch as defense in depth.
 */
import { query, dbExecute } from '@/lib/db'
import {
  getQuote, getOptionQuote, buildOccSymbol, getDailyHistory,
  canPlaceLiveOrders, placeFlameV2CallSpreadOrder,
} from '@/lib/tradier'
import { marketCloseMinuteCT } from '@/lib/market-calendar'
import { callGuardShouldClose } from './math'
import { flameCallSpreadMode, isEnabled, isLive } from './flags'
import { flameCallSpreadDecision } from './engine'

const TABLE = 'flame_v2_call_positions'
const TICKER = 'SPY'
let _tableReady = false

async function ensureTable(): Promise<void> {
  if (_tableReady) return
  try {
    await dbExecute(
      `CREATE TABLE IF NOT EXISTS ${TABLE} (
         id SERIAL PRIMARY KEY,
         position_id TEXT NOT NULL,
         side TEXT NOT NULL DEFAULT 'call',
         ticker TEXT NOT NULL,
         expiration DATE NOT NULL,
         short_strike NUMERIC NOT NULL,
         long_strike NUMERIC NOT NULL,
         credit NUMERIC NOT NULL,
         contracts INTEGER NOT NULL,
         collateral NUMERIC NOT NULL,
         spot_at_entry NUMERIC,
         tier INTEGER,
         is_calm BOOLEAN,
         is_longg BOOLEAN,
         person TEXT NOT NULL DEFAULT 'PAPER',
         account_type TEXT NOT NULL DEFAULT 'sandbox',
         mode TEXT NOT NULL,
         status TEXT NOT NULL DEFAULT 'open',
         open_date DATE NOT NULL,
         open_time TIMESTAMP NOT NULL DEFAULT NOW(),
         close_time TIMESTAMP,
         close_price NUMERIC,
         close_reason TEXT,
         realized_pnl NUMERIC,
         sandbox_order_id TEXT,
         created_at TIMESTAMP NOT NULL DEFAULT NOW(),
         UNIQUE (person, account_type, open_date)
       )`,
    )
    _tableReady = true
  } catch (e) {
    console.error('[flame-v2] ensureTable(flame_v2_call_positions) failed (fail-closed, no ledger writes):', e)
  }
}

/**
 * One entry tick, called from tryOpenFlamePutSpread for the SPY book only,
 * which itself only runs inside FLAME's own 13:05-13:10 CT (14:05-14:10 ET)
 * entry window (scanner.ts isInEntryWindow) — so this needs no window check
 * of its own. Idempotent per (person, account_type, open_date) via the
 * table's UNIQUE constraint, so repeat ticks inside that window are no-ops
 * after the first successful write. Never throws; returns '' when the mode
 * is off or the decision/quote is unavailable.
 */
export async function runFlameV2CallSpreadEntryTick(
  dateStr: string, spot: number, flameBaseContracts: number,
): Promise<string> {
  const mode = flameCallSpreadMode()
  if (!isEnabled(mode)) return ''
  try {
    const decision = await flameCallSpreadDecision(dateStr, spot, flameBaseContracts)
    if (!decision.available || decision.contracts < 1 || decision.shortStrike == null || decision.longStrike == null) {
      return `call_spread=skip:${decision.reason}`
    }

    await ensureTable()
    const already = await query<{ cnt: string }>(
      `SELECT COUNT(*) AS cnt FROM ${TABLE} WHERE person = 'PAPER' AND account_type = 'sandbox' AND open_date = $1`,
      [dateStr],
    )
    if (Number(already[0]?.cnt ?? 0) >= 1) return ''

    const expiration = dateStr // SPY 0DTE — same-day expiry
    const [shortQ, longQ] = await Promise.all([
      getOptionQuote(buildOccSymbol(TICKER, expiration, decision.shortStrike, 'C')),
      getOptionQuote(buildOccSymbol(TICKER, expiration, decision.longStrike, 'C')),
    ])
    if (!shortQ || !longQ) return 'call_spread=skip:no_quotes'

    let credit = shortQ.bid - longQ.ask
    if (credit <= 0) {
      const shortMid = (shortQ.bid + shortQ.ask) / 2
      const longMid = (longQ.bid + longQ.ask) / 2
      credit = Math.max(0, shortMid - longMid)
    }
    credit = Math.round(credit * 10000) / 10000
    const MIN_CREDIT = 0.10
    if (credit < MIN_CREDIT) return `call_spread=skip:credit_low(${credit.toFixed(2)})`

    const width = decision.longStrike - decision.shortStrike
    const maxLossPer = Math.round((width - credit) * 100 * 100) / 100
    if (maxLossPer <= 0) return 'call_spread=skip:invalid_max_loss'
    const collateral = maxLossPer * decision.contracts
    const positionId = `FLAMEV2C-${TICKER}-${expiration.replace(/-/g, '')}-${Math.random().toString(36).slice(2, 8).toUpperCase()}`

    // Paper/sandbox ledger row ALWAYS written (shadow and live both) — the
    // shadow record this sleeve exists to produce.
    await query(
      `INSERT INTO ${TABLE} (
         position_id, side, ticker, expiration, short_strike, long_strike, credit,
         contracts, collateral, spot_at_entry, tier, is_calm, is_longg,
         person, account_type, mode, status, open_date
       ) VALUES ($1,'call',$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'PAPER','sandbox',$13,'open',$3::date)
       ON CONFLICT (person, account_type, open_date) DO NOTHING`,
      [
        positionId, TICKER, expiration, decision.shortStrike, decision.longStrike, credit,
        decision.contracts, collateral, spot, decision.tier, null, null, mode,
      ],
    )
    console.log(
      `[flame-v2] FLAME call_spread(${mode}) PAPER opened ${decision.contracts}x ` +
      `${decision.shortStrike}/${decision.longStrike}C @ $${credit.toFixed(2)} (spot ${spot.toFixed(2)}, tier=${decision.tier})`,
    )

    let liveNote = ''
    if (isLive(mode) && canPlaceLiveOrders('flame')) {
      try {
        const live = await placeFlameV2CallSpreadOrder(
          TICKER, expiration, decision.shortStrike, decision.longStrike,
          decision.contracts, credit, positionId,
        )
        const entries = Object.entries(live)
        if (entries.length === 0) {
          liveNote = ' live:no_fill'
        } else {
          for (const [key, info] of entries) {
            const [person, accountType] = key.split(':') as [string, 'sandbox' | 'production']
            const fillCredit = info.fill_price != null && info.fill_price > 0 ? info.fill_price : credit
            const liveCollateral = Math.max(0, (width - fillCredit) * 100) * info.contracts
            const liveId = `${positionId}-${accountType}-${person.toLowerCase().replace(/[^a-z0-9]/g, '')}`
            await query(
              `INSERT INTO ${TABLE} (
                 position_id, side, ticker, expiration, short_strike, long_strike, credit,
                 contracts, collateral, spot_at_entry, tier, is_calm, is_longg,
                 person, account_type, mode, status, open_date, sandbox_order_id
               ) VALUES ($1,'call',$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,'open',$3::date,$16)
               ON CONFLICT (person, account_type, open_date) DO NOTHING`,
              [
                liveId, TICKER, expiration, decision.shortStrike, decision.longStrike, fillCredit,
                info.contracts, liveCollateral, spot, decision.tier, null, null,
                person, accountType, mode, JSON.stringify({ [key]: info }),
              ],
            )
            console.log(
              `[flame-v2] FLAME call_spread(${mode}) ${accountType.toUpperCase()} [${person}] FILL: ` +
              `${info.contracts}x @ $${fillCredit.toFixed(4)} — order ${info.order_id}`,
            )
          }
          liveNote = ` live:${entries.length}acct`
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        console.error('[flame-v2] FLAME call_spread LIVE ORDER FAILED:', msg)
        liveNote = ` live:failed(${msg.slice(0, 60)})`
      }
    } else if (isLive(mode)) {
      liveNote = ' live:disarmed'
    }

    return `call_spread=traded@${credit.toFixed(2)}${liveNote}`
  } catch (e) {
    console.warn('[flame-v2] runFlameV2CallSpreadEntryTick failed (non-fatal, no order placed):', e)
    return ''
  }
}

/**
 * Mirrored assignment guard, 3 minutes before the close (same window FLAME's
 * own put-side guard uses — assignmentGuardWindow in scanner.ts — duplicated
 * here via marketCloseMinuteCT rather than imported, since that function is
 * module-private to scanner.ts). A short call goes in-the-money as spot
 * RISES, so the test is `spot >= shortStrike - buffer` (callGuardShouldClose,
 * math.ts) — the mirror of the put guard's `spot <= shortStrike + buffer`.
 */
const CALL_GUARD_BUFFER = 0.50

function inGuardWindow(ct: Date): boolean {
  const hhmm = ct.getHours() * 100 + ct.getMinutes()
  const endHHMM = marketCloseMinuteCT(ct)
  const totalMin = Math.floor(endHHMM / 100) * 60 + (endHHMM % 100) - 3
  const startHHMM = Math.floor(totalMin / 60) * 100 + (totalMin % 60)
  return hhmm >= startHHMM && hhmm < endHHMM
}

export async function runFlameV2CallSpreadGuardTick(ct: Date): Promise<string> {
  const mode = flameCallSpreadMode()
  if (!isEnabled(mode)) return ''
  if (!inGuardWindow(ct)) return ''
  try {
    await ensureTable()
    const todayStr = ct.toISOString().slice(0, 10)
    const rows = await query<{
      id: number; position_id: string; expiration: string | Date; short_strike: string | number
      long_strike: string | number; contracts: string | number; credit: string | number
      person: string; account_type: string; sandbox_order_id: string | null
    }>(
      `SELECT id, position_id, expiration, short_strike, long_strike, contracts, credit, person, account_type, sandbox_order_id
         FROM ${TABLE} WHERE status = 'open' AND open_date = $1`,
      [todayStr],
    )
    if (rows.length === 0) return ''

    const q = await getQuote(TICKER)
    const spot = q?.last ?? 0
    if (!(spot > 0)) return 'call_spread_guard=no_quote'

    const out: string[] = []
    for (const r of rows) {
      const shortStrike = Number(r.short_strike)
      if (!callGuardShouldClose(spot, shortStrike, CALL_GUARD_BUFFER)) {
        out.push(`${r.position_id}=clear@${spot.toFixed(2)}`)
        continue
      }
      if (r.sandbox_order_id) {
        out.push(`${r.position_id}=guard_pending`)
        continue
      }
      const exp = (r.expiration as any)?.toISOString?.()?.slice(0, 10) || String(r.expiration).slice(0, 10)
      const longStrike = Number(r.long_strike)
      const contracts = Number(r.contracts)

      if (r.person === 'PAPER') {
        // Paper row: book intrinsic at the guard trigger, no real order.
        const intrinsic = Math.min(Math.max(0, spot - shortStrike), longStrike - shortStrike)
        const pnl = Math.round((Number(r.credit) - intrinsic) * 100 * contracts * 100) / 100
        await dbExecute(
          `UPDATE ${TABLE} SET status='closed', close_time=NOW(), close_price=$1, close_reason='assignment_guard', realized_pnl=$2 WHERE id=$3`,
          [spot, pnl, r.id],
        )
        out.push(`${r.position_id}=guarded_paper@${spot.toFixed(2)}`)
        continue
      }

      // Disarming must never strand an open real position with no route out
      // (same rule tradier.ts's closeIcOrderAllAccounts FLAME inject
      // documents) — the close below does NOT re-check canPlaceLiveOrders.
      try {
        const live = await placeFlameV2CallSpreadOrder(
          TICKER, exp, shortStrike, longStrike, contracts, 0, r.position_id,
          { close: true, targetPerson: r.person, targetAccountType: r.account_type as 'sandbox' | 'production' },
        )
        const info = live[`${r.person}:${r.account_type}`]
        if (!info) {
          console.error(`[flame-v2] FLAME call_spread GUARD: ${r.position_id} close order did not fill — position stays open, retried next cycle.`)
          out.push(`${r.position_id}=guard_no_fill`)
          continue
        }
        // The order itself filled (Tradier confirmed an order.id and did not
        // reject/cancel/expire it — see placeFlameV2CallSpreadOrder), but a
        // null fill_price means the price itself is unknown. Booking $0
        // here would overstate the close credit retained (best-case, not
        // real) — leave realized_pnl NULL and flag it for reconciliation
        // rather than invent a number on a real-money row.
        const closePrice = info.fill_price ?? null
        const pnl = closePrice != null
          ? Math.round((Number(r.credit) - closePrice) * 100 * contracts * 100) / 100
          : null
        const reason = closePrice != null ? 'assignment_guard' : 'assignment_guard_fill_price_unknown'
        await dbExecute(
          `UPDATE ${TABLE} SET status='closed', close_time=NOW(), close_price=$1, close_reason=$2, realized_pnl=$3, sandbox_order_id=$4 WHERE id=$5`,
          [closePrice, reason, pnl, JSON.stringify({ [`${r.person}:${r.account_type}`]: info }), r.id],
        )
        if (closePrice == null) {
          console.error(`[flame-v2] FLAME call_spread GUARD: ${r.position_id} closed but fill price unknown — reconcile against the broker.`)
        }
        console.log(`[flame-v2] FLAME call_spread GUARD CLOSED ${r.position_id} spot=${spot.toFixed(2)} short=${shortStrike}`)
        out.push(`${r.position_id}=guarded@${spot.toFixed(2)}`)
      } catch (e) {
        console.error(`[flame-v2] FLAME call_spread GUARD close failed for ${r.position_id}:`, e)
        out.push(`${r.position_id}=guard_error`)
      }
    }
    return out.length ? `call_spread guard[${out.join(' ')}]` : ''
  } catch (e) {
    console.warn('[flame-v2] runFlameV2CallSpreadGuardTick failed (non-fatal):', e)
    return ''
  }
}

/**
 * Settles any row the guard never caught (expired worthless, or ITM past the
 * guard — should be rare since the guard checks every minute for the last 3)
 * using the SAME daily-history-bar-first, live-quote-fallback convention
 * scanner.ts's own settleExpiredPositions/afternoon-spread-tracker use.
 */
export async function runFlameV2CallSpreadSettleTick(ct: Date): Promise<string> {
  const mode = flameCallSpreadMode()
  if (!isEnabled(mode)) return ''
  const hhmm = ct.getHours() * 100 + ct.getMinutes()
  if (hhmm < marketCloseMinuteCT(ct)) return ''
  try {
    await ensureTable()
    const todayStr = ct.toISOString().slice(0, 10)
    const rows = await query<{
      id: number; position_id: string; short_strike: string | number; long_strike: string | number
      credit: string | number; contracts: string | number; person: string
    }>(
      `SELECT id, position_id, short_strike, long_strike, credit, contracts, person
         FROM ${TABLE} WHERE status = 'open' AND open_date = $1`,
      [todayStr],
    )
    if (rows.length === 0) return ''

    let close: number | null = null
    try {
      const hist = await getDailyHistory(TICKER, 10)
      const bar = hist.find((h) => h.date === todayStr)
      if (bar && bar.close > 0) close = bar.close
    } catch { /* fall through to live quote */ }
    if (close == null) {
      const q = await getQuote(TICKER)
      close = q?.last && q.last > 0 ? q.last : null
    }
    if (close == null) return 'call_spread_settle=no_settle_price'

    const out: string[] = []
    for (const r of rows) {
      const shortStrike = Number(r.short_strike)
      const longStrike = Number(r.long_strike)
      const contracts = Number(r.contracts)
      const intrinsic = Math.min(Math.max(0, close - shortStrike), longStrike - shortStrike)
      const pnl = Math.round((Number(r.credit) - intrinsic) * 100 * contracts * 100) / 100
      await dbExecute(
        `UPDATE ${TABLE} SET status='closed', close_time=NOW(), close_price=$1, close_reason='expiry_settlement', realized_pnl=$2 WHERE id=$3`,
        [close, pnl, r.id],
      )
      out.push(`${r.position_id}=settled@${pnl.toFixed(2)}`)
    }
    return out.length ? `call_spread settle[${out.join(' ')}]` : ''
  } catch (e) {
    console.warn('[flame-v2] runFlameV2CallSpreadSettleTick failed (non-fatal):', e)
    return ''
  }
}

/** Operator visibility — read-only. */
export async function getFlameV2CallPositions(limit = 2000) {
  await ensureTable()
  return query(
    `SELECT position_id, ticker, expiration::text, short_strike, long_strike, credit, contracts,
            collateral, spot_at_entry, tier, person, account_type, mode, status,
            open_date::text, open_time::text, close_time::text, close_price, close_reason, realized_pnl
       FROM ${TABLE}
      ORDER BY open_date DESC, id DESC
      LIMIT $1`,
    [limit],
  )
}

