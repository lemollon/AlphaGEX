'use client'

import { fmtPct, hitRateText, type AdvisorOutlook } from '@/lib/volatility'

const LABEL = 'text-[10px] text-forge-muted uppercase tracking-wider'

function ratioPct(x?: number | null): string {
  if (x === null || x === undefined || Number.isNaN(x)) return '—'
  return fmtPct(x * 100)
}

function pnlClass(x?: number | null): string {
  if (x === null || x === undefined || Number.isNaN(x) || x === 0) return 'text-white'
  return x > 0 ? 'text-emerald-400' : 'text-red-400'
}

/**
 * Always-present plain-English regime read (`summary`) plus, when an outlook
 * sample exists, a compact expected-move / hit-rate stat row. Leads the page
 * so even calm/neutral days surface a useful interpretation.
 */
export default function OutlookCard({
  summary,
  outlook,
}: {
  summary?: string
  outlook?: AdvisorOutlook
}) {
  const hasSample =
    outlook?.sample_n !== null && outlook?.sample_n !== undefined && outlook.sample_n > 0

  if (!summary && !hasSample) return null

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-5">
      <div className={LABEL}>Regime read</div>
      {summary ? (
        <p className="mt-2 text-sm leading-relaxed text-white/90">{summary}</p>
      ) : (
        <p className="mt-2 text-sm text-forge-muted">No regime summary available.</p>
      )}

      {hasSample && (
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-lg border border-forge-border bg-forge-bg/40 px-3 py-2">
            <div className={LABEL}>Exp. SPY 5d</div>
            <div className={`mt-1 font-mono text-sm ${pnlClass(outlook?.fwd_spy_5_ratio)}`}>
              {ratioPct(outlook?.fwd_spy_5_ratio)}
            </div>
          </div>
          <div className="rounded-lg border border-forge-border bg-forge-bg/40 px-3 py-2">
            <div className={LABEL}>Exp. VIX 5d</div>
            <div className={`mt-1 font-mono text-sm ${pnlClass(outlook?.fwd_vix_5_ratio)}`}>
              {ratioPct(outlook?.fwd_vix_5_ratio)}
            </div>
          </div>
          <div className="rounded-lg border border-forge-border bg-forge-bg/40 px-3 py-2">
            <div className={LABEL}>Hit rate</div>
            <div className="mt-1 font-mono text-sm text-white">{hitRateText(outlook?.hit_rate)}</div>
          </div>
          <div className="rounded-lg border border-forge-border bg-forge-bg/40 px-3 py-2">
            <div className={LABEL}>Sample N</div>
            <div className="mt-1 font-mono text-sm text-white">{outlook?.sample_n ?? '—'}</div>
          </div>
        </div>
      )}
    </section>
  )
}
