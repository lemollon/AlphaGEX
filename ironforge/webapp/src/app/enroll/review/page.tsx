import type { Metadata } from 'next'
import { redirect } from 'next/navigation'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import ReviewClient from './ReviewClient'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Review and activate — IronForge',
  description: 'Confirm your configuration before enabling automated execution.',
}

/** ACT-SPARK-01 / ACT-FLAME-01 — the final authorization surface. */
export default async function EnrollReviewPage() {
  const session = await getCustomerSession()
  if (!session.customerId) redirect('/login?next=/enroll')
  return <ReviewClient />
}
