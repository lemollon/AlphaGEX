import { NextResponse } from 'next/server'

/**
 * Enrollment closure flag — 8/1 "Enrollment Waitlist Overlay" handoff.
 *
 * When `ENROLLMENT_WAITLIST_MODE === 'true'`, account creation is CLOSED:
 *   • the Create Account (/signup) and enrollment (/enroll/*) routes render a
 *     blocking "join the waitlist" overlay over the (inert) page, and
 *   • every account-creation API path rejects with 423 + a stable
 *     `ENROLLMENT_CLOSED` code.
 *
 * The overlay is UX, not the security control — closure is ALSO enforced
 * server-side on every create path (handoff §4/§11, "CSS dimming alone is
 * theater with better typography").
 *
 * Fail-secure toward the NORMAL flow: default is OPEN. Anything other than the
 * exact string 'true' (unset, '', 'false', '1') leaves enrollment open, so
 * removing the env var restores the original flow with no redesign or data
 * cleanup (handoff §14). Read at call time, never captured at module load, so a
 * config change takes effect on the next request without a rebuild — mirrors
 * `isPublicMode()` in lib/auth/access.ts.
 */

export const ENROLLMENT_CLOSED_CODE = 'ENROLLMENT_CLOSED'
export const WAITLIST_URL = '/waitlist'

export function isEnrollmentClosed(): boolean {
  return process.env.ENROLLMENT_WAITLIST_MODE === 'true'
}

/**
 * Standard rejection for account-creation endpoints while enrollment is closed.
 * 423 Locked + a stable machine code and the waitlist destination so callers can
 * redirect (handoff §7 "Recommended API contract").
 */
export function enrollmentClosedResponse() {
  return NextResponse.json(
    { code: ENROLLMENT_CLOSED_CODE, waitlistUrl: WAITLIST_URL, message: 'Enrollment is temporarily closed. Join the waitlist for early access.' },
    { status: 423 },
  )
}
