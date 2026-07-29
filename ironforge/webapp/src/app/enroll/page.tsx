import type { Metadata } from 'next'
import { redirect } from 'next/navigation'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import EnrollClient from './EnrollClient'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Set up your strategy — IronForge',
  description: 'Choose a plan, accept the agreements, and connect the account your strategy will trade.',
}

/**
 * /enroll — the enrollment v2 funnel (spec §2).
 *
 * Built ALONGSIDE the legacy /onboarding/* funnel, which is untouched and still the live
 * path. This route adds nothing to a customer's journey until it is linked to; nothing
 * here changes what an existing customer sees.
 *
 * ⚠️ HOW FAR THIS CAN GO TODAY. Activation needs a broker_accounts row with
 * eligibility 'eligible', and that verdict requires an options approval level. Only
 * Tradier reports one, and Tradier OAuth is not provisioned — so the funnel runs
 * correctly to ACCOUNT SELECTION and then stops there, showing each connected account
 * with the real reason it cannot be used ("Options approval level 3 is required").
 *
 * That is a true screen, not a broken one, and the steps before it are fully
 * exercisable. The configure and activate steps are deliberately NOT built yet: they
 * cannot be run against real data until credentials exist, and shipping screens nobody
 * can execute is how untested paths reach customers.
 */
export default async function EnrollPage() {
  const session = await getCustomerSession()
  if (!session.customerId) redirect('/login?next=/enroll')
  return <EnrollClient />
}
