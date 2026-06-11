import { NextRequest, NextResponse } from 'next/server'
import { ONBOARDING_COOKIE, verifyOnboardingToken } from '@/lib/auth/onboarding'
import { isCustomersDbConfigured, customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Records acceptance of the Legal & Disclosures step (sub-project F). Identifies the
 * customer from the signed onboarding cookie (no login session exists yet), bumps
 * users.onboarding_step → 'legal_accepted', and writes a LEGAL_ACCEPTED audit with the
 * acknowledgment flags. Self-guards on the cookie so it holds even in PUBLIC_MODE.
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
  const acks = {
    riskDisclosure: Boolean(body.riskDisclosure),
    automatedExecution: Boolean(body.automatedExecution),
    termsAccepted: Boolean(body.termsAccepted),
  }
  if (!acks.riskDisclosure || !acks.automatedExecution || !acks.termsAccepted) {
    return NextResponse.json(
      { ok: false, error: 'Please accept all disclosures to continue.' },
      { status: 400 },
    )
  }

  try {
    await customerExecute(
      `UPDATE users SET onboarding_step = 'legal_accepted', updated_at = now()
       WHERE id = $1 AND email_verified = TRUE`,
      [claims.uid],
    )
    try {
      await customerExecute(
        `INSERT INTO audit_events (user_id, event_type, ip_address, user_agent, metadata)
         VALUES ($1, 'LEGAL_ACCEPTED', $2, $3, $4)`,
        [claims.uid, clientIp(req), req.headers.get('user-agent'), JSON.stringify(acks)],
      )
    } catch (e) {
      console.error('[onboarding] legal audit write failed:', e)
    }
    return NextResponse.json({ ok: true })
  } catch (e) {
    console.error('[onboarding] accept-legal failed:', e)
    return NextResponse.json(
      { ok: false, error: 'Something went wrong. Please try again.' },
      { status: 500 },
    )
  }
}
