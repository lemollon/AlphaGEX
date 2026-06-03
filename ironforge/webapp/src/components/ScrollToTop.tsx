'use client'

import { usePathname } from 'next/navigation'
import { useEffect } from 'react'

/**
 * Resets scroll to the top on every route (pathname) change.
 *
 * Next.js 14's App Router is supposed to scroll to the top on client-side
 * navigation, but it has a race when leaving a very tall page (our marketing
 * landing at "/"): the scroll reset can fire before the new, shorter page has
 * laid out, leaving the destination dashboard scrolled near the bottom. A hard
 * refresh masks it (a fresh document load always starts at the top). Running
 * the reset in an effect — after the new route has mounted — corrects it
 * reliably for every soft navigation.
 *
 * Keyed on `pathname` only (not the hash), so the landing page's in-page anchor
 * buttons (#bots, #flow, #mech, #proof) still scroll normally.
 */
export default function ScrollToTop() {
  const pathname = usePathname()

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  return null
}
