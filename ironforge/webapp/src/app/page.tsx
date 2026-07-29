import type { Metadata } from 'next'
import HomeNav from './_home/HomeNav'
import HomeFooter from './_home/HomeFooter'
import { Hero, MembershipSection, EverythingSection, CTABanner } from './_home/sections'

/* IronForge public homepage — implements the approved design in
 * IronForge_Public_Homepage_Developer_Handoff_v1 (LOCKED FOR IMPLEMENTATION).
 * Copy, pricing, and section order are locked; no proprietary execution
 * details appear here. Primary conversion: Create Account. */

/**
 * Rendered per request.
 *
 * The hero preview reads the live closed-trade ledger, so this page must NOT be a
 * build-time static render. The database is not reachable during the build, the preview
 * falls back to em-dashes, and Next would bake that empty render into the output — the
 * build above emitted a static `○ /` until this was set.
 *
 * `revalidate` was the first attempt and is the wrong tool for the same reason: it still
 * prerenders at build, so the first visitors after every deploy would be served the
 * dashes until a window expired.
 *
 * Cost is one ledger read per visit — the same query /bot-ledger already runs per
 * request, over ~160 closed trades. If homepage traffic ever makes that matter, cache
 * the loader rather than going back to prerendering the page.
 */
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'IronForge — Build Your Edge',
  description:
    'A disciplined trading ecosystem designed to help you stay informed, execute with confidence, and grow alongside a community of serious traders.',
}

export default function HomePage() {
  return (
    <div className="min-h-screen bg-[#050607]">
      <HomeNav active="home" />
      <main>
        <Hero />
        <MembershipSection />
        <EverythingSection />
        <CTABanner />
      </main>
      <HomeFooter />
    </div>
  )
}
