import type { Metadata } from 'next'
import BillingClient from './BillingClient'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Membership & Billing — IronForge',
  description: 'Manage your IronForge plan, payment method, and invoices.',
}

export default function BillingPage() {
  return <BillingClient />
}
