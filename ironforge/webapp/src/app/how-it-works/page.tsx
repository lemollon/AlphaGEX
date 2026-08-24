import type { Metadata } from 'next'
import HomeNav from '../_home/HomeNav'
import { isPublicMode } from '@/lib/auth/access'
import { MarketingSections, LegalFooter, MARKETING_BG } from '../_home/marketing'

/* IronForge How It Works page.
 *
 * The approved design this page introduced is now the homepage as well, so the
 * sections were lifted into `_home/marketing.tsx` and both routes render the
 * same module. This file is intentionally thin: everything a visitor sees is
 * defined there, once. The only difference between the two routes is the
 * `source` attribution on the signup links and the page metadata.
 */

export const metadata: Metadata = {
  title: 'How It Works — IronForge',
  description:
    'Built on Discipline. Driven by Data. Automated trading powered by real-time analysis and disciplined execution.',
}

export default function HowItWorksPage() {
  return (
    <div className={`min-h-screen ${MARKETING_BG}`}>
      <HomeNav active="how-it-works" showAll={isPublicMode()} />
      <main>
        <MarketingSections source="how_it_works" />
      </main>
      <LegalFooter />
    </div>
  )
}
