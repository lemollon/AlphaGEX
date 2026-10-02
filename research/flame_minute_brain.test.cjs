'use strict';
const assert = require('node:assert/strict');
const B = require('./flame_minute_brain.cjs');

function tape({ drop = 0, vixJump = 0 }) {
  const spots = new Map(), vix = new Map();
  for (let minute = 100; minute <= 120; minute++) {
    const close = 500 + (minute === 120 ? drop : 0);
    spots.set(minute, { open: close, high: close + .05, low: close - .05, close });
    vix.set(minute, 20 + (minute === 120 ? vixJump : 0));
  }
  return { spots, vix };
}
{
  const { spots, vix } = tape({ drop: -2, vixJump: .3 });
  const features = B.completedFeatures({ spots, vix, asOf: 120 });
  assert.equal(features.valid, true);
  assert.equal(B.entryDecision({ right: 'put', features }).action, 'skip');
}
{
  const { spots, vix } = tape({ drop: -.5, vixJump: .1 });
  const features = B.completedFeatures({ spots, vix, asOf: 120 });
  assert.equal(B.entryDecision({ right: 'put', features }).action, 'wait');
}
{
  const { spots, vix } = tape({ drop: -.1, vixJump: 0 });
  const features = B.completedFeatures({ spots, vix, asOf: 120 });
  assert.equal(B.entryDecision({ right: 'put', features }).action, 'enter');
  assert.equal(B.positionDecision({ right: 'put', credit: .30, markedDebit: .52, shortStrike: 499, features }).action, 'exit');
}
{
  const { spots, vix } = tape({}); spots.delete(115);
  assert.equal(B.completedFeatures({ spots, vix, asOf: 120 }).valid, false, 'missing completed input fails closed');
}
console.log(JSON.stringify({ passed: true, cases: 'causal minute features, stable/caution/stress entry, early risk exit, fail-closed missing input' }));
