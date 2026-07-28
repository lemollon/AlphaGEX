import { NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { isPublicMode } from '@/lib/auth/access'
import { isCustomersDbConfigured } from '@/lib/customers-db'
import { isEligibleTradingDay, TRIAL_ELIGIBLE_DAYS } from '@/lib/enrollment/trading-days'
import {
  runTrialDayClose,
  loadActiveTrials,
  marketDateKey,
  isAfterTrialCloseTime,
} from '@/lib/enrollment/trial-close'
import { getCTNow } from '@/lib/pt-tiers'
import { errorEnvelope, statusFor, redactProviderError } from '@/lib/enrollment/errors'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Trial day-close (Enrollment spec §7) — MANUAL / diagnostic entry point.
 *
 * GET  — dry run: what today would do.
 * POST — advance the ledger by one market date and convert anyone who reaches five.
 *
 * The ledger normally runs ITSELF: the scanner process fires it after the close each
 * day (see scanner.ts). This route stays for operator re-runs and for inspecting the
 * decision, and shares the same `runTrialDayClose` so the two can never diverge.
 *
 * Weekends and holidays are no-ops by construction — isEligibleTradingDay refuses them —
 * and the per-market-date guard makes a double run harmless.
 */

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
    // The scheduler will not act before this flips true; surfaced so an operator can
    // see WHY an automatic run has not happened yet today.
    after_close: isAfterTrialCloseTime(ct),
    active_trials: trials.length,
    already_counted_today: trials.filter((t) => t.last_counted_market_date === today).length,
    would_convert: verdict.eligible
      ? trials.filter(
          (t) => t.last_counted_market_date !== today && t.eligible_days_used + 1 >= TRIAL_ELIGIBLE_DAYS,
        ).length
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

  try {
    // Deliberately NOT time-gated: an operator re-running this after an incident is
    // making a considered choice, and the per-date guard still protects the ledger.
    // The AUTOMATIC path is the one that must wait for the close.
    const out = await runTrialDayClose(getCTNow())
    return NextResponse.json({ ok: true, ...out })
  } catch (e) {
    const env = redactProviderError('trial-close-day', e, 'INTERNAL', 'Trial close failed.')
    return NextResponse.json(env, { status: statusFor(env.code) })
  }
}
