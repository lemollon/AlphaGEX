import type { Metadata } from 'next'
import HomeNav from './_home/HomeNav'
import { isPublicMode } from '@/lib/auth/access'
import { MarketingSections, LegalFooter, MARKETING_BG } from './_home/marketing'

/* IronForge public homepage.
 *
 * Renders the approved marketing design, which is defined ONCE in
 * `_home/marketing.tsx` and shared with /how-it-works. Nothing about the layout
 * or the copy lives in this file — see that module before changing anything a
 * visitor can see.
 *
 * This replaced an older homepage (hero + two pricing cards + three feature
 * preview cards). The membership tiers it carried were not deleted: /pricing is
 * a real page again and owns them, because the customer billing screen and the
 * checkout 409 path both need somewhere to send a customer to see plans.
 */

/**
 * Client-side rendered performance figures.
 *
 * The hero's Performance Overview card is a client component that fetches
 * /api/public/track-record after hydration, so unlike the previous homepage this
 * page reads nothing from the database while rendering and can be served
 * statically. `force-dynamic` was required by the old server-rendered ledger
 * preview and is deliberately NOT carried over — leaving it would cost a
 * pointless per-request render on the busiest page on the site.
 */

export const metadata: Metadata = {
  title: 'IronForge — Built on Discipline. Driven by Data.',
  description:
    'Automated trading powered by real-time analysis and disciplined execution. Every trade follows predefined rules, with transparent monitoring and a community of serious traders.',
}

export default function HomePage() {
  return (
    <div className={`min-h-screen ${MARKETING_BG}`}>
      <HomeNav active="home" showAll={isPublicMode()} />
      <main>
        <MarketingSections source="home" />
      </main>
      <LegalFooter />
    </div>
  )
}
