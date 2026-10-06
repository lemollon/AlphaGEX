import { NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'
import { isStripeConfigured, getDefaultPaymentMethod } from '@/lib/billing/stripe'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * GET /api/billing/payment-method — the masked card on file (brand + last4), for the
 * Account tab's "Payment method" row (fidelity audit: design shows `.lrow` with a card
 * icon + "Visa •••• 4242"; no real source existed). Read-only, never the full card
 * number — Stripe does not return that over the API either way.
 *
 * Degrades to `{ok:true, paymentMethod:null}` whenever there is nothing to show (no
 * Stripe customer yet, no card on file, Stripe/the customers DB not provisioned) —
 * never an error for what is a normal, common state.
 */
export async function GET() {
  const identity = await getCustomerIdentity()
  const customerId = identity?.customerId ?? null
  if (!customerId) return NextResponse.json({ ok: false }, { status: 401 })

  if (!isCustomersDbConfigured() || !isStripeConfigured()) {
    return NextResponse.json({ ok: true, paymentMethod: null })
  }

  try {
    const rows = await customerQuery<{ stripe_customer_id: string | null }>(
      `SELECT stripe_customer_id FROM users WHERE id = $1 LIMIT 1`,
      [customerId],
    )
    const stripeCustomerId = rows[0]?.stripe_customer_id
    if (!stripeCustomerId) return NextResponse.json({ ok: true, paymentMethod: null })

    const paymentMethod = await getDefaultPaymentMethod(stripeCustomerId)
    return NextResponse.json({ ok: true, paymentMethod })
  } catch (e) {
    console.error('[billing/payment-method] failed:', e)
    return NextResponse.json({ ok: true, paymentMethod: null })
  }
}
