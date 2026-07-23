'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'

interface BrokerOption {
  slug: string
  name: string
}

// Tradier is a first-class option but connects through its OWN OAuth, not SnapTrade — modeled as a
// sentinel value the submit handler special-cases. Everything else routes through SnapTrade.
const TRADIER = '__tradier__'
// Lets the user open SnapTrade's full brokerage list when their broker isn't in the dropdown.
const OTHER = '__other__'

export default function BrokerageConnectClient() {
  const router = useRouter()
  const [brokers, setBrokers] = useState<BrokerOption[]>([])
  const [selected, setSelected] = useState<string>(TRADIER)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Populate the dropdown from the brokerages our SnapTrade client id can connect.
  useEffect(() => {
    let cancelled = false
    fetch('/api/onboarding/brokerage/brokerages')
      .then((r) => r.json())
      .then((d) => {
        if (!cancelled && Array.isArray(d?.brokers)) setBrokers(d.brokers)
      })
      .catch(() => {
        /* dropdown still works with just Tradier + Other */
      })
    return () => {
      cancelled = true
    }
  }, [])

  const selectedLabel = useMemo(() => {
    if (selected === TRADIER) return 'Tradier'
    if (selected === OTHER) return 'your broker'
    return brokers.find((b) => b.slug === selected)?.name ?? 'your broker'
  }, [selected, brokers])

  // Both providers return { redirectURI } and we hand off to the broker's hosted flow. Tradier has
  // its own OAuth; every other selection goes through the SnapTrade connection portal, deep-linked
  // to the chosen broker (or the full list for "Other").
  async function connect() {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const isTradier = selected === TRADIER
      const path = isTradier
        ? '/api/onboarding/brokerage/tradier/connect'
        : '/api/onboarding/brokerage/connect'
      const init: RequestInit = { method: 'POST' }
      if (!isTradier && selected !== OTHER) {
        init.headers = { 'Content-Type': 'application/json' }
        init.body = JSON.stringify({ broker: selected })
      }

      const res = await fetch(path, init)
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.redirectURI) {
        window.location.href = data.redirectURI
        return
      }
      if (res.status === 503) {
        setError('That connection isn’t available right now. You can pick another broker or skip.')
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
    <div className="mt-8 space-y-4">
      {error && (
        <p className="rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-xs text-red-300">{error}</p>
      )}

      <div>
        <label
          htmlFor="broker"
          className="mb-2 block text-xs font-semibold uppercase tracking-wide text-gray-400"
        >
          Choose your broker
        </label>
        <div className="relative">
          <select
            id="broker"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            disabled={busy}
            className="w-full appearance-none rounded-lg border border-[#FD5301]/60 bg-forge-bg/60 px-4 py-3 pr-10 text-sm font-medium text-white outline-none transition focus:border-[#FD5301] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <option value={TRADIER}>Tradier (Recommended)</option>
            {brokers.length > 0 && (
              <optgroup label="Connect via SnapTrade">
                {brokers.map((b) => (
                  <option key={b.slug} value={b.slug}>
                    {b.name}
                  </option>
                ))}
              </optgroup>
            )}
            <option value={OTHER}>Other broker…</option>
          </select>
          <svg
            aria-hidden="true"
            className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#FD5301]"
            viewBox="0 0 20 20"
            fill="none"
          >
            <path d="M6 8l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        {selected === OTHER && (
          <p className="mt-2 text-xs text-gray-500">
            We’ll open SnapTrade’s full list so you can pick your brokerage.
          </p>
        )}
      </div>

      <button
        onClick={connect}
        disabled={busy}
        className="flex w-full items-center justify-center rounded-lg bg-[#FD5301] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#e04a00] disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? 'Starting…' : `Connect ${selectedLabel}`}
      </button>

      <button onClick={skip} className="w-full text-center text-xs text-gray-500 hover:text-gray-300">
        Skip for now
      </button>
    </div>
  )
}
