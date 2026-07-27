import type { Metadata } from 'next'

import HomeNav from '../_home/HomeNav'
import HomeFooter from '../_home/HomeFooter'
import { parseBotFilter, parsePeriod } from '@/lib/botLedger/params'
import LedgerHero from './LedgerHero'
import LedgerPerformance from './LedgerPerformance'
import PrinciplesSection from './PrinciplesSection'
import TradeLog from './TradeLog'
import LedgerDisclosure from './LedgerDisclosure'

export const dynamic = 'force-dynamic'

const DESCRIPTION =
  'Review Spark and Flame paper-trade win rates, buying-power returns, and recent simulated trades.'

export const metadata: Metadata = {
  title: 'IronForge Bot Ledger | Paper-Trade Results',
  description: DESCRIPTION,
  // Scoped to this route rather than the root layout, so no other page's
  // metadata resolution changes. Needed for the relative OG image URL below.
  metadataBase: new URL('https://ironforge.trade'),
  alternates: { canonical: '/bot-ledger' },
  openGraph: {
    title: 'IronForge Bot Ledger | Paper-Trade Results',
    description: DESCRIPTION,
    url: '/bot-ledger',
    siteName: 'IronForge',
    type: 'website',
    // Static and branded, carrying no P&L figures — the card must never imply
    // a performance number that the page itself may have since revised.
    images: [{ url: '/og-bot-ledger.png', width: 1200, height: 630, alt: 'IronForge Bot Ledger' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'IronForge Bot Ledger | Paper-Trade Results',
    description: DESCRIPTION,
    images: ['/og-bot-ledger.png'],
  },
}

/**
 * Public Bot Ledger.
 *
 * Own chrome, like every other marketing screen (Shell.tsx treats this route as
 * standalone so the OPERATOR nav never renders on a page built for prospects).
 *
 * The hero is rendered HERE, on the server, and passed into the client island
 * as a slot — so the H1 and both CTAs are in the initial HTML with no JS on the
 * critical path, and they stay visible even if the API is down.
 */
export default function BotLedgerPage({
  searchParams,
}: {
  searchParams: Record<string, string | string[] | undefined>
}) {
  const initialPeriod = parsePeriod(searchParams.period)
  const initialBot = parseBotFilter(searchParams.bot)
  // Year is resolved on the server so the log's date labels do not depend on
  // the visitor's clock.
  const year = new Date().getUTCFullYear()

  return (
    <div className="min-h-screen bg-forge-bg">
      <HomeNav />
      <main className="mx-auto max-w-[1280px] px-5 py-12 md:px-8 md:py-16">
        <LedgerPerformance
          initialPeriod={initialPeriod}
          initialBot={initialBot}
          hero={<LedgerHero />}
        />
        <PrinciplesSection />
        <TradeLog initialBot={initialBot} year={year} />
        <LedgerDisclosure />
      </main>
      <HomeFooter />
    </div>
  )
}
