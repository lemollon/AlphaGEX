/**
 * Minimal weekday + 8:30–15:00 CT market-hours check for the marketing site's
 * decorative "market status" badges (hero card, how-it-works timeline).
 *
 * Matches the design spec's own stated limitation verbatim ("the prototype
 * only knows weekdays. Production must use an exchange holiday and
 * early-close calendar for every 'market open' state") — this is the same
 * weekday-only approximation, not a real exchange calendar. Good enough for
 * an illustrative badge; never used for trading decisions.
 */
export function isMarketOpenNow(now: Date = new Date()): boolean {
  const ct = new Date(now.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  const day = ct.getDay()
  if (day === 0 || day === 6) return false
  const minutes = ct.getHours() * 60 + ct.getMinutes()
  return minutes >= 8 * 60 + 30 && minutes < 15 * 60
}

/** Minutes since midnight CT — drives the how-it-works live timeline's "now" step. */
export function minutesSinceMidnightCT(now: Date = new Date()): number {
  const ct = new Date(now.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  return ct.getHours() * 60 + ct.getMinutes()
}
