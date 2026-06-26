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
 *
 * `strategy` is optional — only SURGE (pin_drift_combo) needs it, because its
 * 8-leg combo can't be inferred from leg shape alone (the calendar legs collide
 * with the butterfly in the 4-slot put/call topology below).
 */
export function parseLegs(legs, strategy) {
  if (!Array.isArray(legs) || legs.length === 0) return null;

  // SURGE / pin_drift_combo: butterfly (front) + a call calendar + a put
  // calendar. The calendars share strikes/types with the butterfly side, so
  // the generic topology below clobbers slots and draws nonsense. Map only the
  // butterfly CORE — long wings + short body — onto the geometry. The calendar
  // strikes are surfaced separately (see legGroups / extraStrikes) and by the
  // payoff curve, so the chart stays readable. Legs are in build order (see
  // PinDriftComboSignal.legs()): 0 lower wing, 1-2 body (x2), 3 upper wing.
  if (strategy === 'pin_drift_combo' && legs.length >= 4) {
    const lower = Number(legs[0].strike);
    const body = Number(legs[1].strike);
    const upper = Number(legs[3].strike);
    return { longPut: lower, shortPut: body, shortCall: body, longCall: upper };
  }

  // Single-type butterfly (RIVER): every leg shares one option type, with
  // long wings + a short body (sold twice). Map wings -> long slots and the
  // body -> both short slots so the chart draws lower/upper as long strikes
  // and the body as a single short strike (dedup collapses the doubled body).
  const types = new Set(legs.map(l => l.type));
  if (types.size === 1) {
    const optType = legs[0].type;
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
    // Two-leg vertical spread (UNDERTOW debit / DELTA credit): one long + one
    // short of a single option type. Map each leg to its natural call/put slot
    // so the chart colors the long strike green and the short strike red; the
    // opposite-type slots stay null and the Y-axis derives its range from the
    // defined strikes only.
    if (longs.length === 1 && shorts.length === 1) {
      const out = { longPut: null, shortPut: null, shortCall: null, longCall: null };
      if (optType === 'call') {
        out.longCall = longs[0];
        out.shortCall = shorts[0];
      } else {
        out.longPut = longs[0];
        out.shortPut = shorts[0];
      }
      return out;
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

/** Keep a single raw leg's display fields (incl. expiration, which
 *  normalizeLegs drops — calendars need it to distinguish front vs back). */
function rawLeg(lg) {
  return {
    side: lg.side,
    type: lg.type,
    strike: Number(lg.strike),
    qty: 1,
    expiration: lg.expiration ?? null,
  };
}

/**
 * Split a position's legs into labeled sub-structures for display.
 *
 * Most strategies are a single structure, so this returns one unlabeled group.
 * SURGE (pin_drift_combo) is a butterfly PLUS two calendars — without grouping
 * you can't tell which strike belongs to which leg-set. Legs are in build order
 * (PinDriftComboSignal.legs()):
 *   0 fly lower, 1-2 fly body (x2), 3 fly upper,
 *   4 call-cal front short, 5 call-cal back long,
 *   6 put-cal  front short, 7 put-cal  back long.
 *
 * Returns [{ label, note, legs: [{ side, type, strike, qty, expiration }] }].
 */
export function legGroups(legs, strategy) {
  if (!Array.isArray(legs) || legs.length === 0) return [];

  if (strategy === 'pin_drift_combo' && legs.length >= 8) {
    return [
      { label: 'Butterfly', note: 'pin', legs: normalizeLegs(legs.slice(0, 4)) },
      { label: 'Call calendar', note: 'drift up', legs: legs.slice(4, 6).map(rawLeg) },
      { label: 'Put calendar', note: 'drift down', legs: legs.slice(6, 8).map(rawLeg) },
    ];
  }

  // Single-structure strategies: one group of the true distinct legs.
  return [{ label: null, note: null, legs: normalizeLegs(legs) }];
}
