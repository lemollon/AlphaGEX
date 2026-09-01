/**
 * "Risky setups skipped" counter — reframes a no-trade day as SPARK/FLAME's
 * protection rules doing their job, not the bot doing nothing.
 *
 * Honest-data rule: this must never overcount. The scanner writes a SCAN log
 * row roughly once a minute, so a single blocked day produces many rows with
 * the SAME reason — those collapse to ONE protected day (see
 * countProtectiveSkipDays). A day where the bot also traded later (an early
 * soft block that cleared) must NOT count: nothing was skipped that day.
 *
 * The prefix list below is a DELIBERATE judgment call, not "every skip:
 * reason". Only gates that decline a trade for a genuine risk/quality reason
 * count as "protective" — infra failures (no quote, race guards, backoff,
 * already-traded-today) are operational non-events and counting them would
 * misrepresent an outage as risk management.
 */

/** Reason prefixes (including the `skip:` tag) that represent a real
 *  risk/quality gate declining a trade — see the module doc above. */
export const PROTECTIVE_REASON_PREFIXES: readonly string[] = [
  'skip:vix_elevated',
  'skip:vix_bad_window',
  'skip:vix_too_high',
  'skip:event_blackout',
  'skip:cooldown_after_first_loss',
  'skip:standdown',
  'skip:standdown_after_loss',
  'skip:credit_too_low',
  'skip:credit_pct_too_low',
  'skip:neg_gamma_env',
]

/** True when `reason` is a genuine protective-gate skip. Never throws — a
 *  null/malformed reason (one bad log row) must not break the caller's loop. */
export function isProtectiveSkip(reason: string | null | undefined): boolean {
  if (!reason || typeof reason !== 'string') return false
  return PROTECTIVE_REASON_PREFIXES.some((p) => reason.startsWith(p))
}

/** CT calendar date (America/Chicago) as YYYY-MM-DD, matching the
 *  `en-CA` pattern already used elsewhere in lib/live (e.g. summary.ts,
 *  ctTodayDate) for CT-date formatting. */
function ctDateString(logTime: string | Date): string | null {
  const d = logTime instanceof Date ? logTime : new Date(logTime)
  if (isNaN(d.getTime())) return null
  return d.toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })
}

/**
 * Group scan-log rows by CT calendar date, keep only dates with at least one
 * protective-gate skip, then subtract any date the bot actually traded.
 * Pure — no DB access — so it is fully unit-testable.
 */
export function countProtectiveSkipDays(input: {
  logs: Array<{ logTime: string | Date; reason: string | null }>
  tradedCtDates: Set<string>
}): number {
  const protectiveDates = new Set<string>()
  for (const row of input.logs) {
    if (!isProtectiveSkip(row.reason)) continue
    const ctDate = ctDateString(row.logTime)
    if (!ctDate) continue
    protectiveDates.add(ctDate)
  }
  return Array.from(protectiveDates).filter((date) => !input.tradedCtDates.has(date)).length
}
