/**
 * Sliding Profit Target tiers — must match the scanner schedule exactly.
 *
 * Schedule (Central Time):
 *   FLAME / INFERNO (morning ends 10:30 AM):
 *     8:30 – 10:29  → 50% MORNING
 *     10:30 – 12:59 → 30% MIDDAY
 *     1:00 – 2:44   → 20% AFTERNOON
 *
 *   SPARK (morning extended to 12:00 PM per scanner — keeps the close limit
 *   aggressive longer to avoid stuck unfilled limits when the tier slides):
 *     8:30 – 11:59  → 50% MORNING
 *     12:00 – 12:59 → 30% MIDDAY
 *     1:00 – 2:44   → 20% AFTERNOON
 *
 *   2:45 PM+        → handled by EOD cutoff
 *
 * INFERNO (0DTE) uses its own reversed 20/30/50 schedule in scanner.ts;
 * the UI tier helpers below treat it like FLAME for display purposes.
 */

export type Bot = 'flame' | 'spark' | 'inferno'

export interface PTTier {
  pct: number
  label: string
  color: string       // Tailwind text color
  bgColor: string     // Tailwind badge background
  dotColor: string    // Tailwind dot color
}

const MORNING: PTTier = {
  pct: 0.50,
  label: 'Morning',
  color: 'text-emerald-400',
  bgColor: 'bg-emerald-500/20',
  dotColor: 'bg-emerald-400',
}

const MIDDAY: PTTier = {
  pct: 0.30,
  label: 'Midday',
  color: 'text-yellow-400',
  bgColor: 'bg-yellow-500/20',
  dotColor: 'bg-yellow-400',
}

const AFTERNOON: PTTier = {
  pct: 0.20,
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

/** Is it a weekday and between 8:30 AM and 3:00 PM CT? */
export function isMarketOpen(ctDate?: Date): boolean {
  const d = ctDate ?? getCTNow()
  const day = d.getDay()
  if (day === 0 || day === 6) return false
  const mins = d.getHours() * 60 + d.getMinutes()
  return mins >= 510 && mins < 900 // 8:30 AM – 3:00 PM
}

/** Morning-end minute for each bot (must mirror scanner.ts getSlidingProfitTarget). */
export function morningEndMinutes(bot?: string): number {
  return bot === 'spark' ? 720 : 630 // 12:00 PM CT for SPARK, else 10:30 AM CT
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
export function secondsUntilNextTier(ctDate?: Date, bot?: string): { seconds: number; nextLabel: string } | null {
  const d = ctDate ?? getCTNow()
  const mins = getCTMinutes(d)
  const secs = d.getSeconds()
  const totalSecs = mins * 60 + secs
  const morningEnd = morningEndMinutes(bot)

  if (mins < morningEnd) {
    // Morning → Midday at morningEnd
    return { seconds: morningEnd * 60 - totalSecs, nextLabel: '30% Midday' }
  }
  if (mins < 780) {
    // Midday → Afternoon at 1:00 PM (780 min = 46800 sec)
    return { seconds: 46800 - totalSecs, nextLabel: '20% Afternoon' }
  }
  if (mins < 885) {
    // Afternoon → EOD at 2:45 PM (885 min = 53100 sec)
    return { seconds: 53100 - totalSecs, nextLabel: 'EOD cutoff' }
  }
  return null
}

/** Format a close_reason string for display. Pass bot to get correct PT% for INFERNO. */
export function formatCloseReason(reason: string, bot?: string): { text: string; color: string } {
  const isInferno = bot === 'inferno'
  // FLAME/SPARK: 50/30/20 (Commit O, Apr 2026 — loosened from 30/20/15).
  // INFERNO: 50/30/10 kept unchanged (its displayed label was already
  // pre-existing; actual scanner behavior is 20/30/50 reversed — a display
  // inconsistency that predates this change, not fixed here per scope).
  if (reason === 'profit_target_morning')
    return { text: `Profit Target (Morning 50%)`, color: 'text-emerald-400' }
  if (reason === 'profit_target_midday')
    return { text: `Profit Target (Midday 30%)`, color: 'text-yellow-400' }
  if (reason === 'profit_target_afternoon')
    return { text: `Profit Target (Afternoon ${isInferno ? '10' : '20'}%)`, color: 'text-orange-400' }
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
