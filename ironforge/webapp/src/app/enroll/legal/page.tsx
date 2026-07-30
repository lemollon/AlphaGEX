import type { Metadata } from 'next'
import { redirect } from 'next/navigation'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import LegalClient from './LegalClient'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Review and accept — IronForge',
  description: 'The agreements required for automated trading.',
}

/** LEGAL-AUTO-01 — Automate legal review with electronic signature. */
export default async function EnrollLegalPage() {
  const session = await getCustomerSession()
  if (!session.customerId) redirect('/login?next=/enroll')
  return <LegalClient />
}
