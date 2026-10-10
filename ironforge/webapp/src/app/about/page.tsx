import type { Metadata } from 'next'
import MarketingShell from '@/components/marketing/MarketingShell'

export const metadata: Metadata = {
  title: 'About — IronForge',
  description:
    'Markets are loud. Hype, predictions and emotion push people into trades they regret. We wanted something quieter: clear rules, defined risk and steady execution.',
}

const TEAM = [
  { title: 'Strategy', body: 'Years leading large operational and business transformation work.' },
  { title: 'Data & modeling', body: 'Analytics, forecasting and decision design.' },
  { title: 'AI & automation', body: 'Workflow automation and dependable tooling.' },
  { title: 'Trading', body: 'Market structure, options and execution discipline.' },
]

const VALUES = ['Discipline', 'Patience', 'Stewardship', 'Humility', 'Continuous refinement']

export default function AboutPage() {
  return (
    <MarketingShell>
      <div className="wrap page-head">
        <h1>About IronForge</h1>
        <p>
          Markets are loud. Hype, predictions and emotion push people into trades they regret. We wanted something
          quieter: clear rules, defined risk and steady execution.
        </p>
      </div>

      <section className="sec" id="team">
        <div className="wrap">
          <div className="sec-head">
            <div>
              <h2>Built by people who build systems</h2>
            </div>
          </div>
          <div className="feats">
            {TEAM.map((t) => (
              <div className="card feat" key={t.title}>
                <b>{t.title}</b>
                <p>{t.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="sec" id="values">
        <div className="wrap split">
          <div>
            <h2>Grounded in faith. Focused on discipline.</h2>
            <p className="muted" style={{ marginTop: 10, maxWidth: '52ch' }}>
              The forge is our symbol: pressure, heat and patience turning raw material into something strong. These
              values sit behind every rule we write.
            </p>
          </div>
          <div className="values">
            {VALUES.map((v) => (
              <span key={v}>{v}</span>
            ))}
          </div>
        </div>
      </section>
    </MarketingShell>
  )
}
