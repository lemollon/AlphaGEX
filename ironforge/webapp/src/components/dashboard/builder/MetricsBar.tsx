'use client'

/**
 * MetricsBar — ported from spreadworks/frontend/src/components/MetricsBar.jsx.
 * Two rows:
 *   Row 1: Net Credit, Max Profit, Max Loss, POP (heuristic), Breakevens, IV
 *   Row 2: Δ Delta, Γ Gamma, Θ Theta, ν Vega
 *
 * All values come from /api/{bot}/builder/snapshot { metrics, legs }.
 * IronForge's Tailwind tokens (forge-*) replace SpreadWorks' custom CSS
 * variables so the card fits the dark dashboard aesthetic.
 */
import { useState } from 'react'

interface MetricsBarProps {
  metrics?: {
    net_credit: number | null
    max_profit: number | null
    max_loss: number | null
    breakeven_low: number | null
    breakeven_high: number | null
    pop_heuristic: number | null
    net_delta: number | null
    net_gamma: number | null
    net_theta: number | null
    net_vega: number | null
  } | null
  legs?: Array<{ mid_iv: number | null }>
}

function fmtMoney0(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  const n = Math.abs(Math.round(v))
  return `${v < 0 ? '-' : ''}$${n.toLocaleString()}`
}
function fmtMoney2(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return `$${v.toFixed(2)}`
}
function fmtPct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return `${(v * 100).toFixed(1)}%`
}
function fmtGreek(v: number | null | undefined, digits = 3): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return v.toFixed(digits)
}

function deltaColor(v: number | null | undefined): string {
  if (v == null) return 'text-forge-muted'
  if (Math.abs(v) < 0.05) return 'text-gray-300'
  return v > 0 ? 'text-emerald-400' : 'text-red-400'
}
function thetaColor(v: number | null | undefined): string {
  if (v == null) return 'text-forge-muted'
  return v >= 0 ? 'text-emerald-400' : 'text-red-400'
}

function MetricCell({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="flex-1 flex flex-col gap-1 px-3 py-2 rounded-lg border border-forge-border/40 bg-forge-card/60 min-w-[110px]">
      <span className="text-[10px] uppercase tracking-wider text-forge-muted">{label}</span>
      <span className={`font-semibold text-sm font-mono ${valueClass ?? 'text-white'}`}>{value}</span>
    </div>
  )
}

function GreekCell({ label, symbol, value, valueClass, tooltip }: {
  label: string
  symbol: string
  value: string
  valueClass?: string
  tooltip?: string
}) {
  return (
    <div
      className="flex-1 flex flex-col gap-1 px-3 py-2 rounded-lg border border-forge-border/40 bg-forge-card/60 relative group min-w-[110px]"
      title={tooltip}
    >
      <span className="text-[10px] uppercase tracking-wider text-forge-muted">
        <span className="mr-1">{symbol}</span>{label}
      </span>
      <span className={`font-semibold text-sm font-mono ${valueClass ?? 'text-gray-200'}`}>{value}</span>
    </div>
  )
}

export default function MetricsBar({ metrics, legs }: MetricsBarProps) {
  const [hovered] = useState(false)
  void hovered
  const m = metrics ?? ({} as NonNullable<MetricsBarProps['metrics']>)
  const netCredit = m.net_credit ?? null
  const creditLabel = netCredit != null && netCredit >= 0 ? 'NET CREDIT' : 'NET DEBIT'
  const creditClass = netCredit != null && netCredit >= 0 ? 'text-emerald-400' : 'text-red-400'

  // Implied vol = mean of non-null leg mid_iv values
  const ivs = (legs ?? []).map((l) => l.mid_iv).filter((v): v is number => v != null && Number.isFinite(v))
  const avgIv = ivs.length > 0 ? ivs.reduce((a, b) => a + b, 0) / ivs.length : null

  const beStr = m.breakeven_low != null && m.breakeven_high != null
    ? `$${m.breakeven_low.toFixed(2)} — $${m.breakeven_high.toFixed(2)}`
    : '—'

  return (
    <div className="space-y-1">
      <div className="flex gap-1 flex-wrap">
        <MetricCell label={creditLabel} value={fmtMoney0(netCredit)} valueClass={`${creditClass} text-base`} />
        <MetricCell label="Max Profit" value={fmtMoney0(m.max_profit)} valueClass="text-emerald-400 text-base" />
        <MetricCell label="Max Loss" value={fmtMoney0(m.max_loss)} valueClass="text-red-400 text-base" />
        <MetricCell label="POP (heuristic)" value={fmtPct(m.pop_heuristic)} valueClass="text-amber-400 text-base" />
        <MetricCell label="Breakevens" value={beStr} valueClass="text-white" />
        <MetricCell label="Implied Vol (avg)" value={fmtPct(avgIv)} />
      </div>
      <div className="flex gap-1 flex-wrap">
        <GreekCell
          label="Delta" symbol="Δ" value={fmtGreek(m.net_delta)}
          valueClass={deltaColor(m.net_delta)}
          tooltip="Net position delta — $ change per $1 move in underlying, per contract × contracts"
        />
        <GreekCell
          label="Gamma" symbol="Γ" value={fmtGreek(m.net_gamma, 5)}
          tooltip="Rate of change of delta"
        />
        <GreekCell
          label="Theta" symbol="Θ" value={m.net_theta != null ? `${fmtMoney2(m.net_theta)}/day` : '—'}
          valueClass={thetaColor(m.net_theta)}
          tooltip="Daily time decay — positive = position earns from time passing"
        />
        <GreekCell
          label="Vega" symbol="ν" value={fmtMoney2(m.net_vega)}
          tooltip="Sensitivity to a 1% change in implied volatility"
        />
        <div className="flex-1 min-w-[110px]" />
        <div className="flex-1 min-w-[110px]" />
      </div>
    </div>
  )
}
