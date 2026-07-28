import { isMarketHoliday, isEarlyClose, calendarCoversYear } from '@/lib/market-calendar'

/**
 * The five ELIGIBLE TRADING DAY trial (Enrollment spec §7).
 *
 * "Five trading days", never five calendar days. A weekend plus a holiday can consume
 * most of a calendar trial before the customer has seen the product trade once, which
 * is precisely what the spec forbids and why Stripe's `trial_period_days` CANNOT be
 * used to express this: Stripe only counts wall-clock days.
 *
 * How this composes with Stripe: the subscription is created in `trialing` with a far
 * `trial_end`, and when this ledger reaches TRIAL_ELIGIBLE_DAYS we end the trial
 * programmatically. Stripe stays the billing authority; the CALENDAR authority is here.
 *
 * The trial counter starts only inside the successful activation transaction (§7) —
 * not at card capture, subscription intent, brokerage connection or agent config.
 * Nothing in this module can start it; it only decides whether a given day counts.
 *
 * Pure: the caller passes the date. No clock, so tests are deterministic.
 */

export const TRIAL_ELIGIBLE_DAYS = 5

/**
 * Product decisions the spec explicitly defers ("Product decision required before
 * production"), recorded here as CONFIGURATION rather than scattered conditionals so
 * there is one place to change them and one place to read what was decided.
 *
 * Defaults follow the spec's own recommendation: exchange-open + platform-available
 * days count even when no trade qualified, and user-paused days count once activated,
 * which is what prevents an indefinite trial. Early closes are treated as full trading
 * days — the session happened and the strategy could trade it.
 *
 * ⚠️ These are the values under the doc's launch blocker. They must be confirmed in
 * writing before Automate ships.
 */
export interface TrialDayPolicy {
  /** Count a shortened session (e.g. day after Thanksgiving) as an eligible day. */
  countEarlyCloseSessions: boolean
  /** Count a day the CUSTOMER paused. True stops a paused trial running forever. */
  countUserPausedDays: boolean
  /** Count a day where the strategy found no qualifying setup. */
  countNoQualifyingTradeDays: boolean
}

export const DEFAULT_TRIAL_DAY_POLICY: TrialDayPolicy = {
  countEarlyCloseSessions: true,
  countUserPausedDays: true,
  countNoQualifyingTradeDays: true,
}

export interface DayContext {
  /** The market date being judged, as a Central-Time Date. */
  ct: Date
  /** Platform-wide disable (kill switch, outage). Never counts — not the customer's day. */
  platformDisabled?: boolean
  /** The customer had trading paused for this day. */
  userPaused?: boolean
  /** The strategy found no qualifying setup. */
  noQualifyingTrade?: boolean
}

export type IneligibleReason =
  | 'weekend'
  | 'market_holiday'
  | 'platform_disabled'
  | 'user_paused'
  | 'no_qualifying_trade'
  | 'early_close'
  | 'calendar_not_covered'

export interface DayVerdict {
  eligible: boolean
  reason?: IneligibleReason
}

/**
 * Does this market date consume one of the five trial days?
 *
 * Order matters: exchange-closed reasons are checked FIRST, because a weekend or
 * holiday is never the customer's day regardless of any policy flag.
 */
export function isEligibleTradingDay(
  ctx: DayContext,
  policy: TrialDayPolicy = DEFAULT_TRIAL_DAY_POLICY,
): DayVerdict {
  const { ct } = ctx

  // Fail CLOSED on an unknown year: charging someone because our holiday table ran out
  // is worse than a trial running one day long. LAST_COVERED_YEAR is 2027.
  if (!calendarCoversYear(ct.getFullYear())) {
    return { eligible: false, reason: 'calendar_not_covered' }
  }

  const dow = ct.getDay()
  if (dow === 0 || dow === 6) return { eligible: false, reason: 'weekend' }
  if (isMarketHoliday(ct)) return { eligible: false, reason: 'market_holiday' }

  // Our outage is not the customer's trial day. Checked before the user-side reasons.
  if (ctx.platformDisabled) return { eligible: false, reason: 'platform_disabled' }

  if (!policy.countEarlyCloseSessions && isEarlyClose(ct)) {
    return { eligible: false, reason: 'early_close' }
  }
  if (!policy.countUserPausedDays && ctx.userPaused) {
    return { eligible: false, reason: 'user_paused' }
  }
  if (!policy.countNoQualifyingTradeDays && ctx.noQualifyingTrade) {
    return { eligible: false, reason: 'no_qualifying_trade' }
  }
  return { eligible: true }
}

export interface TrialProgress {
  daysUsed: number
  daysRemaining: number
  /** True once the trial has been fully consumed and should convert to paid. */
  shouldConvert: boolean
}

/** Fold a day's verdict into the running ledger. Never exceeds TRIAL_ELIGIBLE_DAYS. */
export function advanceTrial(daysUsed: number, verdict: DayVerdict): TrialProgress {
  const used = Math.min(TRIAL_ELIGIBLE_DAYS, Math.max(0, daysUsed) + (verdict.eligible ? 1 : 0))
  return {
    daysUsed: used,
    daysRemaining: Math.max(0, TRIAL_ELIGIBLE_DAYS - used),
    shouldConvert: used >= TRIAL_ELIGIBLE_DAYS,
  }
}

/**
 * Customer-facing trial label. Says TRADING days, because "5 days" is the ambiguity the
 * spec is trying to remove (§3, PLAN-01: the badge "must say five trading-day free
 * trial, not five calendar days").
 */
export function trialLabel(daysUsed: number): string {
  const left = Math.max(0, TRIAL_ELIGIBLE_DAYS - daysUsed)
  if (left === 0) return 'Trial complete'
  return `${left} of ${TRIAL_ELIGIBLE_DAYS} trading ${left === 1 ? 'day' : 'days'} left`
}
