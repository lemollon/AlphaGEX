/**
 * Bot Ledger — exact integer arithmetic.
 *
 * WHY NO FLOATS, AND WHY NO decimal.js:
 *
 * `pg` returns NUMERIC columns as JavaScript *strings* (it does not parse OID
 * 1700). So a value arrives as '42.37' and can be converted straight to the
 * integer 4237 by string manipulation — a float is never constructed, and the
 * `Math.round(0.1 * 3 * 100)` class of bug cannot occur.
 *
 * decimal.js would not help: the only genuinely inexact operations here are
 * `pnl / contracts` and `net / bp`, which are non-terminating in general. A
 * decimal library just moves the rounding to a configured precision — you still
 * have to choose a rounding point. Meanwhile every ratio we publish can be
 * computed in pure integers (`divRoundHalfAway(n * 10000, d)`), with products
 * bounded far below Number.MAX_SAFE_INTEGER. So the dependency would buy
 * nothing, and this app ships 8 production dependencies on purpose.
 *
 * Rounding is HALF AWAY FROM ZERO everywhere — the way a reader rounds by hand.
 * A proof page has to be hand-checkable.
 */

/** Largest magnitude we accept before refusing to do exact integer math. */
const SAFE_LIMIT = Number.MAX_SAFE_INTEGER

export class LedgerMathError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'LedgerMathError'
  }
}

/**
 * Parse a Postgres NUMERIC (delivered as a string) into integer cents.
 *
 * Accepts an optional sign, digits, and an optional fractional part of any
 * length; anything past the second decimal is rounded half away from zero.
 * Throws on anything that is not a plain decimal number — a public KPI must
 * never be derived from a value we could not parse.
 */
export function centsFromNumericString(v: unknown): number {
  if (v === null || v === undefined) throw new LedgerMathError('numeric is null')

  // pg hands back strings for NUMERIC, but INT columns arrive as numbers.
  const raw = typeof v === 'number' ? (Number.isInteger(v) ? String(v) : v.toFixed(6)) : String(v).trim()

  const m = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(raw)
  if (!m) throw new LedgerMathError(`not a decimal number: ${JSON.stringify(v)}`)

  const negative = m[1] === '-'
  const intPart = m[2]
  const frac = m[3] ?? ''

  const whole = Number(intPart)
  if (!Number.isSafeInteger(whole) || whole > SAFE_LIMIT / 100) {
    throw new LedgerMathError(`numeric out of safe range: ${raw}`)
  }

  const centDigits = Number((frac + '00').slice(0, 2))
  // Round on the third decimal, half away from zero.
  const roundUp = frac.length > 2 && Number(frac[2]) >= 5
  const magnitude = whole * 100 + centDigits + (roundUp ? 1 : 0)

  return negative ? -magnitude : magnitude
}

/**
 * Integer division rounded half away from zero. Exact for |2a| + |b| within
 * Number.MAX_SAFE_INTEGER.
 *
 * divRoundHalfAway(5, 2)  ===  3
 * divRoundHalfAway(-5, 2) === -3
 * divRoundHalfAway(1, 3)  ===  0
 */
export function divRoundHalfAway(a: number, b: number): number {
  if (!Number.isFinite(a) || !Number.isFinite(b)) throw new LedgerMathError('non-finite operand')
  if (b === 0) throw new LedgerMathError('division by zero')
  if (!Number.isInteger(a) || !Number.isInteger(b)) throw new LedgerMathError('non-integer operand')

  const A = Math.abs(a)
  const B = Math.abs(b)
  if (2 * A + B > SAFE_LIMIT) throw new LedgerMathError('operands exceed exact integer range')

  const sign = a < 0 !== b < 0 ? -1 : 1
  return sign * Math.floor((2 * A + B) / (2 * B))
}

/**
 * Render a scaled integer as a fixed-point decimal string.
 *
 * formatScaled(4237, 2)  === '42.37'
 * formatScaled(-520, 2)  === '-5.20'
 * formatScaled(0, 2)     === '0.00'   (never '-0.00')
 */
export function formatScaled(scaled: number, dp: number): string {
  if (!Number.isInteger(scaled)) throw new LedgerMathError('formatScaled needs an integer')
  if (dp < 0 || dp > 6) throw new LedgerMathError('unsupported decimal places')

  const negative = scaled < 0
  const digits = String(Math.abs(scaled)).padStart(dp + 1, '0')
  const whole = digits.slice(0, digits.length - dp)
  const frac = dp > 0 ? `.${digits.slice(digits.length - dp)}` : ''
  const body = `${whole}${frac}`

  // Guard against the '-0.00' that a naive sign-prefix would produce.
  return negative && scaled !== 0 ? `-${body}` : body
}

/** Sum an integer array, refusing to silently leave the exact range. */
export function sumExact(values: readonly number[]): number {
  let total = 0
  for (const v of values) {
    if (!Number.isInteger(v)) throw new LedgerMathError('non-integer in sum')
    total += v
    if (!Number.isSafeInteger(total)) throw new LedgerMathError('sum exceeded exact integer range')
  }
  return total
}

/** Arithmetic mean of integers, rounded half away from zero. */
export function meanExact(values: readonly number[]): number | null {
  if (values.length === 0) return null
  return divRoundHalfAway(sumExact(values), values.length)
}
