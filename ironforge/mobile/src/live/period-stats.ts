/**
 * Formatting for the Forge tab's Today / This Week / This Month / Lifetime
 * stats row (APP-002 stats card).
 *
 * Extracted from the screen so the display rule can be TESTED rather than
 * trusted: whole dollars, one shared size for all four figures, a sign only
 * when the number is non-zero, and a dash reserved for ONE case — the number
 * could not be loaded. "$0" is a real, honest answer (nothing closed in that
 * window yet) and must never be confused with "—" (the request failed).
 */

export type PeriodTone = 'pos' | 'neg' | 'zero' | 'na'

/** `null`/`undefined` means "could not load" — the one case that gets a dash. */
export function formatPeriodValue(value: number | null | undefined): string {
  if (value == null) return '—'
  const rounded = Math.round(value)
  if (rounded === 0) return '$0'
  const sign = rounded > 0 ? '+' : '−' // real minus sign, not a hyphen
  return `${sign}$${Math.abs(rounded).toLocaleString('en-US')}`
}

export function periodTone(value: number | null | undefined): PeriodTone {
  if (value == null) return 'na'
  const rounded = Math.round(value)
  if (rounded === 0) return 'zero'
  return rounded > 0 ? 'pos' : 'neg'
}
