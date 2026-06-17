'use client'

import React from 'react'

/**
 * DirectionBalanceCard — call vs put exposure for the directional bots
 * (FLARE / BLAZE). These bots open call OR put debit spreads, so they are
 * never 50/50 by design — but a heavy one-sided pile-up is their historical
 * failure mode (FLARE 6/04: 138 put fades, -$40k). This card surfaces the
 * live call/put split so the operator can SEE the imbalance the scanner's
 * per-side force-close stop is there to catch.
 *
 * Data is the live open-position set from /api/{bot}/position-monitor — each
 * directional position carries { direction, debit, contracts, unrealized_pnl }.
 * Capital at risk per leg = debit × 100 × contracts (debit IS the max loss,
 * since FLARE runs SL=100%). No API call of its own.
 *
 * For FLARE, each side also shows its progress toward the per-direction
 * force-close threshold (−forceClosePct × balance): when one side's aggregate
 * unrealized P&L breaches that, runMonitorCycle guillotines the whole side.
 * BLAZE has no such stop, so the gauge is omitted there.
 */

type Pos = {
  direction?: string | null
  debit?: number | null
  contracts?: number | null
  unrealized_pnl?: number | null
}

type SideAgg = {
  count: number
  contracts: number
  risk: number          // capital at risk ($)
  unrealized: number    // aggregate unrealized P&L ($)
}

function aggregate(positions: Pos[], dir: 'call' | 'put'): SideAgg {
  const side = positions.filter((p) => (p.direction || '').toLowerCase() === dir)
  return side.reduce<SideAgg>(
    (a, p) => {
      const contracts = Number(p.contracts) || 0
      const debit = Number(p.debit) || 0
      a.count += 1
      a.contracts += contracts
      a.risk += debit * 100 * contracts
      a.unrealized += Number(p.unrealized_pnl) || 0
      return a
    },
    { count: 0, contracts: 0, risk: 0, unrealized: 0 },
  )
}

function fmtMoney(n: number): string {
  const sign = n < 0 ? '-' : ''
  return `${sign}$${Math.abs(Math.round(n)).toLocaleString('en-US')}`
}

function fmtSigned(n: number): string {
  return `${n >= 0 ? '+' : '-'}$${Math.abs(Math.round(n)).toLocaleString('en-US')}`
}

/** One side (CALL / PUT) column. */
function SideColumn({
  label,
  tone,
  agg,
  threshold,
}: {
  label: string
  tone: 'call' | 'put'
  agg: SideAgg
  threshold: number | null   // negative $ force-close trigger, or null (no FC gauge)
}) {
  const dot = tone === 'call' ? 'bg-emerald-400' : 'bg-rose-400'
  const uColor = agg.unrealized > 0 ? 'text-emerald-400' : agg.unrealized < 0 ? 'text-rose-400' : 'text-forge-muted'

  // Fraction of the way to the force-close trigger (0 when flat/green).
  let fcPct: number | null = null
  if (threshold != null && threshold < 0 && agg.unrealized < 0) {
    fcPct = Math.min(1, agg.unrealized / threshold) // both negative → positive
  } else if (threshold != null) {
    fcPct = 0
  }
  // Literal classes only — Tailwind purges dynamically-built names.
  const safeBar = tone === 'call' ? 'bg-emerald-500/70' : 'bg-rose-500/70'
  const fcColor =
    fcPct == null ? '' : fcPct >= 0.8 ? 'bg-red-500' : fcPct >= 0.5 ? 'bg-amber-400' : safeBar

  return (
    <div className="flex-1 min-w-[150px]">
      <div className="flex items-center gap-1.5 mb-1">
        <span className={`inline-block w-2 h-2 rounded-full ${dot}`} />
        <span className="text-xs font-semibold uppercase tracking-wider text-forge-muted">{label}</span>
      </div>
      <div className="text-sm text-white">
        {agg.count === 0 ? (
          <span className="text-forge-muted">no open {label.toLowerCase()} spreads</span>
        ) : (
          <>
            {agg.count} spread{agg.count !== 1 ? 's' : ''}
            <span className="text-forge-muted"> · {agg.contracts} ct · risk {fmtMoney(agg.risk)}</span>
          </>
        )}
      </div>
      {agg.count > 0 && (
        <div className="text-xs mt-0.5">
          <span className="text-forge-muted">uPnL </span>
          <span className={uColor}>{fmtSigned(agg.unrealized)}</span>
        </div>
      )}

      {/* Force-close gauge (FLARE only) */}
      {fcPct != null && (
        <div className="mt-1.5">
          <div className="h-1.5 rounded-full bg-forge-bg overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${fcColor}`}
              style={{ width: `${Math.round(fcPct * 100)}%` }}
            />
          </div>
          <div className="text-[10px] text-forge-muted mt-0.5">
            {agg.count === 0 || fcPct === 0
              ? `safe · FC at ${fmtMoney(threshold!)}`
              : `${Math.round(fcPct * 100)}% to force-close (${fmtMoney(threshold!)})`}
          </div>
        </div>
      )}
    </div>
  )
}

