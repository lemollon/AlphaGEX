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
