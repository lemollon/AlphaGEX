// Standalone node test (no test framework wired in this app):
//   node src/lib/legs.test.mjs
import assert from 'node:assert/strict';
import { parseLegs, normalizeLegs, legGroups } from './legs.js';

const riverCallFly = [
  { side: 'long',  type: 'call', strike: 498 },
  { side: 'short', type: 'call', strike: 501 },
  { side: 'short', type: 'call', strike: 501 },
  { side: 'long',  type: 'call', strike: 504 },
];
const riverPutFly = riverCallFly.map(l => ({ ...l, type: 'put' }));
const breezeIB = [
  { side: 'short', type: 'call', strike: 500 },
  { side: 'short', type: 'put',  strike: 500 },
  { side: 'long',  type: 'call', strike: 505 },
  { side: 'long',  type: 'put',  strike: 495 },
];

// RIVER butterfly maps onto geometry slots: wings -> long, body -> short.
assert.deepEqual(parseLegs(riverCallFly),
  { longPut: 498, shortPut: 501, shortCall: 501, longCall: 504 },
  'call fly geometry');
assert.deepEqual(parseLegs(riverPutFly),
  { longPut: 498, shortPut: 501, shortCall: 501, longCall: 504 },
  'put fly geometry');

// Standard IB still parses exactly as before (regression guard).
assert.deepEqual(parseLegs(breezeIB),
  { longPut: 495, shortPut: 500, shortCall: 500, longCall: 505 },
  'IB geometry unchanged');

// UNDERTOW bull call spread (debit): long lower call + short upper call.
const undertowBCS = [
  { side: 'long',  type: 'call', strike: 550 },
  { side: 'short', type: 'call', strike: 570 },
];
assert.deepEqual(parseLegs(undertowBCS),
  { longPut: null, shortPut: null, shortCall: 570, longCall: 550 },
  'bull call spread maps onto call slots');

// DELTA bull put spread (credit): short upper put + long lower put.
const deltaBPS = [
  { side: 'long',  type: 'put', strike: 485 },
  { side: 'short', type: 'put', strike: 505 },
];
assert.deepEqual(parseLegs(deltaBPS),
  { longPut: 485, shortPut: 505, shortCall: null, longCall: null },
  'bull put spread maps onto put slots');

// Bear call spread (credit): short lower call + long upper call.
const bearCall = [
  { side: 'short', type: 'call', strike: 550 },
  { side: 'long',  type: 'call', strike: 570 },
];
assert.deepEqual(parseLegs(bearCall),
  { longPut: null, shortPut: null, shortCall: 550, longCall: 570 },
  'bear call spread maps onto call slots');

// Verticals normalize to their two true legs.
assert.deepEqual(normalizeLegs(undertowBCS), [
  { side: 'long',  type: 'call', strike: 550, qty: 1 },
  { side: 'short', type: 'call', strike: 570, qty: 1 },
], 'bull call spread normalized');

// Degenerate input returns null.
assert.equal(parseLegs([]), null);
assert.equal(parseLegs(null), null);

// normalizeLegs collapses the doubled body and reports the true type/qty.
assert.deepEqual(normalizeLegs(riverCallFly), [
  { side: 'long',  type: 'call', strike: 498, qty: 1 },
  { side: 'short', type: 'call', strike: 501, qty: 2 },
  { side: 'long',  type: 'call', strike: 504, qty: 1 },
], 'call fly normalized');

assert.equal(normalizeLegs(breezeIB).length, 4, 'IB has 4 distinct legs');

// SURGE (pin_drift_combo): butterfly (front/0DTE) + call & put calendars.
// Build order per PinDriftComboSignal.legs().
const surge = [
  { side: 'long',  type: 'call', strike: 500, expiration: '2026-06-26' }, // fly lower
  { side: 'short', type: 'call', strike: 505, expiration: '2026-06-26' }, // fly body
  { side: 'short', type: 'call', strike: 505, expiration: '2026-06-26' }, // fly body
  { side: 'long',  type: 'call', strike: 510, expiration: '2026-06-26' }, // fly upper
  { side: 'short', type: 'call', strike: 508, expiration: '2026-06-26' }, // call cal front
  { side: 'long',  type: 'call', strike: 508, expiration: '2026-06-29' }, // call cal back
  { side: 'short', type: 'put',  strike: 502, expiration: '2026-06-26' }, // put cal front
  { side: 'long',  type: 'put',  strike: 502, expiration: '2026-06-29' }, // put cal back
];

// Without the strategy hint the generic topology would clobber slots; WITH it,
// parseLegs maps the butterfly core (wings long, body short).
assert.deepEqual(parseLegs(surge, 'pin_drift_combo'),
  { longPut: 500, shortPut: 505, shortCall: 505, longCall: 510 },
  'SURGE maps butterfly core onto geometry');

// legGroups splits SURGE into its three labeled sub-structures.
const groups = legGroups(surge, 'pin_drift_combo');
assert.equal(groups.length, 3, 'SURGE has 3 sub-structures');
assert.deepEqual(groups[0].legs, [
  { side: 'long',  type: 'call', strike: 500, qty: 1 },
  { side: 'short', type: 'call', strike: 505, qty: 2 },
  { side: 'long',  type: 'call', strike: 510, qty: 1 },
], 'butterfly group = wings + doubled body');
assert.equal(groups[1].label, 'Call calendar');
assert.equal(groups[1].legs.length, 2, 'call calendar = front + back');
assert.equal(groups[1].legs[0].strike, 508);
assert.equal(groups[2].label, 'Put calendar');
assert.equal(groups[2].legs[1].expiration, '2026-06-29', 'calendar keeps back expiration');

// Non-combo strategies fall back to a single unlabeled group.
const single = legGroups(breezeIB, 'iron_butterfly');
assert.equal(single.length, 1, 'IB is one group');
assert.equal(single[0].label, null, 'single group is unlabeled');
assert.equal(single[0].legs.length, 4, 'IB group has 4 legs');

console.log('legs.test.mjs: all assertions passed');
