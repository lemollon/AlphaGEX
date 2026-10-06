'use client'

import { useEffect } from 'react'
import { track } from '@/lib/analytics/track'

/**
 * Fires `enroll_complete` once the Done screen actually renders — this page
 * is a server component (it must verify hasActiveMembership before it can
 * assert "Membership active"), so the event needs this tiny client leaf
 * rather than living in page.tsx itself.
 */
export default function EnrollCompleteBeacon({ agent }: { agent: 'spark' | 'flame' | 'ember' | null }) {
  useEffect(() => {
    track('enroll_complete', agent ? { agent } : undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return null
}
