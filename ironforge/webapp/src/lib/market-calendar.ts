/**
 * US equity market calendar — full-closure holidays and early-close days.
 *
 * WHY THIS EXISTS
 * ---------------
 * The scanner's market-hours gate (isMarketOpen / isInEntryWindow) used to check
 * only "weekday + time window". On Memorial Day 2026-05-25 (a Monday) that gate
 * returned true, so SPARK queued orders into a closed market; they filled at the
 * next open as 7 untracked positions and lost ~$223 of real money. This calendar
 * is the single source of truth so a closed (or half-) session is never treated
 * as a normal full session.
 *
 * Dates are NYSE observed dates (when a holiday lands on a weekend, the observed
 * weekday closure is listed). Errors here are conservative by design: a wrong
 * entry only makes the bot skip trading, never over-trade.
 *
 * ⚠️ MAINTENANCE: this table must be extended each year. `LAST_COVERED_YEAR`
 * lets callers warn when running past the known range (see calendarCoversYear).
 */

export const LAST_COVERED_YEAR = 2027

/** YYYY-MM-DD in the wall-clock the Date's local fields represent (CT for the
 *  scanner's getCTNow() Dates). Mirrors the scanner's ctHHMM(ct) convention. */
function ctDateKey(ct: Date): string {
  const y = ct.getFullYear()
  const m = String(ct.getMonth() + 1).padStart(2, '0')
  const d = String(ct.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/** Full-day NYSE closures (no trading at all). Observed dates. */
const FULL_CLOSURES = new Set<string>([
  // 2025
  '2025-01-01', '2025-01-20', '2025-02-17', '2025-04-18', '2025-05-26',
  '2025-06-19', '2025-07-04', '2025-09-01', '2025-11-27', '2025-12-25',
  // 2026
  '2026-01-01', '2026-01-19', '2026-02-16', '2026-04-03', '2026-05-25',
  '2026-06-19', '2026-07-03', '2026-09-07', '2026-11-26', '2026-12-25',
  // 2027
  '2027-01-01', '2027-01-18', '2027-02-15', '2027-03-26', '2027-05-31',
  '2027-06-18', '2027-07-05', '2027-09-06', '2027-11-25', '2027-12-24',
])

/** Half-days: NYSE closes 1:00 PM ET = 12:00 PM CT. */
const EARLY_CLOSES = new Set<string>([
  // 2025
  '2025-07-03', '2025-11-28', '2025-12-24',
  // 2026 (Jul 3 is a full closure this year, so no July early close)
  '2026-11-27', '2026-12-24',
  // 2027
  '2027-11-26', '2027-12-23',
])

/** True when the US equity market is fully closed for the whole session. */
export function isMarketHoliday(ct: Date): boolean {
  return FULL_CLOSURES.has(ctDateKey(ct))
}

/** True on half-days (early 12:00 PM CT close). Full closures are NOT early closes. */
export function isEarlyClose(ct: Date): boolean {
  return EARLY_CLOSES.has(ctDateKey(ct))
}

/** Minute-of-day (CT, HHMM) the market closes: 1200 on early-close days, else 1500. */
export function marketCloseMinuteCT(ct: Date): number {
  return isEarlyClose(ct) ? 1200 : 1500
}

/** Whether this calendar table covers the given year (for staleness warnings). */
export function calendarCoversYear(year: number): boolean {
  return year >= 2025 && year <= LAST_COVERED_YEAR
}
