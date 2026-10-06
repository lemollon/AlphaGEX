'use client'

import { useMemo, useState } from 'react'
import { loadStripe, type Stripe } from '@stripe/stripe-js'
import { Elements, PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js'

/**
 * Embedded card form (10/5 reorder) — replaces the hosted-Checkout redirect for the
 * Automate billing step with Stripe Elements' Payment Element, still entirely on
 * Stripe: the card never touches our server, only Stripe's iframe does.
 *
 * `clientSecret` comes from a SetupIntent (POST /api/billing/setup-intent), not a
 * subscription — $0 due today, trial still starts only at activation (see
 * lib/billing/stripe.ts createSetupIntent). `redirect: 'if_required'` keeps the
 * customer on this page for the common case (no 3-D Secure challenge) and only leaves
 * if Stripe genuinely needs an off-site step.
 *
 * BillingClient only renders this when NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY is set; it
 * falls back to the hosted-Checkout button otherwise, so a deployment missing that
 * env var degrades to the previous behavior rather than breaking enrollment.
 */

let stripePromise: Promise<Stripe | null> | null = null
function getStripe(publishableKey: string): Promise<Stripe | null> {
  if (!stripePromise) stripePromise = loadStripe(publishableKey)
  return stripePromise
}

export default function StripeCardForm({
  publishableKey,
  clientSecret,
  onSaved,
}: {
  publishableKey: string
  clientSecret: string
  onSaved: () => void
}) {
  const stripe = useMemo(() => getStripe(publishableKey), [publishableKey])
  return (
    <Elements stripe={stripe} options={{ clientSecret, appearance: { theme: 'night' } }}>
      <CardFormInner onSaved={onSaved} />
    </Elements>
  )
}

function CardFormInner({ onSaved }: { onSaved: () => void }) {
  const stripe = useStripe()
  const elements = useElements()
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!stripe || !elements) return
    setSubmitting(true)
    setError(null)
    const { error: confirmError } = await stripe.confirmSetup({
      elements,
      redirect: 'if_required',
    })
    if (confirmError) {
      setError(confirmError.message || 'Could not save your card. Please try again.')
      setSubmitting(false)
      return
    }
    onSaved()
  }

  return (
    <form onSubmit={onSubmit} className="stack" style={{ marginTop: 16 }}>
      <PaymentElement />
      {error ? <p className="err">{error}</p> : null}
      <button type="submit" disabled={!stripe || submitting} className="btn btn-accent btn-block btn-lg">
        {submitting ? 'Saving…' : 'Save Payment & Continue'}
      </button>
    </form>
  )
}
