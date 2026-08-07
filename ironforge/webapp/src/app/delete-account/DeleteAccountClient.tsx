'use client'

import { useEffect, useState } from 'react'

/**
 * The interactive part of the public /delete-account page.
 *
 * Everything above this on the page is readable signed-out by design; this block
 * degrades to a sign-in prompt rather than hiding, so a signed-out reader still
 * sees that a self-serve path exists and how to reach it.
 *
 * Deliberately plain fetch + useState rather than SWR: this is a handful of
 * one-shot mutations, and SWR's fetcher overloads have already cost us a real bug
 * in the mobile app.
 */

interface Status {
  pending: boolean
  requestedAt: string | null
  gracePeriodDays: number
}

const CONFIRM_WORD = 'DELETE'

export default function DeleteAccountClient() {
  const [loading, setLoading] = useState(true)
  const [signedIn, setSignedIn] = useState(false)
  const [status, setStatus] = useState<Status | null>(null)
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  async function refresh() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/account/deletion-request', { cache: 'no-store' })
      if (res.status === 401) {
        setSignedIn(false)
        setStatus(null)
        return
      }
      setSignedIn(true)
      const json = await res.json()
      if (json.ok) setStatus({ pending: json.pending, requestedAt: json.requestedAt, gracePeriodDays: json.gracePeriodDays })
    } catch {
      setError('Could not check your account status. Please reload the page.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/account/deletion-request', { method: 'POST' })
      const json = await res.json().catch(() => ({}))
      if (res.ok && json.ok) {
        setDone(true)
        await refresh()
        return
      }
      // The open-positions refusal carries a message written for the customer —
      // show it verbatim rather than flattening it to "something went wrong".
      setError(json.message || json.error || 'Could not submit the request. Please try again.')
    } catch {
      setError('Could not submit the request. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  async function cancelRequest() {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/account/deletion-request', { method: 'DELETE' })
      const json = await res.json().catch(() => ({}))
      if (res.ok && json.ok) {
        setDone(false)
        setConfirm('')
        await refresh()
        return
      }
      setError(json.error || 'Could not cancel the request.')
    } catch {
      setError('Could not cancel the request.')
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <p className="text-gray-400">Checking your account…</p>

  if (!signedIn) {
    return (
      <div className="rounded-lg border border-white/10 bg-black/30 p-5">
        <p className="text-gray-300">
          Sign in to request deletion of your account.
        </p>
        <a
          href="/login?next=%2Fdelete-account"
          className="mt-4 inline-block rounded bg-amber-500 px-4 py-2 font-semibold text-black hover:bg-amber-400"
        >
          Sign in
        </a>
        <p className="mt-4 text-sm text-gray-500">
          Can&rsquo;t sign in? Email support@ironforge.trade from the address on your account.
        </p>
      </div>
    )
  }

  if (status?.pending) {
    return (
      <div className="rounded-lg border border-amber-900/40 bg-amber-950/20 p-5">
        <p className="font-semibold text-amber-400">Deletion requested</p>
        <p className="mt-2 text-gray-300">
          We received your request
          {status.requestedAt ? ` on ${new Date(status.requestedAt).toLocaleDateString()}` : ''}. Your
          subscription has been cancelled and your brokerage connection removed.
        </p>
        <p className="mt-2 text-gray-300">
          You have {status.gracePeriodDays} days to call this off. Cancelling will not restore your
          subscription or brokerage connection.
        </p>
        {error ? <p className="mt-3 text-red-400">{error}</p> : null}
        <button
          onClick={cancelRequest}
          disabled={busy}
          className="mt-4 rounded border border-white/20 px-4 py-2 font-semibold text-gray-200 hover:bg-white/5 disabled:opacity-50"
        >
          {busy ? 'Working…' : 'Cancel my deletion request'}
        </button>
      </div>
    )
  }

  if (done) {
    return (
      <div className="rounded-lg border border-amber-900/40 bg-amber-950/20 p-5">
        <p className="font-semibold text-amber-400">Request received.</p>
        <p className="mt-2 text-gray-300">Reload this page to see the status of your request.</p>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-red-900/40 bg-red-950/10 p-5">
      <p className="text-gray-300">
        To request deletion, type <strong className="text-gray-100">{CONFIRM_WORD}</strong> below and
        confirm. Your subscription will be cancelled and your brokerage disconnected immediately.
      </p>
      <input
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        aria-label={`Type ${CONFIRM_WORD} to confirm`}
        placeholder={CONFIRM_WORD}
        className="mt-4 w-48 rounded border border-white/20 bg-black/40 px-3 py-2 font-mono text-gray-100"
      />
      {error ? <p className="mt-3 text-red-400">{error}</p> : null}
      <div className="mt-4">
        <button
          onClick={submit}
          disabled={busy || confirm !== CONFIRM_WORD}
          className="rounded bg-red-600 px-4 py-2 font-semibold text-white hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? 'Working…' : 'Request account deletion'}
        </button>
      </div>
    </div>
  )
}
