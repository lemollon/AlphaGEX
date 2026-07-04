'use client'

import type { LiveSummary } from '@/lib/live/types'

const CONDITION_STYLE = {
  good: { label: 'Good', text: 'text-emerald-400' },
  caution: { label: 'Caution', text: 'text-yellow-400' },
  no_trading: { label: 'No Trading Today', text: 'text-gray-300' },
} as const

function formatCTStamp(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (isNaN(d.getTime())) return null
  return d.toLocaleString('en-US', {
    timeZone: 'America/Chicago', weekday: 'short', hour: 'numeric', minute: '2-digit',
  })
}

function Metric({
  label, value, sub, subClass,
}: {
  label: string
  value: string
  sub: string | null
  subClass?: string
}) {
  return (
    <div className="border-l border-forge-border pl-4 first:border-l-0 first:pl-0 sm:border-l sm:pl-4">
      <div className="text-xs uppercase tracking-wider text-gray-500">{label}</div>
      <div className="mt-1 font-mono text-xl font-semibold text-white">{value}</div>
      {sub && <div className={`mt-0.5 text-xs ${subClass ?? 'text-gray-500'}`}>{sub}</div>}
    </div>
  )
}

export default function MarketConditionsCard({ market }: { market: LiveSummary['market'] | null }) {
  const cond = market ? CONDITION_STYLE[market.condition] : null
  const asOf = market ? formatCTStamp(market.vix_as_of) : null

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-spark">Market Conditions</h3>
      {!market ? (
        <div className="mt-4 h-16 animate-pulse rounded-lg bg-forge-border/50" />
      ) : (
        <div className="mt-3 grid grid-cols-2 gap-4 lg:grid-cols-5">
          <div className="col-span-2 flex items-center gap-3 lg:col-span-1">
            <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${market.condition === 'good' ? 'bg-emerald-500/15' : market.condition === 'caution' ? 'bg-yellow-500/15' : 'bg-forge-border/60'}`}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                strokeLinecap="round" strokeLinejoin="round"
                className={`h-5 w-5 ${cond?.text}`}>
                <circle cx="12" cy="12" r="4" />
                <path d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
              </svg>
            </div>
            <div>
              <div className={`text-lg font-semibold ${cond?.text}`}>{cond?.label}</div>
              <div className="text-xs text-gray-500">{market.condition_line}</div>
            </div>
          </div>
          <Metric
            label="SPY Price"
            value={market.spy_price != null ? market.spy_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}
            sub={market.spy_change_pct != null ? `${market.spy_change_pct > 0 ? '+' : ''}${market.spy_change_pct.toFixed(2)}%` : null}
            subClass={market.spy_change_pct != null && market.spy_change_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}
          />
          <Metric
            label="VIX"
            value={market.vix != null ? market.vix.toFixed(2) : '—'}
            sub={asOf ? `as of ${asOf} CT` : null}
          />
          <Metric
            label="Trend"
            value={market.trend ?? '—'}
            sub={market.trend === 'Holding Steady' ? 'Rangebound' : market.trend ? 'Today vs yesterday' : null}
            subClass={market.trend === 'Bullish' ? 'text-emerald-400' : market.trend === 'Bearish' ? 'text-red-400' : undefined}
          />
          <Metric
            label="Outlook"
            value={market.outlook ?? '—'}
            sub={market.condition === 'good' ? 'Good setup for today.' : null}
            subClass={market.condition === 'good' ? 'text-emerald-400' : undefined}
          />
        </div>
      )}
    </section>
  )
}
