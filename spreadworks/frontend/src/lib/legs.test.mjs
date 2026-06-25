// Standalone node test (no test framework wired in this app):
//   node src/lib/legs.test.mjs
import assert from 'node:assert/strict';
import { parseLegs, normalizeLegs } from './legs.js';

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

console.log('legs.test.mjs: all assertions passed');
