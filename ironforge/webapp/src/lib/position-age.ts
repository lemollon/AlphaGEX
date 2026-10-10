/**
 * HOW OLD IS THIS POSITION, AND IS IT ALREADY OVER?
 *
 * SPARK's 8/21, 8/24 and 8/25 positions sat `status = 'open'` for three trading days
 * while the log printed `SETTLED ... pnl=$35.00` once a minute. Nothing on the page
 * said anything was wrong — the card showed `Exp: 2026-08-21` and left the reader to
 * do the date arithmetic. Leron caught it by eye anyway. This gives the eye better
 * data: **"5 days past expiry" is impossible to misread.**
 *
 * The watchdog now repairs a stranded position on its own, so this is no longer the
 * primary defence. It is still the surface that makes the state legible while a repair
 * is in flight, or when the watchdog has escalated instead of acting.
 *
 * Pure: no clock, no DOM. The caller passes CT "now" in, which is what makes the
 * boundary cases testable rather than a thing you notice once a year.
 */

/** Calendar date as YYYY-MM-DD from a Date whose LOCAL fields are the CT wall clock. */
export function ctDateString(nowCT: Date): string {
  const y = nowCT.getFullYear()
  const m = String(nowCT.getMonth() + 1).padStart(2, '0')
  const d = String(nowCT.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/** YYYY-MM-DD out of whatever the API handed back (string, ISO timestamp, or Date). */
export function toDateString(value: unknown): string | null {
  if (!value) return null
  const raw =
    (value as { toISOString?: () => string })?.toISOString?.()?.slice(0, 10) ??
    String(value).slice(0, 10)
  return /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : null
}

/** Whole calendar days between two YYYY-MM-DD dates. Positive when `to` is later. */
export function calendarDaysBetween(from: string, to: string): number {
  const a = Date.parse(`${from}T00:00:00Z`)
  const b = Date.parse(`${to}T00:00:00Z`)
  if (!Number.isFinite(a) || !Number.isFinite(b)) return 0
  return Math.round((b - a) / 86_400_000)
}

export type AgeTone =
  /** Past expiry and still open. Always wrong. */
  | 'critical'
  /** Expires today — normal for a 0DTE, but worth seeing. */
  | 'today'
  /** Deliberate hold with time left on it. */
  | 'normal'

export type PositionAge = {
  tone: AgeTone
  /** The badge text. Reads as a sentence on its own, no arithmetic required. */
  label: string
  /** Calendar days past expiration. 0 unless `tone === 'critical'`. */
  daysPastExpiry: number
  /** Calendar days the position has been open. */
  heldDays: number
  /** Longer line for the footer, e.g. "held 3 days". */
  heldLabel: string
}

/**
 * 🚨 The critical case is deliberately verbose. "1 day past expiry" beats "1d" —
 * an abbreviation is exactly what the eye skips, and skipping it is what cost three
 * trading days.
 */
export function describePositionAge(
  expiration: unknown,
  openTime: unknown,
  nowCT: Date,
): PositionAge {
  const today = ctDateString(nowCT)
  const exp = toDateString(expiration)
  const opened = toDateString(openTime)

  const heldDays = opened ? Math.max(0, calendarDaysBetween(opened, today)) : 0
  const heldLabel =
    heldDays === 0 ? 'opened today' : `held ${heldDays} day${heldDays === 1 ? '' : 's'}`

  if (!exp) {
    return { tone: 'normal', label: 'expiry unknown', daysPastExpiry: 0, heldDays, heldLabel }
  }

  const daysPast = calendarDaysBetween(exp, today)

  if (daysPast > 0) {
    return {
      tone: 'critical',
      label: `${daysPast} day${daysPast === 1 ? '' : 's'} past expiry`,
      daysPastExpiry: daysPast,
      heldDays,
      heldLabel,
    }
  }

  if (daysPast === 0) {
    return { tone: 'today', label: 'expires today', daysPastExpiry: 0, heldDays, heldLabel }
  }

  const left = -daysPast
  return {
    tone: 'normal',
    label: `expires in ${left} day${left === 1 ? '' : 's'}`,
    daysPastExpiry: 0,
    heldDays,
    heldLabel,
  }
}

/** Tailwind classes for the badge, keyed by tone. Critical must not be missable. */
export function ageBadgeClasses(tone: AgeTone): string {
  if (tone === 'critical') return 'bg-red-500/20 text-red-300 border border-red-500/50 font-semibold'
  if (tone === 'today') return 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
  return 'bg-forge-border text-forge-muted'
}
