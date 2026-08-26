/**
 * "THIS BOT HAS NOT TRADED" — the symptom net.
 *
 * The expired-position watchdog fixes one cause. This catches the SYMPTOM, whatever
 * the cause: FLAME and SPARK each expect roughly one entry per trading day, so a run
 * of trading days with zero opens and no strategy reason for it means something is
 * broken — a blocked entry, a dead scanner, a config that reads nothing, a stuck
 * position, or the next thing nobody has thought of. It would have fired on 8/22,
 * four days before a human noticed the page looked stuck.
 *
 * 🚨 THE ALLOWLIST IS THE WHOLE DESIGN. A quiet day is EXPLAINED only by a skip the
 * STRATEGY chose — VIX elevated, already traded, standing down after a loss, credit
 * too thin. Every other skip is PLUMBING (`skip:no_paper_account`,
 * `skip:insufficient_bp`, `skip:tradier_not_configured`, `vix_unavailable`), and those
 * are precisely the silent failures this is meant to catch. Treating them as
 * explanations would blind the net to its own bug class — `skip:no_paper_account`
 * already ran forever on one bot, silently, looking exactly like a decision.
 *
 * So the allowlist is deliberately NARROW and an unrecognised reason counts as
 * SILENCE. This over-alerts on a new strategy skip; the alternative is going blind on
 * a new failure. Only one of those costs trading days.
 *
 * Pure: no DB, no clock. The scanner gathers the days and hands them in.
 */

/** Consecutive trading days of unexplained silence before the alert fires. */
export const HEARTBEAT_SILENT_DAYS = 2

/**
 * CT time-of-day the check runs. After every bot's entry window has closed (FLAME
 * 13:10, SPARK's entry_end is earlier still) so "today produced no entry" is a
 * settled fact, and before the 15:10 CT end of the scan loop.
 */
export const HEARTBEAT_CHECK_HHMM = 1430

/**
 * Calendar days of history the check reads. Comfortably more than the threshold, so a
 * long holiday weekend or a bot that has been quiet for a while still produces enough
 * TRADING days to judge — and bounded, so the log scan stays cheap.
 */
export const HEARTBEAT_LOOKBACK_DAYS = 21

/**
 * Skip markers that EXPLAIN a day with no entry — the strategy looked and declined.
 *
 * Matched as substrings of the scan `reason`, because most carry parameters
 * (`vix_elevated(1.410>1.25)`, `max_trades_reached(1/1)`). Add to this list ONLY a
 * reason that means the strategy chose not to trade. A reason that means something is
 * broken or unconfigured must NOT be here.
 */
export const STRATEGY_SKIP_MARKERS: readonly string[] = [
  'vix_elevated',                // VIX decay regime gate — a deliberate stand-aside
  'vix_too_high',                // hard VIX cap
  'already_traded_today',        // it DID trade; this is the healthiest reason of all
  'max_trades_reached',          // same, from the no_trade branch
  'standdown_after_loss',        // stand-down window after a losing close
  'cooldown_after_first_loss',   // intraday cooldown
  'neg_gamma_env',               // confirmed negative-gamma day, skip_neg_gamma bots
  'credit_too_low',              // thin tape — skipping is the validated behaviour
  'credit_pct_too_low',
  'event_blackout',              // calendar event gate
  'advisor(',                    // the oracle said SKIP
]

/** True when this scan reason means the STRATEGY declined, not that something broke. */
export function isStrategySkip(reason: string): boolean {
  if (!reason) return false
  const r = reason.toLowerCase()
  return STRATEGY_SKIP_MARKERS.some(m => r.includes(m.toLowerCase()))
}

export type HeartbeatDay = {
  /** CT calendar date, YYYY-MM-DD. Trading days only — the caller filters weekends/holidays. */
  date: string
  /** Positions opened that day, any account type. */
  opens: number
  /** Every distinct scan `reason` logged that day. */
  reasons: readonly string[]
}

export type HeartbeatVerdict = {
  /** True when the run of unexplained zero-open days has reached the threshold. */
  silent: boolean
  /** Length of the current run of unexplained zero-open days, counting back from the newest. */
  silentDays: number
  /** The dates in that run, oldest first. */
  dates: string[]
  /** Human-readable line, or null when there is nothing to say. */
  message: string | null
}

/**
 * Count back from the most recent trading day for as long as days are BOTH
 * zero-open AND unexplained. The run stops at the first day that traded or that the
 * strategy explained — it is a CONSECUTIVE run, not a total.
 *
 * `days` must be trading days only, oldest first.
 */
export function evaluateTradeHeartbeat(
  botName: string,
  days: readonly HeartbeatDay[],
  threshold: number = HEARTBEAT_SILENT_DAYS,
): HeartbeatVerdict {
  const run: HeartbeatDay[] = []
  for (let i = days.length - 1; i >= 0; i--) {
    const d = days[i]
    if (d.opens > 0) break
    if (d.reasons.some(isStrategySkip)) break
    run.unshift(d)
  }

  const silentDays = run.length
  const silent = silentDays >= threshold && threshold > 0

  if (!silent) {
    return { silent: false, silentDays, dates: run.map(d => d.date), message: null }
  }

  const name = botName.toUpperCase()
  return {
    silent: true,
    silentDays,
    dates: run.map(d => d.date),
    message:
      `${name} has not opened a position in ${silentDays} trading day` +
      `${silentDays === 1 ? '' : 's'} (${run[0].date}..${run[silentDays - 1].date}) ` +
      `and gave no strategy reason for it. Expect ~1 entry per trading day — ` +
      `check for a stuck position, a blocked entry gate, or a dead scanner.`,
  }
}
