import type { Metadata } from 'next'
import SettingsClient from './SettingsClient'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Settings — IronForge',
  description: 'Membership, brokerage connections, and security.',
}

export default function SettingsPage() {
  return <SettingsClient />
}
