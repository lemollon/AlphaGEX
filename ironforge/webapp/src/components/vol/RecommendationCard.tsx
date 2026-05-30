'use client'

import {
  stanceLabel,
  windowText,
  dteText,
  type AdvisorRecommendation,
  type AdvisorTiming,
} from '@/lib/volatility'

const LABEL = 'text-[10px] text-forge-muted uppercase tracking-wider'

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

export default function RecommendationCard({
  recommendation,
  timing,
}: {
  recommendation?: AdvisorRecommendation
  timing?: AdvisorTiming
}) {
  const win = windowText(timing)
  const dte = dteText(timing)
  const hasDte =
    timing?.suggested_dte !== null &&
    timing?.suggested_dte !== undefined &&
    !Number.isNaN(timing.suggested_dte)

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-5">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <div className={LABEL}>Stance</div>
          <div
            className={`mt-1 text-2xl font-semibold ${stanceAccent(recommendation?.stance)}`}
          >
            {stanceLabel(recommendation?.stance)}
          </div>
        </div>
        {recommendation?.conviction && (
          <div className="text-right">
            <div className={LABEL}>Conviction</div>
            <div className="mt-1 font-mono text-sm text-white">
              {recommendation.conviction}
            </div>
          </div>
        )}
      </div>

      {recommendation?.rationale && (
        <p className="mt-3 text-sm leading-relaxed text-white/90">
          {recommendation.rationale}
        </p>
      )}

      {hasDte && (
        <div className="mt-4 grid grid-cols-2 gap-3">
          <div className="rounded-lg border border-forge-border bg-forge-bg/40 px-3 py-2">
            <div className={LABEL}>Expected window</div>
            <div className="mt-1 font-mono text-sm text-white">{win || '—'}</div>
          </div>
          <div className="rounded-lg border border-forge-border bg-forge-bg/40 px-3 py-2">
            <div className={LABEL}>Target expiration</div>
            <div className="mt-1 font-mono text-sm text-white">{dte || '—'}</div>
          </div>
        </div>
      )}

      {timing?.structure_note && (
        <p className="mt-3 text-xs text-forge-muted">{timing.structure_note}</p>
      )}
    </section>
  )
}
