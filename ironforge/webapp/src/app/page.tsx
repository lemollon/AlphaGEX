import type { Metadata } from 'next'
import HomeNav from './_home/HomeNav'
import HomeFooter from './_home/HomeFooter'
import { Hero, MembershipSection, EverythingSection, CTABanner } from './_home/sections'

/* IronForge public homepage — implements the approved design in
 * IronForge_Public_Homepage_Developer_Handoff_v1 (LOCKED FOR IMPLEMENTATION).
 * Copy, pricing, and section order are locked; no proprietary execution
 * details appear here. Primary conversion: Create Account. */

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
