import { notFound } from 'next/navigation'
import LegalPage, { LegalSection } from '@/components/LegalPage'
import { MARKETING_TIERS, TRIAL_DAYS } from '@/lib/billing/plans'

/**
 * Content pages for the versioned enrollment documents (lib/enrollment/legal.ts
 * points RISK / ADVICE_DISCLAIMER / ELECTRONIC_CONSENT / TRADING_AUTH / REFUND here).
 * These URIs are what the LEGAL-AUTO-01 "Review" actions open — before this file the
 * registry pointed at routes that 404'd.
 *
 * ⚠️ Copy is a working draft pending counsel signoff (same caveat as the registry).
 * Structure, versioning, and acceptance mechanics are final; wording is not.
 */

interface DocPage {
  title: string
  updated: string
  body: () => JSX.Element
}

const DOCS: Record<string, DocPage> = {
  risk: {
    title: 'Options & Automated Trading Risk Disclosure',
    updated: 'July 30, 2026',
    body: () => (
      <>
        <p>
          This disclosure describes the principal risks of trading options and of authorizing
          automated trading through IronForge. Read it carefully before enabling automated
          execution. By accepting it you confirm that you understand and can bear these risks.
        </p>
        <LegalSection heading="Options trading risk">
          <p>
            Options are complex instruments and involve substantial risk. Multi-leg option
            strategies, including the iron condor structures IronForge agents trade, have a
            defined maximum loss per position that can be a multiple of the premium received.
            You can lose the entire amount at risk on a position, and repeated losses can
            substantially reduce your account value. Options may be illiquid, and closing a
            position before expiration may not be possible at a favorable price.
          </p>
        </LegalSection>
        <LegalSection heading="Automated execution risk">
          <p>
            Automated trading submits orders without a per-order confirmation from you. Orders
            may be placed while you are not watching the market. Software, connectivity, market
            data, or brokerage failures can cause missed entries, missed exits, duplicate or
            rejected orders, or positions remaining open longer than intended. Safeguards such
            as kill switches and pause controls reduce but do not eliminate these risks.
          </p>
        </LegalSection>
        <LegalSection heading="No guaranteed outcome">
          <p>
            Strategy performance shown anywhere on the Service — including paper-trading
            results — is not a guarantee or prediction of future results. Market conditions
            change, and a strategy that performed well historically can lose money. You should
            only authorize capital you can afford to lose.
          </p>
        </LegalSection>
        <LegalSection heading="Your responsibilities">
          <p>
            You are responsible for maintaining sufficient funds and required options approval
            with your brokerage, for monitoring your account, and for pausing or revoking
            automated trading if you no longer wish it to operate. IronForge cannot withdraw
            funds or transfer cash from your brokerage account.
          </p>
        </LegalSection>
      </>
    ),
  },
  'investment-advice-disclaimer': {
    title: 'Investment Advice Disclaimer',
    updated: 'July 30, 2026',
    body: () => (
      <>
        <p>
          IronForge is a software tool. It is not an investment adviser, broker-dealer,
          commodity trading advisor, or financial planner, and it is not registered as any of
          those with the SEC, FINRA, the CFTC, or any state authority.
        </p>
        <LegalSection heading="No individualized advice">
          <p>
            Nothing on the Service — including agent descriptions, risk profiles, market
            commentary, briefings, educational content, community discussion, or the behavior
            of any automated strategy — constitutes individualized investment, legal, tax, or
            financial advice, or a recommendation that any security, strategy, or transaction
            is suitable for you.
          </p>
        </LegalSection>
        <LegalSection heading="Your decision">
          <p>
            Selecting an agent and activating automated trading is your decision alone. The
            strategies are rules-based and are not selected or adjusted for your personal
            financial situation, objectives, or risk tolerance. If you are unsure whether
            options trading or automated execution is appropriate for you, consult a qualified
            financial professional before activating.
          </p>
        </LegalSection>
      </>
    ),
  },
  'electronic-consent': {
    title: 'Electronic Communications Consent',
    updated: 'July 30, 2026',
    body: () => (
      <>
        <p>
          By accepting this consent you agree to receive and sign records electronically in
          connection with your IronForge membership.
        </p>
        <LegalSection heading="What you are consenting to">
          <p>
            You consent to receive agreements, disclosures, notices, confirmations, statements,
            and other records from IronForge electronically — through the Service or to the
            email address on your account — instead of on paper, and to the use of electronic
            signatures (including typing your legal name) with the same effect as a handwritten
            signature.
          </p>
        </LegalSection>
        <LegalSection heading="Hardware and software">
          <p>
            To access and retain electronic records you need a device with a current web
            browser, an internet connection, a valid email address, and the ability to view and
            save or print PDF and HTML documents.
          </p>
        </LegalSection>
        <LegalSection heading="Withdrawing consent">
          <p>
            You may withdraw this consent by contacting{' '}
            <a href="mailto:leron@ironforge.trade" className="text-amber-500 hover:underline">
              leron@ironforge.trade
            </a>
            . Because the Service is delivered electronically, withdrawing consent will require
            closing your automated-trading enrollment. Keep your email address current so
            records reach you.
          </p>
        </LegalSection>
      </>
    ),
  },
  'trading-authorization': {
    title: 'Automated Trading Authorization',
    updated: 'July 30, 2026',
    body: () => (
      <>
        <p>
          This authorization takes effect only when you complete the Review &amp; Activate step
          for a specific agent configuration. It is the record of what activation authorizes.
        </p>
        <LegalSection heading="What you authorize">
          <p>
            You authorize IronForge to submit, manage, and close orders in your connected
            brokerage account, without per-order confirmation, strictly under the agent,
            brokerage account, rule version, and maximum capital deployment shown to you on the
            Review &amp; Activate screen at the time you activate. A material change to that
            configuration requires a fresh preview and a fresh authorization.
          </p>
        </LegalSection>
        <LegalSection heading="What you do not authorize">
          <p>
            IronForge cannot withdraw funds, transfer cash or securities, change your brokerage
            credentials, or act outside the authorized agent configuration. Your money remains
            in your own brokerage account at all times.
          </p>
        </LegalSection>
        <LegalSection heading="Pausing and revoking">
          <p>
            You may pause automated trading at any time from the dashboard; pausing stops new
            order submission without disconnecting your brokerage. You may revoke this
            authorization entirely by disconnecting your brokerage or canceling your membership.
            Pausing or revoking does not close positions already open unless you close them.
          </p>
        </LegalSection>
        <LegalSection heading="Kill switches">
          <p>
            IronForge may halt order submission platform-wide or per-agent at any time as a
            protective control. A halt blocks new orders and new activations until cleared.
          </p>
        </LegalSection>
      </>
    ),
  },
  'refund-policy': {
    title: 'Refund Policy',
    updated: 'July 30, 2026',
    body: () => (
      <>
        <p>
          This policy describes billing, cancellation, and refunds for IronForge memberships.
          Prices shown here are read from the same configuration that drives checkout.
        </p>
        <LegalSection heading="Billing">
          <p>
            Memberships are billed monthly in advance through Stripe. {MARKETING_TIERS.community.name} is
            billed at ${MARKETING_TIERS.community.priceMonthly}/month starting at enrollment. Automated-trading
            memberships (${MARKETING_TIERS.starter.priceMonthly}/month for one agent) begin with a{' '}
            {TRIAL_DAYS} eligible trading-day free trial that starts only when you activate
            automated trading; your card is required at setup but is not charged until the
            trial ends.
          </p>
        </LegalSection>
        <LegalSection heading="Cancellation">
          <p>
            You may cancel at any time from Manage Membership. Cancellation takes effect at the
            end of the current billing period; you keep access until then. Canceling during a
            free trial before it converts means you are never charged.
          </p>
        </LegalSection>
        <LegalSection heading="Refunds">
          <p>
            Except where required by law, payments are non-refundable, including for partial
            billing periods. Trading losses are never refundable — they occur in your own
            brokerage account under the risks you accepted when activating. If you believe you
            were billed in error, contact{' '}
            <a href="mailto:leron@ironforge.trade" className="text-amber-500 hover:underline">
              leron@ironforge.trade
            </a>{' '}
            within 30 days of the charge and we will review it.
          </p>
        </LegalSection>
      </>
    ),
  },
}

export function generateStaticParams() {
  return Object.keys(DOCS).map((slug) => ({ slug }))
}

export function generateMetadata({ params }: { params: { slug: string } }) {
  const doc = DOCS[params.slug]
  if (!doc) return {}
  return { title: `${doc.title} — IronForge` }
}

export default function LegalDocumentPage({ params }: { params: { slug: string } }) {
  const doc = DOCS[params.slug]
  if (!doc) notFound()
  return (
    <LegalPage title={doc.title} updated={doc.updated}>
      <doc.body />
    </LegalPage>
  )
}
