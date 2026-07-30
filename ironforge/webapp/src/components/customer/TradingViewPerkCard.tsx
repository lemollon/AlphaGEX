'use client'

import { useEffect, useState } from 'react'

/**
 * TradingView indicator perk (7/30, Leron's two-doors directive applied to
 * TradingView): members get IronForge's invite-only TradingView indicators.
 *
 * Door 1 — already use TradingView: enter the username, access is granted to it.
 * Door 2 — don't have TradingView: create a free account (their site, new tab),
 *          then come back and enter the username.
 *
 * Grants are completed operator-side (TradingView invite-only access lists are
 * managed in their UI), so submitted usernames show "being granted" until the ops
 * queue marks them done. Changing the username restarts the process — access
 * follows the handle.
 */
export default function TradingViewPerkCard() {
  const [username, setUsername] = useState('')
  const [saved, setSaved] = useState<string | null>(null)
  const [granted, setGranted] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    fetch('/api/account/tradingview')
      .then((r) => r.json())
      .then((d) => {
        if (!alive) return
        setSaved(d?.username ?? null)
        setGranted(Boolean(d?.granted))
        setLoaded(true)
      })
      .catch(() => {
        if (alive) setLoaded(true)
      })
    return () => {
      alive = false
    }
  }, [])

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/account/tradingview', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ username }),
      })
      const d = await res.json().catch(() => null)
      if (!res.ok) {
        setError(d?.error || 'Could not save your username. Please try again.')
        return
      }
      setSaved(d.username)
      setGranted(false)
      setEditing(false)
      setUsername('')
    } catch {
      setError('Could not save your username. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-5">
      <h3 className="text-sm font-bold text-white">TradingView indicators</h3>
      <p className="mt-1 text-sm leading-relaxed text-gray-400">
        Membership includes IronForge&rsquo;s invite-only TradingView indicators — gamma levels drawn
        on your own charts.
      </p>

      {!loaded ? (
        <div className="mt-4 h-10 animate-pulse rounded-lg bg-forge-border/50" />
      ) : saved && !editing ? (
        <div className="mt-4">
          {granted ? (
            <p className="flex items-center gap-2 text-sm text-gray-200">
              <span aria-hidden className="font-bold text-emerald-400">✓</span>
              Access granted to <span className="font-mono text-gray-100">{saved}</span> — find them under
              Indicators&nbsp;→&nbsp;Invite-only scripts on TradingView.
            </p>
          ) : (
            <p className="text-sm text-gray-200">
              Access for <span className="font-mono text-gray-100">{saved}</span> is being granted — usually
              within a day. You&rsquo;ll see the scripts under Indicators&nbsp;→&nbsp;Invite-only scripts.
            </p>
          )}
          <button
            type="button"
            onClick={() => {
              setEditing(true)
              setUsername(saved)
            }}
            className="mt-2 text-xs font-semibold text-gray-400 underline-offset-2 hover:text-white hover:underline"
          >
            Change username
          </button>
        </div>
      ) : (
        <div className="mt-4">
          <label htmlFor="tv-username" className="block text-xs text-gray-400">
            Already use TradingView? Your username
          </label>
          <div className="mt-1 flex gap-2">
            <input
              id="tv-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. OptionistPrime"
              className="w-full rounded-md border border-white/15 bg-black/40 px-3 py-2 text-sm text-white outline-none focus:border-amber-500"
            />
            <button
              type="button"
              disabled={busy || username.trim().length < 2}
              onClick={submit}
              className="shrink-0 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-black transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? 'Saving…' : 'Save'}
            </button>
          </div>
          {error ? <p className="mt-2 text-xs text-red-400">{error}</p> : null}
          <p className="mt-2 text-xs text-gray-500">
            Don&rsquo;t have TradingView?{' '}
            <a
              href="https://www.tradingview.com/"
              target="_blank"
              rel="noopener noreferrer"
              className="font-semibold text-amber-500 hover:text-amber-400"
            >
              Create a free account ↗
            </a>{' '}
            (free tier works), then enter your username here.
          </p>
        </div>
      )}
    </section>
  )
}
