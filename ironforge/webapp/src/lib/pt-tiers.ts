/**
 * Sliding Profit Target tiers — must match the scanner schedule exactly.
 *
 * Schedule (Central Time) for FLAME / SPARK:
 *   FLAME (morning ends 10:30 AM):
 *     8:30 – 10:29  → 30% MORNING
 *     10:30 – 12:59 → 20% MIDDAY
 *     1:00 – 2:44   → 15% AFTERNOON
 *
 *   SPARK (morning extended to 12:00 PM per scanner — keeps the close limit
 *   aggressive longer to avoid stuck unfilled limits when the tier slides):
 *     8:30 – 11:59  → 30% MORNING
 *     12:00 – 12:59 → 20% MIDDAY
 *     1:00 – 2:44   → 15% AFTERNOON
 *
 *   2:45 PM+        → handled by EOD cutoff
 *
 * INFERNO (0DTE) uses its own reversed schedule in scanner.ts;
 * the UI tier helpers below treat it like FLAME for display purposes.
 */

import { isMarketHoliday, isEarlyClose } from './market-calendar'

export type Bot = 'flame' | 'spark' | 'inferno' | 'blaze'

export interface PTTier {
  pct: number
  label: string
  color: string       // Tailwind text color
  bgColor: string     // Tailwind badge background
  dotColor: string    // Tailwind dot color
}

const MORNING: PTTier = {
  pct: 0.30,
  label: 'Morning',
  color: 'text-emerald-400',
  bgColor: 'bg-emerald-500/20',
  dotColor: 'bg-emerald-400',
}

const MIDDAY: PTTier = {
  pct: 0.20,
  label: 'Midday',
  color: 'text-yellow-400',
  bgColor: 'bg-yellow-500/20',
  dotColor: 'bg-yellow-400',
}

const AFTERNOON: PTTier = {
  pct: 0.15,
  label: 'Afternoon',
  color: 'text-orange-400',
  bgColor: 'bg-orange-500/20',
  dotColor: 'bg-orange-400',
}

/** Get the current CT date object. */
export function getCTNow(): Date {
  const ct = new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' })
  return new Date(ct)
}

/** Get current minutes-since-midnight in CT. */
export function getCTMinutes(ctDate?: Date): number {
  const d = ctDate ?? getCTNow()
  return d.getHours() * 60 + d.getMinutes()
}

/** Is it a regular-session weekday (not a holiday) between 8:30 AM CT and the
 *  session close (3:00 PM normally, 12:00 PM on early-close half-days)? */
export function isMarketOpen(ctDate?: Date): boolean {
  const d = ctDate ?? getCTNow()
  const day = d.getDay()
  if (day === 0 || day === 6) return false
  if (isMarketHoliday(d)) return false // full-closure holidays (see market-calendar.ts)
  const mins = d.getHours() * 60 + d.getMinutes()
  const closeMins = isEarlyClose(d) ? 720 : 900 // 12:00 PM CT half-day, else 3:00 PM CT
  return mins >= 510 && mins < closeMins
}

/** Morning-end minute for each bot (must mirror scanner.ts getSlidingProfitTarget). */
export function morningEndMinutes(bot?: string): number {
  return bot === 'spark' ? 720 : 630 // 12:00 PM CT for SPARK, else 10:30 AM CT
}

/** Default EOD cutoff in minutes-since-midnight CT (2:45 PM) — mirrors scanner
 *  DEFAULT_CONFIG.eod_cutoff_hhmm_ct = 1445. Used when config is unavailable. */
export const DEFAULT_EOD_CUTOFF_MIN = 14 * 60 + 45 // 885

/**
 * Convert a stored `eod_cutoff_et` value ("HH:MM") to minutes-since-midnight CT.
 * The value is CENTRAL time (the `_et` suffix is a legacy misnomer — all
 * IronForge times are CT), so it is parsed as-is with NO timezone shift,
 * exactly mirroring scanner.ts's config loader. Missing/invalid input falls
 * back to DEFAULT_EOD_CUTOFF_MIN (2:45 PM CT).
 */
export function eodCutoffMinutesCT(eodCutoffEt?: string | null): number {
  if (!eodCutoffEt || typeof eodCutoffEt !== 'string' || !eodCutoffEt.includes(':')) {
    return DEFAULT_EOD_CUTOFF_MIN
  }
  const [h, m] = eodCutoffEt.split(':').map(Number)
  if (isNaN(h) || isNaN(m) || h < 0 || h > 23 || m < 0 || m > 59) {
    return DEFAULT_EOD_CUTOFF_MIN
  }
  return h * 60 + m
}

