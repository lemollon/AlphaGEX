/**
 * Pure formatting for `Money` (ui.tsx) — extracted so the NaN/tiny-value edge
 * cases can be tested without a renderer (see vitest.config.ts's note on why
 * logic lives in plain .ts modules).
 *
 * `null`/`undefined` and non-finite (NaN from a bad API value or an undefined
 * arithmetic result, Infinity) are the SAME "could not load" case — the caller
 * renders a dash for either, never a propagated "-$NaN".
 *
 * A magnitude that rounds to zero at 2 decimal places but is NOT actually zero
 * (e.g. -0.004) gets 4 decimal places instead of 2 — a sign in front of
 * "$0.00" reads as a glitch, not as "slightly negative," and would otherwise
 * erase a real loss into something that looks flat. A value that is genuinely
 * zero still gets the plain 2-decimal "$0.00".
 */
export interface FormattedMoney {
  text: string
  tone: 'pos' | 'neg'
}

export function formatMoney(value: number | null | undefined): FormattedMoney | null {
  if (value == null || !Number.isFinite(value)) return null
  const abs = Math.abs(value)
  const roundsToZero = abs !== 0 && Math.round(abs * 100) / 100 === 0
  const precision = roundsToZero ? 4 : 2
  const sign = value >= 0 ? '+' : '-'
  const text = `${sign}$${abs.toLocaleString('en-US', {
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  })}`
  return { text, tone: value >= 0 ? 'pos' : 'neg' }
}
