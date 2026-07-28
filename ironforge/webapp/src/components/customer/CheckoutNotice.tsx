'use client'

import { useEffect, useState } from 'react'

/**
 * Post-checkout acknowledgment (`?welcome=…` / `?canceled=…`).
 *
 * Stripe has always been sent back to a URL carrying these params, and NOTHING read
 * them — `welcome`, `canceled` and `session_id` were all decorative. So paying produced
 * no confirmation and abandoning produced no acknowledgment; in both cases you landed on
 * a page that looked exactly like it did before you clicked, and had to infer what
 * happened from whether the dashboard had changed yet.
 *
 * That inference is worst precisely when it matters: the subscription row is written by
 * the Stripe WEBHOOK, so for the second or two before it lands, a customer who just paid
 * sees a page that says they own nothing.
 *
 * Deliberately NOT `useSearchParams`: that forces a Suspense boundary and a CSR bailout
 * on every page that mounts this. Reading `window.location.search` after mount is the
 * idiom already used elsewhere in the app for exactly this reason.
 *
 * The param is stripped via replaceState once shown, so a refresh or a shared link does
 * not replay "Welcome" at someone who did not just buy anything.
 */

type Kind = 'welcome' | 'canceled'

export default function CheckoutNotice({ labels }: { labels?: Record<string, string> }) {
  const [notice, setNotice] = useState<{ kind: Kind; what: string } | null>(null)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const welcome = params.get('welcome')
    const canceled = params.get('canceled')
    if (!welcome && !canceled) return

    setNotice(welcome ? { kind: 'welcome', what: welcome } : { kind: 'canceled', what: canceled as string })

    // Strip the checkout params, keep everything else (utm_*, etc.). replaceState adds
    // no history entry, so Back still leaves the page rather than replaying the banner.
    params.delete('welcome')
    params.delete('canceled')
    params.delete('session_id')
    const qs = params.toString()
    window.history.replaceState(null, '', `${window.location.pathname}${qs ? `?${qs}` : ''}`)
  }, [])

  if (!notice) return null

  const name = labels?.[notice.what] ?? notice.what
  const isWelcome = notice.kind === 'welcome'

  return (
    <div
      role="status"
      className={`mb-4 flex items-start gap-3 rounded-xl border px-4 py-3 ${
        isWelcome
          ? 'border-emerald-700/40 bg-emerald-950/30'
          : 'border-forge-border bg-forge-card/70'
      }`}
    >
      <span aria-hidden className={`mt-0.5 text-lg ${isWelcome ? 'text-emerald-400' : 'text-gray-500'}`}>
        {isWelcome ? '✓' : '○'}
      </span>
      <div className="min-w-0">
        <p className={`text-sm font-semibold ${isWelcome ? 'text-emerald-300' : 'text-gray-300'}`}>
          {isWelcome ? `${name} is active` : 'Checkout canceled'}
        </p>
        <p className="mt-0.5 text-xs leading-relaxed text-gray-400">
          {isWelcome
            ? // Named explicitly because the webhook may not have landed yet, and a
              // customer reading "you own nothing" right after paying will assume the
              // payment failed.
              'Payment received. If this page has not caught up yet, give it a few seconds and refresh.'
            : 'No payment was taken and nothing changed. You can pick up where you left off whenever you like.'}
        </p>
      </div>
      <button
        type="button"
        onClick={() => setNotice(null)}
        aria-label="Dismiss"
        className="ml-auto shrink-0 rounded p-1 text-gray-500 transition hover:text-white"
      >
        ✕
      </button>
    </div>
  )
}
