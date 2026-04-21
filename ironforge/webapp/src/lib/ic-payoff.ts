/**
 * Iron Condor payoff math (pure functions — no I/O, no state).
 *
 * An Iron Condor is 4 legs with the same expiration:
 *   long put  @ putLongStrike   (pl)   — buy cheap put below the range
 *   short put @ putShortStrike  (ps)   — sell the put wing, ps > pl
 *   short call @ callShortStrike (cs)  — sell the call wing, cs > ps
 *   long call @ callLongStrike  (cl)   — buy cheap call above the range, cl > cs
 *
 * Expiration P&L (per $/contract terms, multiplied by 100 × contracts):
 *   P&L(spot_at_exp) = entry_credit
 *                    + max(0, pl − spot)       // long put intrinsic (we own)
 *                    − max(0, ps − spot)       // short put assigned (we pay)
 *                    − max(0, spot − cs)       // short call assigned (we pay)
 *                    + max(0, spot − cl)       // long call intrinsic (we own)
 *
 * The curve is piecewise linear with kinks at each of the four strikes:
 *   price range           slope (per $1 of underlying)
 *   spot ≤ pl             0      (both put legs ITM, flat at max_loss_put_side)
 *   pl < spot < ps        +1     (long put still gaining, short put still OTM)
 *   ps ≤ spot ≤ cs        0      (profit zone — max profit, both wings OTM)
 *   cs < spot < cl        −1     (short call assigned, long call not yet ITM)
 *   spot ≥ cl             0      (flat at max_loss_call_side)
 *
 * Max profit  = entry_credit × 100 × contracts
 * Max loss (put side)  = ((ps − pl) − entry_credit) × 100 × contracts  (negative)
 * Max loss (call side) = ((cl − cs) − entry_credit) × 100 × contracts  (negative)
 * Breakevens:
 *   lower_be = ps − entry_credit
 *   upper_be = cs + entry_credit
 *
 * Because the curve is piecewise linear, we only need the 4 strike kinks
 * plus a padding anchor on each side to draw a complete payoff diagram.
 * No Black-Scholes needed — this is always EXACT at expiration.
 */

export interface IcStrikes {
  putLong: number
  putShort: number
  callShort: number
  callLong: number
}

export interface IcPayoffResult {
  pnl_curve: Array<{ price: number; pnl: number }>
  max_profit: number
  max_loss_put_side: number
  max_loss_call_side: number
  max_loss: number // min of the two sides (most negative)
  breakeven_low: number
  breakeven_high: number
  profit_zone: { low: number; high: number }
  /**
   * Probability-of-profit heuristic. With no IV input we fall back to a
   * distance-based heuristic: width of profit zone divided by the total
   * width of the position (pl → cl). Callers with IV should compute a
   * proper log-normal PoP; we return this placeholder when no IV is
   * available so the UI has a number to render instead of "—".
   */
  pop_heuristic: number
}

/**
 * Compute Iron Condor expiration P&L at a single underlying price.
 * `entry_credit` and the return value are in dollars PER CONTRACT (not
 * multiplied by 100 × contracts). The caller scales for presentation.
 */
export function icPayoffAtPrice(
  spot: number,
  strikes: IcStrikes,
  entryCredit: number,
): number {
  const { putLong, putShort, callShort, callLong } = strikes
  const longPut = Math.max(0, putLong - spot)
  const shortPut = Math.max(0, putShort - spot)
  const shortCall = Math.max(0, spot - callShort)
  const longCall = Math.max(0, spot - callLong)
  // Per-contract P&L in dollars. The "×100" multiplier (contract size)
  // is applied by the caller when constructing the P&L curve for UI.
  return entryCredit + longPut - shortPut - shortCall + longCall
}

/**
 * Build the full P&L curve for an Iron Condor. Returns dollar P&L values
 * already scaled by 100 × contracts so the UI can plot them directly.
 *
 * `priceRange` defaults to a symmetric window around the strikes padded
 * by 2× the put-side width on each end — enough headroom that the flat
 * max-loss plateaus are visible in the chart.
 */
export function computeIcPayoff(
  strikes: IcStrikes,
  entryCredit: number,
  contracts: number,
  spot: number,
  priceRange?: { low: number; high: number },
): IcPayoffResult {
  const { putLong, putShort, callShort, callLong } = strikes
  const contractMultiplier = 100 * Math.max(1, contracts)

  const putWidth = putShort - putLong
  const callWidth = callLong - callShort
  const paddingLow = Math.max(putWidth * 2, 2)
  const paddingHigh = Math.max(callWidth * 2, 2)

  // Default price range centered around the strikes + current spot so the
  // visible window always contains the position's critical region AND the
  // current mark-to-market location.
  const rawLow = Math.min(spot, putLong) - paddingLow
  const rawHigh = Math.max(spot, callLong) + paddingHigh
  const low = priceRange?.low ?? Math.max(0.01, rawLow)
  const high = priceRange?.high ?? rawHigh

  // Kink points: the 4 strikes + the range endpoints + current spot.
  // Deduplicate and sort so the polyline renders monotonically in x.
  const kinks = Array.from(
    new Set([low, putLong, putShort, callShort, callLong, spot, high]),
  )
    .filter((p) => p >= low && p <= high && Number.isFinite(p))
    .sort((a, b) => a - b)

  const pnl_curve = kinks.map((price) => ({
    price: Math.round(price * 100) / 100,
    pnl: Math.round(icPayoffAtPrice(price, strikes, entryCredit) * contractMultiplier * 100) / 100,
  }))

  const maxProfit = entryCredit * contractMultiplier
  const maxLossPut = (entryCredit - putWidth) * contractMultiplier // negative
  const maxLossCall = (entryCredit - callWidth) * contractMultiplier // negative
  const maxLoss = Math.min(maxLossPut, maxLossCall)

  const breakevenLow = putShort - entryCredit
  const breakevenHigh = callShort + entryCredit

  const totalWidth = callLong - putLong
  const profitZoneWidth = callShort - putShort
  const pop_heuristic = totalWidth > 0
    ? Math.max(0, Math.min(1, profitZoneWidth / totalWidth))
    : 0

  return {
    pnl_curve,
    max_profit: Math.round(maxProfit * 100) / 100,
    max_loss_put_side: Math.round(maxLossPut * 100) / 100,
    max_loss_call_side: Math.round(maxLossCall * 100) / 100,
    max_loss: Math.round(maxLoss * 100) / 100,
    breakeven_low: Math.round(breakevenLow * 100) / 100,
    breakeven_high: Math.round(breakevenHigh * 100) / 100,
    profit_zone: { low: putShort, high: callShort },
    pop_heuristic: Math.round(pop_heuristic * 10000) / 10000,
  }
}
