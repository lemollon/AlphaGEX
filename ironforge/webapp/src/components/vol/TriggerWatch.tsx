'use client'

import {
  signalDisplayName,
  triggerGroups,
  type AdvisorSignal,
  type SignalEntry,
} from '@/lib/volatility'
import { ProximityBar } from './SignalsPanel'

const LABEL = 'text-[10px] text-forge-muted uppercase tracking-wider'

function TriggerRow({ entry }: { entry: SignalEntry }) {
  const sig = entry.signal
  return (
    <div className="rounded-lg border border-forge-border bg-forge-bg/40 px-3 py-2">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-white">{signalDisplayName(entry.key)}</span>
        {sig.active && (
          <span className="rounded border border-emerald-500/40 px-1 text-[10px] uppercase tracking-wider text-emerald-400">
            active
          </span>
        )}
      </div>
      <div className="mt-1 font-mono text-[11px] text-forge-muted">
        <span className="text-white/80">{sig.current_text || '—'}</span>
        <span className="px-1 text-forge-muted">→</span>
        <span className="text-white/80">{sig.trigger_text || '—'}</span>
      </div>
      <ProximityBar sig={sig} />
    </div>
  )
}

function Column({
  title,
  accent,
  entries,
}: {
  title: string
  accent: string
  entries: SignalEntry[]
}) {
  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <div className={`${LABEL} mb-3 ${accent}`}>{title}</div>
      {entries.length > 0 ? (
        <div className="space-y-2">
          {entries.map((e) => (
            <TriggerRow key={e.key} entry={e} />
          ))}
        </div>
      ) : (
        <p className="text-xs text-forge-muted">Nothing watching here.</p>
      )}
    </div>
  )
}

/**
 * "What would flip it" — groups signals by direction into Bullish and Bearish
 * columns, each showing the live reading → firing condition and how close it is.
 * Makes calm days actionable by spelling out exactly what to watch.
 */
export default function TriggerWatch({
  signals,
}: {
  signals?: Record<string, AdvisorSignal>
}) {
  const groups = triggerGroups(signals)
  if (groups.bullish.length === 0 && groups.bearish.length === 0) return null

  return (
    <section>
      <div className={`${LABEL} mb-2`}>What would flip it</div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Column title="Bullish triggers" accent="text-emerald-400" entries={groups.bullish} />
        <Column title="Bearish triggers" accent="text-red-400" entries={groups.bearish} />
      </div>
    </section>
  )
}
