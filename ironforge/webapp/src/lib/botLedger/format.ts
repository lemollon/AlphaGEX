/**
 * Bot Ledger — display formatting.
 *
 * PURE. Takes `now` as a parameter and never calls Date.now(), so every rule
 * here is unit-testable in vitest's node environment and `relativeTime` can be
 * rendered deterministically.
 *
 * The client formats; it never computes. Every KPI arrives from the API as an
 * exact decimal string and is only ever rendered here.
 */

/** Typographic minus (U+2212). Intl emits ASCII hyphen; marketing pages use this. */
const MINUS = '−'
export const EM_DASH = '—'

const pct1 = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

const pct1Signed = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
  signDisplay: 'exceptZero',
})

const pct2 = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const dollars0 = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
})

/** Swap ASCII hyphen for the typographic minus, matching the other public pages. */
function typographic(s: string): string {
  return s.replace(/-/g, MINUS)
}

function toNumber(v: string | null | undefined): number | null {
  if (v === null || v === undefined || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

/** Win rate never carries a plus sign — it is a proportion, not a change. */
export function winRate(v: string | null | undefined): string {
  const n = toNumber(v)
  if (n === null) return EM_DASH
  return `${pct1.format(n)}%`
}

/**
 * Signed percentage for return-on-BP, average winner and average loser.
 * Values that round to zero render unsigned, never as a signed zero.
 */
export function signedPct(v: string | null | undefined): string {
  const n = toNumber(v)
  if (n === null) return EM_DASH
  const safe = Math.abs(n) < 0.05 ? 0 : n
  return `${typographic(pct1Signed.format(safe))}%`
}

/** Profit factor shows two decimals; null means "no losses", not zero. */
export function profitFactor(v: string | null | undefined): string {
  const n = toNumber(v)
  if (n === null) return EM_DASH
  return pct2.format(n)
}

export function wholeDollars(v: string | null | undefined): string {
  const n = toNumber(v)
  if (n === null) return EM_DASH
  return typographic(dollars0.format(n))
}

/** Signed whole dollars for the net-result column, e.g. '+$42' / '−$26'. */
export function signedDollars(v: string | null | undefined): string {
  const n = toNumber(v)
  if (n === null) return EM_DASH
  const rounded = Math.round(n)
  if (rounded === 0) return dollars0.format(0)
  const body = dollars0.format(Math.abs(rounded))
  return rounded > 0 ? `+${body}` : `${MINUS}${body}`
}

export function integer(n: number | null | undefined): string {
  return typeof n === 'number' && Number.isFinite(n) ? n.toLocaleString('en-US') : EM_DASH
}

const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']

/**
 * Render an ISO date (already in market time from the API) for the log.
 * Parsed by hand rather than through `new Date()` so the browser's local
 * timezone can never shift the day the server computed.
 */
export function marketDate(iso: string, nowYear: number): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!m) return iso
  const [, year, month, day] = m
  const label = `${MONTHS[Number(month) - 1] ?? month} ${Number(day)}`
  return Number(year) === nowYear ? label : `${label} ${year}`
}

/** Long form for the card's inception disclosure, e.g. '23 Apr 2026'. */
export function longDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!m) return iso
  const [, year, month, day] = m
  const name = MONTHS[Number(month) - 1] ?? month
  return `${Number(day)} ${name.charAt(0)}${name.slice(1).toLowerCase()} ${year}`
}

/**
 * Coarse relative time for the stale chip. Deliberately low-resolution — the
 * page revalidates on a 5-minute snapshot, so second-level precision would
 * imply a freshness the data does not have.
 */
export function relativeTime(iso: string, nowMs: number): string {
  const then = Date.parse(iso)
  if (!Number.isFinite(then)) return ''
  const seconds = Math.max(0, Math.round((nowMs - then) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.round(hours / 24)
  return `${days} day${days === 1 ? '' : 's'} ago`
}

/**
 * Sample line: '14 wins · 5 losses · 19 closed trades'.
 * The scratch term appears only when non-zero, per the spec.
 */
export function sampleLine(wins: number, losses: number, scratches: number, closed: number): string {
  const parts = [`${wins} win${wins === 1 ? '' : 's'}`, `${losses} loss${losses === 1 ? '' : 'es'}`]
  if (scratches > 0) parts.push(`${scratches} scratch${scratches === 1 ? '' : 'es'}`)
  parts.push(`${closed} closed trade${closed === 1 ? '' : 's'}`)
  return parts.join(' · ')
}

/** Screen-reader phrasing for the same sample, without the middot shorthand. */
export function sampleLineAccessible(
  wins: number,
  losses: number,
  scratches: number,
  closed: number,
): string {
  const parts = [`${wins} wins`, `${losses} losses`]
  if (scratches > 0) parts.push(`${scratches} scratches`)
  parts.push(`${closed} closed paper trades`)
  return parts.join(', ')
}
