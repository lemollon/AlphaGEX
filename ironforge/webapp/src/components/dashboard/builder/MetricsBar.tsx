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
    /** True max loss: full wing breach at expiration = collateral at risk.
     * Headline figure — stops can fail (gap, hung scanner, slippage) so
     * risk display must anchor on the worst case the position can realize. */
    max_loss_at_expiry?: number | null
    /** Configured stop-loss target: dollar loss IF the stop fires at
     * sl_mult × credit. Surfaced as a secondary "where the stop sits"
     * line — NOT the max-loss headline. */
    stop_target_loss?: number | null
    /** Stop-loss multiplier (sl_mult) used to compute stop_target_loss.
     * Surfaced so the tooltip can explain "Stop at 2.0× credit". */
    sl_mult?: number | null
    /** Legacy alias for max_loss_at_expiry — keep until all consumers
     * migrate to the explicit fields. */
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

function MetricCell({ label, value, valueClass, tooltip, footnote }: {
  label: string
  value: string
  valueClass?: string
  tooltip?: string
  footnote?: string
}) {
  return (
    <div
      className="flex-1 flex flex-col gap-1 px-3 py-2 rounded-lg border border-forge-border/40 bg-forge-card/60 min-w-[110px]"
      title={tooltip}
    >
      <span className="text-[10px] uppercase tracking-wider text-forge-muted">{label}</span>
      <span className={`font-semibold text-sm font-mono ${valueClass ?? 'text-white'}`}>{value}</span>
      {footnote && (
        <span className="text-[9px] text-forge-muted leading-tight mt-0.5">{footnote}</span>
      )}
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
        {/* "Max Profit @ Exp" — the trailing @ Exp is deliberate: SPARK is
             a same-day exit bot, so the $ number here is only reachable by
             holding overnight to next-day expiration, which SPARK doesn't
             do. The PayoffTable's "Same-Day Exits" section shows the real
             intraday exit targets (Morning/Midday/PM PT tiers). */}
        <MetricCell label="Max Profit @ Exp" value={fmtMoney0(m.max_profit)} valueClass="text-emerald-400 text-base" />
        {/* Headline "Max Loss" — the TRUE wing-breach figure (collateral at
            risk). Stops can fail (gap moves, hung scanner, slippage 10–50%
            past trigger) so the headline anchors on the worst case the
            position can realize. The configured stop-loss target moves to
            a footnote so operators see where the stop sits without it
            being mistaken for a hard cap on loss. */}
        {(() => {
          const wingBreach = (m.max_loss_at_expiry ?? m.max_loss ?? null)
          const stopTarget = (m.stop_target_loss ?? null)
          const slMult = m.sl_mult ?? null
          const stopLabel = slMult != null ? `${slMult.toFixed(1)}× credit` : 'stop'
          const stopStr = stopTarget != null ? fmtMoney0(stopTarget) : null
          return (
            <MetricCell
              label="Max Loss"
              value={fmtMoney0(wingBreach)}
              valueClass="text-red-400 text-base"
              tooltip={
                `Full wing-breach at expiration = collateral at risk. This is the worst ` +
                `case if the stop fails to fire (gap move, quote outage, scanner down). ` +
                (stopStr != null
                  ? `Configured stop fires at ${stopLabel} (≈ ${stopStr}), but actual ` +
                    `fills slip past the trigger by 10–50% due to bid/ask spread on the ` +
                    `closing order.`
                  : `No stop-loss config loaded yet.`)
              }
              footnote={stopStr != null ? `stop target: ${stopStr} @ ${stopLabel}` : undefined}
            />
          )
        })()}
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
