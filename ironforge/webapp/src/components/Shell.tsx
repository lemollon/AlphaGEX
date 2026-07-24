'use client'

import { usePathname } from 'next/navigation'
import ClientNav from './ClientNav'
import ScrollToTop from './ScrollToTop'
import AdminBadge from './AdminBadge'

/**
 * App chrome wrapper. Operator routes get the global nav; standalone
 * marketing/auth/onboarding screens ship their own chrome.
 */
export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  // Standalone full-bleed marketing/auth/onboarding screens: no app nav, own chrome.
  const isStandalone =
    pathname === '/' ||
    pathname === '/how-it-works' ||
    // Public proof page. Omitting it rendered the OPERATOR nav (SPARK/INFERNO/
    // BLAZE/Compare, "Signed in as Admin") on a page built for prospects — and
    // Nav.tsx has no surface filtering, so those links 404 on the customer
    // deployment. It carries its own chrome like every other marketing screen.
    pathname === '/track-record' ||
    pathname === '/signup' ||
    pathname === '/pricing' ||
    pathname === '/contact' ||
    pathname === '/privacy' ||
    pathname === '/terms' ||
    pathname === '/login' ||
    pathname === '/ops/login' ||
    pathname === '/forgot-password' ||
    pathname === '/reset-password' ||
    pathname === '/account/trades' ||
    pathname === '/live' ||
    // Per-bot "Open Account" pages carry the customer chrome, not the operator
    // nav — they are a subscribe surface, and Nav.tsx links 404 on this deployment.
    pathname.startsWith('/live/') ||
    pathname === '/home' ||
    // Signed-in password change is a customer screen; without this it rendered
    // the operator nav (SPARK/INFERNO/Compare) over a customer's account page.
    pathname === '/change-password' ||
    pathname === '/performance' ||
    pathname === '/community' ||
    pathname.startsWith('/onboarding')

  return (
    <>
      <ScrollToTop />
      {!isStandalone && <ClientNav />}
      {isStandalone ? children : <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>}
      {/* Operator-only floating admin pill (renders nothing for everyone else). */}
      <AdminBadge />
    </>
  )
}
