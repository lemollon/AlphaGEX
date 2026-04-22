'use client'

/**
 * PayoffTable — numeric "what does the bot target" view.
 *
 * Replaces the generic price-grid table with exit-scenario rows that
 * match SPARK's actual same-day exit behavior. The bot closes by 2:50 PM
 * on day T — it does NOT hold to next-day expiration — so the theoretical
 * max profit is unreachable. The table makes that distinction explicit:
 *
 *   SAME-DAY EXITS  (what the bot actually targets)
 *     - Now (Live)        → current MTM, interpolated from pnl_curve at spot
 *     - Morning PT 30%    → credit × 0.70 × 100 × contracts
 *     - Midday PT 20%     → credit × 0.80 × 100 × contracts
 *     - PM PT 15%         → credit × 0.85 × 100 × contracts
 *     - EOD Force 2:50 PM → "varies" (backstop, P&L unknowable until close)
 *
 *   THEORETICAL CEILING  (not reached by SPARK)
 *     - At Expiration     → max_profit (what would be retained if held to T+1 close)
 *
 * The row for the currently-active PT tier (based on CT clock) gets
 * a subtle green/yellow/orange badge so the operator can see which
 * tier the bot is aiming for right now without checking a separate
 * widget. Highlight transitions at 10:30 AM CT and 1:00 PM CT.
 *
 * `Now (Live)` updates every snapshot poll (30s) — everything else is
 * static for the life of the position (credit is fixed at entry).
 *
 * $/% toggle:
 *   'dollar'  → absolute P&L (e.g. "+$201")
 *   'percent' → signed % of credit (e.g. "+70%" — positive side) or
 *              % of |max_loss| for negative values. Matches the
 *              SpreadWorks convention where full max_profit ≈ +100%
 *              relative to the credit captured.
 */
import type { PnlPoint } from '@/lib/payoff-shape'
import { getCurrentPTTier } from '@/lib/pt-tiers'

interface PayoffTableProps {
  pnlCurve: PnlPoint[] | null | undefined
  maxProfit?: number | null
  maxLoss?: number | null
  spotPrice?: number | null
  /** Per-contract entry credit (dollars per contract, e.g. 0.41). */
  netCredit?: number | null
  contracts?: number | null
  pnlMode: 'dollar' | 'percent'
}

function fmtDollar(v: number): string {
  const rounded = Math.round(v)
  const abs = Math.abs(rounded).toLocaleString()
  return rounded >= 0 ? `+$${abs}` : `-$${abs}`
}
function fmtPct(v: number): string {
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
}

/**
 * Interpolate P&L at `p` on a piecewise-linear curve.
 * Returns 0 if no segment covers the price (caller's guard).
 */
function interpPnl(curve: PnlPoint[], p: number): number {
  for (let i = 0; i < curve.length - 1; i++) {
    const a = curve[i], b = curve[i + 1]
    if ((a.price <= p && p <= b.price) || (b.price <= p && p <= a.price)) {
      const t = b.price === a.price ? 0 : (p - a.price) / (b.price - a.price)
      return a.pnl + t * (b.pnl - a.pnl)
    }
  }
  return 0
}

type RowKind = 'live' | 'morning' | 'midday' | 'afternoon' | 'eod' | 'expiration'

interface Row {
  kind: RowKind
  label: string
  sublabel?: string
  pnl: number | null        // null → "varies" (EOD)
  pctOfMax: number | null   // null → "varies"
  barPct: number            // 0..100 magnitude for the bar
  color: string             // text color
  barColor: string          // bar fill
}