/** Format minutes-since-midnight CT as a clock string, e.g. 885 → "2:45 PM". */
export function formatCTClock(minsSinceMidnight: number, withMeridiem = true): string {
  const h24 = Math.floor(minsSinceMidnight / 60)
  const m = minsSinceMidnight % 60
  const meridiem = h24 >= 12 ? 'PM' : 'AM'
  let h12 = h24 % 12
  if (h12 === 0) h12 = 12
  const core = `${h12}:${String(m).padStart(2, '0')}`
  return withMeridiem ? `${core} ${meridiem}` : core
}

/** Get the active PT tier based on current CT time and bot. */
export function getCurrentPTTier(ctDate?: Date, bot?: string): PTTier {
  const mins = getCTMinutes(ctDate)
  if (mins < morningEndMinutes(bot)) return MORNING
  if (mins < 780) return MIDDAY       // before 1:00 PM
  return AFTERNOON
}

/**
 * Seconds until the next PT tier change.
 * Returns null if market is past 2:45 PM or closed.
 */
export function secondsUntilNextTier(
  ctDate?: Date,
  bot?: string,
  eodCutoffMin: number = DEFAULT_EOD_CUTOFF_MIN,
): { seconds: number; nextLabel: string } | null {
  const d = ctDate ?? getCTNow()
  const mins = getCTMinutes(d)
  const secs = d.getSeconds()
  const totalSecs = mins * 60 + secs
  const morningEnd = morningEndMinutes(bot)

  if (mins < morningEnd) {
    // Morning → Midday at morningEnd
    return { seconds: morningEnd * 60 - totalSecs, nextLabel: '20% Midday' }
  }
  if (mins < 780) {
    // Midday → Afternoon at 1:00 PM (780 min = 46800 sec)
    return { seconds: 46800 - totalSecs, nextLabel: '15% Afternoon' }
  }
  if (mins < eodCutoffMin) {
    // Afternoon → EOD at the configured cutoff (Central time). Defaults to
    // 2:45 PM CT; callers pass the bot's real eod_cutoff so the countdown
    // never diverges from the scanner's actual force-close time.
    return { seconds: eodCutoffMin * 60 - totalSecs, nextLabel: 'EOD cutoff' }
  }
  return null
}

/** Format a close_reason string for display. Pass bot to get correct PT% for INFERNO. */
export function formatCloseReason(reason: string, bot?: string): { text: string; color: string } {
  const isInferno = bot === 'inferno'
  // FLAME/SPARK: 30/20/15 (reverted from 50/30/20 — see scanner.ts).
  // INFERNO: 50/30/10 displayed label kept; actual scanner behavior is
  // 20/30/50 reversed — a display inconsistency that predates this change.
  if (reason === 'profit_target_morning')
    return { text: `Profit Target (Morning ${isInferno ? '50' : '30'}%)`, color: 'text-emerald-400' }
  if (reason === 'profit_target_midday')
    return { text: `Profit Target (Midday ${isInferno ? '30' : '20'}%)`, color: 'text-yellow-400' }
  if (reason === 'profit_target_afternoon')
    return { text: `Profit Target (Afternoon ${isInferno ? '10' : '15'}%)`, color: 'text-orange-400' }
  if (reason === 'profit_target')
    return { text: 'Profit Target', color: 'text-emerald-400' }
  if (reason === 'stop_loss')
    return { text: 'Stop Loss', color: 'text-red-400' }
  if (reason === 'eod_cutoff' || reason === 'eod_safety' || reason === 'eod_safety_no_data')
    return { text: 'EOD Cutoff', color: 'text-amber-400' }
  if (reason === 'stale_holdover' || reason === 'stale_overnight_position')
    return { text: 'Stale Holdover', color: 'text-gray-400' }
  if (reason === 'expired_previous_day')
    return { text: 'Expired', color: 'text-blue-400' }
  if (reason === 'data_feed_failure')
    return { text: 'Data Failure', color: 'text-red-400' }
  if (reason === 'server_restart_recovery')
    return { text: 'Recovery', color: 'text-gray-400' }
  return { text: reason.replace(/_/g, ' '), color: 'text-gray-400' }
}
