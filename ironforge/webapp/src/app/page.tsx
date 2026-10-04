import type { Metadata } from 'next'
import MarketingShell from '@/components/marketing/MarketingShell'
import HomePageBody from '@/components/marketing/HomePageBody'

/**
 * IronForge public homepage — 10.4 marketing redesign.
 *
 * Replaces the older `_home/marketing.tsx`-driven page (still used by
 * /waitlist, which is out of this redesign's scope). Nothing about layout
 * or copy lives in this file — see `HomePageBody` and `lib/marketing/agents.ts`.
 */

export const metadata: Metadata = {
  title: 'IronForge — Automated options trading, run by rules.',
  description:
    'Pick an agent. It trades in your own brokerage account by the same written rules every day, and you follow along from the app.',
}

export default function HomePage() {
  return (
    <MarketingShell>
      <HomePageBody />
    </MarketingShell>
  )
}
