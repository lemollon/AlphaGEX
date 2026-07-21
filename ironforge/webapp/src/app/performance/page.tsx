import type { Metadata } from 'next'
import PerformanceClient from './PerformanceClient'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Performance — IronForge',
  description: 'Your all-time trading performance across every strategy you own.',
}

export default function PerformancePage() {
  return <PerformanceClient />
}
