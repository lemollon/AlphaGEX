'use client'

/**
 * PayoffTable — numeric view of the IC's expiration P&L curve.
 *
 * Same data the PayoffPanel renders as a curve, but as a 2-column table so
 * the operator can read exact dollar/percent values at each strike price.
 *
 * Source: `pnl_curve` from the snapshot payoff. Each row is one price point
 * on the piecewise-linear IC payoff. The row closest to the current spot
 * gets a `◂` pointer + emphasized styling so it's immediately clear where
 * the position is currently trading relative to the strikes.
 *
 * `pnlMode`:
 *   'dollar'  → P&L in dollars (e.g. "+$287", "-$3,213")
 *   'percent' → P&L as % of the max loss magnitude. This matches the
 *              SpreadWorks convention where +100% means full max profit
 *              and -100% means full max loss.
 *
 * Color rules match the payoff curve: green for profit, red for loss,
 * yellow when within 10% of the breakeven (visual handshake with the
 * BE ticks on the PayoffPanel).
 */
import type { PnlPoint } from '@/lib/payoff-shape'

interface PayoffTableProps {
  pnlCurve: PnlPoint[] | null | undefined
  maxProfit?: number | null
  maxLoss?: number | null
  spotPrice?: number | null
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

export default function PayoffTable({
  pnlCurve,
  maxProfit,
  maxLoss,
  spotPrice,
  pnlMode,
}: PayoffTableProps) {
  if (!pnlCurve || pnlCurve.length === 0) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-8 text-center">
        <p className="text-forge-muted text-sm">No payoff data available</p>
      </div>
    )
  }

  // Max loss magnitude is the denominator for % mode. Max profit falls
  // out naturally because max_profit is a positive P&L near the top of
  // the range so dividing by max_loss magnitude gives a signed % of risk.
  const lossMag = Math.abs(maxLoss ?? 0) || 1

  // Find the row closest to spot so we can mark it + anchor the viewport.
  let nearestIdx = -1
  let nearestDist = Infinity
  if (spotPrice != null) {
    for (let i = 0; i < pnlCurve.length; i++) {
      const d = Math.abs(pnlCurve[i].price - spotPrice)
      if (d < nearestDist) {
        nearestDist = d
        nearestIdx = i
      }
    }
  }

  // Clamp row count for readability — the raw curve has 4-7 kink points;
  // we expand by sampling $2-wide grid between first/last so the table
  // reads like the SpreadWorks $2-step table, not just the 4 IC kinks.
  const minPrice = pnlCurve[0].price
  const maxPrice = pnlCurve[pnlCurve.length - 1].price
  const span = maxPrice - minPrice
  const step = span > 80 ? 5 : span > 40 ? 2 : 1
  const gridRows: Array<{ price: number; pnl: number }> = []
  for (let p = Math.ceil(minPrice / step) * step; p <= maxPrice; p += step) {
    // Interpolate P&L at `p` on the piecewise-linear curve
    let pnlAt = 0
    for (let i = 0; i < pnlCurve.length - 1; i++) {
      const a = pnlCurve[i], b = pnlCurve[i + 1]
      if ((a.price <= p && p <= b.price) || (b.price <= p && p <= a.price)) {
        const t = b.price === a.price ? 0 : (p - a.price) / (b.price - a.price)
        pnlAt = a.pnl + t * (b.pnl - a.pnl)
        break
      }
    }
    gridRows.push({ price: p, pnl: pnlAt })
  }

  // Re-compute nearest against the grid rows (not raw curve) so the
  // highlighted row matches what the user sees
  let nearestGridIdx = -1
  if (spotPrice != null) {
    let best = Infinity
    gridRows.forEach((r, i) => {
      const d = Math.abs(r.price - spotPrice)
      if (d < best) { best = d; nearestGridIdx = i }
    })
  }

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 overflow-hidden" style={{ height: 500 }}>
      <div className="overflow-y-auto h-full">
        <table className="w-full text-xs font-mono">
          <thead className="sticky top-0 bg-forge-card/95 backdrop-blur-sm">
            <tr className="text-forge-muted border-b border-forge-border">
              <th className="text-left py-2 px-4 font-normal uppercase tracking-wider text-[10px]">Price</th>
              <th className="text-right py-2 px-4 font-normal uppercase tracking-wider text-[10px]">
                {pnlMode === 'dollar' ? 'P&L ($)' : 'P&L (%)'}
              </th>
              <th className="text-right py-2 px-4 font-normal uppercase tracking-wider text-[10px]">
                Bar
              </th>
            </tr>
          </thead>
          <tbody>
            {gridRows.map((r, i) => {
              const isSpot = i === nearestGridIdx
              const pct = (r.pnl / lossMag) * 100
              const nearBE = Math.abs(pct) < 10
              const color = nearBE
                ? 'text-amber-400'
                : r.pnl >= 0
                  ? 'text-emerald-400'
                  : 'text-red-400'
              // Bar magnitude: scale |pct| against 100 for visual sizing
              const barPct = Math.min(100, Math.abs(pct))
              const barColor = nearBE
                ? 'bg-amber-500/30'
                : r.pnl >= 0
                  ? 'bg-emerald-500/30'
                  : 'bg-red-500/30'
              return (
                <tr
                  key={r.price}
                  className={`border-b border-forge-border/20 ${isSpot ? 'bg-blue-500/10' : ''}`}
                >
                  <td className="py-1.5 px-4 text-left">
                    <span className={isSpot ? 'text-blue-300 font-semibold' : 'text-gray-200'}>
                      ${r.price.toFixed(0)}
                    </span>
                    {isSpot && <span className="text-blue-400 ml-2">◂</span>}
                  </td>
                  <td className={`py-1.5 px-4 text-right ${color} ${isSpot ? 'font-semibold' : ''}`}>
                    {pnlMode === 'dollar' ? fmtDollar(r.pnl) : fmtPct(pct)}
                  </td>
                  <td className="py-1.5 px-4 text-right">
                    <div className="inline-block w-24 h-3 bg-forge-border/20 rounded-sm overflow-hidden align-middle">
                      <div
                        className={`h-full ${barColor}`}
                        style={{
                          width: `${barPct}%`,
                          marginLeft: r.pnl >= 0 ? 0 : 'auto',
                        }}
                      />
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
