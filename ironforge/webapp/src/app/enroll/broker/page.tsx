import type { Metadata } from 'next'
import { Suspense } from 'react'
import { redirect } from 'next/navigation'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import BrokerClient from './BrokerClient'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Connect your brokerage — IronForge',
  description: 'Authorize IronForge through your broker. Your credentials never touch IronForge.',
}

/** BROKER-01 — brokerage connection + account eligibility. */
export default async function EnrollBrokerPage() {
  const session = await getCustomerSession()
  if (!session.customerId) redirect('/login?next=/enroll')
  return (
    // Suspense: BrokerClient reads useSearchParams (?connected/?error/?incomplete).
    <Suspense fallback={null}>
      <BrokerClient />
    </Suspense>
  )
}
