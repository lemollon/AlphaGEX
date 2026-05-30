'use client'

import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import {
  stanceLabel,
  regimeLabel,
  fmtPct,
  windowText,
  dteText,
  type AdvisorPayload,
  type AdvisorSignal,
} from '@/lib/volatility'

const REFRESH = 60_000

const LABEL = 'text-[10px] text-forge-muted uppercase tracking-wider'
const CARD = 'rounded-xl border border-forge-border bg-forge-card/80 px-4 py-3'

function stanceAccent(stance?: string): string {
  switch (stance) {
    case 'lean_calls':
    case 'buy_the_bounce':
      return 'text-emerald-400'
    case 'lean_puts':
      return 'text-red-400'
    default:
      return 'text-violet-400'
  }
}

function fmtNum(x?: number | null): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—'
  return String(x)
}

function SignalRow({ name, sig }: { name: string; sig: AdvisorSignal }) {
  const dot = sig.active ? 'bg-emerald-400' : 'bg-forge-muted'
  return (
    <li className="flex items-center gap-2 py-1 text-sm">
      <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${dot}`} aria-hidden />
      <span className="text-white">{name}</span>
      {sig.confidence === 'low' && (
        <span className="rounded border border-forge-border px-1 text-[10px] uppercase tracking-wider text-forge-muted">
          low-conf
        </span>
      )}
      {sig.hit_rate !== null && sig.hit_rate !== undefined && (
        <span className="ml-auto font-mono text-forge-muted">
          {(sig.hit_rate * 100).toFixed(0)}% hit
        </span>
      )}
    </li>
  )
}

export default function VolatilityPage() {
  const { data, error, isLoading } = useSWR<AdvisorPayload>('/api/volatility', fetcher, {
    refreshInterval: REFRESH,
  })
  // Second feed for 3B (history charts). Fetched now so the proxy is exercised;
  // not rendered yet.
  useSWR('/api/volatility/history', fetcher, { refreshInterval: REFRESH })

  if (isLoading) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-8">
        <p className="text-sm text-forge-muted">Loading volatility regime…</p>
      </main>
    )
  }

  if (error || !data || (data as any).error) {
    const msg = (data as any)?.error || (error instanceof Error ? error.message : 'unavailable')
    return (
      <main className="mx-auto max-w-3xl px-4 py-8">
        <h1 className="text-lg font-semibold text-white">Volatility Regime</h1>
        <p className="mt-2 text-sm text-forge-muted">Advisor unavailable: {String(msg)}</p>
      </main>
    )
  }

  const report = data.report
  if (!report || report.ok === false) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-8">
        <h1 className="text-lg font-semibold text-white">Volatility Regime</h1>
        <p className="mt-2 text-sm text-forge-muted">
          Advisor returned no recommendation right now.
        </p>
      </main>
    )
  }

  const { inputs, recommendation, timing, signals } = report
  const win = windowText(timing)
  const dte = dteText(timing)

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      {/* Header */}
      <header className="mb-6">
        <h1 className="text-lg font-semibold text-white">Volatility Regime</h1>
        <p className="mt-1 font-mono text-xs text-forge-muted">
          VIX {fmtNum(inputs?.vix)} · VVIX {fmtNum(inputs?.vvix)}
          {report.as_of ? ` · ${report.as_of}` : ''}
        </p>
      </header>

      {/* Recommendation card */}
      <section className={`${CARD} mb-4`}>
        <div className="flex items-baseline justify-between gap-3">
          <div>
            <div className={LABEL}>Regime</div>
            <div className="mt-0.5 text-base font-semibold text-white">
              {regimeLabel(report.regime_label)}
            </div>
          </div>
          <div className="text-right">
            <div className={LABEL}>Stance</div>
            <div className={`mt-0.5 text-base font-semibold ${stanceAccent(recommendation?.stance)}`}>
              {stanceLabel(recommendation?.stance)}
              {recommendation?.conviction ? (
                <span className="ml-2 font-mono text-xs text-forge-muted">
                  {recommendation.conviction}
                </span>
              ) : null}
            </div>
          </div>
        </div>

        {recommendation?.rationale && (
          <p className="mt-3 text-sm text-white/90">{recommendation.rationale}</p>
        )}

        {(win || dte) && (
          <p className="mt-2 font-mono text-xs text-forge-muted">
            {win}
            {win && dte ? ' · ' : ''}
            {dte}
          </p>
        )}

        {timing?.structure_note && (
          <p className="mt-2 text-xs text-forge-muted">{timing.structure_note}</p>
        )}
      </section>

      {/* Signals */}
      <section className={CARD}>
        <div className={`${LABEL} mb-2`}>Signals</div>
        {signals && Object.keys(signals).length > 0 ? (
          <ul>
            {Object.entries(signals).map(([name, sig]) => (
              <SignalRow key={name} name={name} sig={sig} />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-forge-muted">No active signals.</p>
        )}
      </section>
    </main>
  )
}
