import type { StrikeGex } from './types'

type MiniStrike = Pick<StrikeGex, 'strike' | 'net_gamma'>

/**
 * Top-N strikes above (resistance) and below (support) price, ranked by |net_gamma|.
 * `bandPct` (e.g. 0.05 = ±5%) restricts candidates to a band around price so noisy
 * far-OTM gamma spikes can't masquerade as the key level. Omit/0 = whole chain.
 */
export function topStrikesByGamma(
  strikes: MiniStrike[],
  price: number,
  n: number,
  bandPct = 0,
): { resistance: MiniStrike[]; support: MiniStrike[] } {
  const lo = bandPct > 0 && price > 0 ? price * (1 - bandPct) : -Infinity
  const hi = bandPct > 0 && price > 0 ? price * (1 + bandPct) : Infinity
  const inBand = strikes.filter((s) => s.strike >= lo && s.strike <= hi)
  const above = inBand.filter((s) => s.strike > price)
  const below = inBand.filter((s) => s.strike < price)
  const byAbsGammaDesc = (a: MiniStrike, b: MiniStrike) =>
    Math.abs(b.net_gamma) - Math.abs(a.net_gamma)
  // Order by |gamma| descending (strongest level first) — matches the
  // TradingVolatility "Resist/Support: strike (gamma), ..." convention.
  const resistance = [...above].sort(byAbsGammaDesc).slice(0, n)
  const support = [...below].sort(byAbsGammaDesc).slice(0, n)
  return { resistance, support }
}

/**
 * Daily 1-sigma expected move from spot and 30-day vol (VIX), the standard
 * `S · σ · √(1/252)`. Stable and correct, unlike the engine's intraday
 * expected_move which can swing wildly on noisy ATM IV.
 */
export function computeDailyExpectedMove(
  price: number,
  vix: number | null,
): { move: number; lower: number | null; upper: number | null } {
  if (!price || price <= 0 || !vix || vix <= 0) return { move: 0, lower: null, upper: null }
  const move = price * (vix / 100) * Math.sqrt(1 / 252)
  return { move, lower: price - move, upper: price + move }
}

export interface ReactionInput {
  gammaForm: string
  price: number
  flip: number | null
  callWall: number | null
  putWall: number | null
  balanceLabel: string
}

export interface ReactionFrameworkText {
  baseCase: string
  invalidatedIf: string
  notes: string[]
}

/** Deterministic Base Case / Invalidated-if narrative from regime + structure. */
export function buildReactionFramework(input: ReactionInput): ReactionFrameworkText {
  const { gammaForm, price, flip, callWall, putWall } = input
  const aboveFlip = flip != null ? price > flip : null
  const notes: string[] = []
  let baseCase: string
  let invalidatedIf: string

  if (gammaForm === 'NEGATIVE') {
    baseCase =
      'Negative gamma — dealers are short gamma. Expect trend / acceleration and wider ranges; favor directional plays.'
    invalidatedIf = 'Price reclaims the GEX flip and gamma turns positive (mean-reversion resumes).'
  } else if (gammaForm === 'POSITIVE') {
    baseCase =
      'Positive gamma — dealers are long gamma. Chop / pin until a catalyst; favor selling premium inside the expected range.'
    invalidatedIf = 'Vol shock or strong flow pushes cleanly through the call or put wall.'
  } else {
    baseCase = 'Neutral gamma — no strong dealer positioning. Rangebound unless a catalyst expands volatility.'
    invalidatedIf = 'A directional flow or vol expansion breaks the balance.'
  }

  if (aboveFlip === false) {
    notes.push(`Price is below the GEX flip${flip != null ? ` ($${flip.toFixed(0)})` : ''} — downside acceleration risk.`)
  } else if (aboveFlip === true) {
    notes.push(`Price is above the GEX flip${flip != null ? ` ($${flip.toFixed(0)})` : ''} — positive-gamma support.`)
  }
  if (callWall && price) {
    const d = ((callWall - price) / price) * 100
    if (d > 0 && d < 0.5) notes.push(`Call wall $${callWall.toFixed(0)} is ${d.toFixed(1)}% away — watch for rejection.`)
  }
  if (putWall && price) {
    const d = ((price - putWall) / price) * 100
    if (d > 0 && d < 0.5) notes.push(`Put wall $${putWall.toFixed(0)} is ${d.toFixed(1)}% away — watch for a bounce.`)
  }

  return { baseCase, invalidatedIf, notes }
}
