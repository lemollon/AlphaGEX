import type { Metadata } from 'next'
import { Inter, Oswald, Barlow_Condensed } from 'next/font/google'
import { GeistSans } from 'geist/font/sans'
import { GeistMono } from 'geist/font/mono'
import './globals.css'
import Shell from '@/components/Shell'
import EnrollmentGate from '@/components/EnrollmentGate'
import SandboxBanner from '@/components/SandboxBanner'
import TrackPageView from '@/components/TrackPageView'
import { isEnrollmentClosed } from '@/lib/enrollment-mode'
import { isSandbox } from '@/lib/sandbox'

// Single source of truth for site typography. All four are loaded at the
// root so every surface — legacy app shell, marketing, enrollment and the
// customer dashboard — can resolve the design-system tokens in
// styles/forge-tokens.css (--sans/--mono/--brand), not just the marketing
// pages that previously loaded Geist/Geist Mono themselves (ds-type #7-#9:
// "Geist ... everything by default", "numbers in tables, times: Geist Mono",
// "wordmark and agent names on cards: Barlow Condensed 700").
// Inter/Oswald stay for the legacy app shell (--font-sans/--font-display,
// Tailwind font-sans/font-display) which this pass doesn't restyle.
const inter = Inter({ subsets: ['latin'], display: 'swap', variable: '--font-sans' })
const oswald = Oswald({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  display: 'swap',
  variable: '--font-display',
})
const barlowCondensed = Barlow_Condensed({
  subsets: ['latin'],
  weight: ['700'],
  display: 'swap',
  variable: '--font-barlow-condensed',
})

export const metadata: Metadata = {
  title: 'IronForge',
  description:
    'Autonomous, defined-risk options bots for SPY that run in your own Tradier account — every position has a capped max loss, sized and exited by rule. Join the IronForge early-access waitlist.',
  icons: { icon: '/ironforge-mark.png', apple: '/apple-touch-icon.png' },
  openGraph: {
    title: 'IronForge',
    description:
      'Autonomous, defined-risk options bots for SPY that run in your own Tradier account.',
    // Reuses the existing wordmark asset — no dedicated OG card has been
    // exported yet (ds-assets #27, oi-assets #310: mascot/logo exports are
    // an open item). Replace with a proper 1200x630 OG card once designed.
    images: ['/ironforge-mark.png'],
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${oswald.variable} ${barlowCondensed.variable} ${GeistSans.variable} ${GeistMono.variable}`}
    >
      <body className="font-sans antialiased min-h-screen">
        <Shell>{children}</Shell>
        {/* Blocking waitlist overlay — self-limits to /signup + /enroll/* and is
            inert unless ENROLLMENT_WAITLIST_MODE is on. Read server-side here so
            the flag never reaches the client bundle. */}
        <EnrollmentGate enabled={isEnrollmentClosed()} />
        {/* Sandbox ribbon. Inert unless IRONFORGE_ENV=sandbox. Read server-side
            for the same reason as the gate above — the flag stays off the client
            bundle, and the banner cannot be disabled from the browser. */}
        <SandboxBanner enabled={isSandbox()} />
        {/* First-party page-view beacon. No IP/UA/cookies persisted — see
            /api/track. Skips /ops/* on its own. */}
        <TrackPageView />
      </body>
    </html>
  )
}
