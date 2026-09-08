/**
 * Waitlist drip scheduler — "three business days between sends" as a pure function.
 *
 * Business days are Monday-Friday excluding U.S. FEDERAL holidays (the kit's rule), which is
 * NOT the NYSE calendar in lib/market-calendar.ts: Columbus Day and Veterans Day are federal
 * closures the market trades through, and Good Friday is a market closure that is not a
 * federal holiday. So this module has its own calendar, computed from the statutory rules
 * (5 U.S.C. § 6103) rather than a per-year table, including the observed-day rules
 * (Saturday → the Friday before, Sunday → the Monday after). No yearly maintenance.
 *
 * Every calendar decision is made in America/Chicago — the app's convention (db.ts CT_TODAY,
 * the scanner's CT clock). A send at 23:30 CT is "today" here even though it is tomorrow UTC.
 *
 * Cadence rules from the kit, all implemented here and pinned by schedule.test.ts:
 *   - next send = the 3rd business day AFTER the actual send date, at the send hour;
 *   - a send date on a weekend/holiday moves to the next business day;
 *   - the three-day count restarts from the ACTUAL send, so a deferral is never "caught up".
 */

export const DRIP_TIMEZONE = 'America/Chicago'

/** Business days between consecutive emails (the kit's cadence). */
export const DRIP_BUSINESS_DAY_GAP = 3

/**
 * Hour of day (CT, 0-23) a scheduled send is due. Only the DATE is business-day arithmetic;
 * the clock time is fixed so a signup at 11pm does not put every later email at 11pm.
 * Override with WAITLIST_DRIP_SEND_HOUR_CT.
 */
export const DEFAULT_SEND_HOUR_CT = 9

export function sendHourCT(): number {
  const raw = Number(process.env.WAITLIST_DRIP_SEND_HOUR_CT)
  return Number.isInteger(raw) && raw >= 0 && raw <= 23 ? raw : DEFAULT_SEND_HOUR_CT
}

// ---------------------------------------------------------------------------
// Calendar keys (YYYY-MM-DD) — pure date arithmetic, no time zone involved
// ---------------------------------------------------------------------------

/** YYYY-MM-DD. */
export type DateKey = string

const KEY_RE = /^(\d{4})-(\d{2})-(\d{2})$/

export function isDateKey(s: unknown): s is DateKey {
  if (typeof s !== 'string' || !KEY_RE.test(s)) return false
  const [y, m, d] = s.split('-').map(Number)
  const probe = new Date(Date.UTC(y, m - 1, d))
  return probe.getUTCFullYear() === y && probe.getUTCMonth() === m - 1 && probe.getUTCDate() === d
}

function key(y: number, m: number, d: number): DateKey {
  return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
}

function parseKey(k: DateKey): { y: number; m: number; d: number } {
  const mm = KEY_RE.exec(k)
  if (!mm) throw new Error(`not a YYYY-MM-DD date key: ${k}`)
  return { y: Number(mm[1]), m: Number(mm[2]), d: Number(mm[3]) }
}

/** 0 = Sunday … 6 = Saturday, for a calendar date (time-zone free). */
export function weekdayOf(k: DateKey): number {
  const { y, m, d } = parseKey(k)
  return new Date(Date.UTC(y, m - 1, d)).getUTCDay()
}

export function shiftDays(k: DateKey, days: number): DateKey {
  const { y, m, d } = parseKey(k)
  const t = new Date(Date.UTC(y, m - 1, d + days))
  return key(t.getUTCFullYear(), t.getUTCMonth() + 1, t.getUTCDate())
}

// ---------------------------------------------------------------------------
// U.S. federal holidays — rule-based, with observed days
// ---------------------------------------------------------------------------

/** The nth (1-based) given weekday of a month; n = -1 means the last one. */
function nthWeekday(y: number, m: number, weekday: number, n: number): DateKey {
  if (n > 0) {
    const first = weekdayOf(key(y, m, 1))
    const d = 1 + ((weekday - first + 7) % 7) + (n - 1) * 7
    return key(y, m, d)
  }
  const lastDay = new Date(Date.UTC(y, m, 0)).getUTCDate()
  const last = weekdayOf(key(y, m, lastDay))
  return key(y, m, lastDay - ((last - weekday + 7) % 7))
}

/** Saturday holidays are observed the Friday before; Sunday holidays the Monday after. */
function observed(k: DateKey): DateKey {
  const w = weekdayOf(k)
  if (w === 6) return shiftDays(k, -1)
  if (w === 0) return shiftDays(k, 1)
  return k
}

/**
 * Observed federal holidays that fall in calendar year `y`, as observed-date → name.
 * Includes a December 31 of `y` when New Year's Day of `y + 1` is a Saturday.
 */
export function federalHolidays(y: number): Map<DateKey, string> {
  const out = new Map<DateKey, string>()
  const add = (k: DateKey, name: string) => {
    if (k.startsWith(`${y}-`)) out.set(k, name)
  }
  add(observed(key(y, 1, 1)), "New Year's Day")
  add(nthWeekday(y, 1, 1, 3), 'Birthday of Martin Luther King, Jr.')
  add(nthWeekday(y, 2, 1, 3), "Washington's Birthday")
  add(nthWeekday(y, 5, 1, -1), 'Memorial Day')
  add(observed(key(y, 6, 19)), 'Juneteenth National Independence Day')
  add(observed(key(y, 7, 4)), 'Independence Day')
  add(nthWeekday(y, 9, 1, 1), 'Labor Day')
  add(nthWeekday(y, 10, 1, 2), 'Columbus Day')
  add(observed(key(y, 11, 11)), 'Veterans Day')
  add(nthWeekday(y, 11, 4, 4), 'Thanksgiving Day')
  add(observed(key(y, 12, 25)), 'Christmas Day')
  // New Year's Day of next year observed on Dec 31 of this year.
  add(observed(key(y + 1, 1, 1)), "New Year's Day (observed)")
  return out
}

