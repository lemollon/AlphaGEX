import type { Metadata } from 'next'
import Image from 'next/image'
import Link from 'next/link'
import MarketingShell from '@/components/marketing/MarketingShell'
import { getAgent } from '@/lib/marketing/agents'
import { BOT_PLANS, COMMUNITY_PLAN } from '@/lib/billing/plans'

export const metadata: Metadata = {
  title: 'Pricing — IronForge',
  description: 'Pick an agent. Forge Community is included with every one. No contracts, cancel anytime.',
}

const FAQ = [
  {
    q: 'Do I need to know how options work?',
    a: 'No. The agents handle entries, exits and sizing. Forge Community, included with every agent, is there if you’d like to learn along the way.',
  },
  {
    q: 'Where is my money held?',
    a: "In your own brokerage account, connected through Tradier or another supported brokerage. IronForge sends trade instructions and can't withdraw funds.",
  },
  {
    q: 'Is there a track record?',
    a: 'Live trading on Ladder sizing began September 8, 2026. Anything earlier is from backtests, which are hypothetical and don’t guarantee future results.',
  },
  { q: 'Can I lose money?', a: 'Yes. Options trading carries real risk, including loss of the money you invest.' },
  {
    q: 'Can I try it before paying?',
    a: 'Yes. Spark and Flame start with 5 trading days free, trading live in your account. Cancel before the trial ends and you won’t be charged. Ember is always free.',
  },
  {
    q: 'Is Ember really free?',
    a: 'Yes. Ember has no monthly fee. Each person can have one Ember account, funded with $500 to $2,000 in trading capital. To trade more, switch to Spark or Flame.',
  },
  {
    q: 'Does Forge Community cost extra?',
    a: 'No. Community is included with Spark, Flame and Ember at no extra cost.',
  },
  {
    q: 'What happens after the free trial?',
    a: `Spark and Flame are $${BOT_PLANS.spark.priceMonthly} a month each after 5 trading days. Cancel before the trial ends and you won’t be charged.`,
  },
]

function Check() {
  return (
    <svg>
      <use href="#i-check" />
    </svg>
  )
}

export default function PricingPage() {
  const spark = getAgent('spark')
  const flame = getAgent('flame')
  const ember = getAgent('ember')

  return (
    <MarketingShell>
      <div className="wrap page-head">
        <h1>Pricing</h1>
        <p>Pick an agent. Forge Community is included with every one. No contracts, cancel anytime.</p>
      </div>

      <div className="wrap plans cols-4" id="plans">
        <div className="card plan feat-plan">
          <div className="plan-top">
            <h3 style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Image className="av" style={{ width: 28, height: 28, borderRadius: 8 }} src={spark.mascot} alt="" width={28} height={28} />
              Spark
            </h3>
            <span className="tag">5 trading days free</span>
          </div>
          <div className="price">
            <b>${BOT_PLANS.spark.priceMonthly}</b>
            <span>/ month</span>
          </div>
          <p className="muted">Trades the morning session, when the market moves the most.</p>
          <ul>
            <li>
              <Check />
              Spark agent, morning session
            </li>
            <li>
              <Check />
              Ladder position sizing
            </li>
            <li>
              <Check />
              Real-time monitoring and kill switch
            </li>
            <li>
              <Check />
              Forge Community included
            </li>
            <li>
              <Check />
              Dashboard, app and trade history
            </li>
          </ul>
          <Link className="btn btn-lg btn-block btn-accent" href="/signup?bot=spark&source=site&placement=tier_card">
            Start free trial
          </Link>
        </div>

        <div className="card plan feat-plan">
          <div className="plan-top">
            <h3 style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Image className="av" style={{ width: 28, height: 28, borderRadius: 8 }} src={flame.mascot} alt="" width={28} height={28} />
              Flame
            </h3>
            <span className="tag">5 trading days free</span>
          </div>
          <div className="price">
            <b>${BOT_PLANS.flame.priceMonthly}</b>
            <span>/ month</span>
          </div>
          <p className="muted">Trades the calmer afternoon session, after the morning rush settles.</p>
          <ul>
            <li>
              <Check />
              Flame agent, afternoon session
            </li>
            <li>
              <Check />
              Ladder position sizing
            </li>
            <li>
              <Check />
              Real-time monitoring and kill switch
            </li>
            <li>
              <Check />
              Forge Community included
            </li>
            <li>
              <Check />
              Dashboard, app and trade history
            </li>
          </ul>
          <Link className="btn btn-lg btn-block btn-accent" href="/signup?bot=flame&source=site&placement=tier_card">
            Start free trial
          </Link>
        </div>

        <div className="card plan">
          <div className="plan-top">
            <h3 style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Image className="av" style={{ width: 28, height: 28, borderRadius: 8 }} src={ember.mascot} alt="" width={28} height={28} />
              Ember
            </h3>
            <span className="tag" style={{ background: 'var(--up-soft)', color: 'var(--up)' }}>
              Free
            </span>
          </div>
          <div className="price">
            <b>$0</b>
            <span>/ month</span>
          </div>
          <p className="muted">Built for smaller accounts and first-time investors.</p>
          <ul>
            <li>
              <Check />
              Ember agent with Ladder sizing
            </li>
            <li>
              <Check />
              One Ember account per person
            </li>
            <li>
              <Check />
              $500 to $2,000 in trading capital
            </li>
            <li>
              <Check />
              Forge Community included
            </li>
            <li>
              <Check />
              Dashboard, app and trade history
            </li>
          </ul>
          <Link className="btn btn-lg btn-block" href="/signup?bot=ember&source=site&placement=tier_card">
            Start Ember free
          </Link>
        </div>

        <div className="card plan">
          <div className="plan-top">
            <h3>Community</h3>
            <span className="tag">No bot required</span>
          </div>
          <div className="price">
            <b>${COMMUNITY_PLAN.priceMonthly}</b>
            <span>/ month</span>
          </div>
          <p className="muted">Market talk, briefings and education — without an automated agent.</p>
          <ul>
            <li>
              <Check />
              AI market briefings &amp; daily commentary
            </li>
            <li>
              <Check />
              Educational content and trade reviews
            </li>
            <li>
              <Check />
              Member discussions
            </li>
            <li>
              <Check />
              Included free with any agent
            </li>
          </ul>
          <Link className="btn btn-lg btn-block" href="/signup?bot=community&source=site&placement=tier_card">
            Join Community
          </Link>
        </div>
      </div>

      <div className="wrap" style={{ marginTop: 14 }}>
        <div className="band" style={{ padding: '18px 20px' }}>
          <div>
            <h3>Forge Community comes with every agent</h3>
            <p className="muted" style={{ fontSize: '.92rem' }}>
              AI market briefings, daily commentary, educational content, trade reviews and member discussions. No
              separate subscription.
            </p>
          </div>
        </div>
      </div>

      <section className="sec" style={{ marginTop: 44 }} id="faq">
        <div className="wrap split">
          <div>
            <h2>Questions</h2>
          </div>
          <div>
            {FAQ.map((item, i) => (
              <details key={item.q} open={i === 0}>
                <summary>{item.q}</summary>
                <p>{item.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>
    </MarketingShell>
  )
}
