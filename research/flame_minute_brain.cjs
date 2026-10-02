'use strict';

// Pure, causal minute controller used only by research.  It receives maps of
// completed bars and never queries a future minute, broker, or order endpoint.
const money = value => Math.round((value + Number.EPSILON) * 10000) / 10000;
const pct = (latest, prior) => latest > 0 && prior > 0 ? (latest / prior - 1) * 100 : null;

function completedFeatures({ spots, vix, asOf }) {
  const needed = [asOf, asOf - 1, asOf - 3, asOf - 5, asOf - 15];
  if (needed.some(minute => !spots.get(minute))) return { valid: false, reason: 'missing_spy_completed_bar' };
  if (needed.some(minute => !(vix.get(minute) > 0))) return { valid: false, reason: 'missing_vix_completed_bar' };
  const window = width => Array.from({ length: width }, (_, index) => spots.get(asOf - index));
  const range = width => {
    const bars = window(width);
    if (bars.some(bar => !(bar?.high > 0 && bar?.low > 0))) return null;
    return (Math.max(...bars.map(bar => bar.high)) / Math.min(...bars.map(bar => bar.low)) - 1) * 100;
  };
  const latest = spots.get(asOf);
  return {
    valid: true,
    asOf,
    spot: latest.close,
    spy1Pct: money(pct(latest.close, spots.get(asOf - 1).close)),
    spy3Pct: money(pct(latest.close, spots.get(asOf - 3).close)),
    spy5Pct: money(pct(latest.close, spots.get(asOf - 5).close)),
    spy15Pct: money(pct(latest.close, spots.get(asOf - 15).close)),
    vix1Pct: money(pct(vix.get(asOf), vix.get(asOf - 1))),
    vix5Pct: money(pct(vix.get(asOf), vix.get(asOf - 5))),
    range5Pct: money(range(5)),
    range15Pct: money(range(15)),
  };
}

function entryDecision({ right, features }) {
  if (!features?.valid) return { action: 'skip', sizeMultiplier: 0, reason: features?.reason || 'minute_inputs_missing' };
  const down = right === 'put';
  const speed = down ? -features.spy1Pct : features.spy1Pct;
  const trend = down ? -features.spy5Pct : features.spy5Pct;
  const drift = down ? -features.spy15Pct : features.spy15Pct;
  const vixJump = features.vix5Pct;
  // Violent immediate movement is not a "better premium" opportunity.
  if (speed >= .18 || trend >= .35 || vixJump >= 1.0 || features.range5Pct >= .45) {
    return { action: 'skip', sizeMultiplier: 0, reason: 'minute_stress', features };
  }
  // A mild deterioration gets another completed minute rather than forcing
  // the entry window to accept the first displayed credit.
  if (speed >= .08 || trend >= .15 || drift >= .25 || vixJump >= .50 || features.range15Pct >= .75) {
    return { action: 'wait', sizeMultiplier: .5, reason: 'minute_caution', features };
  }
  return { action: 'enter', sizeMultiplier: 1, reason: 'minute_stable', features };
}

function positionDecision({ right, credit, markedDebit, shortStrike, features }) {
  if (!features?.valid || !(credit > 0) || !(markedDebit >= 0) || !(shortStrike > 0)) {
    return { action: 'exit', reason: 'minute_inputs_missing' };
  }
  const lossMultiple = markedDebit / credit;
  const strikeDistancePct = right === 'put'
    ? ((features.spot - shortStrike) / features.spot) * 100
    : ((shortStrike - features.spot) / features.spot) * 100;
  const adverseSpeed = right === 'put' ? -features.spy1Pct : features.spy1Pct;
  const adverseTrend = right === 'put' ? -features.spy5Pct : features.spy5Pct;
  // This exits before the existing late assignment guard. It remains a
  // next-minute execution decision; no theoretical fill is assumed here.
  if (lossMultiple >= 1.60 ||
      (strikeDistancePct <= .12 && lossMultiple >= 1.10) ||
      (adverseSpeed >= .16 && adverseTrend >= .25 && features.vix5Pct >= .75 && lossMultiple >= 1.20)) {
    return { action: 'exit', reason: 'minute_risk_exit', lossMultiple: money(lossMultiple), strikeDistancePct: money(strikeDistancePct), features };
  }
  return { action: 'hold', reason: 'minute_hold', lossMultiple: money(lossMultiple), strikeDistancePct: money(strikeDistancePct), features };
}

module.exports = { completedFeatures, entryDecision, positionDecision };
