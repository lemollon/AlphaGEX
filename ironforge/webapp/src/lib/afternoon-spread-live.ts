/**
 * QUENCH LIVE — the arming switch, the hard size cap, and the fill-quality
 * log. Pure logic only: no DB, no network, no imports beyond the paper
 * sleeve's own math module, so every rule below is unit-testable without
 * mocking Postgres or Tradier (same split as lib/afternoon-spread.ts and
 * lib/ebb-sizing.ts).
 *
 * Why this file exists separately from afternoon-spread-tracker.ts: that
 * tracker carries a HARD SAFETY RULE in its header and a test asserting it
 * imports no order function, ever. Adding a live path there would delete that
 * guarantee. The paper tracker stays paper forever; live is this file plus
 * lib/afternoon-spread-executor.ts.
 *
 * ── Why 1 lot, and why it is not configurable ──────────────────────────────
 *
 * The settled record (RESULT_QUENCH_UNRESTRAINED.md, RESULT_QUENCH_SIZING.md)
 * is a ONE-CONTRACT number: $4,000.80 over 945 sessions on real `nbbo_quotes`
 * bid/ask fills. Every multi-lot figure in the sizing study was produced by
 * MULTIPLYING that daily series, because `nbbo_quotes` has no size columns —
 * there is no way to check from history whether a 2-contract order would have
 * filled at the 1-contract quote.
 *
 * So a 2-lot QUENCH is an untested strategy wearing a tested number's
 * clothes. Leron, 2026-10-17: "i dont want to dial it up willy nilly we have
 * to test it." The cap is therefore a CONSTANT, not an env var and not a
 * config column: raising it has to be a reviewed code change with the forward
 * fill evidence in hand, not a dashboard toggle at 13:10 on a Tuesday.
 *
 * The arithmetic that would justify N=2 later, for whoever does raise it:
 * max drawdown is 14.51% of a $2,000 deposit per lot, so N=2 is 29.03% and
 * N=3 is 43.54% — past the 35% ceiling. **2 is the ceiling even once depth is
 * proven**, and only at the $2,000 tier; nothing above it is available there.
 */

import type { AfternoonSpreadSide } from './afternoon-spread'

/**
 * The hard per-account contract cap. Not an env var. Not a config column.
 * See the module header for why raising this is a code review, not a toggle.
 */
export const QUENCH_MAX_CONTRACTS = 1

/**
 * AFTERNOON_SPREAD_MODE — 'live' arms real orders; anything else (unset, '',
 * 'off', 'paper', a typo) is OFF and places nothing. Deliberately a SEPARATE
 * key from AFTERNOON_SPREAD_PAPER so that turning live on does not turn paper
 * tracking off, and so that neither switch can be flipped by accident while
 * aiming at the other.
 *
 * Fails CLOSED: only the exact string 'live' arms it.
 */
export function getQuenchLiveMode(): boolean {
  return (process.env.AFTERNOON_SPREAD_MODE ?? '').trim().toLowerCase() === 'live'
}

/**
 * Clamp any requested size to the cap. Returns the size actually allowed and,
 * when it had to clamp, the reason — so the caller logs WHY a 3 became a 1
 * rather than silently trading a different size than it asked for.
 *
 * A non-finite or sub-1 request yields 0, never a floored 1: "I could not
 * work out a size" must never become "trade the minimum."
 */
export function clampQuenchContracts(requested: number): {
  contracts: number
  clamped: boolean
  reason?: string
} {
  if (!Number.isFinite(requested) || requested < 1) {
    return { contracts: 0, clamped: true, reason: 'bad_contract_request' }
  }
  const floored = Math.floor(requested)
  if (floored > QUENCH_MAX_CONTRACTS) {
    return {
      contracts: QUENCH_MAX_CONTRACTS,
      clamped: true,
      reason: `capped_at_${QUENCH_MAX_CONTRACTS}_from_${floored}`,
    }
  }
  return { contracts: floored, clamped: false }
}

/**
 * One row of the forward fill-quality record — the whole point of shipping
 * live at 1 lot. `quoted_credit` is what the screen showed when the decision
 * was made (short bid minus long ask, the same convention the backtest
 * scored); `filled_credit` is what Tradier actually gave us.
 *
 * Slippage is stored as a column rather than computed in SQL later so the
 * sign convention can never drift: POSITIVE means we were filled BETTER than
 * quoted (more credit than the screen promised), negative means worse.
 */
export interface QuenchFillLogRow {
  trade_date: string
  side: AfternoonSpreadSide
  account_name: string
  account_type: 'sandbox' | 'production'
  order_id: number | null
  requested_contracts: number
  filled_contracts: number
  quoted_credit: number | null
  filled_credit: number | null
  slippage: number | null
  is_close: boolean
  note: string | null
}

/**
 * Signed slippage in dollars per share, filled minus quoted. Null whenever
 * either side is unknown — an unknown fill is NOT zero slippage, and
 * recording it as zero would quietly bias the forward record toward "the
 * backtest's fills were achievable," which is the single question this log
 * exists to answer honestly.
 */
export function fillSlippage(quotedCredit: number | null, filledCredit: number | null): number | null {
  if (quotedCredit == null || filledCredit == null) return null
  if (!Number.isFinite(quotedCredit) || !Number.isFinite(filledCredit)) return null
  return Math.round((filledCredit - quotedCredit) * 10000) / 10000
}

/**
 * Does this fill clear the bar for believing the backtest's fill convention?
 *
 * The backtest sold at the bid and bought at the ask, i.e. it assumed the
 * WORST displayed price on every leg. A real fill at or above that credit
 * means the convention was not optimistic. `tolerance` allows a penny of
 * rounding without calling it a miss.
 */
export function fillMetBacktestConvention(
  quotedCredit: number | null,
  filledCredit: number | null,
  tolerance = 0.01,
): boolean | null {
  const slip = fillSlippage(quotedCredit, filledCredit)
  if (slip == null) return null
  return slip >= -tolerance
}