export default function PayoffTable({
  pnlCurve,
  maxProfit,
  maxLoss,
  spotPrice,
  netCredit,
  contracts,
  pnlMode,
}: PayoffTableProps) {
  if (!pnlCurve || pnlCurve.length === 0) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-8 text-center">
        <p className="text-forge-muted text-sm">No payoff data available</p>
      </div>
    )
  }

  // Max profit is the denominator for "% of max profit" display — lets us
  // express each tier as a fraction of the theoretical ceiling (morning
  // lands at 70%, midday at 80%, PM at 85%, expiration at 100%).
  const maxP = Math.max(maxProfit ?? 0, 0)
  const maxP_nonzero = maxP > 0 ? maxP : 1

  // Credit × 100 × contracts = the same $ number as max_profit, just
  // computed from raw inputs. Matches the scanner's `getSlidingProfitTarget`
  // behavior exactly: exit when cost_to_close <= tierPct × credit, which
  // retains (1 - tierPct) × credit × 100 × contracts.
  const creditDollars = (netCredit != null && contracts != null)
    ? netCredit * 100 * Math.max(1, contracts)
    : maxP
  const pnlAtTier = (tierPct: number): number => (1 - tierPct) * creditDollars

  // Now (Live) — interpolate pnl_curve at current spot
  const nowPnl = spotPrice != null ? interpPnl(pnlCurve, spotPrice) : 0

  // Identify active PT tier so we can highlight it
  const activeTier = getCurrentPTTier()
  const activeKind: RowKind =
    activeTier.label === 'Morning' ? 'morning'
    : activeTier.label === 'Midday' ? 'midday'
    : 'afternoon'

  const sameDayRows: Row[] = [
    {
      kind: 'live',
      label: 'Now (Live)',
      sublabel: spotPrice != null ? `spot $${spotPrice.toFixed(2)}` : undefined,
      pnl: nowPnl,
      pctOfMax: (nowPnl / maxP_nonzero) * 100,
      barPct: Math.min(100, Math.max(0, (nowPnl / maxP_nonzero) * 100)),
      color: nowPnl >= 0 ? 'text-emerald-400' : 'text-red-400',
      barColor: nowPnl >= 0 ? 'bg-emerald-500/40' : 'bg-red-500/40',
    },
    {
      kind: 'morning',
      label: 'Morning PT (30%)',
      sublabel: 'before 10:30 AM CT',
      pnl: pnlAtTier(0.30),
      pctOfMax: 70,
      barPct: 70,
      color: 'text-emerald-400',
      barColor: 'bg-emerald-500/40',
    },
    {
      kind: 'midday',
      label: 'Midday PT (20%)',
      sublabel: '10:30 AM – 1:00 PM CT',
      pnl: pnlAtTier(0.20),
      pctOfMax: 80,
      barPct: 80,
      color: 'text-yellow-400',
      barColor: 'bg-yellow-500/40',
    },
    {
      kind: 'afternoon',
      label: 'PM PT (15%)',
      sublabel: '1:00 PM – 2:45 PM CT',
      pnl: pnlAtTier(0.15),
      pctOfMax: 85,
      barPct: 85,
      color: 'text-orange-400',
      barColor: 'bg-orange-500/40',
    },
    {
      kind: 'eod',
      label: 'EOD Force (2:50 PM)',
      sublabel: 'backstop — depends on market',
      pnl: null,
      pctOfMax: null,
      barPct: 0,
      color: 'text-amber-400',
      barColor: 'bg-amber-500/30',
    },
  ]

  const ceilingRow: Row = {
    kind: 'expiration',
    label: 'At Expiration',
    sublabel: 'SPARK does NOT hold to this',
    pnl: maxP,
    pctOfMax: 100,
    barPct: 100,
    color: 'text-gray-400',
    barColor: 'bg-gray-500/30',
  }

  const renderCell = (r: Row) => {
    if (r.pnl == null) return <span className="text-amber-400/90 italic">varies</span>
    if (pnlMode === 'dollar') return <span className={r.color}>{fmtDollar(r.pnl)}</span>
    // For % mode, show percentage of MAX profit (the ceiling), signed.
    if (r.pctOfMax == null) return <span className="text-amber-400/90 italic">varies</span>
    return <span className={r.color}>{fmtPct(r.pctOfMax)}</span>
  }

  const renderBar = (r: Row) => {
    if (r.pnl == null) return null
    return (
      <div className="inline-block w-28 h-3 bg-forge-border/20 rounded-sm overflow-hidden align-middle">
        <div
          className={`h-full ${r.barColor}`}
          style={{
            width: `${r.barPct}%`,
            marginLeft: r.pnl >= 0 ? 0 : 'auto',
          }}
        />
      </div>
    )
  }

  const SectionHeader = ({ title, note }: { title: string; note?: string }) => (
    <tr>
      <td colSpan={3} className="pt-4 pb-1 px-4">
        <div className="flex items-baseline gap-3">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-300">{title}</span>
          {note && <span className="text-[10px] text-forge-muted italic">{note}</span>}
        </div>
        <div className="h-px bg-forge-border/50 mt-1" />
      </td>
    </tr>
  )

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 overflow-hidden" style={{ height: 500 }}>
      <div className="overflow-y-auto h-full">
        <table className="w-full text-xs font-mono">
          <thead className="sticky top-0 bg-forge-card/95 backdrop-blur-sm z-10">
            <tr className="text-forge-muted border-b border-forge-border">
              <th className="text-left py-2 px-4 font-normal uppercase tracking-wider text-[10px]">Exit Point</th>
              <th className="text-right py-2 px-4 font-normal uppercase tracking-wider text-[10px]">
                {pnlMode === 'dollar' ? 'P&L ($)' : 'P&L (% of max)'}
              </th>
              <th className="text-right py-2 px-4 font-normal uppercase tracking-wider text-[10px]">Bar</th>
            </tr>
          </thead>
          <tbody>
            <SectionHeader title="Same-Day Exits" note="what SPARK actually targets" />
            {sameDayRows.map((r) => {
              const isActive = r.kind === activeKind
              return (
                <tr
                  key={r.kind}
                  className={`border-b border-forge-border/20 ${isActive ? 'bg-blue-500/10' : ''}`}
                >
                  <td className="py-2 px-4 text-left">
                    <div className={`flex items-center gap-2 ${isActive ? 'font-semibold' : ''}`}>
                      {isActive && <span className={`inline-block w-1.5 h-1.5 rounded-full ${r.barColor.replace('/40', '').replace('/30', '')}`} />}
                      <span className={isActive ? r.color : 'text-gray-200'}>{r.label}</span>
                      {isActive && (
                        <span className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded ${r.barColor} ${r.color}`}>
                          active
                        </span>
                      )}
                    </div>
                    {r.sublabel && <div className="text-[10px] text-forge-muted mt-0.5">{r.sublabel}</div>}
                  </td>
                  <td className="py-2 px-4 text-right align-top">{renderCell(r)}</td>
                  <td className="py-2 px-4 text-right align-top">{renderBar(r)}</td>
                </tr>
              )
            })}

            <SectionHeader title="Theoretical Ceiling" note="SPARK does NOT reach this" />
            <tr className="border-b border-forge-border/20 opacity-60">
              <td className="py-2 px-4 text-left">
                <div className="text-gray-400">{ceilingRow.label}</div>
                {ceilingRow.sublabel && <div className="text-[10px] text-forge-muted mt-0.5">{ceilingRow.sublabel}</div>}
              </td>
              <td className="py-2 px-4 text-right align-top">{renderCell(ceilingRow)}</td>
              <td className="py-2 px-4 text-right align-top">{renderBar(ceilingRow)}</td>
            </tr>

            {/* Footer caveat */}
            <tr>
              <td colSpan={3} className="px-4 py-3 text-[10px] text-forge-muted leading-relaxed">
                SPARK exits same-day (T). The position is 1DTE, but the bot closes before
                expiration (T+1) via PT tiers or EOD at 2:50 PM CT. The theoretical max
                profit is only realized by holding overnight to expiration close, which
                SPARK is not designed to do.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
