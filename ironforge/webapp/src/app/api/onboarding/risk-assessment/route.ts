import { NextRequest, NextResponse } from 'next/server'
import { ONBOARDING_COOKIE, verifyOnboardingToken } from '@/lib/auth/onboarding'
import { scoreToProfile, validateRiskAnswers } from '@/lib/onboarding/risk-scoring'
import { isCustomersDbConfigured, customerExecute, customerTransaction } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Records the onboarding risk assessment (suitability → recommended bot). Identifies the
 * customer from the signed onboarding cookie (no login session exists yet), computes the
 * risk profile, stores the assessment + denormalizes tier/bot onto users, bumps
 * onboarding_step → 'risk_assessed', and writes a RISK_ASSESSMENT_COMPLETED audit.
 * Self-guards on the cookie so it holds even in PUBLIC_MODE. Advisory — never blocks.
 */

function clientIp(req: NextRequest): string | null {
  const xff = req.headers.get('x-forwarded-for')
  return xff ? xff.split(',')[0].trim() : null
}

export async function POST(req: NextRequest) {
  const claims = await verifyOnboardingToken(req.cookies.get(ONBOARDING_COOKIE)?.value)
  if (!claims) {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }
  if (!isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'Onboarding is temporarily unavailable. Please try again shortly.' },
      { status: 503 },
    )
  }

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  const answers = body.answers
  if (!validateRiskAnswers(answers)) {
    return NextResponse.json({ ok: false, error: 'Please answer every question.' }, { status: 400 })
  }

  const profile = scoreToProfile(answers)

  try {
    await customerTransaction(async (run) => {
      await run(
        `INSERT INTO risk_assessments (user_id, answers, score, tier, recommended_bot)
         VALUES ($1, $2, $3, $4, $5)`,
        [claims.uid, JSON.stringify(answers), profile.score, profile.tier, profile.recommendedBot],
      )
      await run(
        `UPDATE users
            SET risk_tier = $2, recommended_bot = $3,
                onboarding_step = 'risk_assessed', updated_at = now()
          WHERE id = $1 AND email_verified = TRUE`,
        [claims.uid, profile.tier, profile.recommendedBot],
      )
    })

    try {
      await customerExecute(
        `INSERT INTO audit_events (user_id, event_type, ip_address, user_agent, metadata)
         VALUES ($1, 'RISK_ASSESSMENT_COMPLETED', $2, $3, $4)`,
        [
          claims.uid,
          clientIp(req),
          req.headers.get('user-agent'),
          JSON.stringify({ score: profile.score, tier: profile.tier, recommended_bot: profile.recommendedBot }),
        ],
      )
    } catch (e) {
      console.error('[risk-assessment] audit write failed:', e)
    }

    return NextResponse.json({
      ok: true,
      score: profile.score,
      tier: profile.tier,
      recommendedBot: profile.recommendedBot,
      caution: profile.caution,
    })
  } catch (e) {
    console.error('[risk-assessment] failed:', e)
    return NextResponse.json(
      { ok: false, error: 'Something went wrong. Please try again.' },
      { status: 500 },
    )
  }
}
