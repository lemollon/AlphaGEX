import LegalPage, { LegalSection } from '@/components/LegalPage'
import { MARKETING_TIERS, TRIAL_DAYS } from '@/lib/billing/plans'

export const metadata = {
  title: 'Terms of Service — IronForge',
  description: 'The terms governing your use of IronForge.',
}

export default function TermsPage() {
  return (
    <LegalPage title="Terms of Service" updated="June 21, 2026">
      <p>
        These Terms of Service (&ldquo;Terms&rdquo;) govern your access to and use of the website and
        services provided by <strong>IronForge Technologies LLC</strong> (&ldquo;IronForge,&rdquo;
        &ldquo;we,&rdquo; &ldquo;us&rdquo;) at ironforge.trade (the &ldquo;Service&rdquo;). By creating an
        account or using the Service, you agree to these Terms.
      </p>

      <LegalSection heading="The Service">
        <p>
          IronForge provides software that connects to your own brokerage account so that automated
          options and equity strategies can generate trade ideas. <strong>Every order requires your
          explicit confirmation at the time of placement.</strong> IronForge does not exercise
          discretionary authority over your account, does not take custody of your funds, and does not
          place trades without your per-trade approval. Your money always remains in your own brokerage
          account.
        </p>
      </LegalSection>

      <LegalSection heading="Not investment advice">
        <p>
          IronForge is a software tool, not an investment adviser, broker-dealer, or financial planner.
          Nothing on the Service constitutes personalized investment, legal, tax, or financial advice, or
          a recommendation to buy or sell any security. You are solely responsible for your own trading
          decisions and for approving or declining each order.
        </p>
      </LegalSection>

      <LegalSection heading="Risk disclosure">
        <p>
          Trading options and other securities involves substantial risk and is not suitable for every
          investor. You can lose some or all of your investment. Past performance is not indicative of
          future results. IronForge makes no representation or guarantee of profit, income, or any
          particular outcome. You should only trade with capital you can afford to lose.
        </p>
      </LegalSection>

      <LegalSection heading="Eligibility and accounts">
        <p>
          You must be at least 18 years old and capable of forming a binding contract to use the Service.
          You are responsible for maintaining the confidentiality of your login credentials and for all
          activity under your account. Notify us promptly of any unauthorized use.
        </p>
      </LegalSection>

      <LegalSection heading="Brokerage connections">
        <p>
          The Service connects to supported brokerages through our partners using secure authorization
          flows. IronForge does not collect or store your brokerage username or password. You may
          disconnect a linked brokerage at any time, which revokes IronForge&rsquo;s access to that
          account going forward.
        </p>
      </LegalSection>

      <LegalSection heading="Subscriptions, trials, and billing">
        <p>
          {/* Prices read from MARKETING_TIERS so the terms can never quote a number the
              site or Stripe no longer charges. This paragraph said Community $10 +
              "Forge Automate" $50 while /pricing said $15 / Starter / Pro. */}
          Paid plans are billed monthly through Stripe. {MARKETING_TIERS.community.name} is billed at $
          {MARKETING_TIERS.community.priceMonthly} per month upon activation. {MARKETING_TIERS.starter.name} (one
          bot, ${MARKETING_TIERS.starter.priceMonthly} per month) and {MARKETING_TIERS.pro.name} (two bots, $
          {MARKETING_TIERS.pro.priceMonthly} per month) each include a {TRIAL_DAYS} trading-day free trial; unless
          you cancel before the trial ends, the plan converts to its monthly price. You authorize us to charge your selected payment
          method on a recurring basis until you cancel. You may cancel at any time, effective at the end
          of the current billing period; except where required by law, payments are non-refundable.
        </p>
      </LegalSection>

      <LegalSection heading="Acceptable use">
        <p>
          You agree not to misuse the Service, including by attempting to gain unauthorized access,
          interfering with its operation, reverse-engineering it, or using it in violation of applicable
          laws or the rules of any brokerage or exchange.
        </p>
      </LegalSection>

      <LegalSection heading="Limitation of liability">
        <p>
          To the maximum extent permitted by law, the Service is provided &ldquo;as is&rdquo; without
          warranties of any kind. IronForge and its officers, employees, and partners will not be liable
          for any indirect, incidental, special, or consequential damages, or for any trading losses,
          arising out of or relating to your use of the Service.
        </p>
      </LegalSection>

      <LegalSection heading="Changes and termination">
        <p>
          We may modify the Service or these Terms from time to time; material changes will be reflected
          by the &ldquo;Last updated&rdquo; date above. We may suspend or terminate access for violation
          of these Terms or to comply with legal obligations. You may stop using the Service and close
          your account at any time.
        </p>
      </LegalSection>

      <LegalSection heading="Governing law">
        <p>
          These Terms are governed by the laws of the State of Texas, United States, without regard to
          its conflict-of-laws principles.
        </p>
      </LegalSection>

      <LegalSection heading="Contact">
        <p>
          Questions about these Terms? Email{' '}
          <a href="mailto:leron@ironforge.trade" className="text-amber-500 hover:underline">
            leron@ironforge.trade
          </a>
          .
        </p>
      </LegalSection>
    </LegalPage>
  )
}
