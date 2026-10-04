import type { Metadata } from 'next'
import Link from 'next/link'
import { redirect } from 'next/navigation'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { hasActiveMembership } from '@/lib/live/membership'
import EnrollShell from '../EnrollShell'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Welcome to the Forge — IronForge',
  description: 'Your membership is active.',
}

/**
 * Enrollment completion landing — the Community checkout success return
 * (Automate never lands here: activation routes straight to /live per DASH-FIRST-01).
 *
 * NOT static: this page ASSERTS "Membership active", so it must verify it (UAT-007 —
 * the static version told every session holder they were in, including brand-new
 * accounts that had bought nothing). hasActiveMembership fails closed, and anyone
 * without a live subscription is bounced to /enroll, which resumes their real state.
 * Webhook lag is covered: the checkout return path runs resume-time reconciliation
 * before landing here, so a just-paid member has their subscription row already.
 */
export default async function EnrollDonePage() {
  const session = await getCustomerSession()
  if (!session.customerId) redirect('/login?next=/enroll')
  if (!(await hasActiveMembership(session.customerId))) redirect('/enroll')
  return (
    <EnrollShell headline="Welcome to the Forge." subline="Your membership is active." topRight="none">
      <div className="done-wrap">
        <span className="badge ok">Membership active</span>
        <h1>You&rsquo;re in.</h1>
        <p className="muted" style={{ maxWidth: '48ch', lineHeight: 1.6 }}>
          Your Forge Community membership is live — briefings, market commentary, and member
          discussions are open to you now.
        </p>
        <Link href="/community" className="btn btn-accent btn-lg">
          Enter the Community
        </Link>
      </div>
    </EnrollShell>
  )
}
