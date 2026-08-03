import { NextRequest, NextResponse } from 'next/server'
import { ONBOARDING_COOKIE, verifyOnboardingToken } from '@/lib/auth/onboarding'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isCustomersDbConfigured, customerExecute } from '@/lib/customers-db'
import { createOrResumeEnrollment, recordAcceptedDocuments } from '@/lib/enrollment/service'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Records acceptance of the Legal & Disclosures step (sub-project F). Identifies the
 * customer from the signed onboarding cookie (fresh signup, no login session yet) OR
 * from their login session (resuming onboarding later), bumps users.onboarding_step →
 * 'legal_accepted', and writes a LEGAL_ACCEPTED audit with the acknowledgment flags.
 * Self-guards so it holds even in PUBLIC_MODE.
 *
 * The session fallback must match the page's (see onboarding/legal/page.tsx): the
 * onboarding cookie is device-local and 7-day-lived, so without this a returning
 * customer could reach the form and then get a bare 401 on submit — the same lockout,
 * one click later.
 */

function clientIp(req: NextRequest): string | null {
  const xff = req.headers.get('x-forwarded-for')
  return xff ? xff.split(',')[0].trim() : null
}

export async function POST(req: NextRequest) {
  const claims = await verifyOnboardingToken(req.cookies.get(ONBOARDING_COOKIE)?.value)
  const identity = await getCustomerIdentity()
  // Cookie OR mobile bearer. Shape preserved so the checks below read unchanged.
  const session = { customerId: identity?.customerId ?? null }
  // Token first (fresh signup), session second (resuming). Never a body-supplied id.
  const userId = claims?.uid ?? session.customerId
  if (!userId) {
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
      [userId],
    )
    try {
      await customerExecute(
        `INSERT INTO audit_events (user_id, event_type, ip_address, user_agent, metadata)
         VALUES ($1, 'LEGAL_ACCEPTED', $2, $3, $4)`,
        [userId, clientIp(req), req.headers.get('user-agent'), JSON.stringify(acks)],
      )
    } catch (e) {
      console.error('[onboarding] legal audit write failed:', e)
    }

    // ── Record the SAME acceptance the v1 chain reads (§3 LEGAL-01) ──────────────
    //
    // The audit row above is a log line: three booleans, no document version, nothing
    // joinable. `acceptedVersionsFor()` reads `legal_acceptances`, so without this a
    // customer who completed this funnel has zero acceptance rows and every required
    // document reads as stale — blocking activation permanently, with no screen to
    // re-accept on.
    //
    // The three checkboxes map exactly onto three registry codes (see legal.ts):
    // termsAccepted→TERMS, riskDisclosure→RISK, automatedExecution→TRADING_AUTH.
    // ELECTRONIC_CONSENT is not collected here and is left for the activation review,
    // which is where an Automate-scope consent belongs.
    //
    // Non-fatal: a customer must never be blocked at the legal step because a
    // convergence write failed. The backfill endpoint repairs any gap.
    try {
      const enrollment = await createOrResumeEnrollment(userId, 'onboarding')
      await recordAcceptedDocuments({
        userId,
        enrollmentId: enrollment.id,
        codes: ['TERMS', 'RISK', 'TRADING_AUTH'],
        ip: clientIp(req),
        userAgent: req.headers.get('user-agent'),
      })
    } catch (e) {
      console.error('[onboarding] versioned acceptance write failed:', e)
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
