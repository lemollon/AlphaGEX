'use client'

import { usePathname } from 'next/navigation'
import ClientNav from './ClientNav'
import ScrollToTop from './ScrollToTop'

/**
 * App chrome wrapper. Every route gets the global nav.
 *
 * The marketing landing at "/" now shares the global nav (so the home page is
 * consistent with the rest of the site), but still renders edge-to-edge below
 * it — it ships its own full-bleed chrome (sticky titleblock masthead + footer)
 * and must NOT be wrapped in the width-constrained <main>.
 */
export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const isLanding = pathname === '/'
  // Standalone full-bleed marketing/auth/onboarding screens: no app nav, own chrome.
  const isStandalone =
    pathname === '/signup' ||
    pathname === '/pricing' ||
    pathname === '/login' ||
    pathname === '/ops/login' ||
    pathname === '/forgot-password' ||
    pathname === '/reset-password' ||
    pathname.startsWith('/onboarding')

  return (
    <>
      <ScrollToTop />
      {!isStandalone && <ClientNav />}
      {isLanding || isStandalone ? children : <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>}
    </>
  )
}
