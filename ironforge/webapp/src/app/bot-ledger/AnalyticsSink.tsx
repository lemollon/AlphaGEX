'use client'

import { useEffect } from 'react'

import { setAnalyticsSink, type AnalyticsEvent } from '@/lib/analytics'

const ENDPOINT = '/api/public/bot-ledger/events'
const FLUSH_MS = 3_000
const MAX_BATCH = 20

/**
 * Installs the first-party analytics sink for this route.
 *
 * Renders nothing. Batches events and ships them with `sendBeacon`, which the
 * browser delivers even if the page is being unloaded — otherwise the most
 * interesting event on the page (a CTA click, which navigates away) would be
 * the one most likely to be lost.
 *
 * Failure is silent by design: analytics must never surface an error to a
 * visitor or block a navigation.
 */
export default function AnalyticsSink() {
  useEffect(() => {
    let buffer: AnalyticsEvent[] = []
    let timer: ReturnType<typeof setTimeout> | null = null

    function send() {
      if (timer) {
        clearTimeout(timer)
        timer = null
      }
      if (buffer.length === 0) return
      const events = buffer.slice(0, MAX_BATCH)
      buffer = buffer.slice(MAX_BATCH)
      const body = JSON.stringify({ events })
      try {
        // Beacon survives unload; fetch+keepalive is the fallback for browsers
        // where sendBeacon is unavailable or refuses the payload.
        const blob = new Blob([body], { type: 'application/json' })
        if (!navigator.sendBeacon?.(ENDPOINT, blob)) {
          void fetch(ENDPOINT, {
            method: 'POST',
            body,
            headers: { 'content-type': 'application/json' },
            keepalive: true,
          }).catch(() => {})
        }
      } catch {
        // Never let telemetry break the page.
      }
      if (buffer.length > 0) schedule()
    }

    function schedule() {
      if (timer) return
      timer = setTimeout(send, FLUSH_MS)
    }

    setAnalyticsSink((event) => {
      buffer.push(event)
      if (buffer.length >= MAX_BATCH) send()
      else schedule()
    })

    // A CTA click navigates away; flush before the page goes.
    const onHide = () => {
      if (document.visibilityState === 'hidden') send()
    }
    document.addEventListener('visibilitychange', onHide)
    window.addEventListener('pagehide', send)

    return () => {
      document.removeEventListener('visibilitychange', onHide)
      window.removeEventListener('pagehide', send)
      send()
    }
  }, [])

  return null
}
