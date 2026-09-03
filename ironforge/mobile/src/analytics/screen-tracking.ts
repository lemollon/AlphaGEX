/**
 * Automatic screen views (APP-048).
 *
 * One hook, mounted once in app/(tabs)/_layout.tsx, rather than a track() call pasted
 * into every screen — a screen that forgets to call it is invisible, and a hook that
 * forgets to fire is a bug everyone notices immediately.
 */
import { useEffect, useRef } from 'react'
import { usePathname } from 'expo-router'
import { track } from '@/analytics/track'

export function useScreenTracking(): void {
  const pathname = usePathname()
  const last = useRef<string | null>(null)

  useEffect(() => {
    if (last.current === pathname) return
    last.current = pathname
    track('screen_view', { path: pathname })
  }, [pathname])
}
