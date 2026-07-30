import type { Metadata } from 'next'
import { redirect } from 'next/navigation'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import AgentClient from './AgentClient'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Choose your trading agent — IronForge',
  description: 'Spark or Flame — two rules-based iron condor strategies with different risk profiles.',
}

/** AGENT-01 — agent selection (creates a draft configuration; never activates). */
export default async function EnrollAgentPage() {
  const session = await getCustomerSession()
  if (!session.customerId) redirect('/login?next=/enroll')
  return <AgentClient />
}
