'use client'

import type { LiveOpenPosition } from '@/lib/live/types'
import { formatDollarPnl } from '@/lib/format'

/**
 * The two-card swing view.
 *
 * SPARK holds a losing condor to expiry rather than stopping out, so on any day it opens
 * a new trade there are TWO live positions: yesterday's swung leg and today's. The page
 * previously described only the newest, so the overnight position — with the customer's
 * money in it — appeared nowhere.
 *
 * Rendered ONLY when a swing is actually live (two or more open positions). One position
 * keeps the original single-card layout, so the normal day is untouched.
 *
 * NO PER-CARD SPARKLINE, deliberately. `spark_equity_snapshots` has no position_id — the
 * P&L history is an account-level aggregate — so there is no honest way to draw a
 * separate line per position. Showing the same account series inside both cards would
 * imply each was that position's history. The per-position P&L NUMBERS are real
 * (mark-to-market is per position); the shared curve stays in Today's Performance below,
 * where it is correctly labelled as the account.
 */

function formatCT(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString('en-US', {
    timeZone: 'America/Chicago', hour: 'numeric', minute: '2-digit',
  })
}

function formatDuration(min: number | null): string {
  if (min == null) return '—'
  const h = Math.floor(min / 60)
  const m = min % 60
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function Step({ done, active, label, sub, tone }: {
  done: boolean; active: boolean; label: string; sub: string; tone: string
}) {
  return (
    <div className="flex min-w-0 flex-1 flex-col items-center text-center">
      <span
        className={`flex h-5 w-5 items-center justify-center rounded-full border-2 ${
          done || active ? '' : 'border-gray-700 bg-transparent'
        }`}
        style={done || active ? { borderColor: tone, backgroundColor: done ? tone : 'transparent' } : undefined}
        aria-hidden
      >
        {done ? <span className="text-[10px] font-bold text-black">✓</span> : null}
        {active && !done ? <span className="h-2 w-2 rounded-full" style={{ backgroundColor: tone }} /> : null}
      </span>
      <span className="mt-1.5 text-[11px] font-medium leading-tight text-gray-300">{label}</span>
      <span className="text-[11px] leading-tight" style={active ? { color: tone } : { color: '#6b7280' }}>
        {sub}
      </span>
    </div>
  )
}

/**
 * Regime + how much of the account this trade is using.
 *
 * Both come from the position row, so they describe THIS trade rather than today's
 * market. The cap is shown beside the actual figure so "17% of a 20% limit" reads as the
 * rule it is — Spark deploys up to 50% of the account on positive gamma and 20% on
 * negative, because positive-gamma days carry about a third of the variance.
 */
function RegimeRow({ p, accountValue }: { p: LiveOpenPosition; accountValue: number | null }) {
  const known = p.gex_regime != null
  const positive = p.gex_regime === 'POSITIVE'
  const tone = !known ? '#9CA3AF' : positive ? '#22C55E' : '#F59E0B'

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

function PositionCard({ p, accountValue }: { p: LiveOpenPosition; accountValue: number | null }) {
  const swung = p.held_overnight
  // Blue reads "carried over", green reads "new" — matching the badge colours so the
  // card's whole state is legible at a glance.
  const tone = swung ? '#3B82F6' : '#22C55E'
  const pnl = p.unrealized_pnl
  const pnlColor = pnl == null ? 'text-gray-400' : pnl >= 0 ? 'text-[#22C55E]' : 'text-[#EF4444]'

  return (
    <div className="rounded-2xl border bg-[#0A0B0C] p-5" style={{ borderColor: `${tone}66` }}>
      <div className="flex flex-wrap items-center gap-2.5">
        <h3 className="text-[17px] font-bold text-white">{p.opened_date_label} Trade</h3>
        <span
          className="rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider"
          style={{ backgroundColor: `${tone}22`, color: tone }}
        >
          {swung ? 'Held Overnight' : 'Opened Today'}
        </span>
      </div>
      <p className="mt-1 text-[13px] text-gray-400">
        Day {p.day_number} • {swung ? 'Managing Overnight' : 'New Position'}
      </p>

      <div className="mt-4 grid grid-cols-3 gap-3 border-t border-white/10 pt-3.5">
        <div>
          <div className="text-[11px] text-gray-500">Opened</div>
          <div className="mt-0.5 text-[13px] font-medium text-white">{formatCT(p.opened_at)} CT</div>
        </div>
        <div>
          <div className="text-[11px] text-gray-500">Expires</div>
          <div className="mt-0.5 text-[13px] font-medium text-white">{p.expires_label ?? '—'}</div>
        </div>
        <div>
          <div className="text-[11px] text-gray-500">Time in Trade</div>
          <div className="mt-0.5 text-[13px] font-medium" style={{ color: tone }}>
            {formatDuration(p.time_in_trade_min)}
          </div>
        </div>
      </div>

      <div className="mt-3.5 rounded-xl border border-white/10 bg-[#0C0D0E] p-3.5">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">Unrealized P&amp;L</div>
        <div className={`mt-1 text-[26px] font-bold ${pnlColor}`}>
          {/* Never $0.00 when quotes are unavailable — "—" is the honest reading. */}
          {pnl == null ? '—' : formatDollarPnl(pnl)}
        </div>
        <div className="mt-0.5 text-[11px] text-gray-500">
          {p.unrealized_pnl_pct == null
            ? 'Live pricing unavailable'
            : `${p.unrealized_pnl_pct > 0 ? '+' : ''}${p.unrealized_pnl_pct.toFixed(2)}% of ${
                (pnl ?? 0) >= 0 ? 'max profit' : 'max loss'
              }`}
        </div>
      </div>

      <RegimeRow p={p} accountValue={accountValue} />

      <div className="mt-4">
        <div className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: tone }}>
          What is happening right now?
        </div>
        <div className="mt-3 flex items-start gap-1">
          <Step done label="Trade Opened" sub={formatCT(p.opened_at)} active={false} tone={tone} />
          {swung ? (
            <Step done label="Held Overnight" sub={p.opened_date_label} active={false} tone={tone} />
          ) : null}
          <Step done={false} active label="Managing" sub="Live" tone={tone} />
          <Step done={false} active={false} label="Closing" sub="EOD" tone={tone} />
        </div>
      </div>
    </div>
  )
}

export default function SwingTradeCards({
  positions,
  accountValue,
}: {
  positions: LiveOpenPosition[]
  accountValue: number | null
}) {
  if (positions.length < 2) return null
  // Oldest first, so the swung leg reads left-to-right as the earlier trade.
  const ordered = [...positions].sort((a, b) => (a.opened_at ?? '').localeCompare(b.opened_at ?? ''))
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {ordered.map((p) => (
        <PositionCard key={p.position_id || p.opened_at} p={p} accountValue={accountValue} />
      ))}
    </div>
  )
}
