import type { Metadata } from 'next'
import LiveClient from './LiveClient'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Live — IronForge',
  description: 'Real-time view of what Spark is doing with your account.',
}

export default function LivePage() {
  return <LiveClient />
}
