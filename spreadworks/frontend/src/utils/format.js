/**
 * Number formatting utilities for SpreadWorks.
 * All functions return "--" for null, undefined, or NaN inputs.
 */

const currFmt = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 0,
  minimumFractionDigits: 0,
});

const currFmt2 = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
});

function _bad(n) {
  return n == null || typeof n !== 'number' || !isFinite(n);
}

/**
 * Unsigned currency: "$1,357" or "$769".
 * Always positive — caller handles sign/prefix.
 */
export function formatCurrency(n) {
  if (_bad(n)) return '--';
  return '$' + currFmt.format(Math.abs(n));
}

/**
 * Unsigned currency with cents: "$1,357.42".
 */
export function formatCurrency2(n) {
  if (_bad(n)) return '--';
  return '$' + currFmt2.format(Math.abs(n));
}

/**
 * Signed P&L dollar: "+$1,357" or "-$769".
 */
export function formatDollarPnl(n) {
  if (_bad(n)) return '--';
  const sign = n >= 0 ? '+' : '-';
  return sign + '$' + currFmt.format(Math.abs(n));
}

/**
 * Percentage from a 0-1 ratio: 0.36 → "36.0%".
 * If value is already > 1 (i.e. pre-multiplied), pass raw=true.
 */
export function formatPct(n, { raw = false } = {}) {
  if (_bad(n)) return '--';
  const val = raw ? n : n * 100;
  return val.toFixed(1) + '%';
}

/**
 * Signed percentage: "+36.0%" or "-12.3%".
 * Expects pre-multiplied value (already in % scale).
 */
export function formatSignedPct(n) {
  if (_bad(n)) return '--';
  const sign = n >= 0 ? '+' : '';
  return sign + n.toFixed(1) + '%';
}

/**
 * Greek value: "+0.0034" (signed, fixed decimals).
 */
export function formatGreek(n, decimals = 4) {
  if (_bad(n)) return '--';
  const sign = n >= 0 ? '+' : '';
  return sign + n.toFixed(decimals);
}

/**
 * Greek dollar value (theta/vega after *100 multiplier): "$1.23" or "-$0.50".
 */
export function formatGreekDollar(n) {
  if (_bad(n)) return '--';
  const val = n * 100;
  const sign = val < 0 ? '-' : '';
  return sign + '$' + Math.abs(val).toFixed(2);
}
