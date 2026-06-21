import LegalPage, { LegalSection } from '@/components/LegalPage'

export const metadata = {
  title: 'Privacy Policy — IronForge',
  description: 'How IronForge Technologies LLC collects, uses, and protects your information.',
}

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy" updated="June 21, 2026">
      <p>
        This Privacy Policy explains how <strong>IronForge Technologies LLC</strong> (&ldquo;IronForge,&rdquo;
        &ldquo;we,&rdquo; &ldquo;us&rdquo;) collects, uses, and safeguards information when you use our
        website and services at ironforge.trade (the &ldquo;Service&rdquo;). By using the Service you agree
        to the practices described here.
      </p>

      <LegalSection heading="Information we collect">
        <p>We collect the following categories of information:</p>
        <ul className="list-disc pl-6 space-y-1.5">
          <li><strong>Account information</strong> — name, email address, and password (stored only as a salted hash).</li>
          <li><strong>Billing information</strong> — billing name and address, plan selection, and subscription status. Card payments are processed by Stripe; we receive tokens and identifiers, not full card numbers, CVV, or expiration dates.</li>
          <li><strong>Brokerage connection data</strong> — when you connect a brokerage account, we receive access tokens and limited account metadata (such as account ID, type, status, and buying power). We never collect or store your broker username or password.</li>
          <li><strong>Usage and device data</strong> — IP address, browser type, and activity logs used for security, auditing, and improving the Service.</li>
        </ul>
      </LegalSection>

      <LegalSection heading="How we use information">
        <ul className="list-disc pl-6 space-y-1.5">
          <li>To provide, operate, and secure the Service, including presenting trade ideas and executing orders that you explicitly approve.</li>
          <li>To process subscriptions and billing through Stripe.</li>
          <li>To communicate with you about your account, trials, alerts, and support requests.</li>
          <li>To maintain audit records and comply with legal and regulatory obligations.</li>
        </ul>
      </LegalSection>

      <LegalSection heading="Service providers we share with">
        <p>
          We share information only as needed with the providers that power the Service, each under their
          own terms and privacy policies:
        </p>
        <ul className="list-disc pl-6 space-y-1.5">
          <li><strong>SnapTrade</strong> and <strong>Tradier</strong> — to securely connect your brokerage account and place orders you approve.</li>
          <li><strong>Stripe</strong> — to process payments and manage subscriptions.</li>
          <li><strong>Attio</strong> — for customer relationship and lifecycle management.</li>
          <li><strong>Infrastructure and email providers</strong> — for hosting, data storage, and transactional notifications.</li>
        </ul>
        <p>We do not sell your personal information.</p>
      </LegalSection>

      <LegalSection heading="How we protect information">
        <p>
          Brokerage access and refresh tokens are encrypted at rest. All traffic to the Service is
          transmitted over TLS. Access to sensitive data is limited, and brokerage authorization events
          are audited. No method of transmission or storage is perfectly secure, but we work to protect
          your information using industry-standard safeguards.
        </p>
      </LegalSection>

      <LegalSection heading="Data retention">
        <p>
          We retain account, billing, and audit records for as long as your account is active and as
          required to meet legal, accounting, and compliance obligations. You may request deletion of
          your account by contacting us, subject to records we are required to keep.
        </p>
      </LegalSection>

      <LegalSection heading="Your choices and rights">
        <p>
          You may access or update your account information, disconnect a linked brokerage at any time,
          and cancel your subscription. Depending on where you live, you may have additional rights to
          access, correct, or delete your personal information. To exercise these rights, contact us at
          the email below.
        </p>
      </LegalSection>

      <LegalSection heading="Changes to this policy">
        <p>
          We may update this Privacy Policy from time to time. Material changes will be reflected by the
          &ldquo;Last updated&rdquo; date above, and where appropriate we will notify you.
        </p>
      </LegalSection>

      <LegalSection heading="Contact">
        <p>
          Questions about this policy? Email{' '}
          <a href="mailto:leron@ironforge.trade" className="text-amber-500 hover:underline">
            leron@ironforge.trade
          </a>
          .
        </p>
      </LegalSection>
    </LegalPage>
  )
}
