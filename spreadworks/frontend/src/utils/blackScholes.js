/**
 * Client-side Black-Scholes for instant DTE slider interpolation.
 * Used for approximate payoff recalculation when the slider moves.
 */

function normCdf(x) {
  const a1 = 0.254829592;
  const a2 = -0.284496736;
  const a3 = 1.421413741;
  const a4 = -1.453152027;
  const a5 = 1.061405429;
  const p = 0.3275911;
  const sign = x < 0 ? -1 : 1;
  x = Math.abs(x) / Math.sqrt(2);
  const t = 1.0 / (1.0 + p * x);
  const y = 1.0 - ((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
  return 0.5 * (1.0 + sign * y);
}

export function bsCallPrice(S, K, T, r, sigma) {
  if (T <= 0) return Math.max(S - K, 0);
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * Math.sqrt(T));
  const d2 = d1 - sigma * Math.sqrt(T);
  return S * normCdf(d1) - K * Math.exp(-r * T) * normCdf(d2);
}

export function bsPutPrice(S, K, T, r, sigma) {
  if (T <= 0) return Math.max(K - S, 0);
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * Math.sqrt(T));
  const d2 = d1 - sigma * Math.sqrt(T);
  return K * Math.exp(-r * T) * normCdf(-d2) - S * normCdf(-d1);
}

/**
 * Calculate DD payoff at a given DTE for an array of price points.
 * legs = { longPut, shortPut, shortCall, longCall }
 * shortDte = DTE for short legs, longDte = DTE for long legs
 * Returns [{price, pnl}, ...]
 */
export function calcDDPayoff(legs, spotPrice, shortDte, longDte, iv, r = 0.05, numPoints = 80) {
  const { longPut, shortPut, shortCall, longCall } = legs;
  if (!longPut || !shortPut || !shortCall || !longCall) return [];

  const lp = Number(longPut), sp = Number(shortPut);
  const sc = Number(shortCall), lc = Number(longCall);
  const sigma = iv || 0.25;
  const Tshort = Math.max(shortDte / 365, 0.0001);
  const Tlong = Math.max(longDte / 365, 0.0001);

  // Entry cost (at current spot and full DTE)
  const entryLongPut = bsPutPrice(spotPrice, lp, Tlong, r, sigma);
  const entryShortPut = bsPutPrice(spotPrice, sp, Tshort, r, sigma);
  const entryShortCall = bsCallPrice(spotPrice, sc, Tshort, r, sigma);
  const entryLongCall = bsCallPrice(spotPrice, lc, Tlong, r, sigma);
  const netDebit = (entryLongPut - entryShortPut) + (entryLongCall - entryShortCall);

  const range = (lc - lp) * 0.3;
  const lo = lp - range;
  const hi = lc + range;
  const step = (hi - lo) / numPoints;

  const curve = [];
  for (let i = 0; i <= numPoints; i++) {
    const price = lo + step * i;
    // Value at evaluation DTE
    const valLongPut = bsPutPrice(price, lp, Tlong, r, sigma);
    const valShortPut = bsPutPrice(price, sp, Tshort, r, sigma);
    const valShortCall = bsCallPrice(price, sc, Tshort, r, sigma);
    const valLongCall = bsCallPrice(price, lc, Tlong, r, sigma);
    const posValue = (valLongPut - valShortPut) + (valLongCall - valShortCall);
    const pnl = (posValue - netDebit) * 100; // per contract
    curve.push({ price, pnl });
  }

  return curve;
}
