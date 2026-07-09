import type { Metadata } from 'next'
import HomeClient from './HomeClient'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Home — IronForge',
  description: 'Your IronForge dashboard: agent status, wealth snapshot, daily brief, and recent trades.',
}

export default function HomePage() {
  return <HomeClient />
}
