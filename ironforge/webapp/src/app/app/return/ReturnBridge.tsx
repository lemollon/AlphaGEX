'use client'

import { useEffect, useState } from 'react'
import { appSchemeUrl, type AppRoute } from '@/lib/mobile/deep-link'

/**
 * Hands off to the app, with an honest fallback when it can't.
 *
 * There is no reliable way to detect whether a custom-scheme launch succeeded — the
 * browser reports nothing either way. So rather than guess, this attempts the handoff
 * once and then shows a button. If the app opened, the customer never sees the button;
 * if it didn't, they get a working action instead of a page that appears to hang.
 */
export default function ReturnBridge({
  route,
  params,
}: {
  route: AppRoute
  params: Record<string, string>
}) {
  const [showFallback, setShowFallback] = useState(false)
  const target = appSchemeUrl(route, params)

  useEffect(() => {
    // `replace`, not `assign`: if the app does open, the customer must not land back
    // here when they hit Back in the browser they were bounced through.
    window.location.replace(target)
    const t = setTimeout(() => setShowFallback(true), 1200)
    return () => clearTimeout(t)
  }, [target])

  return (
    <main className="flex min-h-screen items-center justify-center bg-forge-bg px-6">
      <div className="w-full max-w-sm rounded-xl border border-forge-border bg-forge-card p-8 text-center">
        <p className="font-display text-2xl tracking-wide text-white">
          IRON<span className="text-[#FD5301]">FORGE</span>
        </p>

        {showFallback ? (
          <>
            <p className="mt-6 text-sm text-forge-muted">
              Tap below to return to the IronForge app.
            </p>
            <a
              href={target}
              className="mt-5 inline-block w-full rounded-lg bg-[#FD5301] px-5 py-3 text-sm font-semibold text-white"
            >
              Open IronForge
            </a>
            {/* Someone who opened this on a desktop browser has no app to return to,
                so give them the web equivalent rather than a dead end. */}
            <a
              href={route}
              className="mt-3 inline-block w-full rounded-lg border border-forge-border px-5 py-3 text-sm text-forge-muted"
            >
              Continue in your browser
            </a>
          </>
        ) : (
          <p className="mt-6 text-sm text-forge-muted">Returning to the app…</p>
        )}
      </div>
    </main>
  )
}
