import Image from 'next/image'
import Link from 'next/link'
import type { MarketingAgent } from '@/lib/marketing/agents'

/**
 * One agent card — home page grid and the /agents page. Mirrors the design's
 * `<template id="agentTpl">` (card > agent-top > desc > rows > actions).
 */
export default function AgentCard({ agent, placement }: { agent: MarketingAgent; placement: 'agent_card' | 'home' }) {
  return (
    <article className={`card agent ${agent.slug}`} id={agent.slug}>
      <div className="agent-top">
        <Image className="av lg" src={agent.mascot} alt="" width={56} height={56} />
        <div>
          <h3 className="agent-name">{agent.name}</h3>
          <small className="tag-line">{agent.tagline}</small>
        </div>
        <div className={`price-chip${agent.isFree ? ' free' : ''}`}>
          <b>{agent.price}</b>
          <small>{agent.per}</small>
        </div>
      </div>
      <p className="desc">{agent.desc}</p>
      <dl className="rows">
        {agent.rows.map((row) => (
          <div key={row.label}>
            <dt>{row.label}</dt>
            <dd>
              {row.value}
              {row.riskLevel != null && (
                <span className="meter" aria-hidden="true">
                  {[1, 2, 3].map((i) => (
                    <i key={i} className={i <= row.riskLevel! ? 'on' : ''} />
                  ))}
                </span>
              )}
            </dd>
          </div>
        ))}
      </dl>
      <span className="limit">
        <b>{agent.note}</b>
        {agent.communityIncluded && ' Community included.'}
      </span>
      <div className="agent-actions">
        <Link className="pick" href={`/signup?bot=${agent.planParam}&source=site&placement=${placement}`}>
          {agent.isFree ? `Start ${agent.name} free` : `Choose ${agent.name}`}
        </Link>
        <Link className="pick alt" href={`/agents#${agent.slug}`}>
          Details
        </Link>
      </div>
    </article>
  )
}
