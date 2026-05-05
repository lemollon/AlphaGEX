import type { TradeOfDay, MacroRibbon } from '@/lib/forgeBriefings/types'

/**
 * Iron-Condor payoff diagram for the day's headline trade.
 *
 * The curve is drawn from the trade's STRIKES, not from the bot-supplied
 * `payoff_points`, because:
 *   1. An IC at expiration is a 5-segment piecewise-linear function — we
 *      know the exact shape from PL/PS/CS/CL + entry credit + contracts.
 *   2. Sparse `payoff_points` (or a sample range that didn't extend past
 *      the wings) was making symmetric ICs render asymmetrically.
 *
 * The X-axis is centered on the strike midpoint (PS + CS) / 2 with equal
 * extent on both sides, so a balanced IC always looks balanced.
 *
 * For partial spreads (put-credit-spread only or call-credit-spread only)
 * we fall through to a 3-segment payoff. As a last resort if the strikes
 * are missing entirely, we use payoff_points.
 */
interface Props {
  trade: TradeOfDay | null
  macro?: MacroRibbon | null
}

const PAD_L = 52
const PAD_R = 24
const PAD_T = 28
const PAD_B = 44
const W = 540
const H = 240

const FONT = "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"

function fmtMoney(n: number): string {
  const sign = n >= 0 ? '+' : '−'
  const abs = Math.abs(n)
  if (abs >= 1000) return `${sign}$${(abs / 1000).toFixed(1)}k`
  if (abs >= 100)  return `${sign}$${abs.toFixed(0)}`
  return `${sign}$${abs.toFixed(2)}`
}

function fmtSpot(n: number): string {
  return `$${n.toFixed(2)}`
}

interface PayoffPoint { spot: number; pnl: number }

/**
 * Build the canonical IC / vertical-spread payoff at expiration from
 * strikes + credit + contracts. Returns the polyline and the strike
 * midpoint used to center the chart.
 */
function buildCanonicalPayoff(trade: TradeOfDay): {
  curve: PayoffPoint[]
  strikeMin: number
  strikeMax: number
  midpoint: number
  maxProfit: number
  maxLoss: number
} | null {
  const { strikes, contracts, entry_credit } = trade
  const ps = strikes.ps
  const pl = strikes.pl
  const cs = strikes.cs ?? null
  const cl = strikes.cl ?? null
  if (typeof ps !== 'number' || typeof pl !== 'number') return null
  const credit = entry_credit
  const mult = contracts * 100

  // Full 4-leg IC
  if (cs !== null && cl !== null) {
    const putWidth  = Math.abs(ps - pl)
    const callWidth = Math.abs(cl - cs)
    const wingWidth = Math.max(putWidth, callWidth)
    const maxProfit = credit * mult
    const maxLoss   = (wingWidth - credit) * mult
    // Piecewise linear: PL → PS → CS → CL with flat tails.
    const curve: PayoffPoint[] = [
      { spot: pl - putWidth,  pnl: -maxLoss },   // far left flat tail
      { spot: pl,             pnl: -maxLoss },
      { spot: ps,             pnl:  maxProfit },
      { spot: cs,             pnl:  maxProfit },
      { spot: cl,             pnl: -maxLoss },
      { spot: cl + callWidth, pnl: -maxLoss },   // far right flat tail
    ]
    return {
      curve,
      strikeMin: pl,
      strikeMax: cl,
      midpoint: (ps + cs) / 2,
      maxProfit,
      maxLoss,
    }
  }

  // Put-credit spread only
  if (cs === null) {
    const w = Math.abs(ps - pl)
    const maxProfit = credit * mult
    const maxLoss   = (w - credit) * mult
    const curve: PayoffPoint[] = [
      { spot: pl - w, pnl: -maxLoss },
      { spot: pl,     pnl: -maxLoss },
      { spot: ps,     pnl:  maxProfit },
      { spot: ps + w, pnl:  maxProfit },
    ]
    return {
      curve,
      strikeMin: pl,
      strikeMax: ps,
      midpoint: (ps + pl) / 2,
      maxProfit,
      maxLoss,
    }
  }

  // Call-credit spread only (cs/cl present, ps/pl irrelevant)
  return null
}

