'use client'

import { useEffect, useState } from 'react'
import useSWR from 'swr'
import Link from 'next/link'
import { fetcher } from '@/lib/fetcher'
import { Wordmark } from '@/components/Brand'

interface OutstandingDoc {
  code: string
  title: string
  version: string
  contentUri: string
  accepted: boolean
}

interface OutstandingResponse {
  ok: boolean
  documents: OutstandingDoc[]
  outstanding: string[]
}

/**
 * Blocking re-acceptance screen for an ALREADY-SIGNED-IN customer whose
 * accepted document version is behind the current one in
 * lib/enrollment/legal.ts — the same re-acceptance mechanism enrollment
 * already has (staleDocumentCodes), applied for the first time to someone
 * who is already active rather than someone still being activated.
 *
 * Mounted once in CustomerShell, which every signed-in page renders through,
 * so there is no page-by-page wiring: outstanding === [] renders nothing and
 * the dashboard underneath is untouched; outstanding.length > 0 replaces the
 * ENTIRE shell with this screen until the member opens, checks and signs
 * every changed document — the same "nothing is implicitly consent" rule
 * enrollment's Agreements step already enforces.
 */
export default function LegalReacceptGate({ children }: { children: React.ReactNode }) {
  const { data, mutate } = useSWR<OutstandingResponse>('/api/v1/legal/outstanding', fetcher)
  const outstandingCodes = data?.outstanding ?? []
  const changed = (data?.documents ?? []).filter((d) => outstandingCodes.includes(d.code))

  const [opened, setOpened] = useState<Record<string, boolean>>({})
  const [signature, setSignature] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // A fresh set of outstanding docs resets the local review/signature state —
  // guards against a stale "all opened" carrying over if the set changes mid-session.
  useEffect(() => {
    setOpened({})
    setSignature('')
    setError(null)
  }, [outstandingCodes.join(',')])

  if (changed.length === 0) return <>{children}</>

  const allOpened = changed.every((d) => opened[d.code])
  const canSubmit = allOpened && signature.trim().length >= 2 && /\s/.test(signature.trim()) && !busy

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/v1/legal/reaccept', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ codes: changed.map((d) => d.code), signature_name: signature.trim() }),
      })
      const json = await res.json().catch(() => ({}))
      if (!res.ok || !json.ok) {
        setError(json.error || 'Could not record your acceptance. Please try again.')
        return
      }
      await mutate()
    } catch {
      setError('Network error — please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="if-dash flex min-h-screen items-center justify-center bg-[var(--bg)] px-4 py-10">
      <div className="w-full max-w-lg rounded-xl border border-[var(--line)] bg-[var(--bg)] p-6">
        <div className="mb-5"><Wordmark markClass="h-7 w-auto" textClass="text-base" /></div>
        <h1 className="text-xl font-semibold text-[var(--fg)]">We&rsquo;ve updated our agreements</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Review and re-accept the documents below to keep using your dashboard. Nothing else about your
          account or trading changes.
        </p>

        <div className="mt-5 space-y-2">
          {changed.map((d) => (
            <div key={d.code} className="flex items-center justify-between rounded-lg border border-[var(--line)] px-3 py-2.5">
              <div>
                <div className="text-sm font-medium text-[var(--fg)]">{d.title}</div>
                <div className="text-xs text-[var(--muted)]">Version {d.version}</div>
              </div>
              <Link
                href={d.contentUri}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => setOpened((o) => ({ ...o, [d.code]: true }))}
                className="whitespace-nowrap text-xs font-semibold text-[var(--accent)] hover:opacity-80"
              >
                {opened[d.code] ? 'Reviewed ✓' : 'Review →'}
              </Link>
            </div>
          ))}
        </div>

        {error ? <p className="mt-4 text-sm text-[var(--bad)]">{error}</p> : null}

        <label htmlFor="reaccept-signature" className="mt-5 block text-sm font-medium text-[var(--fg)]">
          Type your full legal name to sign
        </label>
        <input
          id="reaccept-signature"
          value={signature}
          onChange={(e) => setSignature(e.target.value)}
          disabled={!allOpened}
          placeholder="First and last name"
          className="mt-1.5 w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm text-[var(--fg)] disabled:opacity-50"
        />
        <p className="mt-1 text-xs text-[var(--muted)]">
          {allOpened ? 'Must match the name on your account.' : 'Open every document above first.'}
        </p>

        <button
          type="button"
          onClick={submit}
          disabled={!canSubmit}
          className="btn btn-accent btn-block btn-lg mt-5 disabled:opacity-50"
        >
          {busy ? 'Saving…' : 'Accept and continue'}
        </button>
      </div>
    </div>
  )
}
