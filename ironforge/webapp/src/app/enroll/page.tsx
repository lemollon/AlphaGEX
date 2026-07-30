import type { Metadata } from 'next'
import { redirect } from 'next/navigation'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomersDbConfigured } from '@/lib/customers-db'
import {
  advanceBillingIfComplete,
  ensureLegalDocumentsSeeded,
  getOpenEnrollment,
  createOrResumeEnrollment,
  nextStepFor,
} from '@/lib/enrollment/service'
import { ownsStrategy, hasActiveMembership } from '@/lib/live/membership'
import { routeForNextStep } from './steps'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Get started — IronForge',
  description: 'Choose your membership, accept the agreements, and set up automated trading.',
}

/**
 * /enroll — THE front door after login/verification (cutover 7/30) and the funnel's
 * resume point. Ownership-aware, so one URL is safe for everyone:
 *
 *  - open enrollment       → resume at the server-owned step (§3 DONE-01)
 *  - owns a strategy       → /live (their product; never re-enter the funnel)
 *  - active community only → /community
 *  - nothing yet           → start a fresh enrollment at the plan screen
 *
 * Without the ownership checks, every returning paying customer would be handed a
 * brand-new draft enrollment and a plan-selection screen for a membership they
 * already pay for. Each funnel screen still re-checks on mount, so nothing depends
 * on arriving through this door.
 */
export default async function EnrollPage() {
  const session = await getCustomerSession()
  if (!session.customerId) redirect('/login?next=/enroll')

  let route = '/enroll/plan'
  if (isCustomersDbConfigured()) {
    try {
      await ensureLegalDocumentsSeeded()
      const open = await getOpenEnrollment(session.customerId)
      if (open) {
        const enrollment = await advanceBillingIfComplete(open)
        route = routeForNextStep(nextStepFor(enrollment), enrollment.selected_plan).route
      } else if (await ownsStrategy(session.customerId)) {
        route = '/live'
      } else if (await hasActiveMembership(session.customerId)) {
        route = '/community'
      } else {
        const enrollment = await createOrResumeEnrollment(session.customerId, 'enroll_page')
        route = routeForNextStep(nextStepFor(enrollment), enrollment.selected_plan).route
      }
    } catch {
      // Fall through to the first screen; it resumes client-side and surfaces errors.
    }
  }
  redirect(route)
}
