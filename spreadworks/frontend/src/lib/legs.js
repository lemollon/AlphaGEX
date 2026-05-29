// Leg parsing for the bot Strategy Chart.
//
// Two views of a position's legs:
//   parseLegs()     -> geometry slot map { longPut, shortPut, shortCall, longCall }
//                      consumed by the chart's strike lines + Y-axis range.
//   normalizeLegs() -> the TRUE legs as [{ side, type, strike, qty }] for accurate
//                      leg chips (correct option type + quantity).
//
// The chart was originally built around the four-slot put/call topology shared
// by Iron Condor / Iron Butterfly / Double Calendar / Double Diagonal. RIVER's
// long (debit) butterfly breaks that assumption: it is a SINGLE option type
// (all calls OR all puts) with two long wings and a body sold twice. parseLegs
// maps that onto the geometry slots so the chart renders — the wings are the
// long strikes, the body is the short strike — while normalizeLegs preserves
// the real option type/quantity for display.

/**
 * Map a position's legs onto the chart geometry slots.
 * Returns { longPut, shortPut, shortCall, longCall } (numbers) or null when the
 * legs can't be interpreted.
 */
export function parseLegs(legs) {
  if (!Array.isArray(legs) || legs.length === 0) return null;

  // Single-type butterfly (RIVER): every leg shares one option type, with
  // long wings + a short body (sold twice). Map wings -> long slots and the
  // body -> both short slots so the chart draws lower/upper as long strikes
  // and the body as a single short strike (dedup collapses the doubled body).
  const types = new Set(legs.map(l => l.type));
  if (types.size === 1) {
    const longs = legs
      .filter(l => l.side === 'long')
      .map(l => Number(l.strike))
      .sort((a, b) => a - b);
    const shorts = legs.filter(l => l.side === 'short').map(l => Number(l.strike));
    if (longs.length >= 2 && shorts.length >= 1) {
      const body = shorts[0];
      return {
        longPut: longs[0],                 // lower wing (long)
        shortPut: body,                    // body (short) — deduped in chart
        shortCall: body,                   // body (short)
        longCall: longs[longs.length - 1], // upper wing (long)
      };
    }
    return null;
  }

  // Standard put/call topology: one leg per long/short × put/call slot.
  const out = { longPut: null, shortPut: null, shortCall: null, longCall: null };
  for (const lg of legs) {
    const k = (lg.side === 'long' ? 'long' : 'short') + (lg.type === 'call' ? 'Call' : 'Put');
    out[k] = Number(lg.strike);
  }
  if ([out.longPut, out.shortPut, out.shortCall, out.longCall].some(v => v == null)) {
    return null;
  }
  return out;
}

/**
 * Collapse a position's legs into the true distinct legs with a quantity,
 * sorted by strike. e.g. a RIVER call fly -> [{long,call,498,1},
 * {short,call,501,2}, {long,call,504,1}].
 */
export function normalizeLegs(legs) {
  if (!Array.isArray(legs)) return [];
  const map = new Map();
  for (const lg of legs) {
    const strike = Number(lg.strike);
    const key = `${lg.side}-${lg.type}-${strike}`;
    const existing = map.get(key);
    if (existing) existing.qty += 1;
    else map.set(key, { side: lg.side, type: lg.type, strike, qty: 1 });
  }
  return Array.from(map.values()).sort((a, b) => a.strike - b.strike);
}
