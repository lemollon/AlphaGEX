'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import EnrollShell from '../EnrollShell'
import { useEnrollment } from '../useEnrollment'
import { track } from '@/lib/analytics/track'
import { trackEnrollStepComplete } from '@/lib/analytics/enroll'

/**
 * LEGAL-AUTO-01 — Agreements (10/5 reorder: step 2, BEFORE Choose agent).
 *
 * Seven documents, each with a Review action that opens the versioned content page.
 * The aggregate acceptance checkbox enables only after EVERY required document has
 * been opened (already-accepted documents count as reviewed — a customer must not
 * re-review what the record shows they already agreed to). Acceptance requires an
 * explicit electronic signature: the member's typed full legal name. The server
 * enforces both again (§ "a pre-checked control is not consent").
 *
 * No plan is known yet at this screen (it now runs before Choose agent), so the API
 * requires/returns the full automate-family superset unconditionally — reusing the
 * existing 'automate' family value server-side (GET .../legal, POST .../acceptances)
 * rather than a plan-conditional set. Accepting the superset up front trivially
 * satisfies whatever narrower set the eventual plan choice (including Community)
 * turns out to need, so there is no second legal touch later in the funnel.
 */

interface LegalDoc {
  code: string
  title: string
  version: string
  contentUri: string
  accepted: boolean
}

/**
 * Row subtitles. TERMS, RISK and PRIVACY are the exact `doc` summary strings
 * from IronForge_Enrollment_10.4.html's AGREEMENTS array — the one place
 * either source document supplies verbatim enrollment-step copy. The other
 * four codes have no verbatim source text in either the design prototype or
 * the dev handoff (which lists only docId + title for them), so they keep
 * their prior placeholder subtitles rather than inventing legal copy.
 */
const DOC_SUBTITLES: Record<string, string> = {
  TERMS:
    'By creating an account you agree to use IronForge for your own personal accounts, keep your login secure, and follow these terms. Subscriptions renew monthly until cancelled. You can cancel anytime from your dashboard.',
  RISK:
    'Options are complex and not suitable for every investor. Spreads limit risk to a defined amount, but you can still lose some or all of the capital used for a trade. Past performance, real or hypothetical, does not guarantee future results. Backtested results are hypothetical.',
  PRIVACY:
    'We collect the information you give us during enrollment and the brokerage data needed to place and monitor trades. We do not sell your personal information. Brokerage credentials are never stored by IronForge; access uses secure tokens you can revoke.',
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
    track('legal_accept_all')
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
      trackEnrollStepComplete('legal')
      router.push('/enroll/plan')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not record your agreement.')
      setBusy(false)
    }
  }

  return (
    <EnrollShell
      headline="Know what you’re authorizing."
      subline="Review the required agreements before you choose your agent."
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

          <div className="nav-row" style={{ justifyContent: 'flex-end' }}>
            <button type="button" disabled={!canSubmit} onClick={accept} className="btn btn-accent btn-lg">
              {busy ? 'Saving…' : 'Accept & Continue'}
            </button>
          </div>
        </>
      ) : null}
    </EnrollShell>
  )
}
