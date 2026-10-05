import type { Metadata } from 'next'
import Link from 'next/link'
import { redirect } from 'next/navigation'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { hasActiveMembership } from '@/lib/live/membership'
import { customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'
import { BOT_PLANS } from '@/lib/billing/plans'
import { EMBER_AGENT } from '@/lib/agents/ember'
import EnrollShell from '../EnrollShell'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Welcome to the Forge — IronForge',
  description: 'Your membership is active.',
}

type WelcomeAgent = 'spark' | 'flame' | 'ember'

function isWelcomeAgent(v: string | null): v is WelcomeAgent {
  return v === 'spark' || v === 'flame' || v === 'ember'
}

/**
 * Enrollment completion landing (design spec §5 "Done screen") — the ONE page every
 * completed enrollment lands on: paid (Spark/Flame), Ember, and Community alike
 * (gap audit "Web enrollment — Done screen (3 cards)", previously MISSING for
 * paid/Ember, which skipped straight to /agents/{agent} and never saw this screen).
 *
 * `?welcome=spark|flame|ember|community` is the same landing convention already used
 * by /live and the Community checkout return (api/billing/checkout/route.ts) — reused
 * here rather than inventing a second param name. ReviewClient (paid/Ember activation)
 * and BillingClient (Community) both set it on their success redirect.
 *
 * NOT static: this page ASSERTS "Membership active", so it must verify it (UAT-007 —
 * the static version told every session holder they were in, including brand-new
 * accounts that had bought nothing). hasActiveMembership fails closed and already
 * covers every bot (Spark/Flame/Ember) and Community — it reads ANY live row in
 * customer_bot_subscriptions, not a Community-only table — so no extra gate is needed
 * per agent. Webhook lag is covered: the checkout return path runs resume-time
 * reconciliation before landing here, so a just-paid member has their subscription row
 * already.
 */
export default async function EnrollDonePage({
  searchParams,
}: {
  searchParams?: Record<string, string | string[] | undefined>
}) {
  const session = await getCustomerSession()
  if (!session.customerId) redirect('/login?next=/enroll')
  if (!(await hasActiveMembership(session.customerId))) redirect('/enroll')

  const welcomeParam = typeof searchParams?.welcome === 'string' ? searchParams.welcome : null
  const agent = isWelcomeAgent(welcomeParam) ? welcomeParam : null

  // Best-effort first name for the spec's "Welcome to the Forge, {FirstName}." — a
  // lookup failure must never block a member from seeing their own completion screen,
  // so this falls back to the name-less headline rather than erroring the page.
  let firstName: string | null = null
  if (isCustomersDbConfigured()) {
    try {
      const rows = await customerQuery<{ first_name: string | null }>(
        `SELECT first_name FROM users WHERE id = $1 LIMIT 1`,
        [session.customerId],
      )
      firstName = rows[0]?.first_name || null
    } catch {
      /* headline falls back below */
    }
  }

  const agentName = agent === 'spark' ? BOT_PLANS.spark.name : agent === 'flame' ? BOT_PLANS.flame.name : agent === 'ember' ? EMBER_AGENT.name : null
  const agentAccent =
    agent === 'spark' ? BOT_PLANS.spark.accent : agent === 'flame' ? BOT_PLANS.flame.accent : agent === 'ember' ? EMBER_AGENT.accent : undefined

  const headline = firstName ? `Welcome to the Forge, ${firstName}.` : 'Welcome to the Forge.'
  const subline = agentName
    ? agent === 'ember'
      ? `${agentName} is connected to your brokerage and will start with its next session.`
      : `${agentName} is connected to your brokerage and will start with its next session. Your first 5 trading days are free.`
    : 'Your Forge Community membership is live — briefings, market commentary, and member discussions are open to you now.'

  return (
    <EnrollShell headline={headline} subline={subline} topRight="none">
      <div className="done-wrap">
        <span className="badge ok">Membership active</span>
        <h1>You&rsquo;re in.</h1>

        {agentName ? (
          <div className="next">
            <div>
              <b style={agentAccent ? { color: agentAccent } : undefined}>Open your dashboard</b>
              <p>See {agentName}&rsquo;s status, trades and results.</p>
              <Link href={`/agents/${agent}`} className="link" style={{ marginTop: 6, display: 'inline-block' }}>
                Go to {agentName} &rarr;
              </Link>
            </div>
            <div>
              <b>Get the app</b>
              <p>Follow along from iPhone or Android.</p>
              <span style={{ display: 'flex', gap: 10, marginTop: 6 }}>
                <a href="https://apps.apple.com/us/search?term=IronForge" target="_blank" rel="noopener noreferrer" className="link">
                  App Store
                </a>
                <a href="https://play.google.com/store/search?q=IronForge&c=apps" target="_blank" rel="noopener noreferrer" className="link">
                  Google Play
                </a>
              </span>
            </div>
            <div>
              <b>Join the Community</b>
              <p>Daily briefings and member discussions.</p>
              <Link href="/community" className="link" style={{ marginTop: 6, display: 'inline-block' }}>
                Enter the Community &rarr;
              </Link>
            </div>
          </div>
        ) : (
          <div className="next">
            <div>
              <b>Open the Community</b>
              <p>Daily briefings, market commentary and member discussions.</p>
              <Link href="/community" className="link" style={{ marginTop: 6, display: 'inline-block' }}>
                Enter the Community &rarr;
              </Link>
            </div>
            <div>
              <b>Get the app</b>
              <p>Follow along from iPhone or Android.</p>
              <span style={{ display: 'flex', gap: 10, marginTop: 6 }}>
                <a href="https://apps.apple.com/us/search?term=IronForge" target="_blank" rel="noopener noreferrer" className="link">
                  App Store
                </a>
                <a href="https://play.google.com/store/search?q=IronForge&c=apps" target="_blank" rel="noopener noreferrer" className="link">
                  Google Play
                </a>
              </span>
            </div>
            <div>
              <b>Explore agents</b>
              <p>Add Spark, Flame or Ember whenever you&rsquo;re ready.</p>
              <Link href="/agents" className="link" style={{ marginTop: 6, display: 'inline-block' }}>
                Compare agents &rarr;
              </Link>
            </div>
          </div>
        )}

        <Link href={agentName ? `/agents/${agent}` : '/community'} className="btn btn-accent btn-lg" style={{ marginTop: 10 }}>
          {agentName ? `Go to ${agentName}` : 'Enter the Community'}
        </Link>
      </div>
    </EnrollShell>
  )
}
