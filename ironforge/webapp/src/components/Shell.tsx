'use client'

import { usePathname } from 'next/navigation'
import ClientNav from './ClientNav'

/**
 * App chrome wrapper. Every route gets the global nav + width-constrained main,
 * EXCEPT the marketing landing at "/", which ships its own full-bleed chrome
 * (titleblock header + footer) and must render edge-to-edge with no app nav.
 */
export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()

  if (pathname === '/') {
    return <>{children}</>
  }

  return (
    <>
      <ClientNav />
      <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
    </>
  )
}
