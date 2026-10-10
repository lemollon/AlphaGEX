import { isMarketHoliday, marketCloseMinuteCT } from '@/lib/market-calendar'

/**
 * Weekday + exchange-calendar market-hours check for the marketing site's
 * decorative "market status" badges (hero card, how-it-works timeline).
 *
 * Previously weekday-only, matching the design spec's own stated prototype
 * limitation ("Production must use an exchange holiday and early-close
 * calendar for every 'market open' state" — ps-hero #51). Now reuses the
 * same `lib/market-calendar` the scanner's real trading gate uses, so a
 * holiday or a 12:00 PM CT early close shows "Market closed" here too.
 * Still illustrative only — never used for trading decisions.
 */
export function isMarketOpenNow(now: Date = new Date()): boolean {
  const ct = new Date(now.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  const day = ct.getDay()
  if (day === 0 || day === 6) return false
  if (isMarketHoliday(ct)) return false
  const minutes = ct.getHours() * 60 + ct.getMinutes()
  return minutes >= 8 * 60 + 30 && minutes < marketCloseMinuteCT(ct)
}

/**
 * Status badge wording, matching the design's states ("Market open",
 * "Pre-market", "After hours", "Market closed") driven by the same
 * exchange calendar as `isMarketOpenNow` — not used for trading decisions.
 */
export function marketStatusLabel(now: Date = new Date()): string {
  const ct = new Date(now.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  const day = ct.getDay()
  if (day === 0 || day === 6) return 'Market closed'
  if (isMarketHoliday(ct)) return 'Market closed'
  const minutes = ct.getHours() * 60 + ct.getMinutes()
  if (minutes < 8 * 60 + 30) return 'Pre-market'
  if (minutes < marketCloseMinuteCT(ct)) return 'Market open'
  return 'After hours'
}

/** Minutes since midnight CT — drives the how-it-works live timeline's "now" step. */
export function minutesSinceMidnightCT(now: Date = new Date()): number {
  const ct = new Date(now.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  return ct.getHours() * 60 + ct.getMinutes()
}

export type HeroTab = 'spark' | 'flame'

/** Hero-card tab session windows, in minutes since midnight CT — matches the dev-handoff
 * spec's own stated tab ranges ("Spark 9:00-12:00, Flame 12:30-3:00"). Illustrative only;
 * the real entry windows (see ironforge/SPARK_FLAME_CURRENT_STATE doc) are narrower. */
const HERO_SESSION: Record<HeroTab, { start: number; end: number }> = {
  spark: { start: 9 * 60, end: 12 * 60 },
  flame: { start: 12 * 60 + 30, end: 15 * 60 },
}

/** Which hero tab matches "right now" in Central time (ps-hero #46: "Default tab follows
 * the current Central time"). Before Spark's window, or after Flame's, falls back to
 * whichever window is closer so the badge never looks stuck on a stale tab overnight. */
export function defaultHeroTab(now: Date = new Date()): HeroTab {
  const minutes = minutesSinceMidnightCT(now)
  if (minutes < HERO_SESSION.flame.start) return 'spark'
  return 'flame'
}

function formatClockCT(minutes: number): string {
  const h24 = Math.floor(minutes / 60)
  const m = minutes % 60
  const period = h24 >= 12 ? 'PM' : 'AM'
  const h12 = h24 % 12 === 0 ? 12 : h24 % 12
  return `${h12}:${String(m).padStart(2, '0')} ${period} CT`
}

/** One-line live state for the hero card's agent strip (ps-hero #49: "Trading now",
 * "Starts …" or "Done for today") — driven by the same illustrative session windows
 * the tabs use, not the real production entry windows. */
export function heroAgentStripState(tab: HeroTab, now: Date = new Date()): string {
  const minutes = minutesSinceMidnightCT(now)
  const { start, end } = HERO_SESSION[tab]
  if (minutes < start) return `Starts ${formatClockCT(start)}`
  if (minutes < end) return 'Trading now'
  return 'Done for today'
}
