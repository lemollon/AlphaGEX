import type { Metadata } from 'next'
import Image from 'next/image'
import MarketingShell from '@/components/marketing/MarketingShell'
import AgentCard from '@/components/marketing/AgentCard'
import { AGENTS, AGENT_COMPARE_ROWS, getAgent } from '@/lib/marketing/agents'

export const metadata: Metadata = {
  title: 'Agents — IronForge',
  description:
    'Spark and Flame split the trading day. Ember is built for smaller accounts that are just getting started.',
}

const GUARDRAILS = [
  { icon: 'i-steps', title: 'Ladder sizing', body: "Trade size follows your account's best level, never your losses." },
  { icon: 'i-drop', title: 'Liquidity guard', body: 'No order takes more than 25% of the visible bid.' },
  { icon: 'i-pause', title: 'Pause anytime', body: 'Turn automation off from the app in one tap.' },
  { icon: 'i-eye', title: 'Full history', body: 'Every entry, exit and result on the record.' },
]

export default function AgentsPage() {
  const spark = getAgent('spark')
  const flame = getAgent('flame')
  const ember = getAgent('ember')

  return (
    <MarketingShell>
      <div className="wrap page-head">
        <h1>Agents</h1>
        <p>Spark and Flame split the trading day. Ember is built for smaller accounts that are just getting started.</p>
      </div>

      <div className="wrap">
        <div className="agents">
          {AGENTS.map((agent) => (
            <AgentCard key={agent.slug} agent={agent} placement="agent_card" />
          ))}
        </div>
      </div>

      <section className="sec" style={{ marginTop: 44 }} id="compare">
        <div className="wrap">
          <div className="sec-head">
            <div>
              <h2>Side by side</h2>
            </div>
          </div>
          <div className="tbl-wrap">
            <table>
              <thead>
                <tr>
                  <th />
                  <th>
                    <span className="th-agent">
                      <Image src={spark.mascot} alt="" width={30} height={30} />
                      Spark
                    </span>
                  </th>
                  <th>
                    <span className="th-agent">
                      <Image src={flame.mascot} alt="" width={30} height={30} />
                      Flame
                    </span>
                  </th>
                  <th>
                    <span className="th-agent">
                      <Image src={ember.mascot} alt="" width={30} height={30} />
                      Ember
                    </span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {AGENT_COMPARE_ROWS.map((row) => (
                  <tr key={row.label}>
                    <td>{row.label}</td>
                    <td>{row.label === 'Price' ? <b>{row.spark}</b> : row.spark}</td>
                    <td>{row.label === 'Price' ? <b>{row.flame}</b> : row.flame}</td>
                    <td>
                      {row.label === 'Price' ? <b style={{ color: 'var(--up)' }}>{row.ember}</b> : row.ember}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="sec" id="guardrails">
        <div className="wrap">
          <div className="sec-head">
            <div>
              <h2>Guardrails on every agent</h2>
            </div>
          </div>
          <div className="feats">
            {GUARDRAILS.map((g) => (
              <div className="card feat" key={g.title}>
                <svg>
                  <use href={`#${g.icon}`} />
                </svg>
                <b>{g.title}</b>
                <p>{g.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </MarketingShell>
  )
}
