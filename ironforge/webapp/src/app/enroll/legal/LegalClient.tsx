'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import EnrollShell from '../EnrollShell'
import { useEnrollment } from '../useEnrollment'

/**
 * LEGAL-AUTO-01 — Automate legal review (July 29 handoff).
 *
 * Seven documents, each with a Review action that opens the versioned content page.
 * The aggregate acceptance checkbox enables only after EVERY required document has
 * been opened (already-accepted documents count as reviewed — a customer must not
 * re-review what the record shows they already agreed to). Acceptance requires an
 * explicit electronic signature: the member's typed full legal name. The server
 * enforces both again (§ "a pre-checked control is not consent").
 */

interface LegalDoc {
  code: string
  title: string
  version: string
  contentUri: string
  accepted: boolean
}

/** Row subtitles from the approved screen. Fallback: no subtitle. */
const DOC_SUBTITLES: Record<string, string> = {
  TERMS: 'Platform terms and member responsibilities',
  RISK: 'Risks associated with options and automated trading',
  PRIVACY: 'How IronForge collects and protects information',
  ADVICE_DISCLAIMER: 'IronForge does not provide individualized advice',
  ELECTRONIC_CONSENT: 'Consent to receive and sign records electronically',
  TRADING_AUTH: 'Authorization to submit orders through your brokerage',
  REFUND: 'Billing, cancellation and refund terms',
}

export default function LegalClient() {
  const { enrollment, busy, setBusy, error, setError, call, router } = useEnrollment('legal')
  const [docs, setDocs] = useState<LegalDoc[]>([])
  const [opened, setOpened] = useState<Record<string, boolean>>({})
  const [agreed, setAgreed] = useState(false)
  const [signature, setSignature] = useState('')

  useEffect(() => {
    if (!enrollment) return
    // Community never sees this screen — its clickwrap lives at billing.
    if (enrollment.selected_plan === 'community') {
      router.replace('/enroll/billing')
      return
    }
    ;(async () => {
      try {
        const d = await call(`/api/v1/enrollments/${enrollment.id}/legal`)
        const documents: LegalDoc[] = d.documents ?? []
        setDocs(documents)
        // Already-accepted documents count as reviewed.
        const seen: Record<string, boolean> = {}
        for (const doc of documents) if (doc.accepted) seen[doc.code] = true
        setOpened((o) => ({ ...seen, ...o }))
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Could not load the agreements.')
      }
    })()
  }, [enrollment, call, router, setError])

  const allOpened = docs.length > 0 && docs.every((d) => opened[d.code])
  const canSubmit = allOpened && agreed && signature.trim().length >= 2 && !busy

  async function accept() {
    if (!enrollment) return
    setBusy(true)
    setError(null)
    try {
      await call(`/api/v1/enrollments/${enrollment.id}/acceptances`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          accepted: docs.map((d) => d.code),
          signature_name: signature.trim(),
        }),
      })
      router.push('/enroll/billing')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not record your agreement.')
      setBusy(false)
    }
  }

  return (
    <EnrollShell
      headline="Know what you’re authorizing."
      subline="Review the required agreements before continuing with Forge Automate."
      maxWidthClass="max-w-3xl"
    >
      <div className="rounded-2xl border border-forge-border bg-forge-card/60 p-6 lg:p-8">
        <h2 className="text-2xl font-bold text-white">Review and accept</h2>
        <p className="mt-1 text-sm text-gray-400">These agreements are required for automated trading.</p>

        {error ? (
          <p className="mt-4 rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-sm text-red-300">{error}</p>
        ) : null}

        {!enrollment || (docs.length === 0 && !error) ? (
          <div className="mt-6 h-72 animate-pulse rounded-2xl border border-forge-border bg-forge-card/40" />
        ) : null}

        {docs.length > 0 ? (
          <>
            <ul className="mt-5 divide-y divide-forge-border rounded-xl border border-forge-border bg-black/20">
              {docs.map((d) => (
                <li key={d.code} className="flex items-center gap-4 px-4 py-3.5">
                  <span aria-hidden className="text-lg text-gray-500">📄</span>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-white">{d.title}</div>
                    <p className="mt-0.5 truncate text-xs text-gray-500">{DOC_SUBTITLES[d.code] ?? `Version ${d.version}`}</p>
                  </div>
                  {opened[d.code] ? (
                    <span aria-hidden className="text-xs font-bold text-emerald-400">✓</span>
                  ) : null}
                  <Link
                    href={d.contentUri}
                    target="_blank"
                    onClick={() => setOpened((o) => ({ ...o, [d.code]: true }))}
                    className="shrink-0 text-sm font-semibold text-amber-500 hover:text-amber-400"
                  >
                    Review
                  </Link>
                </li>
              ))}
            </ul>

            <label className="mt-5 flex items-start gap-3 text-sm text-gray-200">
              <input
                type="checkbox"
                checked={agreed}
                disabled={!allOpened}
                onChange={(e) => setAgreed(e.target.checked)}
                className="mt-1 h-4 w-4 shrink-0 accent-amber-500 disabled:opacity-40"
              />
              <span>
                I have opened, reviewed, and agree to all required agreements.
                {!allOpened ? (
                  <span className="block text-xs text-gray-500">Review each document above to enable this.</span>
                ) : null}
              </span>
            </label>

            <div className="mt-5">
              <label htmlFor="signature" className="block text-xs text-gray-400">
                Electronic signature
              </label>
              <input
                id="signature"
                type="text"
                value={signature}
                onChange={(e) => setSignature(e.target.value)}
                placeholder="Enter your full legal name"
                autoComplete="name"
                className="mt-1 w-full rounded-md border border-white/15 bg-black/40 px-3 py-2.5 text-sm text-white outline-none focus:border-amber-500"
              />
              <p className="mt-1 text-xs text-gray-500">Your signature and acceptance date will be recorded electronically.</p>
            </div>

            <button
              type="button"
              disabled={!canSubmit}
              onClick={accept}
              className="mt-6 w-full rounded-lg bg-amber-500 px-5 py-3 text-sm font-semibold text-black transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? 'Saving…' : 'Accept & Continue'}
            </button>

            <Link href="/enroll/plan" className="mt-4 inline-block text-sm text-gray-400 hover:text-white">
              ← Back to membership selection
            </Link>
          </>
        ) : null}
      </div>
    </EnrollShell>
  )
}
