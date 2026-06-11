'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Wordmark } from '@/components/Brand'

/* ── Inline glyphs (custom SVG, no emojis/stock icons) ─────────────── */

function ShieldSmall() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true">
      <path d="M12 3l7 3v5c0 4.2-2.9 7.4-7 8.5-4.1-1.1-7-4.3-7-8.5V6l7-3z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  )
}

function CheckCircle() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="mx-auto h-12 w-12" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="#EE5A24" strokeWidth="1.6" />
      <path d="M8 12.5l2.5 2.5L16 9.5" stroke="#EE5A24" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

interface AckState {
  riskDisclosure: boolean
  automatedExecution: boolean
  termsAccepted: boolean
}

const DISCLOSURES: { key: keyof AckState; body: React.ReactNode }[] = [
  {
    key: 'riskDisclosure',
    body: (
      <>
        I have read and accept the <span className="font-medium text-amber-500">Options &amp; Automated Trading Risk Disclosure</span>.
        Trading options carries a substantial risk of loss, is not suitable for every investor, and I may lose more than my initial investment.
      </>
    ),
  },
  {
    key: 'automatedExecution',
    body: (
      <>
        I understand IronForge places trades <span className="font-medium text-amber-500">automatically</span> on my connected brokerage
        according to the strategies I authorize, that I remain responsible for monitoring my account, and that IronForge{' '}
        <span className="font-medium text-amber-500">does not provide financial, investment, tax, or legal advice</span>.
      </>
    ),
  },
  {
    key: 'termsAccepted',
    body: (
      <>
        I agree to the IronForge <span className="font-medium text-amber-500">Terms of Service</span> and{' '}
        <span className="font-medium text-amber-500">Privacy Policy</span>.
      </>
    ),
  },
]

export default function LegalForm() {
  const [acks, setAcks] = useState<AckState>({
    riskDisclosure: false,
    automatedExecution: false,
    termsAccepted: false,
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const allChecked = acks.riskDisclosure && acks.automatedExecution && acks.termsAccepted

  function set(key: keyof AckState, value: boolean) {
    setAcks((a) => ({ ...a, [key]: value }))
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!allChecked || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const res = await fetch('/api/onboarding/accept-legal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(acks),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok || !data.ok) {
        setError(data.error || 'Something went wrong. Please try again.')
        setSubmitting(false)
        return
      }
      setDone(true)
    } catch {
      setError('Network error. Please try again.')
      setSubmitting(false)
    }
  }

  if (done) {
    return (
      <div className="min-h-screen bg-forge-bg bg-ember-glow px-4 py-16">
        <div className="mx-auto max-w-md rounded-2xl border border-white/10 bg-forge-card/90 p-8 text-center shadow-2xl">
          <CheckCircle />
          <h1 className="mt-4 text-xl font-bold text-white">Disclosures accepted</h1>
          <p className="mt-2 text-sm leading-relaxed text-gray-400">
            Thank you. Your acceptance has been recorded. The next steps — billing, brokerage connection,
            and risk profile — are coming soon. We&apos;ll email you the moment they&apos;re ready.
          </p>
          <p className="mt-6 text-xs text-gray-500">
            <Link href="/" className="font-semibold text-amber-500 hover:text-amber-400">Return home</Link>
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-forge-bg bg-ember-glow px-4 py-8 sm:py-12">
      <div className="mx-auto max-w-lg">
        <div className="mb-6 flex justify-center">
          <Wordmark />
        </div>

        <div className="rounded-2xl border border-white/10 bg-forge-card/90 p-6 shadow-2xl sm:p-8">
          <p className="text-xs font-semibold uppercase tracking-wide text-amber-500">Step 2 · Legal &amp; Disclosures</p>
          <h1 className="mt-1 text-2xl font-bold text-white">Review and accept</h1>
          <p className="mt-2 text-sm leading-relaxed text-gray-400">
            Before connecting billing or your brokerage, please review and accept the disclosures below.
            Nothing is activated and no trading can occur until every onboarding step is complete.
          </p>

          <form onSubmit={onSubmit} noValidate className="mt-6 space-y-4">
            <div className="space-y-3">
              {DISCLOSURES.map((d) => (
                <Consent key={d.key} checked={acks[d.key]} onChange={(v) => set(d.key, v)}>
                  {d.body}
                </Consent>
              ))}
            </div>

            {error && (
              <p className="rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-xs text-red-300">{error}</p>
            )}

            <button
              type="submit"
              disabled={!allChecked || submitting}
              className="flex w-full items-center justify-center gap-2 rounded-md bg-amber-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-amber-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <ShieldSmall />
              {submitting ? 'Recording…' : 'Accept & Continue'}
            </button>

            <p className="text-center text-[11px] text-gray-500">
              Your acceptance is timestamped and recorded for compliance.
            </p>
          </form>
        </div>
      </div>
    </div>
  )
}

function Consent({
  checked,
  onChange,
  children,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  children: React.ReactNode
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-white/10 bg-black/20 px-3 py-3 text-xs leading-relaxed text-gray-300 transition hover:border-white/20">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 shrink-0 rounded border border-white/20 bg-black/40 accent-amber-600"
      />
      <span>{children}</span>
    </label>
  )
}
