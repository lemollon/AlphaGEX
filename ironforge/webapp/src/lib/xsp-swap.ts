/**
 * XSP SWAP (R4) — move the host leg's first min(n,2) contracts from SPY to a
 * same-moneyness XSP 0DTE put credit spread when XSP prices at least as well
 * as SPY.
 *
 * Source of truth: `C:\Users\lemol\dev\meltup\RESULT_xsp_addon.md` (the
 * "R1-R4" section, 2026-09-28) and `xsp_replace_r4_fixtures.json`. Leron's
 * reframing: XSP is cash-settled (European-style, no early assignment), so
 * it can be held straight to expiration with NO $0.25 guard buyback — the
 * lever is MOVING the host leg's first contract(s) from SPY+guard to XSP
 * held-to-settlement, same strikes/moneyness, same total contract count
 * (risk-neutral by construction: only the ticker and the guard exemption
 * differ).
 *
 * R4 (the frozen, shipped rule): first min(n,2) contracts move to XSP ONLY
 * on days XSP's real credit >= SPY's real credit − $0.05/share ($5/contract);
 * else 100% stays on SPY. Held-out backtest: passes median + p10 + max-DD +
 * 0-floor-breach at FLAME $4,242, SPARK $5,000, SPARK $7,500; misses ONLY on
 * max-DD at FLAME $2,000 (money is still better there — ship-decision is
 * Leron's, not gated by this module).
 *
 * This module is PURE — no DB, no network, no clock — exactly like
 * settle-watchdog.ts and customer-executor/contracts.ts, which is what makes
 * it parity-testable against the frozen fixtures and unit-testable at every
 * boundary. The touch-size check is a LIVE safety addition on top of the
 * backtested R4 price gate (the backtest's own "XSP fill %" already assumed
 * fillable-at-the-touch; the live version must check that itself before
 * routing real money) — see decideXspSwap's doc for the exact convention.
 *
 * Kill switch: XSP_SWAP unset or anything other than the literal string
 * 'on' reads as OFF. Off means every caller in tradier.ts / scanner.ts /
 * customer-executor/executor.ts takes its pre-existing SPY-only branch —
 * byte-for-byte unchanged. See the "kill switch" tests in xsp-swap.test.ts
 * and the mocked-integration tests for the assertion that OFF makes zero
 * extra network calls, not just a decision that happens to be a no-op.
 */

/** The only ticker this module ever routes contracts to. */
export const XSP_TICKER = 'XSP'

/** R4: at most this many host contracts ever move to XSP, regardless of n_host. */
export const XSP_SWAP_MAX_CONTRACTS = 2

/** R4's price gate: XSP credit must clear SPY credit by no more than this much, per share. */
export const XSP_SWAP_MIN_CREDIT_EDGE = 0.05

/**
 * Master on/off switch. Unset, empty, or anything but the exact lowercase
 * string 'on' reads as OFF — same fail-closed convention as
 * `isCustomerFlintEnabled()` in customer-executor/executor.ts and
 * `FLINT_MODE` in flint.ts. Reads process.env.XSP_SWAP.
 */
export function isXspSwapMode(): boolean {
  return String(process.env.XSP_SWAP ?? '').trim().toLowerCase() === 'on'
}

/** True iff the given ticker (or OCC symbol prefix) is XSP. Case-insensitive. */
export function isXspTicker(ticker: string | null | undefined): boolean {
  return String(ticker ?? '').trim().toUpperCase() === XSP_TICKER
}

/** True iff the given OCC option symbol's root is XSP (handles both the
 *  unpadded tradier.ts convention, e.g. "XSP260929P00773000", and the
 *  space-padded OCC convention used by customer-executor/contracts.ts,
 *  e.g. "XSP   260929P00773000"). */
export function isXspOccSymbol(occSymbol: string | null | undefined): boolean {
  return /^XSP\s*\d{6}[CP]\d{8}$/.test(String(occSymbol ?? '').trim())
}

export type XspSwapReason =
  | 'xsp_swap_disabled'
  | 'no_host_contracts'
  | 'xsp_quote_unavailable'
  | 'xsp_credit_below_gate'
  | 'xsp_touch_too_thin'
  | 'xsp_swap_applied'

export interface XspSwapDecisionInput {
  /** Total host-leg contracts about to be placed for this account, BEFORE any split. */
  nHost: number
  /** SPY's real per-contract entry credit (dollars/share), sell-bid/buy-ask, today's quote. */
  spyCreditPerContract: number
  /**
   * XSP's real per-contract entry credit for the SAME strikes/moneyness (dollars/share),
   * sell-bid/buy-ask — e.g. `getPutSpreadEntryCredit('XSP', expiration, putShort, putLong)`'s
   * `putCredit`. `null` means the quote could not be fetched at all (unmatched symbol,
   * broker error, etc.) — this is NOT the same as a thin/zero quote, and both null and a
   * real-but-losing quote route 100% to SPY.
   */
  xspCreditPerContract: number | null
  /**
   * Displayed bid size on the XSP short strike, from the SAME quote pull as
   * `xspCreditPerContract` — e.g. that same call's `shortBidSize`. This mirrors the
   * existing EBB liquidity check's convention (lib/ebb-sizing.ts: only the short leg's
   * displayed bid size gates size; the long leg is assumed to have matching depth).
   * `null` (Tradier sent no size) is treated as UNKNOWN, not "enough" — conservative by
   * design, since this is new money movement onto a book that can be thin (the historical
   * XSP order-book capacity study found p05 depth = 2 contracts). Unlike EBB's own
   * unknown-liquidity fallback (which still allows some lots), an unknown XSP touch size
   * routes the WHOLE host leg to SPY rather than guessing a real order onto a market we
   * cannot see the depth of.
   */
  xspShortBidSize: number | null
}

