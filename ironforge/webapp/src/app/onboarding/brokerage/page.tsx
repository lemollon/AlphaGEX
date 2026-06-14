import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { ONBOARDING_COOKIE, verifyOnboardingToken } from '@/lib/auth/onboarding'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import BrokerageConnectClient from './BrokerageConnectClient'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export default async function OnboardingBrokeragePage() {
  // Guarded exactly like the other onboarding steps: a valid handoff cookie OR a customer session.
  const claims = await verifyOnboardingToken(cookies().get(ONBOARDING_COOKIE)?.value)
  const session = await getCustomerSession()
  if (!claims && !session.customerId) redirect('/login?next=/onboarding/brokerage')

  return (
    <div className="min-h-screen bg-forge-bg bg-ember-glow px-4 py-16">
      <div className="mx-auto max-w-md rounded-2xl border border-white/10 bg-forge-card/90 p-8 shadow-2xl">
        <h1 className="text-2xl font-bold text-white">Connect your brokerage</h1>
        <p className="mt-2 text-sm leading-relaxed text-gray-400">
          Link the brokerage account you already use. Your funds stay in your account, in your
          name — IronForge never holds your money. You&apos;ll review and approve every trade
          before it&apos;s placed.
        </p>

        <ul className="mt-6 space-y-3 text-sm text-gray-300">
          <li className="flex gap-2"><span className="text-amber-500">•</span> Bank-level security — we never see your brokerage password.</li>
          <li className="flex gap-2"><span className="text-amber-500">•</span> You approve each trade at placement time.</li>
          <li className="flex gap-2"><span className="text-amber-500">•</span> Disconnect anytime from your account settings.</li>
        </ul>

        <BrokerageConnectClient />
      </div>
    </div>
  )
}
