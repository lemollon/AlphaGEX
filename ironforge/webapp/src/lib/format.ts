/**
 * Shared number formatting utilities for IronForge.
 *
 * All functions return "--" for null, undefined, and NaN.
 * Uses Intl.NumberFormat for locale-aware comma grouping.
 */

const currencyFmt = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
})

const currencyFmt2 = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

/** Format as whole-dollar currency. null → "--", 1357.4 → "$1,357", -769 → "-$769" */
export function formatCurrency(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return '--'
  return currencyFmt.format(n)
}

/** Format as percentage. null → "--", 36.0 → "36.0%", -5.2 → "-5.2%" */
export function formatPct(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return '--'
  return `${n.toFixed(1)}%`
}

/** Format a greek or numeric value with configurable decimals. null → "--", signed. */
export function formatGreek(n: number | null | undefined, decimals = 4): string {
  if (n == null || isNaN(n)) return '--'
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toFixed(decimals)}`
}

/** Format as dollar P&L with sign. null → "--", +$125.50, -$42.00 */
export function formatDollarPnl(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return '--'
  const sign = n > 0 ? '+' : n < 0 ? '-' : ''
  const abs = Math.abs(n)
  return `${sign}${currencyFmt2.format(abs).replace('-', '')}`
}