export interface XspSwapDecision {
  /** Contracts to place on XSP (0 or min(nHost,2)). */
  nXsp: number
  /** Contracts to keep on SPY (nHost - nXsp). */
  nSpy: number
  spyCreditPerContract: number
  xspCreditPerContract: number | null
  usedXsp: boolean
  reason: XspSwapReason
}

/**
 * The R4 decision, plus the live touch-size safety check. Deterministic, total
 * (never throws), and side-effect-free — every input is a plain number the
 * caller already has or already fetched from a single quote pull.
 *
 * Evaluation order matches the spec literally:
 *   1. n_host <= 0 -> nothing to split.
 *   2. XSP_SWAP off -> all SPY (caller is expected to short-circuit before this,
 *      but the decision itself is also a safe no-op if called anyway).
 *   3. No usable XSP quote -> all SPY.
 *   4. XSP credit < SPY credit - $0.05/share -> all SPY.
 *   5. XSP touch depth does not cover the candidate size -> all SPY.
 *   6. Otherwise: min(n_host, 2) contracts to XSP, the rest to SPY.
 */
export function decideXspSwap(input: XspSwapDecisionInput, opts?: { swapEnabled?: boolean }): XspSwapDecision {
  const nHost = Math.max(0, Math.floor(Number(input.nHost) || 0))
  const spyCreditPerContract = Number(input.spyCreditPerContract) || 0
  const allSpy = (reason: XspSwapReason): XspSwapDecision => ({
    nXsp: 0,
    nSpy: nHost,
    spyCreditPerContract,
    xspCreditPerContract: input.xspCreditPerContract,
    usedXsp: false,
    reason,
  })

  if (nHost <= 0) {
    return { nXsp: 0, nSpy: 0, spyCreditPerContract, xspCreditPerContract: input.xspCreditPerContract, usedXsp: false, reason: 'no_host_contracts' }
  }
  if (opts?.swapEnabled === false) return allSpy('xsp_swap_disabled')

  const xspCredit = input.xspCreditPerContract
  if (xspCredit == null || !Number.isFinite(xspCredit)) return allSpy('xsp_quote_unavailable')

  if (!(xspCredit >= spyCreditPerContract - XSP_SWAP_MIN_CREDIT_EDGE)) return allSpy('xsp_credit_below_gate')

  const candidate = Math.min(nHost, XSP_SWAP_MAX_CONTRACTS)
  const touch = input.xspShortBidSize
  if (touch == null || !Number.isFinite(touch) || touch < candidate) return allSpy('xsp_touch_too_thin')

  return {
    nXsp: candidate,
    nSpy: nHost - candidate,
    spyCreditPerContract,
    xspCreditPerContract: xspCredit,
    usedXsp: true,
    reason: 'xsp_swap_applied',
  }
}

/**
 * Runtime fill fallback: "If XSP doesn't fill, fall back to SPY for that
 * contract. Never skip the trade because XSP failed." Called AFTER an
 * attempted XSP order comes back, not as part of the pure pricing decision
 * above (a broker-level order failure is a different kind of fact than a
 * quote/price gate). Pure and total — the caller supplies whether the XSP
 * order itself succeeded.
 */
export function applyXspFillFallback(decision: XspSwapDecision, xspOrderFilled: boolean): XspSwapDecision {
  if (!decision.usedXsp || xspOrderFilled) return decision
  return {
    ...decision,
    nXsp: 0,
    nSpy: decision.nSpy + decision.nXsp,
    usedXsp: false,
    reason: 'xsp_quote_unavailable',
  }
}

/**
 * XSP settles in cash from the OFFICIAL SPX close, divided by 10 — European-style,
 * no early assignment, which is the entire reason this leg needs no guard.
 * NEVER use SPY's own close here: SPY drifts from SPX/10 over time (dividends,
 * tracking error) and is a DIFFERENT settlement series, not a proxy for it.
 */
export function xspSettlementValueFromSpxClose(officialSpxClose: number): number | null {
  if (!Number.isFinite(officialSpxClose) || officialSpxClose <= 0) return null
  return Math.round((officialSpxClose / 10) * 10000) / 10000
}

/**
 * Intrinsic value of the XSP put spread at settlement, clamped to the wing width —
 * same shape as settle-watchdog.ts's settlementValue(), scoped to XSP's host-leg shape
 * (put credit spread only; XSP is never given a call leg by this feature).
 * Returns null (never 0) on a malformed row or unusable settle price — refuse to
 * guess a settlement rather than silently booking max profit or max loss.
 */
export function xspSpreadSettlementValue(putShort: number, putLong: number, settleXsp: number): number | null {
  if (!Number.isFinite(settleXsp) || settleXsp <= 0) return null
  const width = putShort - putLong
  if (!(width > 0)) return null
  return Math.round(Math.min(Math.max(putShort - settleXsp, 0), width) * 10000) / 10000
}

/** Realized P&L of the XSP leg at settlement. Credit and value are per-contract, dollars/share. */
export function xspSettlementPnl(credit: number, value: number, contracts: number): number {
  return Math.round((credit - value) * 100 * contracts * 100) / 100
}
