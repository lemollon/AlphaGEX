import type { Metadata } from 'next'
import MarketingShell from '@/components/marketing/MarketingShell'
import DayTimeline from '@/components/marketing/DayTimeline'
import LadderChart from '@/components/marketing/LadderChart'

export const metadata: Metadata = {
  title: 'How it works — IronForge',
  description: "The same five-part routine runs every trading day. Here's where today stands.",
}

const GETTING_STARTED = [
  { n: '01', title: 'Create your account', body: 'Sign up and review the agreements.' },
  { n: '02', title: 'Choose your agent', body: 'Spark, Flame or Ember.' },
  { n: '03', title: 'Connect a brokerage', body: 'Tradier is recommended. Already have an account? Link it.' },
  {
    n: '04',
    title: 'Try 5 trading days free',
    body: 'Spark and Flame start with a free trial. Ember is always free.',
  },
]

const CONTROL = [
  { icon: 'i-lock', title: 'No withdrawals', body: 'IronForge places trades. It can never move money out.' },
  { icon: 'i-shield', title: 'Secure connection', body: 'OAuth sign-in with encrypted sessions.' },
  { icon: 'i-pause', title: 'Kill switch', body: 'Stop all automation instantly.' },
  { icon: 'i-link', title: 'Revoke anytime', body: 'Disconnect your brokerage whenever you choose.' },
]

const RULES = [
  {
    title: 'Steps follow your best level',
    body: "Size is tied to the highest value your account has reached, rounded down to the nearest step.",
  },
  {
    title: 'No making it up after a dip',
    body: 'A down stretch never triggers bigger trades. Size only climbs after a new high.',
  },
  { title: 'Fair fills only', body: 'No order takes more than 25% of the visible bid.' },
]

export default function HowItWorksPage() {
  return (
    <MarketingShell>
      <div className="wrap page-head">
        <h1>How it works</h1>
        <p>The same five-part routine runs every trading day. Here&apos;s where today stands.</p>
      </div>

      <DayTimeline />
      <p className="wrap fine">Times show the shape of the routine. Exact timing varies by agent.</p>

      <section className="sec" style={{ marginTop: 40 }} id="ladder">
        <div className="wrap split">
          <div>
            <h2>The Ladder</h2>
            <p className="muted" style={{ margin: '8px 0 18px' }}>
              How each agent decides trade size, in three plain rules.
            </p>
            <div className="rule-list">
              {RULES.map((r) => (
                <div key={r.title}>
                  <b>{r.title}</b>
                  <p>{r.body}</p>
                </div>
              ))}
            </div>
          </div>
          <LadderChart />
        </div>
      </section>

      <section className="sec" id="brokerage">
        <div className="wrap">
          <div className="sec-head">
            <div>
              <h2>Connect your brokerage</h2>
              <p>Tradier is our official partner, and IronForge is built to connect with other brokerages too.</p>
            </div>
          </div>
          <div
            className="feats"
            style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))', marginBottom: 28 }}
          >
            <div className="card feat">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                <svg viewBox="0 0 134 44" height={26} role="img" aria-label="Tradier" style={{ color: 'var(--fg)' }}>
                  <text
                    x={0}
                    y={39}
                    fontFamily="Geist,Arial,sans-serif"
                    fontWeight={700}
                    fontSize={33}
                    letterSpacing={-1.4}
                    fill="currentColor"
                  >
                    tradier
                  </text>
                  <polygon points="106,2 133,2 128.5,8.5 101.5,8.5" fill="#e8344e" />
                  <polygon points="127,2 133,2 133,27 127,21" fill="#2a7de1" />
                  <line x1={104} y1={26} x2={124} y2={7} stroke="#f5b921" strokeWidth={6.5} />
                </svg>
                <span className="tag">Official partner</span>
              </div>
              <b>Tradier</b>
              <p>
                Our recommended brokerage, with real-time execution built in. Don&apos;t have an account? You can
                open one during setup.
              </p>
            </div>
            <div className="card feat">
              <span className="tag" style={{ justifySelf: 'start', background: 'var(--bg-2)', color: 'var(--muted)' }}>
                Expanding
              </span>
              <b>Other brokerages</b>
              <p>We&apos;re adding connections to more brokerages. Join the waitlist to hear when yours is supported.</p>
            </div>
          </div>
          <div className="sec-head" id="path">
            <div>
              <h2 style={{ fontSize: '1.3rem' }}>Getting started</h2>
              <p>Set up in minutes. Your first 5 trading days are free.</p>
            </div>
          </div>
          <div className="feats">
            {GETTING_STARTED.map((s) => (
              <div className="card feat" key={s.n}>
                <span className="num" style={{ color: 'var(--accent)', fontSize: '.8rem' }}>
                  {s.n}
                </span>
                <b>{s.title}</b>
                <p>{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="sec" id="control">
        <div className="wrap">
          <div className="sec-head">
            <div>
              <h2>You stay in control</h2>
            </div>
          </div>
          <div className="feats">
            {CONTROL.map((c) => (
              <div className="card feat" key={c.title}>
                <svg>
                  <use href={`#${c.icon}`} />
                </svg>
                <b>{c.title}</b>
                <p>{c.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </MarketingShell>
  )
}
