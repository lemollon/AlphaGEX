import Link from 'next/link'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { ONBOARDING_COOKIE, verifyOnboardingToken } from '@/lib/auth/onboarding'
import { getCustomerSession } from '@/lib/auth/customer-session'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export default async function OnboardingCompletePage() {
  // Reachable by a valid onboarding handoff cookie OR a logged-in customer session.
  const claims = await verifyOnboardingToken(cookies().get(ONBOARDING_COOKIE)?.value)
  const session = await getCustomerSession()
  if (!claims && !session.customerId) redirect('/login?next=/onboarding/complete')

  return (
    <div className="min-h-screen bg-forge-bg bg-ember-glow px-4 py-16">
      <div className="mx-auto max-w-md rounded-2xl border border-white/10 bg-forge-card/90 p-8 text-center shadow-2xl">
        <h1 className="text-xl font-bold text-white">You&apos;re all set — for now</h1>
        <p className="mt-2 text-sm leading-relaxed text-gray-400">
          Your account is created, your disclosures are on file, and we&apos;ve matched you to a
          recommended bot. The next steps — billing, brokerage connection, and deployment — are
          coming soon. We&apos;ll email you the moment they&apos;re ready.
        </p>
        <p className="mt-6 text-xs text-gray-500">
          <Link href="/" className="font-semibold text-amber-500 hover:text-amber-400">Return home</Link>
        </p>
      </div>
    </div>
  )
}
