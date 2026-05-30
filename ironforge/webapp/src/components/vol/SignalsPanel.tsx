'use client'

import {
  signalDisplayName,
  directionClass,
  proximityPct,
  sortedSignalEntries,
  type AdvisorSignal,
  type SignalDirection,
} from '@/lib/volatility'

const LABEL = 'text-[10px] text-forge-muted uppercase tracking-wider'

function directionLabel(direction?: SignalDirection): string {
  switch (direction) {
    case 'bullish':
      return 'Bullish'
    case 'bearish':
      return 'Bearish'
    case 'neutral':
      return 'Neutral'
    default:
      return ''
  }
}

/** A 0–100% proximity bar. Active → full + emerald; armed → blue at width. */
export function ProximityBar({ sig }: { sig: AdvisorSignal }) {
  const pct = proximityPct(sig)
  const fill = sig.active ? 'bg-emerald-500' : 'bg-blue-500/60'
  return (
    <div className="mt-2">
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-forge-border">
        <div className={`h-full rounded-full ${fill}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1 font-mono text-[10px] text-forge-muted">
        {sig.active ? 'firing now' : `≈${pct}% to trigger`}
      </div>
    </div>
  )
}

function SignalCard({ keyName, sig }: { keyName: string; sig: AdvisorSignal }) {
  const dirClass = directionClass(sig.direction)
  const dirLabel = directionLabel(sig.direction)
  const stateLabel = sig.active ? 'Active' : 'Armed'
  const stateClass = sig.active
    ? 'border-emerald-500/40 text-emerald-400'
    : 'border-forge-border text-forge-muted'

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-white">{signalDisplayName(keyName)}</span>
        <span
          className={`rounded border px-1.5 py-px text-[10px] uppercase tracking-wider ${stateClass}`}
        >
          {stateLabel}
        </span>
        {dirLabel && (
          <span className={`text-[10px] uppercase tracking-wider ${dirClass}`}>{dirLabel}</span>
        )}
        {sig.confidence === 'low' && (
          <span className="rounded border border-amber-500/40 px-1 text-[10px] uppercase tracking-wider text-amber-500">
            low-conf
          </span>
        )}
        <span className="ml-auto font-mono text-[11px] text-forge-muted">
          {sig.hit_rate !== null && sig.hit_rate !== undefined
            ? `${Math.round(sig.hit_rate * 100)}% historical hit`
            : '—'}
        </span>
      </div>

      {sig.blurb && <p className="mt-2 text-xs leading-relaxed text-white/80">{sig.blurb}</p>}

      {(sig.current_text || sig.trigger_text) && (
        <div className="mt-2 grid grid-cols-2 gap-2">
          <div className="rounded-lg border border-forge-border bg-forge-bg/40 px-2.5 py-1.5">
            <div className={LABEL}>Now</div>
            <div className="mt-0.5 font-mono text-xs text-white">{sig.current_text || '—'}</div>
          </div>
          <div className="rounded-lg border border-forge-border bg-forge-bg/40 px-2.5 py-1.5">
            <div className={LABEL}>Triggers when</div>
            <div className="mt-0.5 font-mono text-xs text-white">{sig.trigger_text || '—'}</div>
          </div>
        </div>
      )}

      <ProximityBar sig={sig} />
    </div>
  )
}

export default function SignalsPanel({
  signals,
}: {
  signals?: Record<string, AdvisorSignal>
}) {
  const entries = sortedSignalEntries(signals)
  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <div className={`${LABEL} mb-3`}>Signals</div>
      {entries.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {entries.map(({ key, signal }) => (
            <SignalCard key={key} keyName={key} sig={signal} />
          ))}
        </div>
      ) : (
        <p className="text-sm text-forge-muted">No signals.</p>
      )}
    </section>
  )
}
