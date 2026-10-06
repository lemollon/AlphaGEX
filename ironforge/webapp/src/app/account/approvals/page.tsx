import type { Metadata } from 'next'
import ApprovalsPageClient from './ApprovalsPageClient'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Trade Approvals — IronForge',
  description: 'Review and approve pending trades before they are placed.',
}

export default function ApprovalsPage() {
  return <ApprovalsPageClient />
}
