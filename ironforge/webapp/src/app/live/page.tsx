import { redirect } from 'next/navigation'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'

export const dynamic = 'force-dynamic'

/**
 * RETIRED as a destination (UAT-008 / IF-NAV-001): trade monitoring lives inside each
 * agent's workspace at /agents/{spark|flame}. This route survives only as a redirect —
 * it was the checkout/activation landing URL and is linked externally. Owners land on
 * their (first) agent's workspace; everyone else goes to /enroll, the ownership-aware
 * door. Query params (welcome, checkout state) are carried through.
 */
export default async function LivePage({
  searchParams,
}: {
  searchParams?: Record<string, string | string[] | undefined>
}) {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(searchParams ?? {})) {
    if (typeof v === 'string' && k !== 'account') qs.set(k, v)
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : ''

  // ?account= (the old switcher param) names the agent directly.
  const requested = typeof searchParams?.account === 'string' ? searchParams.account : null
  if (requested === 'spark' || requested === 'flame') redirect(`/agents/${requested}${suffix}`)

  // ?welcome=spark|flame is a just-completed purchase/activation landing — send it to
  // that agent's workspace even before the webhook writes the subscription row (the
  // workspace's CheckoutNotice covers the lag; the APIs still authorize server-side).
  const welcome = typeof searchParams?.welcome === 'string' ? searchParams.welcome : null
  if (welcome === 'spark' || welcome === 'flame') redirect(`/agents/${welcome}${suffix}`)

  const session = await getCustomerSession()
  if (session.customerId && isCustomersDbConfigured()) {
    let target: string | null = null
    try {
      const rows = await customerQuery<{ bot: string }>(
        `SELECT bot FROM customer_bot_subscriptions
          WHERE user_id = $1 AND status IN ('trialing', 'active', 'past_due')
            AND bot IN ('spark', 'flame')
          ORDER BY bot`,
        [session.customerId],
      )
      target = rows[0]?.bot ?? null
    } catch { /* fall through to /enroll */ }
    if (target) redirect(`/agents/${target}${suffix}`)
  }
  redirect('/enroll')
}
