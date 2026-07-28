import { customerQuery, customerExecute } from '@/lib/customers-db'
import { isEligibleTradingDay, advanceTrial, TRIAL_ELIGIBLE_DAYS } from './trading-days'
import { getProductionPauseState } from '@/lib/tradier'
import { endTrialNow } from '@/lib/billing/stripe'

/**
 * Trial day-close ledger (Enrollment spec §7).
 *
 * Extracted from the ops route so the in-process scheduler and the manual endpoint run
 * THE SAME code. Two schedulers with two copies of this logic would eventually disagree
 * about what a trial day is, and the customer pays for that disagreement.
 *
 * IDEMPOTENT PER MARKET DATE via `last_counted_market_date`. Running twice on one day
 * cannot consume two of the customer's five days — which matters for a retried cron, a
 * manual re-run during an incident, or a brief window where two instances overlap.
 */

export interface TrialRow {
  id: string
  user_id: string
  agent_code: string
  eligible_days_used: number
  last_counted_market_date: string | null
  stripe_subscription_id: string | null
}

export interface TrialCloseResult {
  market_date: string
  counted: number
  converted: number
  summary: string
  results: Array<Record<string, unknown>>
}

export function marketDateKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export async function loadActiveTrials(): Promise<TrialRow[]> {
  return customerQuery<TrialRow>(
    `SELECT t.id, t.user_id, t.agent_code, t.eligible_days_used,
            to_char(t.last_counted_market_date, 'YYYY-MM-DD') AS last_counted_market_date,
            s.stripe_subscription_id
       FROM trials t
       LEFT JOIN customer_bot_subscriptions s
         ON s.user_id = t.user_id AND s.bot = t.agent_code
      WHERE t.status = 'active'`,
  )
}

/**
 * Advance every active trial by one market date.
 *
 * ⚠️ CALL ONLY AFTER THE CLOSE. `isEligibleTradingDay` deliberately has no time-of-day
 * check — it answers "is this DATE a trading day", not "is the session over". Calling
 * this at 9am would consume the day before it happened, and the per-date idempotence
 * would then lock that mistake in. The caller owns the when; see `isAfterTrialCloseTime`.
 */
export async function runTrialDayClose(ct: Date): Promise<TrialCloseResult> {
  const today = marketDateKey(ct)
  const results: Array<Record<string, unknown>> = []
  const trials = await loadActiveTrials()

  for (const t of trials) {
    if (t.last_counted_market_date === today) {
      results.push({ trial: t.id, skipped: 'already_counted_today' })
      continue
    }

    // Per-bot pause participates: a bot the platform disabled today did not give the
    // customer a trading day. Fails CLOSED — an unreadable pause state counts as paused,
    // which errs toward giving the customer the day back.
    const pause = await getProductionPauseState(t.agent_code).catch(() => ({ paused: true }))
    const verdict = isEligibleTradingDay({ ct, platformDisabled: pause.paused === true })

    if (!verdict.eligible) {
      results.push({ trial: t.id, counted: false, reason: verdict.reason })
      continue
    }

    const progress = advanceTrial(t.eligible_days_used, verdict)
    await customerExecute(
      `UPDATE trials
          SET eligible_days_used = $2, last_counted_market_date = $3::date, updated_at = now()
        WHERE id = $1`,
      [t.id, progress.daysUsed, today],
    )

    if (progress.shouldConvert) {
      // End the Stripe trial NOW; the webhook then moves the row to active when the
      // invoice is paid. We do NOT mark it paid ourselves — billing state is Stripe's
      // word (§7 "Webhook state is authoritative for billing").
      if (t.stripe_subscription_id) {
        await endTrialNow(t.stripe_subscription_id)
      }
      await customerExecute(
        `UPDATE trials SET status = 'completed', completed_at = now(), updated_at = now() WHERE id = $1`,
        [t.id],
      )
      results.push({ trial: t.id, counted: true, days_used: progress.daysUsed, converted: true })
    } else {
      results.push({ trial: t.id, counted: true, days_used: progress.daysUsed, converted: false })
    }
  }

  const counted = results.filter((r) => r.counted).length
  const converted = results.filter((r) => r.converted).length
  return {
    market_date: today,
    counted,
    converted,
    summary:
      counted === 0
        ? 'No trial day consumed today.'
        : `${counted} trial(s) advanced, ${converted} converted to paid.`,
    results,
  }
}

/**
 * 15:05 CT — five minutes after the 15:00 CT equity close.
 *
 * The trial ledger must never count a day that is still being traded. The cushion covers
 * the bots' own EOD close (14:50 CT cutoff) plus fill settlement, so by the time a day is
 * counted it is genuinely finished.
 */
export const TRIAL_CLOSE_MINUTES_CT = 15 * 60 + 5

/** Dry-run helper and scheduler guard share one definition of "after the close". */
export function isAfterTrialCloseTime(ct: Date): boolean {
  return ct.getHours() * 60 + ct.getMinutes() >= TRIAL_CLOSE_MINUTES_CT
}
