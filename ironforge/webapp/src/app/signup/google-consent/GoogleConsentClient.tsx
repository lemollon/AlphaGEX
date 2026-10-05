'use client'

import { useState } from 'react'
import Link from 'next/link'
import Consent from '@/components/ConsentCheckbox'

/**
 * The one-time consent screen for a Google sign-in that would otherwise CREATE a
 * brand-new account. The verified Google identity already rode here in the
 * httpOnly google-pending-signup cookie (google/callback/route.ts); this screen's
 * only job is to collect the SAME 3 explicit consents the password form requires
 * before anything is written to the users table.
 *
 * POST, not a plain navigation: it carries the 3 booleans in a JSON body and the
 * server re-verifies the pending cookie itself — the cookie is httpOnly + signed +
 * SameSite=Lax, so a cross-site page cannot forge this request (the browser will
 * not attach it), and a same-site forged value cannot pass the HMAC check.
 */
export default function GoogleConsentClient({ email }: { email: string }) {
  const [ageConfirmed, setAgeConfirmed] = useState(false)
  const [noAdviceAcknowledged, setNoAdviceAcknowledged] = useState(false)
  const [electronicCommConsent, setElectronicCommConsent] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const allChecked = ageConfirmed && noAdviceAcknowledged && electronicCommConsent

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!allChecked || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const res = await fetch('/api/auth/google/complete-signup', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ ageConfirmed, noAdviceAcknowledged, electronicCommConsent }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok || !data.ok) {
        setError(data.error || 'Something went wrong creating your account. Please try again.')
        return
      }
      window.location.href = data.next || '/enroll'
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="rounded-2xl border border-forge-border bg-forge-card/60 p-6 lg:p-8">
      <h1 className="text-2xl font-bold text-white">One more step</h1>
      <p className="mt-1 text-sm leading-relaxed text-gray-400">
        Confirm these 3 things to finish creating your account as{' '}
        <span className="font-medium text-amber-500">{email}</span>.
      </p>

      <form onSubmit={onSubmit} noValidate className="mt-5 space-y-4">
        <div className="space-y-3">
          <Consent checked={ageConfirmed} onChange={setAgeConfirmed}>
            I am at least 18 years old and legally able to open and manage a brokerage account.
          </Consent>
          <Consent checked={noAdviceAcknowledged} onChange={setNoAdviceAcknowledged}>
            I understand IronForge provides automated trade execution technology and{' '}
            <span className="font-medium text-amber-500">does not provide financial, investment, tax, or legal advice</span>.
          </Consent>
          <Consent checked={electronicCommConsent} onChange={setElectronicCommConsent}>
            I agree to receive <span className="font-medium text-amber-500">electronic communications</span> related to my account, billing, legal notices, and platform activity.
          </Consent>
        </div>

        {error && (
          <p className="rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-xs text-red-300">{error}</p>
        )}

        <button
          type="submit"
          disabled={!allChecked || submitting}
          className="flex w-full items-center justify-center gap-2 rounded-md bg-amber-500 px-4 py-3 text-sm font-semibold text-black transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? 'Creating account…' : 'Create Account'}
        </button>

        <p className="text-center text-sm text-gray-400">
          Not you?{' '}
          <Link href="/signup" className="font-semibold text-amber-500 hover:text-amber-400">Start over</Link>
        </p>
      </form>
    </div>
  )
}