function zeroCrossingX(x0: number, y0: number, x1: number, y1: number): number {
  if (y0 === y1) return x0
  return x0 + (x1 - x0) * (-y0 / (y1 - y0))
}

export default function BriefingTradeOfDay({ trade, macro }: Props) {
  if (!trade) return null
  const { strikes, contracts, pnl, entry_credit, exit_cost } = trade

  // Prefer the canonical strike-derived curve for symmetry; fall back to
  // bot-supplied payoff_points only if strikes are insufficient.
  const canonical = buildCanonicalPayoff(trade)
  const curve: PayoffPoint[] =
    canonical?.curve ??
    (Array.isArray(trade.payoff_points) && trade.payoff_points.length >= 2
      ? trade.payoff_points
      : [])
  if (curve.length < 2) return null

  // ----- X-range: center on strike midpoint when we have one -----
  let displayMin: number
  let displayMax: number
  if (canonical) {
    const halfRange = Math.max(
      canonical.midpoint - canonical.strikeMin,
      canonical.strikeMax - canonical.midpoint,
    )
    // Add ~25% buffer so the flat max-loss tails are visible on both sides.
    const buffer = halfRange * 0.25
    displayMin = canonical.midpoint - halfRange - buffer
    displayMax = canonical.midpoint + halfRange + buffer
  } else {
    const xs = curve.map(p => p.spot)
    displayMin = Math.min(...xs)
    displayMax = Math.max(...xs)
  }
  const xRange = displayMax - displayMin || 1

  // ----- Y-range: from curve, padded -----
  const ys = curve.map(p => p.pnl)
  let minY = Math.min(0, ...ys)
  let maxY = Math.max(0, ...ys)
  if (minY === maxY) { minY -= 1; maxY += 1 }
  const yPad = (maxY - minY) * 0.10
  minY -= yPad
  maxY += yPad
  const yRange = maxY - minY

  const innerW = W - PAD_L - PAD_R
  const innerH = H - PAD_T - PAD_B
  const xToPx = (x: number) => PAD_L + ((x - displayMin) / xRange) * innerW
  const yToPx = (y: number) => PAD_T + (1 - (y - minY) / yRange) * innerH
  const zeroPx = yToPx(0)

  // Clip the canonical curve to the visible X-range so we don't render
  // flat tails past the right edge.
  const visible = curve.filter(p => p.spot >= displayMin && p.spot <= displayMax)
  // Ensure first/last points sit exactly on the display edges.
  if (visible[0]?.spot !== displayMin) visible.unshift({ spot: displayMin, pnl: curve[0].pnl })
  if (visible[visible.length - 1]?.spot !== displayMax) {
    visible.push({ spot: displayMax, pnl: curve[curve.length - 1].pnl })
  }

  const linePath = visible.map((p, i) => {
    const cmd = i === 0 ? 'M' : 'L'
    return `${cmd}${xToPx(p.spot).toFixed(1)},${yToPx(p.pnl).toFixed(1)}`
  }).join(' ')

  // Profit / loss area fills, clipped to the zero baseline.
  const areaPath = (filterFn: (p: PayoffPoint) => boolean): string => {
    const segs = visible.filter(filterFn)
    if (segs.length === 0) return ''
    let path = ''
    for (let i = 0; i < segs.length; i++) {
      const x = xToPx(segs[i].spot).toFixed(1)
      const y = yToPx(segs[i].pnl).toFixed(1)
      path += `${i === 0 ? 'M' : 'L'}${x},${y} `
    }
    const lastX = xToPx(segs[segs.length - 1].spot).toFixed(1)
    const firstX = xToPx(segs[0].spot).toFixed(1)
    path += `L${lastX},${zeroPx.toFixed(1)} L${firstX},${zeroPx.toFixed(1)} Z`
    return path
  }
  const profitArea = areaPath(p => p.pnl >= 0)
  const lossArea   = areaPath(p => p.pnl <= 0)

  // Breakevens (where curve crosses zero).
  const breakevens: number[] = []
  for (let i = 1; i < visible.length; i++) {
    const a = visible[i - 1]
    const b = visible[i]
    if ((a.pnl < 0 && b.pnl >= 0) || (a.pnl > 0 && b.pnl <= 0)) {
      breakevens.push(zeroCrossingX(a.spot, a.pnl, b.spot, b.pnl))
    }
  }

  // Strike markers (only those visible)
  const strikeMarkers: Array<{ x: number; label: string }> = []
  if (typeof strikes.pl === 'number' && strikes.pl >= displayMin && strikes.pl <= displayMax) {
    strikeMarkers.push({ x: strikes.pl, label: `${strikes.pl}` })
  }
  if (typeof strikes.ps === 'number' && strikes.ps >= displayMin && strikes.ps <= displayMax) {
    strikeMarkers.push({ x: strikes.ps, label: `${strikes.ps}` })
  }
  if (typeof strikes.cs === 'number' && strikes.cs >= displayMin && strikes.cs <= displayMax) {
    strikeMarkers.push({ x: strikes.cs, label: `${strikes.cs}` })
  }
  if (typeof strikes.cl === 'number' && strikes.cl >= displayMin && strikes.cl <= displayMax) {
    strikeMarkers.push({ x: strikes.cl, label: `${strikes.cl}` })
  }

  const spot = macro?.spy_close
  const showSpot = typeof spot === 'number' && spot >= displayMin && spot <= displayMax

  // Quartile gridlines on the Y axis for a more "grown-up" chart feel.
  const yTicks = [maxY, minY + (maxY - minY) * 0.66, minY + (maxY - minY) * 0.33, minY]

  const curveMaxPnl = canonical ? canonical.maxProfit : Math.max(...ys)
  const curveMinPnl = canonical ? -canonical.maxLoss : Math.min(...ys)

  return (
    <div className="bg-forge-card rounded-lg p-4">
      <div className="flex items-baseline justify-between mb-1">
        <h3 className="text-amber-300 text-sm uppercase tracking-wider">Trade of the Day</h3>
        <span className={pnl >= 0 ? 'text-emerald-400 font-semibold' : 'text-red-400 font-semibold'}>
          {fmtMoney(pnl)}
        </span>
      </div>
      <div className="text-xs text-gray-400 mb-3">
        {contracts}× {strikes.ps}/{strikes.pl}p
        {strikes.cs ? ` · ${strikes.cs}/${strikes.cl}c` : ''}
        {' · '}in {entry_credit.toFixed(2)} → out {exit_cost.toFixed(2)}
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} width="100%"
        style={{ display: 'block', fontFamily: FONT }} className="overflow-visible">
        <defs>
          <linearGradient id="payoffProfitFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"  stopColor="#34d399" stopOpacity={0.32} />
            <stop offset="100%" stopColor="#34d399" stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="payoffLossFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"  stopColor="#f87171" stopOpacity={0.02} />
            <stop offset="100%" stopColor="#f87171" stopOpacity={0.30} />
          </linearGradient>
        </defs>

        {/* Plot-area background bevel — soft inner shadow */}
        <rect x={PAD_L} y={PAD_T} width={innerW} height={innerH}
          fill="#0e1014" stroke="#1f2937" strokeWidth={1} rx={3} />

        {/* Y-axis quartile gridlines */}
        {yTicks.map((yv, i) => (
          <g key={i}>
            <line
              x1={PAD_L} y1={yToPx(yv)} x2={PAD_L + innerW} y2={yToPx(yv)}
              stroke="#1f2937" strokeWidth={1}
              strokeDasharray={i === 0 || i === yTicks.length - 1 ? undefined : '2,4'}
            />
            <text x={PAD_L - 8} y={yToPx(yv) + 3.5} textAnchor="end"
              fontSize={10.5} fontWeight={500} fill="#9ca3af">
              {fmtMoney(yv)}
            </text>
          </g>
        ))}

        {/* Strike vertical guides — subtle, behind areas */}
        {strikeMarkers.map((s, i) => {
          const x = xToPx(s.x)
          return (
            <g key={`sk${i}`}>
              <line x1={x} y1={PAD_T} x2={x} y2={PAD_T + innerH}
                stroke="#374151" strokeWidth={1} strokeDasharray="1,3" />
              <text x={x} y={H - 24} textAnchor="middle"
                fontSize={10} fontWeight={500} fill="#9ca3af">
                {s.label}
              </text>
            </g>
          )
        })}

        {/* Profit + loss area fills */}
        {profitArea ? <path d={profitArea} fill="url(#payoffProfitFill)" /> : null}
        {lossArea   ? <path d={lossArea}   fill="url(#payoffLossFill)" />   : null}

        {/* Zero baseline — bolder */}
        <line x1={PAD_L} y1={zeroPx} x2={PAD_L + innerW} y2={zeroPx}
          stroke="#6b7280" strokeWidth={1} />

        {/* Payoff curve */}
        <path d={linePath} fill="none" stroke="#fbbf24" strokeWidth={2}
          strokeLinejoin="round" strokeLinecap="round" />

        {/* Strike inflection points — small filled dots for a finished feel */}
        {strikeMarkers.map((s, i) => {
          const cx = xToPx(s.x)
          // Find the curve y at this x (curve is piecewise linear).
          let cy = zeroPx
          for (let j = 1; j < visible.length; j++) {
            const a = visible[j - 1]; const b = visible[j]
            if (s.x >= a.spot && s.x <= b.spot) {
              const t = b.spot === a.spot ? 0 : (s.x - a.spot) / (b.spot - a.spot)
              cy = yToPx(a.pnl + (b.pnl - a.pnl) * t)
              break
            }
          }
          return (
            <circle key={`skd${i}`} cx={cx} cy={cy} r={2.5}
              fill="#fbbf24" stroke="#0b0b0d" strokeWidth={1} />
          )
        })}

        {/* Breakeven crossings */}
        {breakevens.map((bx, i) => {
          const x = xToPx(bx)
          return (
            <g key={`be${i}`}>
              <circle cx={x} cy={zeroPx} r={3.5}
                fill="#0b0b0d" stroke="#fbbf24" strokeWidth={1.5} />
              <line x1={x} y1={PAD_T + innerH} x2={x} y2={PAD_T + innerH + 5}
                stroke="#fbbf24" strokeWidth={1} />
              <text x={x} y={PAD_T + innerH + 16} textAnchor="middle"
                fontSize={10} fontWeight={500} fill="#fbbf24">
                {fmtSpot(bx)}
              </text>
            </g>
          )
        })}

        {/* Spot-at-close marker */}
        {showSpot && spot !== undefined ? (() => {
          const sx = xToPx(spot)
          return (
            <g>
              <line x1={sx} y1={PAD_T - 4} x2={sx} y2={PAD_T + innerH}
                stroke="#e5e7eb" strokeWidth={1.25} strokeDasharray="2,3" />
              <rect x={sx - 36} y={PAD_T - 18} rx={3} ry={3} width={72} height={15}
                fill="#0b0b0d" stroke="#e5e7eb" strokeWidth={0.75} />
              <text x={sx} y={PAD_T - 7} textAnchor="middle"
                fontSize={10.5} fontWeight={600} fill="#e5e7eb">
                SPY {fmtSpot(spot)}
              </text>
            </g>
          )
        })() : null}

        {/* X-axis label */}
        <text x={PAD_L + innerW / 2} y={H - 6} textAnchor="middle"
          fontSize={10} fontWeight={500} fill="#6b7280" letterSpacing="0.04em">
          SPOT PRICE
        </text>
      </svg>

      <div className="mt-2 flex items-center justify-between text-[11px] text-gray-500">
        <span>Max profit <span className="text-emerald-400 font-medium ml-1">{fmtMoney(curveMaxPnl)}</span></span>
        <span>Breakeven{breakevens.length > 1 ? 's' : ''}{' '}
          <span className="text-amber-300 font-medium ml-1">
            {breakevens.length === 0 ? '—' : breakevens.map(b => fmtSpot(b)).join(' / ')}
          </span>
        </span>
        <span>Max loss <span className="text-red-400 font-medium ml-1">{fmtMoney(curveMinPnl)}</span></span>
      </div>
    </div>
  )
}
