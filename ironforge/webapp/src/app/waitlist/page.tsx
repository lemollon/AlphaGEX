import type { Metadata } from 'next'
import HomeNav from '@/app/_home/HomeNav'
import { isPublicMode } from '@/lib/auth/access'
import HomeFooter from '@/app/_home/HomeFooter'
import WaitlistClient from './WaitlistClient'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Join the Waitlist — IronForge',
  description: 'Be first. Join the IronForge waitlist for early access to automated, disciplined trading.',
}

export default function WaitlistPage() {
  return (
    <div className="min-h-screen bg-forge-bg">
      <HomeNav showAll={isPublicMode()} />
      <WaitlistClient />
      <HomeFooter />
    </div>
  )
}