export default function DirectionBalanceCard({
  positions,
  balance,
  bot,
  forceClosePct,
}: {
  positions: Pos[] | undefined
  balance: number | undefined
  bot: 'flare' | 'blaze'
  /** Per-direction force-close fraction (FLARE = 0.10). Omit to hide the FC gauge. */
  forceClosePct?: number
}) {
  const open = (positions || []).filter((p) => p.direction)
  const calls = aggregate(open, 'call')
  const puts = aggregate(open, 'put')
  const totalRisk = calls.risk + puts.risk
  const callShare = totalRisk > 0 ? calls.risk / totalRisk : 0.5

  // FLARE force-close trigger per side = −forceClosePct × balance.
  const threshold =
    forceClosePct && balance && balance > 0 ? -forceClosePct * balance : null

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white">Call / Put Balance</h3>
        <span className="text-[11px] text-forge-muted">
          {open.length === 0
            ? 'no open positions'
            : balance && balance > 0
              ? `bal ${fmtMoney(balance)}`
              : `${open.length} open`}
        </span>
      </div>

      <div className="flex flex-wrap gap-4">
        <SideColumn label="Calls" tone="call" agg={calls} threshold={threshold} />
        <div className="w-px self-stretch bg-forge-border hidden sm:block" />
        <SideColumn label="Puts" tone="put" agg={puts} threshold={threshold} />
      </div>

      {/* Balance bar — share of capital-at-risk, call (green) vs put (red) */}
      <div className="mt-3">
        <div className="h-2 rounded-full overflow-hidden flex bg-forge-bg">
          <div className="h-full bg-emerald-500/80" style={{ width: `${Math.round(callShare * 100)}%` }} />
          <div className="h-full bg-rose-500/80" style={{ width: `${Math.round((1 - callShare) * 100)}%` }} />
        </div>
        <div className="flex justify-between text-[10px] text-forge-muted mt-1">
          <span>{Math.round(callShare * 100)}% call</span>
          <span className="text-forge-muted/70">
            {totalRisk > 0 ? `${fmtMoney(totalRisk)} at risk` : 'flat'}
          </span>
          <span>{Math.round((1 - callShare) * 100)}% put</span>
        </div>
      </div>

      <p className="text-[10px] text-forge-muted/70 mt-2 leading-snug">
        {bot === 'flare'
          ? 'FLARE is directional — one-sided by design, but the per-side force-close guillotines a side whose aggregate unrealized breaches −' +
            `${Math.round((forceClosePct || 0.1) * 100)}% of balance.`
          : 'BLAZE is directional — one-sided exposure is expected; no per-side force-close stop on this bot.'}
      </p>
    </div>
  )
}
