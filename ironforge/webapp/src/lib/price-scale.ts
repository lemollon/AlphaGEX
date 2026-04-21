/**
 * Shared price-to-Y mapping + price-range computation.
 * Ported verbatim from spreadworks/frontend/src/utils/priceScale.js.
 *
 * Used by BOTH CandleChart and PayoffPanel so strike lines align perfectly
 * across the flexbox divider (same minPrice/maxPrice props → identical
 * Y coordinate for any given price).
 */

export function priceToY(price: number, minPrice: number, maxPrice: number, height: number): number {
  if (maxPrice === minPrice) return height / 2
  return height - ((price - minPrice) / (maxPrice - minPrice)) * height
}

export interface StrikeSet {
  // SpreadWorks-style keys (retained for 1:1 parity with the ported
  // components) — kept alongside the IronForge-native snake-case keys.
  longPutStrike?: number | null
  longCallStrike?: number | null
  shortPutStrike?: number | null
  shortCallStrike?: number | null
}

export interface GexLevels {
  flip_point?: number | null
  call_wall?: number | null
  put_wall?: number | null
}

export interface Candle {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

/**
 * Min/max price spanning candles + strikes + (optional) GEX levels.
 * Adds a small buffer so lines don't sit flush against the chart edge.
 */
export function computePriceRange(
  candles: Candle[] | null | undefined,
  strikes: StrikeSet | null | undefined,
  gexData: GexLevels | null | undefined,
  bufferPct = 0.005,
): { minPrice: number; maxPrice: number } {
  const prices: number[] = []

  if (candles && candles.length > 0) {
    for (const c of candles) {
      if (c.high != null) prices.push(c.high)
      if (c.low != null) prices.push(c.low)
    }
  }

  if (strikes) {
    for (const s of Object.values(strikes)) {
      const n = Number(s)
      if (s != null && !isNaN(n) && isFinite(n)) prices.push(n)
    }
  }

  if (gexData) {
    if (gexData.flip_point != null) prices.push(gexData.flip_point)
    if (gexData.call_wall != null) prices.push(gexData.call_wall)
    if (gexData.put_wall != null) prices.push(gexData.put_wall)
  }

  if (prices.length === 0) return { minPrice: 550, maxPrice: 590 }

  let minPrice = Math.min(...prices)
  let maxPrice = Math.max(...prices)
  const buffer = (maxPrice - minPrice) * bufferPct
  minPrice -= Math.max(buffer, 1)
  maxPrice += Math.max(buffer, 1)

  return { minPrice, maxPrice }
}
