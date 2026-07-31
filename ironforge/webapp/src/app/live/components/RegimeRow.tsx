'use client'

import type { LiveOpenPosition } from '@/lib/live/types'

/**
 * Regime + how much of the account this trade is using.
 *
 * Both come from the position row, so they describe THIS trade rather than today's
 * market. The cap is shown beside the actual figure so "17% of a 20% limit" reads as the
 * rule it is — Spark deploys up to 50% of the account on positive gamma and 20% on
 * negative, because positive-gamma days carry about a third of the variance.
 */
export default function RegimeRow({ p, accountValue }: { p: LiveOpenPosition; accountValue: number | null }) {
  const known = p.gex_regime != null
  const positive = p.gex_regime === 'POSITIVE'
  const tone = !known ? '#9CA3AF' : positive ? '#10B981' : '#F59E0B'

  const usedPct =
    p.capital_used != null && accountValue != null && accountValue > 0
      ? (p.capital_used / accountValue) * 100
      : null

  return (
    <div className="mt-3.5 grid grid-cols-2 gap-3 rounded-xl border border-white/10 bg-[#0C0D0E] p-3.5">
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">Market Regime</div>
        <div className="mt-1 flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: tone }} aria-hidden />
          <span className="text-[15px] font-bold" style={{ color: tone }}>
            {!known ? 'Unknown' : positive ? 'Positive Gamma' : 'Negative Gamma'}
          </span>
        </div>
        <div className="mt-0.5 text-[11px] leading-snug text-gray-500">
          {!known
            ? 'Regime was not recorded for this trade.'
            : positive
              ? 'Calmer tape — Spark trades a larger share.'
              : 'Choppier tape — Spark trades a smaller share.'}
        </div>
      </div>
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">Account at Risk</div>
        <div className="mt-1 text-[15px] font-bold text-white">
          {/* "—" rather than 0% when the account value is unavailable. */}
          {usedPct == null ? '—' : `${usedPct.toFixed(1)}%`}
        </div>
        <div className="mt-0.5 text-[11px] leading-snug text-gray-500">
          {p.capital_used != null ? `$${p.capital_used.toLocaleString('en-US')} max loss` : 'Not available'}
          {p.regime_cap_pct != null ? ` · limit ${Math.round(p.regime_cap_pct * 100)}%` : ''}
        </div>
      </div>
    </div>
  )
}
