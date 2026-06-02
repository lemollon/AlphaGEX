'use client'

import { useEffect } from 'react'
import { usePathname } from 'next/navigation'

/**
 * Resets the window scroll position to the top on every client-side route
 * change.
 *
 * Why this exists: the marketing landing at "/" is very tall, and the global
 * nav navigates with Next.js <Link> (soft navigation). When you scroll down the
 * landing and click a bot link (SPARK/FLAME/INFERNO/BLAZE/FLARE), the App
 * Router does not reliably reset the scroll offset, so you keep your old large
 * scrollY and land near the *bottom* of the freshly-rendered bot page. A hard
 * refresh loads a new document and starts at the top — which is why the bug
 * only showed up on soft navigation. Forcing scroll-to-top on pathname change
 * makes soft navigation behave like a fresh load.
 *
 * Keyed on `pathname` only (not the hash), so in-page anchor links on the
 * landing page (#bots, #flow, #mech) still scroll to their target untouched.
 */
export default function ScrollToTop() {
  const pathname = usePathname()

  useEffect(() => {
    // Don't fight an explicit in-page hash target (deep links / anchor nav).
    if (typeof window !== 'undefined' && window.location.hash) return
    window.scrollTo(0, 0)
  }, [pathname])

  return null
}
