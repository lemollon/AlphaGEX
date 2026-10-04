'use client'

import Image from 'next/image'
import Link from 'next/link'
import { useState } from 'react'
import AgentCard from './AgentCard'
import AppStoreBadges from './AppStoreBadges'
import PutSpreadHeroCard from './PutSpreadHeroCard'
import { AGENTS, type MarketingAgent } from '@/lib/marketing/agents'

type Filter = 'all' | 'morning' | 'afternoon' | 'small' | 'new' | 'calm'

const CHIPS: Array<{ id: Filter; label: string; dot?: string }> = [
  { id: 'all', label: 'All agents' },
  { id: 'morning', label: 'Morning', dot: 'var(--spark)' },
  { id: 'afternoon', label: 'Afternoon', dot: 'var(--flame)' },
  { id: 'small', label: 'Smaller accounts', dot: 'var(--ember)' },
  { id: 'new', label: 'New to investing' },
  { id: 'calm', label: 'Calmer ride' },
]

function matches(agent: MarketingAgent, filter: Filter): boolean {
  return filter === 'all' || agent.tags.includes(filter as MarketingAgent['tags'][number])
}

const STEPS = [
  {
    n: '01',
    title: 'Connect your brokerage',
    body: "Start with our partner Tradier or connect another supported brokerage. Your money stays there, and you can disconnect anytime.",
    href: '/how-it-works#brokerage',
  },
  {
    n: '02',
    title: 'Choose an agent',
    body: 'Spark, Flame or Ember, depending on your schedule, account size and comfort with risk.',
    href: '/agents#compare',
  },
  {
    n: '03',
    title: 'Follow along',
    body: 'Every trade, its size and result appear in your dashboard and the IronForge app for iPhone and Android.',
    href: '/#app',
  },
]

/**
 * The full interactive body of the home page: chip bar, hero, stats, steps,
 * agents grid, app band, FAQ and closing CTA — one client component so the
 * filter chips (above the hero) and the agent grid they drive (below the
 * hero and stat strip) can share state exactly like the source design.
 */
export default function HomePageBody() {
  const [filter, setFilter] = useState<Filter>('all')
  const visible = AGENTS.filter((a) => matches(a, filter))

  return (
    <>
      <div className="chips" role="group" aria-label="Filter agents">
        <div className="chips-in">
          {CHIPS.map((chip) => (
            <button
              key={chip.id}
              className="chip"
              aria-pressed={filter === chip.id}
              onClick={() => setFilter(chip.id)}
              type="button"
            >
              {chip.dot && <span className="dot" style={{ background: chip.dot }} />}
              {chip.label}
            </button>
          ))}
        </div>
      </div>

      <div className="wrap hero">
        <div>
          <h1>Automated options trading, run by rules.</h1>
          <p className="sub">
            Pick an agent. It trades in your own brokerage account by the same written rules every day, and you
            follow along from the app.
          </p>
          <div className="hero-actions">
            <Link className="btn btn-accent btn-lg" href="/signup?source=site&placement=hero">
              Create account
            </Link>
            <Link className="btn btn-lg" href="/waitlist">
              Join the waitlist
            </Link>
          </div>
          <div className="ticks">
            <span>
              <svg>
                <use href="#i-check" />
              </svg>
              5 trading days free
            </span>
            <span>
              <svg>
                <use href="#i-check" />
              </svg>
              Cancel anytime
            </span>
            <span>
              <svg>
                <use href="#i-check" />
              </svg>
              Funds stay in your account
            </span>
          </div>
          <div style={{ marginTop: 26 }}>
            <AppStoreBadges />
          </div>
        </div>
        <PutSpreadHeroCard />
      </div>

      <section className="sec" id="home-agents" style={{ paddingBlock: 0 }}>
        <div className="wrap stats">
          <Link className="stat" href="/how-it-works#ladder">
            <small>Live trading since</small>
            <b>Sep 8, 2026</b>
          </Link>
          <Link className="stat" href="/how-it-works#brokerage">
            <small>Brokerage partner</small>
            <b>Tradier + more</b>
          </Link>
          <Link className="stat" href="/#app">
            <small>Mobile app</small>
            <b>iOS &amp; Android</b>
          </Link>
          <Link className="stat" href="/how-it-works#ladder">
            <small>Max share of visible bid</small>
            <b className="num">25%</b>
          </Link>
        </div>
      </section>

      <section className="sec" id="home-how">
        <div className="wrap">
          <div className="sec-head">
            <div>
              <h2>How it works</h2>
              <p>Three steps. After that, the rules do the work.</p>
            </div>
            <Link className="link" href="/how-it-works#day">
              Learn more →
            </Link>
          </div>
          <div className="steps">
            {STEPS.map((s) => (
              <Link key={s.n} className="card step" href={s.href}>
                <span className="n">{s.n}</span>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="sec" id="home-agents-grid">
        <div className="wrap">
          <div className="sec-head">
            <div>
              <h2>Agents</h2>
              <p>Each agent follows its own rules, sized by the Ladder.</p>
            </div>
            <Link className="link" href="/agents#compare">
              Compare all →
            </Link>
          </div>
          <div className="agents">
            {visible.length === 0 ? (
              <p className="empty">No agents match that filter.</p>
            ) : (
              visible.map((agent) => <AgentCard key={agent.slug} agent={agent} placement="home" />)
            )}
          </div>
        </div>
      </section>

      <section className="sec" id="app">
        <div className="wrap app-band">
          <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
            <div className="band-avs">
              {AGENTS.map((a) => (
                <Image key={a.slug} src={a.mascot} alt="" width={46} height={46} />
              ))}
            </div>
            <div>
              <h2 style={{ fontSize: '1.4rem' }}>Get the IronForge app</h2>
              <p className="muted">Check trades, results and your agent&apos;s status from your phone.</p>
            </div>
          </div>
          <AppStoreBadges />
        </div>
      </section>

      <section className="sec" id="home-faq">
        <div className="wrap split">
          <div>
            <h2>Questions</h2>
            <p className="muted" style={{ marginTop: 6 }}>
              More answers in the{' '}
              <Link className="link" href="/pricing#faq">
                pricing FAQ
              </Link>
              .
            </p>
          </div>
          <div>
            <details>
              <summary>Do I need to know how options work?</summary>
              <p>
                No. The agents handle entries, exits and sizing. Forge Community, included with every agent, is there
                if you&apos;d like to learn along the way.
              </p>
            </details>
            <details>
              <summary>Where is my money held?</summary>
              <p>
                In your own brokerage account, connected through Tradier or another supported brokerage. IronForge
                sends trade instructions and can&apos;t withdraw funds.
              </p>
            </details>
            <details>
              <summary>Can I lose money?</summary>
              <p>
                Yes. Options trading carries real risk, including loss of the money you invest. The rules control
                sizing; they don&apos;t remove risk.
              </p>
            </details>
          </div>
        </div>
      </section>

      <section className="sec" id="home-join">
        <div className="wrap band">
          <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
            <div className="band-avs">
              {AGENTS.map((a) => (
                <Image key={a.slug} src={a.mascot} alt="" width={46} height={46} />
              ))}
            </div>
            <div>
              <h3 style={{ fontSize: '1.2rem' }}>Ready to start?</h3>
              <p className="muted">Create your account now, or join the waitlist for the next onboarding wave.</p>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Link className="btn btn-lg" href="/waitlist">
              Join the waitlist
            </Link>
            <Link className="btn btn-accent btn-lg" href="/signup?source=site&placement=final_cta">
              Create account
            </Link>
          </div>
        </div>
      </section>
    </>
  )
}