const _holidayCache = new Map<number, Map<DateKey, string>>()
function holidaysFor(y: number): Map<DateKey, string> {
  let h = _holidayCache.get(y)
  if (!h) {
    h = federalHolidays(y)
    _holidayCache.set(y, h)
  }
  return h
}

/** Name of the observed federal holiday on this date, or null. */
export function federalHolidayName(k: DateKey): string | null {
  return holidaysFor(parseKey(k).y).get(k) ?? null
}

export function isFederalHoliday(k: DateKey): boolean {
  return federalHolidayName(k) !== null
}

/** Monday-Friday and not an observed federal holiday. */
export function isBusinessDay(k: DateKey): boolean {
  const w = weekdayOf(k)
  if (w === 0 || w === 6) return false
  return !isFederalHoliday(k)
}

/** `k` itself when it is a business day, else the next one (the kit's deferral rule). */
export function moveToBusinessDay(k: DateKey): DateKey {
  let cur = k
  for (let i = 0; i < 14 && !isBusinessDay(cur); i++) cur = shiftDays(cur, 1)
  return cur
}

/** The nth business day strictly AFTER `k`. */
export function addBusinessDays(k: DateKey, n: number): DateKey {
  let cur = k
  let remaining = n
  while (remaining > 0) {
    cur = shiftDays(cur, 1)
    if (isBusinessDay(cur)) remaining--
  }
  return cur
}

// ---------------------------------------------------------------------------
// Instants ↔ Chicago wall clock
// ---------------------------------------------------------------------------

export interface CtParts {
  y: number
  m: number
  d: number
  h: number
  mi: number
  s: number
}

const _fmt = new Intl.DateTimeFormat('en-US', {
  timeZone: DRIP_TIMEZONE,
  hourCycle: 'h23',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})

/** The Chicago wall-clock fields of an instant. */
export function ctParts(at: Date): CtParts {
  const p: Record<string, number> = {}
  for (const part of _fmt.formatToParts(at)) {
    if (part.type !== 'literal') p[part.type] = Number(part.value)
  }
  // Some engines report midnight as 24 even with h23; normalise.
  const h = p.hour === 24 ? 0 : p.hour
  return { y: p.year, m: p.month, d: p.day, h, mi: p.minute, s: p.second }
}

/** The Chicago calendar date of an instant. */
export function ctDateKey(at: Date): DateKey {
  const p = ctParts(at)
  return key(p.y, p.m, p.d)
}

/**
 * The instant at which Chicago's wall clock reads `k` `hour`:`minute`. Resolved by
 * offset correction rather than a fixed -5/-6, so DST transitions are handled.
 */
export function fromCtWallClock(k: DateKey, hour: number, minute = 0): Date {
  const { y, m, d } = parseKey(k)
  // The wall-clock we want, expressed as if Chicago were UTC. Each pass measures how far
  // the current guess's Chicago reading is from it and shifts by that amount.
  const desired = Date.UTC(y, m - 1, d, hour, minute, 0)
  let guess = desired
  for (let i = 0; i < 3; i++) {
    const p = ctParts(new Date(guess))
    const reading = Date.UTC(p.y, p.m - 1, p.d, p.h, p.mi, p.s)
    const diff = reading - desired
    if (diff === 0) break
    guess -= diff
  }
  return new Date(guess)
}

// ---------------------------------------------------------------------------
// The scheduler
// ---------------------------------------------------------------------------

/**
 * When the NEXT email is due, given the instant the previous one ACTUALLY went out.
 *
 * Counts `businessDays` business days after the Chicago date of `from` and returns the send
 * hour on that day. Because the input is the real send instant — never the originally
 * planned one — a deferred send restarts the count from the day it really happened.
 */
export function nextSendDate(
  from: Date,
  businessDays = DRIP_BUSINESS_DAY_GAP,
  opts?: { sendHour?: number },
): Date {
  const hour = opts?.sendHour ?? sendHourCT()
  const due = addBusinessDays(ctDateKey(from), businessDays)
  return fromCtWallClock(due, hour)
}

/**
 * The first-send instant for a requested calendar date (the backfill parameter): the date
 * itself when it is a business day, otherwise the next business day — at the send hour.
 */
export function firstSendAt(requested: DateKey, opts?: { sendHour?: number }): Date {
  const hour = opts?.sendHour ?? sendHourCT()
  return fromCtWallClock(moveToBusinessDay(requested), hour)
}

/** Default backfill date: the next business day strictly AFTER today (Chicago). */
export function defaultFirstSendDate(now: Date = new Date()): DateKey {
  return addBusinessDays(ctDateKey(now), 1)
}

/** Human-readable CT timestamp for ops output, e.g. "2026-09-09 09:00 CT". */
export function formatCT(at: Date): string {
  const p = ctParts(at)
  return `${key(p.y, p.m, p.d)} ${String(p.h).padStart(2, '0')}:${String(p.mi).padStart(2, '0')} CT`
}
