'use client'

import { useEffect } from 'react'
import { usePathname } from 'next/navigation'

/**
 * First-party page-view beacon. Fires a fire-and-forget POST to /api/track on
 * every client-side route change, using sendBeacon (survives the tab closing
 * mid-navigation) with a fetch keepalive fallback for browsers without it.
 *
 * Skips /ops/* — that's the operator console, not a visitor page, and mixing
 * operator traffic into the dashboard would make the numbers meaningless.
 *
 * Renders nothing. Mounted once in the root layout.
 */
export default function TrackPageView() {
  const pathname = usePathname()

  useEffect(() => {
    if (!pathname || pathname.startsWith('/ops')) return

    const payload = JSON.stringify({ path: pathname })

    if (typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
      try {
        const blob = new Blob([payload], { type: 'application/json' })
        if (navigator.sendBeacon('/api/track', blob)) return
      } catch {
        /* fall through to fetch */
      }
    }

    fetch('/api/track', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: payload,
      keepalive: true,
    }).catch(() => {})
  }, [pathname])

  return null
}
