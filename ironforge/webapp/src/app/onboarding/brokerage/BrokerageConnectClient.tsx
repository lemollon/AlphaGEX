'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

export default function BrokerageConnectClient() {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Both providers return { redirectURI } and we hand off to the broker's hosted flow.
  // SnapTrade covers Tastytrade/Webull/E*Trade/etc.; Tradier has its own OAuth.
  async function start(path: string) {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(path, { method: 'POST' })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.redirectURI) {
        window.location.href = data.redirectURI
        return
      }
      if (res.status === 503) {
        setError('That connection isn’t available right now. You can try the other option or skip.')
      } else {
        setError(data.error || 'Could not start the connection. Please try again.')
      }
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  function skip() {
    // Advisory step — skipping advances without setting brokerage_connected.
    router.push('/onboarding/complete')
  }

  return (
    <div className="mt-8 space-y-3">
      {error && (
        <p className="rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-xs text-red-300">{error}</p>
      )}
      <button
        onClick={() => start('/api/onboarding/brokerage/connect')}
        disabled={busy}
        className="flex w-full items-center justify-center rounded-md bg-amber-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-amber-500 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? 'Starting…' : 'Connect a brokerage (Tastytrade, Webull, E*Trade…)'}
      </button>
      <button
        onClick={() => start('/api/onboarding/brokerage/tradier/connect')}
        disabled={busy}
        className="flex w-full items-center justify-center rounded-md border border-amber-600/60 px-4 py-3 text-sm font-semibold text-amber-400 transition hover:bg-amber-600/10 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? 'Starting…' : 'Connect Tradier'}
      </button>
      <button
        onClick={skip}
        className="w-full text-center text-xs text-gray-500 hover:text-gray-300"
      >
        Skip for now
      </button>
    </div>
  )
}
