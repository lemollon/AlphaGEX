'use client'

import { signalDisplayName, type AdvisorSignal } from '@/lib/volatility'

const LABEL = 'text-[10px] text-forge-muted uppercase tracking-wider'

function SignalRow({ keyName, sig }: { keyName: string; sig: AdvisorSignal }) {
  const dot = sig.active ? 'bg-emerald-400' : 'bg-forge-muted'
  return (
    <li className="flex items-center gap-2 border-t border-forge-border/60 py-2 text-sm first:border-t-0">
      <span
        className={`inline-block h-2 w-2 shrink-0 rounded-full ${dot}`}
        aria-hidden
      />
      <span className={sig.active ? 'text-white' : 'text-forge-muted'}>
        {signalDisplayName(keyName)}
      </span>
      {sig.confidence === 'low' && (
        <span className="rounded border border-amber-500/40 px-1 text-[10px] uppercase tracking-wider text-amber-500">
          low-conf
        </span>
      )}
      <span className="ml-auto font-mono text-forge-muted">
        {sig.hit_rate !== null && sig.hit_rate !== undefined
          ? `${Math.round(sig.hit_rate * 100)}% hit`
          : '—'}
      </span>
    </li>
  )
}

export default function SignalsPanel({
  signals,
}: {
  signals?: Record<string, AdvisorSignal>
}) {
  const entries = signals ? Object.entries(signals) : []
  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <div className={`${LABEL} mb-2`}>Signals</div>
      {entries.length > 0 ? (
        <ul>
          {entries.map(([name, sig]) => (
            <SignalRow key={name} keyName={name} sig={sig} />
          ))}
        </ul>
      ) : (
        <p className="text-sm text-forge-muted">No signals.</p>
      )}
    </section>
  )
}
