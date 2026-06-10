import { NextRequest, NextResponse } from 'next/server'
import { validateSignup, type SignupPayload } from '@/lib/signup-validation'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Account Creation — STUB (Phase B).
 *
 * This endpoint performs SERVER-SIDE VALIDATION ONLY and returns success without
 * persisting anything. It deliberately does NOT:
 *   - create an auth user,
 *   - insert a Postgres `users` / `audit_events` row,
 *   - send a verification email,
 *   - create/update an Attio contact.
 *
 * Those are sub-projects C/D/E and must be wired behind THIS SAME request/response
 * contract so the /signup client form does not change.
 *
 * Request  (application/json): SignupPayload (see @/lib/signup-validation)
 * Response (200): { ok: true }
 * Response (400): { ok: false, error: string, fields?: Partial<Record<field,string>> }
 */
export async function POST(req: NextRequest) {
  let body: Partial<SignupPayload>
  try {
    body = (await req.json()) as Partial<SignupPayload>
  } catch {
    return NextResponse.json({ ok: false, error: 'Invalid request body.' }, { status: 400 })
  }

  const payload: SignupPayload = {
    firstName: String(body.firstName ?? ''),
    lastName: String(body.lastName ?? ''),
    email: String(body.email ?? ''),
    phone: String(body.phone ?? ''),
    state: String(body.state ?? ''),
    password: String(body.password ?? ''),
    confirmPassword: String(body.confirmPassword ?? ''),
    referralCode: String(body.referralCode ?? ''),
    ageConfirmed: Boolean(body.ageConfirmed),
    noAdviceAcknowledged: Boolean(body.noAdviceAcknowledged),
    electronicCommConsent: Boolean(body.electronicCommConsent),
  }

  const result = validateSignup(payload)
  if (!result.ok) {
    return NextResponse.json(
      { ok: false, error: 'Please correct the highlighted fields.', fields: result.errors },
      { status: 400 },
    )
  }

  // Stub: no persistence yet. The real pipeline (auth user -> Postgres users ->
  // Attio -> audit -> verification email) lands in sub-projects C/D/E.
  return NextResponse.json({ ok: true })
}
