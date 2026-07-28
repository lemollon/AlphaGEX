import { NextRequest, NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { isPublicMode } from '@/lib/auth/access'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'
import { isEligibleTradingDay, advanceTrial, TRIAL_ELIGIBLE_DAYS } from '@/lib/enrollment/trading-days'
import { getCTNow } from '@/lib/pt-tiers'
import { getProductionPauseState } from '@/lib/tradier'
import { endTrialNow } from '@/lib/billing/stripe'
import { errorEnvelope, statusFor, redactProviderError } from '@/lib/enrollment/errors'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Trial day-close (Enrollment spec §7).
 *
 * GET  — dry run: what today would do.
 * POST — advance the ledger by one market date and convert anyone who reaches five.
 *
 * Run once after the close, each weekday. Weekends and holidays are no-ops by
 * construction — isEligibleTradingDay refuses them — so a scheduler that fires every
 * day is harmless.
 *
 * IDEMPOTENT PER MARKET DATE. `last_counted_market_date` means running twice on the
 * same day cannot consume two of the customer's five days. That matters more than it
 * sounds: a retried cron, a manual re-run during an incident, or two overlapping
 * schedulers would otherwise silently shorten every active trial.
 *
 * A platform-disabled day never counts — "our outage is not the customer's trial day".
 */

interface TrialRow {
  id: string
  user_id: string
  agent_code: string
  eligible_days_used: number
  last_counted_market_date: string | null
  stripe_subscription_id: string | null
}

async function loadActiveTrials(): Promise<TrialRow[]> {
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

function marketDateKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

async function gate() {
  if (isPublicMode()) return null
  const ops = await getSession()
  if (!ops.userId) {
    const e = errorEnvelope('UNAUTHORIZED', 'Operator session required.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  return null
}

export async function GET() {
  const blocked = await gate()
  if (blocked) return blocked
  if (!isCustomersDbConfigured()) {
    const e = errorEnvelope('NOT_CONFIGURED', 'Customers DB not configured.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  const ct = getCTNow()
  const today = marketDateKey(ct)
  const trials = await loadActiveTrials()
  const verdict = isEligibleTradingDay({ ct })

  return NextResponse.json({
    dryRun: true,
    market_date: today,
    day_is_eligible: verdict.eligible,
    reason: verdict.reason ?? null,
    active_trials: trials.length,
    already_counted_today: trials.filter((t) => t.last_counted_market_date === today).length,
    would_convert: verdict.eligible
      ? trials.filter((t) => t.last_counted_market_date !== today && t.eligible_days_used + 1 >= TRIAL_ELIGIBLE_DAYS).length
      : 0,
  })
}

export async function POST() {
  const blocked = await gate()
  if (blocked) return blocked
  if (!isCustomersDbConfigured()) {
    const e = errorEnvelope('NOT_CONFIGURED', 'Customers DB not configured.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }

  const ct = getCTNow()
  const today = marketDateKey(ct)
  const results: Array<Record<string, unknown>> = []

  try {
    const trials = await loadActiveTrials()
    for (const t of trials) {
      // Idempotence per market date — the guard that stops a re-run stealing a day.
      if (t.last_counted_market_date === today) {
        results.push({ trial: t.id, skipped: 'already_counted_today' })
        continue
      }

      // Per-bot pause participates: a bot the platform disabled today did not give the
      // customer a trading day.
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
    return NextResponse.json({
      ok: true,
      market_date: today,
      counted,
      converted,
      summary: counted === 0
        ? 'No trial day consumed today.'
        : `${counted} trial(s) advanced, ${converted} converted to paid.`,
      results,
    })
  } catch (e) {
    const env = redactProviderError('trial-close-day', e, 'INTERNAL', 'Trial close failed.')
    return NextResponse.json(env, { status: statusFor(env.code) })
  }
}
