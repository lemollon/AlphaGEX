'use client'

import { usePathname } from 'next/navigation'
import ClientNav from './ClientNav'
import ScrollToTop from './ScrollToTop'
import AdminBadge from './AdminBadge'
import { clientSurface } from '@/lib/surface'

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
    pathname === '/bot-ledger' ||
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

  // 'both' (mirror unset) keeps today's behaviour for local dev; only the
  // customer deployment actively suppresses it.
  const showAdminBadge = clientSurface() !== 'customer'

  return (
    <>
      <ScrollToTop />
      {!isStandalone && <ClientNav />}
      {isStandalone ? children : <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>}
      {/*
        The floating admin pill belongs to the OPS CONSOLE, not the customer
        site. On the customer deployment its "Ops" button pointed at /spark,
        which 404s there by design (see lib/surface.ts) — a dead button sitting
        on top of every customer page. ironforge.trade is now gated by login
        alone, with no operator chrome layered over it.

        It still renders on the operator surface, where the links resolve and
        the impersonation controls are actually usable.
      */}
      {showAdminBadge && <AdminBadge />}
    </>
  )
}
