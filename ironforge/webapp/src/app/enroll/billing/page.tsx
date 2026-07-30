import type { Metadata } from 'next'
import { Suspense } from 'react'
import { redirect } from 'next/navigation'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import BillingClient from './BillingClient'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Set up billing — IronForge',
  description: 'Payment is securely processed by Stripe.',
}

/** BILL-COMM-01 / BILL-AUTO-01 — order summary + Stripe Checkout hand-off. */
export default async function EnrollBillingPage() {
  const session = await getCustomerSession()
  if (!session.customerId) redirect('/login?next=/enroll')
  return (
    // Suspense: BillingClient reads useSearchParams (?checkout=...), which requires a
    // boundary in the app router even on a force-dynamic page.
    <Suspense fallback={null}>
      <BillingClient />
    </Suspense>
  )
}
