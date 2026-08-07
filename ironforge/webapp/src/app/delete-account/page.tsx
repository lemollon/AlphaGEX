import LegalPage, { LegalSection } from '@/components/LegalPage'
import DeleteAccountClient from './DeleteAccountClient'

export const metadata = {
  title: 'Delete Your Account — IronForge',
  description:
    'How to request deletion of your IronForge account, what is deleted, and what is kept.',
}

/**
 * Public account-deletion page. Google Play requires that account deletion be
 * requestable from a URL reachable WITHOUT signing in and without going back
 * through the app, so this page is on the public allowlist in lib/auth/access.ts
 * and explains the whole policy to a signed-out reader. Only the button that
 * actually files a request needs a session.
 */
export default function DeleteAccountPage() {
  return (
    <LegalPage title="Delete Your Account" updated="August 7, 2026">
      <p>
        You can ask us to delete your <strong>IronForge</strong> account at any time. This page
        explains exactly what happens, what is removed, and what we keep. You do not need to be
        signed in to read it.
      </p>

      <LegalSection heading="Before you start: close your positions">
        <p>
          IronForge places trades in <strong>your own brokerage account</strong>. We will not accept a
          deletion request while you still have positions that have not settled, because deleting your
          account would leave real money exposed with nothing watching it.
        </p>
        <p>
          If you have anything open, close it first — then come back. The request will tell you what is
          still outstanding if you try early.
        </p>
      </LegalSection>

      <LegalSection heading="What happens as soon as you request deletion">
        <ul className="list-disc pl-6 space-y-1.5">
          <li>
            <strong>Your subscription is cancelled.</strong> You will not be billed again.
          </li>
          <li>
            <strong>Your brokerage connection is removed.</strong> IronForge loses its access to your
            broker immediately, and no further orders can be placed.
          </li>
          <li>
            <strong>Your account is scheduled for deletion</strong> and marked so it cannot be used to
            start trading again.
          </li>
        </ul>
      </LegalSection>

      <LegalSection heading="What is deleted">
        <p>When your request is processed, we permanently remove the information that identifies you:</p>
        <ul className="list-disc pl-6 space-y-1.5">
          <li>Your name, email address, phone number, and state.</li>
          <li>Your password (stored only as a salted hash).</li>
          <li>Your brokerage access tokens and connection records.</li>
          <li>Your saved notification preferences and registered devices.</li>
          <li>Your community posts, messages, and reactions.</li>
        </ul>
        <p>
          We also ask the providers that process data on our behalf — including Stripe, SnapTrade, and
          Attio — to delete what they hold, in line with their own retention obligations.
        </p>
      </LegalSection>

      <LegalSection heading="What is kept, and why">
        <p>
          IronForge is a financial service, so some records cannot simply be destroyed. We keep the
          following, but we <strong>de-identify</strong> them — the link between the record and you as a
          person is severed:
        </p>
        <ul className="list-disc pl-6 space-y-1.5">
          <li>Trade and position history, and the orders placed on your behalf.</li>
          <li>Enrollment, activation, and risk-assessment records.</li>
          <li>Your acceptances of our legal agreements, and the security audit log.</li>
          <li>Billing and payment records held by Stripe for tax and accounting purposes.</li>
        </ul>
        <p>
          This matches our{' '}
          <a href="/privacy" className="text-amber-500 hover:text-amber-400 font-semibold">
            Privacy Policy
          </a>
          , which explains that deletion is subject to records we are required to keep.
        </p>
      </LegalSection>

      <LegalSection heading="Changing your mind">
        <p>
          You have <strong>14 days</strong> to call off a deletion request. Sign in and cancel it from
          this page.
        </p>
        <p>
          Cancelling stops the deletion, but it does{' '}
          <strong>not automatically restore your subscription or your brokerage connection</strong> —
          those were ended when you made the request, and you would need to set them up again yourself.
          We will not quietly re-subscribe you.
        </p>
      </LegalSection>

      <LegalSection heading="Request deletion">
        <DeleteAccountClient />
      </LegalSection>

      <LegalSection heading="If you cannot sign in">
        <p>
          Email us at{' '}
          <a
            href="mailto:support@ironforge.trade"
            className="text-amber-500 hover:text-amber-400 font-semibold"
          >
            support@ironforge.trade
          </a>{' '}
          from the address on your account and we will process the request for you. We may ask you to
          confirm a detail of the account before we act, so that nobody else can delete it.
        </p>
      </LegalSection>
    </LegalPage>
  )
}
