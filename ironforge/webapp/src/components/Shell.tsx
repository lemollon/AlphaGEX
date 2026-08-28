'use client'

import { usePathname } from 'next/navigation'
import ClientNav from './ClientNav'
import ScrollToTop from './ScrollToTop'
import AdminBadge from './AdminBadge'
import { clientSurface, isCustomerPage } from '@/lib/surface'

/**
 * App chrome wrapper. Operator routes get the global nav; customer and standalone
 * marketing/auth/onboarding screens ship their own chrome.
 */
export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()

  // DERIVED, not hand-listed. This used to be a second list of pathnames kept in sync
  // with surface.ts CUSTOMER_PAGES by memory, and it drifted three times — most recently
  // leaving /support and /account/billing rendering the operator bot-console nav
  // (SPARK/INFERNO/BLAZE/FLARE/Compare) on a signed-in customer's pages, where
  // every one of those links 404s. Adding a page to CUSTOMER_PAGES is now enough;
  // surface.test.ts fails if the two ever disagree again.
  //
  // /ops/login is the one deliberate extra: it is operator content (so not a customer
  // page) but it is a bare login screen that carries its own chrome.
  const isStandalone = isCustomerPage(pathname) || pathname === '/ops/login'

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
