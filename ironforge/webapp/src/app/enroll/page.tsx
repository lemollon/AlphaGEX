import type { Metadata } from 'next'
import { redirect } from 'next/navigation'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomersDbConfigured } from '@/lib/customers-db'
import { advanceBillingIfComplete, createOrResumeEnrollment, ensureLegalDocumentsSeeded, nextStepFor } from '@/lib/enrollment/service'
import { routeForNextStep } from './steps'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Get started — IronForge',
  description: 'Choose your membership, accept the agreements, and set up automated trading.',
}

/**
 * /enroll — entry + resume point for the enrollment funnel (July 29 handoff).
 *
 * Route-per-screen: this page only asks the server where the customer is and
 * redirects to that screen. The server owns funnel position (§3 DONE-01); a deep link
 * from an email lands here and cannot disagree with the record. Each screen also
 * re-checks on mount, so nothing depends on arriving through this door.
 *
 * Still UNLINKED site-wide: nothing navigates here until the cutover flip, exactly
 * like the spine it replaces (#2679).
 */
export default async function EnrollPage() {
  const session = await getCustomerSession()
  if (!session.customerId) redirect('/login?next=/enroll')

  let route = '/enroll/plan'
  if (isCustomersDbConfigured()) {
    try {
      await ensureLegalDocumentsSeeded()
      const enrollment = await advanceBillingIfComplete(
        await createOrResumeEnrollment(session.customerId, 'enroll_page'),
      )
      route = routeForNextStep(nextStepFor(enrollment), enrollment.selected_plan).route
    } catch {
      // Fall through to the first screen; it resumes client-side and surfaces errors.
    }
  }
  redirect(route)
}
