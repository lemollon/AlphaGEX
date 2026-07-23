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

        <ul className="mt-8 space-y-5 border-t border-white/10 pt-6">
          <li className="flex items-start gap-3">
            <svg aria-hidden="true" className="mt-0.5 h-6 w-6 shrink-0 text-[#FD5301]" viewBox="0 0 24 24" fill="none">
              <path d="M12 3l7 3v5c0 4.4-3 8-7 10-4-2-7-5.6-7-10V6l7-3z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
              <rect x="9.25" y="10.5" width="5.5" height="4.5" rx="1" stroke="currentColor" strokeWidth="1.5" />
              <path d="M10.5 10.5V9.25a1.5 1.5 0 013 0v1.25" stroke="currentColor" strokeWidth="1.5" />
            </svg>
            <div>
              <div className="text-sm font-semibold text-white">Bank-level security</div>
              <div className="text-sm text-gray-400">We never see your brokerage password.</div>
            </div>
          </li>
          <li className="flex items-start gap-3">
            <svg aria-hidden="true" className="mt-0.5 h-6 w-6 shrink-0 text-[#FD5301]" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
              <path d="M8 12.5l2.5 2.5L16 9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <div>
              <div className="text-sm font-semibold text-white">You stay in control</div>
              <div className="text-sm text-gray-400">You approve each trade at placement time.</div>
            </div>
          </li>
          <li className="flex items-start gap-3">
            <svg aria-hidden="true" className="mt-0.5 h-6 w-6 shrink-0 text-[#FD5301]" viewBox="0 0 24 24" fill="none">
              <path d="M12 3v8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              <path d="M6.5 7a8 8 0 1011 0" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <div>
              <div className="text-sm font-semibold text-white">Disconnect anytime</div>
              <div className="text-sm text-gray-400">Disconnect anytime from your account settings.</div>
            </div>
          </li>
        </ul>

        <div className="mt-6 border-t border-white/10 pt-2" />

        <BrokerageConnectClient />
      </div>
    </div>
  )
}
