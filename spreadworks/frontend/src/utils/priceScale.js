/**
 * Shared price-to-Y mapping used by both CandleChart and PayoffPanel
 * so strike lines align perfectly across the divider.
 */
export const priceToY = (price, minPrice, maxPrice, height) => {
  if (maxPrice === minPrice) return height / 2;
  return height - ((price - minPrice) / (maxPrice - minPrice)) * height;
};

/**
 * Compute the min/max price range from candles + strikes + GEX levels.
 * Adds a buffer so lines don't sit on the edge.
 */
export function computePriceRange(candles, strikes, gexData, bufferPct = 0.005) {
  const prices = [];

  if (candles && candles.length > 0) {
    for (const c of candles) {
      if (c.high != null) prices.push(c.high);
      if (c.low != null) prices.push(c.low);
    }
  }

  if (strikes) {
    for (const s of Object.values(strikes)) {
      if (s) prices.push(Number(s));
    }
  }

  if (gexData) {
    if (gexData.flip_point) prices.push(gexData.flip_point);
    if (gexData.call_wall) prices.push(gexData.call_wall);
    if (gexData.put_wall) prices.push(gexData.put_wall);
  }

  if (prices.length === 0) return { minPrice: 550, maxPrice: 590 };

  let minPrice = Math.min(...prices);
  let maxPrice = Math.max(...prices);
  const buffer = (maxPrice - minPrice) * bufferPct;
  minPrice -= Math.max(buffer, 1);
  maxPrice += Math.max(buffer, 1);

  return { minPrice, maxPrice };
}
