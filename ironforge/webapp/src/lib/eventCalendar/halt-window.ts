/**
 * Halt-window math for the IronForge event blackout system (Vigil).
 *
 * All inputs are interpreted as Central Time (America/Chicago).
 * Outputs are absolute UTC `Date` objects (TIMESTAMPTZ when stored).
 *
 * DST is handled by computing the CT-local wall-clock time, then asking
 * the host environment what UTC instant that is.
 */

const CT_TZ = 'America/Chicago'

/** Returns the UTC offset (in minutes) for a given UTC date in America/Chicago. */
function ctUtcOffsetMinutes(d: Date): number {
  const dtf = new Intl.DateTimeFormat('en-US', {
    timeZone: CT_TZ,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  })
  const parts = dtf.formatToParts(d).reduce((acc, p) => {
    if (p.type !== 'literal') acc[p.type] = p.value
    return acc
  }, {} as Record<string, string>)
  const ctMs = Date.UTC(
    parseInt(parts.year),
    parseInt(parts.month) - 1,
    parseInt(parts.day),
    parseInt(parts.hour === '24' ? '0' : parts.hour),
    parseInt(parts.minute),
    parseInt(parts.second),
  )
  return (ctMs - d.getTime()) / 60000
}

/** Construct a Date for a given CT-local wall-clock time (date + HH:MM). */
function ctWallToUtc(dateStr: string, hhmm: string): Date {
  const [y, mo, d] = dateStr.split('-').map(Number)
  const [hh, mm] = hhmm.split(':').map(Number)
  // Initial guess: treat the wall time as UTC, then correct by CT offset
  const guess = new Date(Date.UTC(y, mo - 1, d, hh, mm, 0))
  const offsetMin = ctUtcOffsetMinutes(guess)
  // CT is behind UTC, so offsetMin is negative (e.g., -300 for CDT, -360 for CST).
  // Subtracting a negative shifts forward to the correct UTC instant.
  return new Date(guess.getTime() - offsetMin * 60000)
}

/** Day-of-week of a YYYY-MM-DD string interpreted as a calendar date. */
function dayOfWeek(dateStr: string): number {
  const [y, mo, d] = dateStr.split('-').map(Number)
  return new Date(Date.UTC(y, mo - 1, d)).getUTCDay() // 0=Sun .. 6=Sat
}

/** Subtract `n` calendar days from a YYYY-MM-DD date string. */
function subtractDays(dateStr: string, n: number): string {
  const [y, mo, d] = dateStr.split('-').map(Number)
  const t = new Date(Date.UTC(y, mo - 1, d))
  t.setUTCDate(t.getUTCDate() - n)
  return `${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, '0')}-${String(t.getUTCDate()).padStart(2, '0')}`
}

/**
 * Returns the Friday strictly before `eventDate` at 08:30 CT, as a UTC Date.
 *
 * - If `eventDate` is itself a Friday → returns the Friday a week before.
 * - If `eventDate` is a weekend day → returns the Friday immediately before that weekend.
 */
export function computeFridayPriorAt0830CT(eventDate: string): Date {
  const dow = dayOfWeek(eventDate) // 0=Sun, 5=Fri, 6=Sat
  let daysBack: number
  if (dow === 5) daysBack = 7              // Fri → Fri prior week (strict-prior)
  else if (dow === 6) daysBack = 1         // Sat → Fri before
  else if (dow === 0) daysBack = 2         // Sun → Fri before
  else daysBack = ((dow + 7) - 5) % 7      // Mon→3, Tue→4, Wed→5, Thu→6
  const fridayDateStr = subtractDays(eventDate, daysBack)
  return ctWallToUtc(fridayDateStr, '08:30')
}

/**
 * Returns `eventDate` at `eventTimeCt` + `offsetMinutes`, as a UTC Date.
 */
export function computeEventDayAt(
  eventDate: string,
  eventTimeCt: string,
  offsetMinutes: number,
): Date {
  const base = ctWallToUtc(eventDate, eventTimeCt)
  return new Date(base.getTime() + offsetMinutes * 60000)
}

/**
 * @deprecated Pre-2026-05-06 multi-day halt math. Kept only for legacy
 * call-site safety; current IronForge policy is day-of-news only via
 * `computeDayOfNewsHaltWindow` below.
 *
 * Returns `n` TRADING days (Mon–Fri) before `eventDate`, at 08:30 CT (RTH open),
 * as a UTC Date. Walks back calendar days, only counting weekdays.
 */
export function computeNTradingDaysPriorAt0830CT(
  eventDate: string,
  n: number,
): Date {
  let counted = 0
  let stepsBack = 0
  while (counted < n) {
    stepsBack += 1
    const candidate = subtractDays(eventDate, stepsBack)
    const dow = dayOfWeek(candidate)
    if (dow !== 0 && dow !== 6) counted += 1
  }
  const haltDateStr = subtractDays(eventDate, stepsBack)
  return ctWallToUtc(haltDateStr, '08:30')
}

/** Market open in CT — bots only trade RTH (08:30–15:00 CT). */
const MARKET_OPEN_CT = '08:30'

/** Convert HH:MM (24h) into minutes-from-midnight. */
function hhmmToMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

/**
 * IronForge halt window under the day-of-news policy (effective 2026-05-06,
 * replacing the prior multi-day halt). Same date for halt-start; halt-end
 * branches on whether the release is pre-market or mid-day:
 *
 *   - Pre-market release (event_time_ct < 08:30 CT):
 *       resume at market open (08:30 CT). The release has already crushed
 *       IV by the time the bots wake up, so trading at the bell is fine.
 *
 *   - Mid-day release (event_time_ct >= 08:30 CT):
 *       resume `resumeOffsetMin` minutes after the release timestamp
 *       (default 30 min). Bots stay flat through the release and the
 *       initial whipsaw, then resume.
 *
 * `halt_start_ts` is set to the event date at 00:00 CT for both branches.
 * The bots don't trade overnight anyway, so the 00:00 anchor just guarantees
 * the gate is hot from the first scanner cycle of the event day forward.
 */
export function computeDayOfNewsHaltWindow(
  eventDate: string,
  eventTimeCt: string,
  resumeOffsetMin: number,
): { haltStart: Date; haltEnd: Date } {
  const haltStart = ctWallToUtc(eventDate, '00:00')
  const eventMin = hhmmToMinutes(eventTimeCt)
  const openMin = hhmmToMinutes(MARKET_OPEN_CT)
  const haltEnd = eventMin < openMin
    ? ctWallToUtc(eventDate, MARKET_OPEN_CT)
    : computeEventDayAt(eventDate, eventTimeCt, resumeOffsetMin)
  return { haltStart, haltEnd }
}
