import type { Metadata } from 'next'
import { Suspense } from 'react'
import DashboardClient from './DashboardClient'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Dashboard — IronForge',
  description: 'Your agents, performance, community, and account settings in one place.',
}

export default function DashboardPage() {
  return (
    <Suspense fallback={null}>
      <DashboardClient />
    </Suspense>
  )
}
