/**
 * Shared price-to-Y mapping used by both CandleChart and PayoffPanel
 * so strike lines align perfectly across the divider.
 */
export const priceToY = (price, minPrice, maxPrice, height) => {
  if (maxPrice === minPrice) return height / 2;
  return height - ((price - minPrice) / (maxPrice - minPrice)) * height;
};

/**
 * How far from spot a GEX level (flip point / call wall / put wall) may sit and
 * still be allowed to widen the price axis.
 *
 * Upstream GEX snapshots occasionally go bad — on 2026-07-27 the builder served
 * a flip point of $540 while SPY traded at $739. Feeding that straight into the
 * axis stretched the scale over 200 points, collapsing every candle and the
 * payoff curve into a sliver at the top of the chart. A level further out than
 * this is dropped from the domain; CandleChart already skips drawing lines that
 * fall outside [minPrice, maxPrice], so a bad level goes quiet instead of
 * destroying the view. A genuinely distant level still renders once the user
 * widens RANGE enough to cover it.
 */
const GEX_AXIS_MAX_DRIFT_PCT = 0.05;

/**
 * Compute the min/max price range from candles + strikes + GEX levels.
 * Adds a buffer so lines don't sit on the edge.
 *
 * `spotPrice` anchors the GEX sanity check; when it's absent the midpoint of
 * the candle/strike range is used instead.
 */
export function computePriceRange(candles, strikes, gexData, bufferPct = 0.005, spotPrice = null) {
  const prices = [];

  if (candles && candles.length > 0) {
    for (const c of candles) {
      if (c.high != null) prices.push(c.high);
      if (c.low != null) prices.push(c.low);
    }
  }

  if (strikes) {
    for (const s of Object.values(strikes)) {
      const n = Number(s);
      if (s && !isNaN(n) && isFinite(n)) prices.push(n);
    }
  }

  if (gexData) {
    // Anchor for the sanity check: spot if we have it, else the middle of what
    // we've collected so far. With neither, there's nothing to judge against,
    // so the levels are the only price information available and go in as-is.
    const anchor = Number(spotPrice) > 0
      ? Number(spotPrice)
      : prices.length > 0
        ? (Math.min(...prices) + Math.max(...prices)) / 2
        : null;
    const maxDrift = anchor ? anchor * GEX_AXIS_MAX_DRIFT_PCT : Infinity;

    for (const level of [gexData.flip_point, gexData.call_wall, gexData.put_wall]) {
      const n = Number(level);
      if (!level || isNaN(n) || !isFinite(n)) continue;
      if (anchor && Math.abs(n - anchor) > maxDrift) continue;
      prices.push(n);
    }
  }

  if (prices.length === 0) return { minPrice: 550, maxPrice: 590 };

  let minPrice = Math.min(...prices);
  let maxPrice = Math.max(...prices);
  const buffer = (maxPrice - minPrice) * bufferPct;
  minPrice -= Math.max(buffer, 1);
  maxPrice += Math.max(buffer, 1);

  return { minPrice, maxPrice };
}
