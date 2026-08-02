import type { Metadata } from 'next'
import { Inter, Oswald } from 'next/font/google'
import './globals.css'
import Shell from '@/components/Shell'
import EnrollmentGate from '@/components/EnrollmentGate'
import SandboxBanner from '@/components/SandboxBanner'
import { isEnrollmentClosed } from '@/lib/enrollment-mode'
import { isSandbox } from '@/lib/sandbox'

// Single source of truth for site typography.
// Inter = body/UI sans (--font-sans, also Tailwind's font-sans).
// Oswald = condensed industrial display face for headings (--font-display / font-display).
const inter = Inter({ subsets: ['latin'], display: 'swap', variable: '--font-sans' })
const oswald = Oswald({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  display: 'swap',
  variable: '--font-display',
})

export const metadata: Metadata = {
  title: 'IronForge',
  description:
    'Autonomous, defined-risk options bots for SPY that run in your own Tradier account — every position has a capped max loss, sized and exited by rule. Join the IronForge early-access waitlist.',
  icons: { icon: '/ironforge-mark.png', apple: '/apple-touch-icon.png' },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${oswald.variable}`}>
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
      </body>
    </html>
  )
}
