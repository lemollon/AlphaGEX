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
    pathname === '/home' ||
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
