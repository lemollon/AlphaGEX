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

  const openedCount = docs.filter((d) => opened[d.code]).length
  const allOpened = docs.length > 0 && openedCount === docs.length
  const canSubmit = allOpened && agreed && signature.trim().length >= 2 && !busy

  // Design spec §5 step 2: "'Accept all' link toggles every box. Progress line: 'X of
  // 6 accepted.'" (gap audit "Agreements gating" PARTIAL/S — previously neither
  // existed). "Accept all" here is a one-click alias for the single aggregate
  // checkbox below, not a bypass of reading each document — it only has anything to
  // do once every document has actually been opened.
  function acceptAll() {
    if (!allOpened) return
    setAgreed(true)
  }

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
      step="legal"
      enrollment={enrollment}
    >
      {error ? <p className="err" style={{ marginBottom: 14 }}>{error}</p> : null}

      {!enrollment || (docs.length === 0 && !error) ? <div className="card pad" style={{ height: 280 }} /> : null}

      {docs.length > 0 ? (
        <>
          <div className="nav-row" style={{ borderTop: 'none', paddingTop: 0, marginBottom: 10 }}>
            <span className="help">{openedCount} of {docs.length} reviewed</span>
            <button type="button" onClick={acceptAll} disabled={!allOpened || agreed} className="link">
              Accept all
            </button>
          </div>
          <div className="card">
            {docs.map((d) => (
              <div key={d.code} className="ack" style={{ gridTemplateColumns: '1fr auto' }}>
                <div>
                  <b>{d.title}</b>
                  <p>{DOC_SUBTITLES[d.code] ?? `Version ${d.version}`}</p>
                </div>
                <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  {opened[d.code] ? <span aria-hidden className="num" style={{ color: 'var(--up)', fontWeight: 700 }}>✓</span> : null}
                  <Link
                    href={d.contentUri}
                    target="_blank"
                    onClick={() => setOpened((o) => ({ ...o, [d.code]: true }))}
                    className="link"
                  >
                    Review
                  </Link>
                </span>
              </div>
            ))}
          </div>

          <label className="field" style={{ gridTemplateColumns: '22px 1fr', display: 'grid', marginTop: 20, alignItems: 'start' }}>
            <input
              type="checkbox"
              checked={agreed}
              disabled={!allOpened}
              onChange={(e) => setAgreed(e.target.checked)}
              style={{ width: 18, height: 18, marginTop: 2 }}
            />
            <span style={{ fontWeight: 400 }}>
              I have opened, reviewed, and agree to all required agreements.
              {!allOpened ? <span className="help" style={{ display: 'block', marginTop: 2 }}>Review each document above to enable this.</span> : null}
            </span>
          </label>

          <div className="field" style={{ marginTop: 20 }}>
            <label htmlFor="signature">Electronic signature</label>
            <input
              id="signature"
              type="text"
              value={signature}
              onChange={(e) => setSignature(e.target.value)}
              placeholder="Enter your full legal name"
              autoComplete="name"
            />
            <p className="help">Your signature and acceptance date will be recorded electronically.</p>
          </div>

          <div className="nav-row">
            <Link href="/enroll/plan" className="btn">← Back</Link>
            <button type="button" disabled={!canSubmit} onClick={accept} className="btn btn-accent btn-lg">
              {busy ? 'Saving…' : 'Accept & Continue'}
            </button>
          </div>
        </>
      ) : null}
    </EnrollShell>
  )
}
