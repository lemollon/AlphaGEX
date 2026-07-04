'use client'

import type { CustomerState } from '@/lib/live/types'

const STEPS = [
  { n: 1, label: 'Trade Opened' },
  { n: 2, label: 'Monitoring Position' },
  { n: 3, label: 'Profit Target or Stop Loss' },
  { n: 4, label: 'Trade Closes Automatically' },
]

function explainer(state: CustomerState | null): string {
  if (!state) return ''
  switch (state.key) {
    case 'TRADE_ACTIVE':
      return 'Spark is opening a position designed with a defined risk limit.'
    case 'MONITORING_POSITION':
      return 'Spark is monitoring your position and will manage it according to your risk rules.'
    case 'TRADE_COMPLETE':
      return "Today's trade finished and closed automatically. Spark starts fresh at the next market open."
    case 'BLOCKED':
      return 'No trade today — the conditions did not meet your protection standards.'
    case 'PAUSED':
      return 'New trades are paused. Any open position keeps following your risk rules.'
    case 'ACTION_REQUIRED':
      return 'Spark is checking its connection. Any open position keeps following your risk rules.'
    default:
      return 'When Spark finds the right setup, the trade moves through these steps automatically.'
  }
}

export default function NowTimelineCard({ state }: { state: CustomerState | null }) {
  const step = state?.timeline_step ?? null
  const complete = state?.key === 'TRADE_COMPLETE'

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-spark">
        What is happening right now?
      </h3>
      <div className="mt-6 flex items-start">
        {STEPS.map((s, i) => {
          const done = step != null && (complete ? s.n <= 4 : s.n < step)
          const current = !complete && step != null && s.n === step
          return (
            <div key={s.n} className="flex flex-1 flex-col items-center">
              <div className="flex w-full items-center">
                <div className={`h-0.5 flex-1 ${i === 0 ? 'bg-transparent' : done || current ? 'bg-spark/60' : 'bg-forge-border'}`} />
                <div
                  className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
                    done
                      ? 'bg-spark/80'
                      : current
                        ? 'animate-pulse bg-spark ring-4 ring-spark/25'
                        : 'border-2 border-forge-border bg-forge-card'
                  }`}
                >
                  {done && (
                    <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3"
                      strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
                      <path d="m5 13 4 4L19 7" />
                    </svg>
                  )}
                  {current && <div className="h-2.5 w-2.5 rounded-full bg-white" />}
                </div>
                <div className={`h-0.5 flex-1 ${i === STEPS.length - 1 ? 'bg-transparent' : done ? 'bg-spark/60' : 'bg-forge-border'}`} />
              </div>
              <div className={`mt-2.5 px-1 text-center text-xs leading-tight ${current ? 'font-medium text-white' : done ? 'text-gray-300' : 'text-gray-500'}`}>
                {s.label}
              </div>
              {current && <div className="mt-1 text-xs font-medium text-spark">Live</div>}
            </div>
          )
        })}
      </div>
      <p className="mt-5 text-center text-sm text-gray-400">{explainer(state)}</p>
    </section>
  )
}
