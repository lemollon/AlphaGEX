import LegalPage, { LegalSection } from '@/components/LegalPage'

export const metadata = {
  title: 'Contact — IronForge',
  description: 'Get in touch with IronForge Technologies LLC — support, billing, and account questions.',
}

export default function ContactPage() {
  return (
    <LegalPage title="Contact us" updated="June 21, 2026">
      <p>
        IronForge is operated by <strong>IronForge Technologies LLC</strong>, based in Austin, Texas,
        United States. We are happy to help with support, billing, brokerage-connection, or account
        questions. The fastest way to reach a person is by email.
      </p>

      <LegalSection heading="Support &amp; general inquiries">
        <p>
          Email:{' '}
          <a href="mailto:leron@ironforge.trade" className="text-amber-500 hover:underline">
            leron@ironforge.trade
          </a>
        </p>
        <p>We aim to respond to all inquiries within two business days.</p>
      </LegalSection>

      <LegalSection heading="Billing &amp; subscriptions">
        <p>
          For questions about a charge, your plan, the free trial, or to cancel a
          subscription, email{' '}
          <a href="mailto:leron@ironforge.trade" className="text-amber-500 hover:underline">
            leron@ironforge.trade
          </a>{' '}
          with the email address on your account. Payments are processed by Stripe; IronForge does not
          store full card details.
        </p>
      </LegalSection>

      <LegalSection heading="Brokerage connections">
        <p>
          IronForge connects to your own brokerage account through our partners and never asks for or
          stores your broker username or password. If you need to disconnect a brokerage or have a
          question about a trade approval, contact us at the email above or disconnect directly from
          your account settings.
        </p>
      </LegalSection>

      <LegalSection heading="Mailing address">
        <p>
          IronForge Technologies LLC<br />
          Austin, TX, United States
        </p>
        <p className="text-sm text-forge-muted">A full mailing address is available on request.</p>
      </LegalSection>
    </LegalPage>
  )
}
