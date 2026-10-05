import type { Metadata } from 'next'
import MarketingShell from '@/components/marketing/MarketingShell'
import WaitlistClient from './WaitlistClient'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Join the Waitlist — IronForge',
  description: 'Join the IronForge waitlist for early access to automated, disciplined options trading.',
}

/**
 * 10.4 restyle (gap audit "Waitlist as in-page modal" PARTIAL/L, "Footer on /waitlist"
 * MISSING/M) — was a standalone dark/amber Tailwind page with no nav, no footer and no
 * 10.4 tokens (see the retired `_home/HomeNav` + `_home/HomeFooter` it used to render).
 * Now wrapped in the same `MarketingShell` every other 10.4 page uses, so nav/footer/
 * fonts/tokens match exactly. Fields and the API contract are unchanged — see
 * WaitlistClient and lib/waitlist.ts.
 */
export default function WaitlistPage() {
  return (
    <MarketingShell>
      <WaitlistClient />
    </MarketingShell>
  )
}
