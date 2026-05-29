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
