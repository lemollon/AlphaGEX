/**
 * Calendar boundaries for the Forge Home stats card's "This Week" / "This
 * Month" figures — computed in Eastern Time (the exchange's own clock), not
 * Central (CT_TODAY's zone in db.ts) and not the server's UTC.
 *
 * Returned as real UTC instants (not SQL fragments) so home.ts can bind them
 * straight into a `close_time >= '<iso>'` comparison. That also makes the
 * boundary math unit-testable here without a live Postgres connection — see
 * period-windows.test.ts for the Sunday-23:59-ET / Monday-00:00-ET and
 * month-end / month-start cases this replaced a `now() - interval '7 days'`
 * rolling window with.
 *
 * "Week" resets Monday 00:00:00 ET (a trade that closed Sunday 23:59 ET is in
 * the PRIOR week). "Month" resets the 1st at 00:00:00 ET.
 */

const ET_ZONE = 'America/New_York'

/** Y/M/D/H/M/S as observed on the wall clock in `zone` for a given instant. */
function partsInZone(instant: Date, zone: string) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: zone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(instant)
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value)
  // Midnight formats as hour "24" on some ICU builds — normalize to 0.
  const hour = get('hour')
  return {
    year: get('year'),
    month: get('month'),
    day: get('day'),
    hour: hour === 24 ? 0 : hour,
    minute: get('minute'),
    second: get('second'),
  }
}

/**
 * The UTC instant whose wall clock in `zone` reads Y-M-D 00:00:00. Iterates
 * the offset correction twice so a target date near a DST transition still
 * resolves to the correct instant (a fixed offset guess can be off by an hour
 * right at the transition).
 */
function midnightInZoneToUtc(year: number, month: number, day: number, zone: string): Date {
  let guessMs = Date.UTC(year, month - 1, day)
  for (let i = 0; i < 2; i++) {
    const p = partsInZone(new Date(guessMs), zone)
    const observedMs = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second)
    const wantedMs = Date.UTC(year, month - 1, day, 0, 0, 0)
    guessMs += wantedMs - observedMs
  }
  return new Date(guessMs)
}

/** ISO weekday in `zone`: 1 = Monday … 7 = Sunday. */
function isoWeekdayInZone(instant: Date, zone: string): number {
  const label = new Intl.DateTimeFormat('en-US', { timeZone: zone, weekday: 'short' }).format(instant)
  return ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].indexOf(label) + 1
}

/** Monday 00:00:00 ET of the week containing `now`. */
export function weekStartET(now: Date): Date {
  const p = partsInZone(now, ET_ZONE)
  const isoDow = isoWeekdayInZone(now, ET_ZONE)
  // Calendar-day subtraction on a UTC-anchored date never touches DST (UTC has
  // none); the resulting Y/M/D is re-anchored to ET midnight below.
  const monday = new Date(Date.UTC(p.year, p.month - 1, p.day) - (isoDow - 1) * 86_400_000)
  return midnightInZoneToUtc(monday.getUTCFullYear(), monday.getUTCMonth() + 1, monday.getUTCDate(), ET_ZONE)
}

/** The 1st of the month, 00:00:00 ET, containing `now`. */
export function monthStartET(now: Date): Date {
  const p = partsInZone(now, ET_ZONE)
  return midnightInZoneToUtc(p.year, p.month, 1, ET_ZONE)
}
