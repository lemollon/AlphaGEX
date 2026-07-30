import type { Metadata } from 'next'
import { redirect } from 'next/navigation'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import PlanClient from './PlanClient'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Choose your membership — IronForge',
  description: 'Forge Community or Forge Automate.',
}

/** PLAN-01 — membership selection. */
export default async function EnrollPlanPage() {
  const session = await getCustomerSession()
  if (!session.customerId) redirect('/login?next=/enroll')
  return <PlanClient />
}
