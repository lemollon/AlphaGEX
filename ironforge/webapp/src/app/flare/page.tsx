'use client'

import BotDashboard from '@/components/BotDashboard'
import './flare-design.css'

/**
 * FLARE dashboard route.
 *
 * The page structure, layout, and BotDashboard component are unchanged — this
 * route is restyled to the IronForge design system from ~/Downloads/landing.html
 * via a colocated stylesheet scoped under `.flare-design`. Other bot routes use
 * the same BotDashboard but render without this wrapper, so they're unaffected.
 */
export default function FlarePage() {
  return (
    <>
      {/* Design-system fonts: IBM Plex Sans/Mono + Cormorant Garamond italic. */}
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      {/* eslint-disable-next-line @next/next/google-font-preconnect */}
      <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
      <link
        href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600;700&family=Cormorant+Garamond:ital,wght@1,400;1,500&display=swap"
        rel="stylesheet"
      />
      <div className="flare-design">
        <BotDashboard bot="flare" accent="fuchsia" />
      </div>
    </>
  )
}
