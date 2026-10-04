'use client'

import Image from 'next/image'
import Link from 'next/link'
import { useState } from 'react'
import MarketStatusBadge from './MarketStatusBadge'
import { AGENTS } from '@/lib/marketing/agents'

type Tab = 'spark' | 'flame'

/** Illustrative day-line paths — NOT trading results. Shape only differs per tab for visual variety. */
const PATHS: Record<Tab, { line: string; sell: string }> = {
  spark: {
    line: 'M10 150 C 90 110, 160 70, 230 90 S 360 150, 430 120 S 500 70, 510 60',
    sell: 'M10 110 H 510',
  },
  flame: {
    line: 'M10 140 C 100 120, 170 100, 240 105 S 350 130, 420 110 S 490 95, 510 90',
    sell: 'M10 105 H 510',
  },
}

const EXPLAIN = [
  { color: 'var(--up)', title: 'Above the sell line', body: 'The trade keeps the credit it collected up front.' },
  {
    color: 'var(--warn)',
    title: 'Between the lines',
    body: 'Part of the credit is given back, or a small loss.',
  },
  { color: 'var(--bad)', title: 'Below protection', body: "The loss stops growing. It's capped from the start." },
]

/** Hero card — "How a put spread works" tabs, home page only. */
export default function PutSpreadHeroCard() {
  const [tab, setTab] = useState<Tab>('spark')
  const path = PATHS[tab]
  const colorVar = tab === 'spark' ? 'var(--spark)' : 'var(--flame)'

  return (
    <div className="card" aria-label="How a trading day plays out">
      <div className="live-top">
        <span className="t">How a put spread works</span>
        <MarketStatusBadge />
      </div>
      <div className="hc-tabs" role="tablist" aria-label="Choose an agent">
        {(['spark', 'flame'] as Tab[]).map((t) => {
          const agent = AGENTS.find((a) => a.slug === t)!
          return (
            <button
              key={t}
              className="hc-tab"
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              type="button"
            >
              <Image src={agent.mascot} alt="" width={22} height={22} />
              {agent.name}
              <span className="hc-when"> · {t === 'spark' ? 'morning' : 'afternoon'}</span>
            </button>
          )
        })}
      </div>
      <div className="hc-wrap">
        <svg
          id="dayChart"
          viewBox="0 0 520 250"
          role="img"
          aria-label="Illustration of a put spread: the market line stays above the sell line during the agent's session, so the trade keeps its credit. Losses are capped at the protection line."
        >
          <rect x={0} y={0} width={520} height={100} fill="var(--up-soft)" opacity={0.5} />
          <rect x={0} y={100} width={520} height={50} fill="var(--accent-soft)" opacity={0.5} />
          <rect x={0} y={150} width={520} height={100} fill="var(--bg-2)" />
          <path d={path.sell} fill="none" stroke="var(--line-2)" strokeWidth={1.5} strokeDasharray="4 4" />
          <path d={path.line} fill="none" stroke={colorVar} strokeWidth={2.5} strokeLinecap="round" />
        </svg>
      </div>
      <div className="hc-explain">
        {EXPLAIN.map((e) => (
          <div key={e.title}>
            <b>
              <i style={{ background: e.color }} />
              {e.title}
            </b>
            {e.body}
          </div>
        ))}
      </div>
      <div className="hc-agents">
        {AGENTS.map((agent) => (
          <Link key={agent.slug} className="hc-agent" href={`/agents#${agent.slug}`}>
            <Image src={agent.mascot} alt="" width={34} height={34} />
            <div>
              <b>{agent.name}</b>
              <div className="state">
                {agent.slug === 'ember' ? <span className="muted">Smaller accounts</span> : agent.tagline}
              </div>
            </div>
          </Link>
        ))}
      </div>
      <p className="hc-cap">Simplified illustration of a put spread at the end of a session. Not trading results.</p>
    </div>
  )
}
