/**
 * GEX wall/level helper — replaces the dead alphagex-api `/api/gex/{symbol}`
 * route (deleted in a964d310 "cleanup: focus AlphaGEX on VALOR and crypto
 * perpetuals"). Computes dealer dollar-gamma exposure directly from a Tradier
 * option chain, the same data IronForge already pulls for tradier.ts
 * getNetGex(). Shared by market-brief.ts and the BLAZE gex-context route so
 * FLINT's daily-context logger can reuse it too.
 *
 * Never fabricates a number: any input gap (no chain, no spot, no OI/gamma
 * for a side) resolves to null on that field rather than a stale/guessed
 * value. Callers render "n/a" for null fields.
 */
import { getQuote, getOptionChainForGex, type GexChainOption } from './tradier'

export interface GexLevels {
  spot: number | null
  /** Net dealer dollar-gamma exposure: sum(call $gamma) - sum(put $gamma). */
  net_gex: number | null
  call_gex: number | null
  put_gex: number | null
  /** Strike with the largest call dollar-gamma — acts as a ceiling/magnet. */
  call_wall: number | null
  /** Strike with the largest put dollar-gamma — acts as a floor/magnet. */
  put_wall: number | null
}

function emptyGexLevels(spot: number | null): GexLevels {
  return { spot, net_gex: null, call_gex: null, put_gex: null, call_wall: null, put_wall: null }
}

/** Strike key with the largest accumulated value in the map, or null if empty. */
function strikeOfMax(byStrike: Map<number, number>): number | null {
  let bestStrike: number | null = null
  let bestVal = -Infinity
  byStrike.forEach((val, strike) => {
    if (val > bestVal) {
      bestVal = val
      bestStrike = strike
    }
  })
  return bestStrike
}

/**
 * Pure per-strike dollar-gamma computation — no I/O, fully unit-testable.
 * Dollar gamma per option = gamma * OI * 100 (contract multiplier) * spot^2 * 0.01
 * (standard GEX convention: dealer $ P&L per 1% move in the underlying).
 * Empty `options` or non-positive `spot` -> all-null GexLevels.
 */
export function computeGexLevels(options: GexChainOption[], spot: number | null): GexLevels {
  if (!spot || spot <= 0 || options.length === 0) return emptyGexLevels(spot ?? null)

  const callByStrike = new Map<number, number>()
  const putByStrike = new Map<number, number>()

  for (const o of options) {
    if (!Number.isFinite(o.gamma) || !Number.isFinite(o.oi) || o.gamma <= 0 || o.oi <= 0) continue
    const dollarGamma = o.gamma * o.oi * 100 * spot * spot * 0.01
    const byStrike = o.type === 'call' ? callByStrike : putByStrike
    byStrike.set(o.strike, (byStrike.get(o.strike) ?? 0) + dollarGamma)
  }

  if (callByStrike.size === 0 && putByStrike.size === 0) return emptyGexLevels(spot)

  const callGex = Array.from(callByStrike.values()).reduce((a, b) => a + b, 0)
  const putGex = Array.from(putByStrike.values()).reduce((a, b) => a + b, 0)

  return {
    spot,
    net_gex: callGex - putGex,
    call_gex: callByStrike.size > 0 ? callGex : null,
    put_gex: putByStrike.size > 0 ? putGex : null,
    call_wall: strikeOfMax(callByStrike),
    put_wall: strikeOfMax(putByStrike),
  }
}

/** Same regime buckets the old blaze/gex-client.ts derived from net GEX. */
export function regimeFromNetGex(netGex: number): string {
  if (netGex <= -3e9) return 'EXTREME_NEGATIVE'
  if (netGex <= -2e9) return 'HIGH_NEGATIVE'
  if (netGex <= -1e9) return 'MODERATE_NEGATIVE'
  if (netGex >= 3e9) return 'EXTREME_POSITIVE'
  if (netGex >= 2e9) return 'HIGH_POSITIVE'
  if (netGex >= 1e9) return 'MODERATE_POSITIVE'
  return 'NEUTRAL'
}

/**
 * Fetches spot + the option chain from Tradier and computes GEX levels.
 * Never throws — any failure degrades to emptyGexLevels(spot ?? null) so
 * callers can render "n/a" instead of crashing or inventing a number.
 */
export async function fetchGexLevels(symbol = 'SPY', maxDte = 45): Promise<GexLevels> {
  let spot: number | null = null
  try {
    const q = await getQuote(symbol)
    spot = q?.last ?? null
  } catch {
    spot = null
  }
  let chain: GexChainOption[] = []
  try {
    chain = await getOptionChainForGex(symbol, maxDte)
  } catch {
    chain = []
  }
  return computeGexLevels(chain, spot)
}
