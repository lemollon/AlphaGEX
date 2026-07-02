/**
 * Event-blackout gate for the IronForge scanner.
 *
 * Returns whether a bot is currently in a macro-event blackout window
 * (FOMC, custom events).  Cheap (one config read + one indexed range query),
 * intended to be called as the first gate inside the open-trade path.
 *
 * Defaults to ENABLED when no config row exists.  On DB error, fails OPEN
 * (returns blocked=false) so a transient blip can never indefinitely freeze
 * trading.  The macro event is rare; getting one trade through during a DB
 * hiccup is preferable to silently halting the scanner.
 */

import { query } from '../db'
import { findCurrentBlackout } from './repo'

/**
 * Master switch for the macro-event blackout halt.
 *
 * DISABLED 2026-07-02 (per operator). Rationale: the validated SPARK backtest
 * (2020–2026) already traded through every FOMC / CPI / NFP in-sample and stayed
 * +EV and survivable — event days are already priced into the edge. SPARK's real
 * risk control is the code-enforced 15% BP size cap with the stop-off swing
 * (scanner.ts), not a calendar halt. The blackout was a redundant post-hoc overlay
 * that only cost trades the strategy would otherwise take (and idled the bots for
 * paying customers on the busiest macro days). Disabling it for all three bots
 * (FLAME / SPARK / INFERNO) realigns live behavior with the backtest.
 *
 * Everything below (per-bot `event_blackout_enabled` toggle, calendar, halt-window
 * math, dashboard banner) is left fully intact — flip this back to `true` to
 * re-arm the halt with no other change.
 */
export const BLACKOUT_HALT_ENABLED: boolean = false

export interface BlackoutResult {
  blocked: boolean
  reason?: string
  eventId?: string
  eventTitle?: string
  resumesAt?: Date
}

function formatCT(d: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Chicago',
    month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
    hour12: true,
  }).format(d) + ' CT'
}

export async function isEventBlackoutActive(bot: string, now: Date): Promise<BlackoutResult> {
  // Master kill: event-blackout halt globally disabled (see BLACKOUT_HALT_ENABLED).
  // Single chokepoint for both the scanner halt and the dashboard banner, so this
  // clears the halt everywhere (including any currently-active window) for all bots.
  if (!BLACKOUT_HALT_ENABLED) return { blocked: false }

  const botKey = bot.toLowerCase()
  if (botKey !== 'flame' && botKey !== 'spark' && botKey !== 'inferno') {
    return { blocked: false }
  }

  // 1. Per-bot toggle. Default: enabled if no row or column missing.
  let enabled = true
  try {
    const rows = await query<{ event_blackout_enabled: boolean | null }>(
      `SELECT event_blackout_enabled FROM ${botKey}_config LIMIT 1`,
    )
    if (rows.length > 0 && rows[0].event_blackout_enabled === false) {
      enabled = false
    }
  } catch {
    // Column missing on a freshly-deployed schema or DB hiccup — treat as enabled.
  }
  if (!enabled) return { blocked: false }

  // 2. Window check.
  let row: Awaited<ReturnType<typeof findCurrentBlackout>>
  try {
    row = await findCurrentBlackout(now)
  } catch {
    return { blocked: false } // fail-open
  }
  if (!row) return { blocked: false }

  const resumesAt = row.halt_end_ts instanceof Date ? row.halt_end_ts : new Date(row.halt_end_ts)
  return {
    blocked: true,
    reason: `event_blackout(${row.title} until ${formatCT(resumesAt)})`,
    eventId: row.event_id,
    eventTitle: row.title,
    resumesAt,
  }
}
