import type { SparklinePoint } from '@/lib/forgeBriefings/types'

/**
 * 7-day cumulative-P&L chart shown at the bottom of every briefing card
 * and inside the weekly synthesis hero.
 *
 * Designed to read as a small but finished financial chart, not a sparkline
 * stub: 4-row gridlines at quartiles of the Y-range, dashed zero baseline,
 * proper sans-serif typography, end-point dot + value chip with absolute
 * value AND total change, and a date tick at every data point so the
 * 7-day cadence reads visually.
 */
interface Props {
  data: SparklinePoint[] | null
  /** When true (default), renders the full chart with axes/labels. When false,
   *  renders a tiny line-only sparkline (used as a calendar-cell glyph). */
  withAxes?: boolean
  width?: number
  height?: number
}

const PAD_L = 52
const PAD_R = 78    // room for the end-of-line value + delta chip
const PAD_T = 14
const PAD_B = 30
const FONT = "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"

function fmtMoney(n: number, withSign = true): string {
  const sign = withSign ? (n >= 0 ? '+' : '−') : ''
  const abs = Math.abs(n)
  if (abs >= 10_000) return `${sign}$${(abs / 1000).toFixed(0)}k`
  if (abs >= 1000)   return `${sign}$${(abs / 1000).toFixed(1)}k`
  if (abs >= 100)    return `${sign}$${abs.toFixed(0)}`
  return `${sign}$${abs.toFixed(2)}`
}

function fmtDateShort(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!m) return iso
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  return `${months[Number(m[2]) - 1]} ${Number(m[3])}`
}

export default function BriefingSparkline({
  data,
  withAxes = true,
  width = 560,
  height = 180,
}: Props) {
  if (!data || data.length < 2) {
    return <div className="text-xs text-gray-500 italic">No equity data yet.</div>
  }

  const ys = data.map(p => p.cumulative_pnl)
  let minY = Math.min(0, ...ys)
  let maxY = Math.max(0, ...ys)
  if (minY === maxY) { minY -= 1; maxY += 1 }
  const yPad = (maxY - minY) * 0.12
  minY -= yPad
  maxY += yPad
  const yRange = maxY - minY

  const innerW = width - PAD_L - PAD_R
  const innerH = height - PAD_T - PAD_B
  const xToPx = (i: number) => PAD_L + (i / (data.length - 1)) * innerW
  const yToPx = (y: number) => PAD_T + (1 - (y - minY) / yRange) * innerH

  const linePath = data.map((p, i) => {
    const cmd = i === 0 ? 'M' : 'L'
    return `${cmd}${xToPx(i).toFixed(1)},${yToPx(p.cumulative_pnl).toFixed(1)}`
  }).join(' ')

  const zeroPx = yToPx(0)
  const areaPath = `${linePath} L${xToPx(data.length - 1).toFixed(1)},${zeroPx.toFixed(1)} L${xToPx(0).toFixed(1)},${zeroPx.toFixed(1)} Z`

  const last  = ys[ys.length - 1]
  const first = ys[0]
  const delta = last - first
  const positive = delta >= 0
  const stroke = positive ? '#34d399' : '#f87171'
  const fillId = positive ? 'sparkFillUp' : 'sparkFillDown'

  // Tiny variant: line only.
  if (!withAxes) {
    return (
      <svg width={width} height={height} className="overflow-visible">
        <path d={linePath} fill="none" stroke={stroke} strokeWidth={1.5} />
      </svg>
    )
  }

  // Y quartile ticks for proper gridlines.
  const yTicks = [maxY, minY + (maxY - minY) * 0.66, minY + (maxY - minY) * 0.33, minY]

  // X tick density: dot at every data point, label every other point so
  // a 7-day series reads cleanly without crowding.
  const labelStride = data.length > 8 ? Math.ceil(data.length / 5) : 1

  const lastX = xToPx(data.length - 1)
  const lastY = yToPx(last)

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      style={{ maxWidth: width, display: 'block', fontFamily: FONT }}
      className="overflow-visible"
    >
      <defs>
        <linearGradient id="sparkFillUp" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"  stopColor="#34d399" stopOpacity={0.32} />
          <stop offset="100%" stopColor="#34d399" stopOpacity={0.0} />
        </linearGradient>
        <linearGradient id="sparkFillDown" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"  stopColor="#f87171" stopOpacity={0.32} />
          <stop offset="100%" stopColor="#f87171" stopOpacity={0.0} />
        </linearGradient>
      </defs>

      {/* Plot area background */}
      <rect x={PAD_L} y={PAD_T} width={innerW} height={innerH}
        fill="#0e1014" stroke="#1f2937" strokeWidth={1} rx={3} />

      {/* Quartile gridlines + Y-axis labels */}
      {yTicks.map((yv, i) => (
        <g key={`y${i}`}>
          <line
            x1={PAD_L} y1={yToPx(yv)} x2={PAD_L + innerW} y2={yToPx(yv)}
            stroke="#1f2937" strokeWidth={1}
            strokeDasharray={i === 0 || i === yTicks.length - 1 ? undefined : '2,4'}
          />
          <text x={PAD_L - 8} y={yToPx(yv) + 3.5} textAnchor="end"
            fontSize={10.5} fontWeight={500} fill="#9ca3af">
            {fmtMoney(yv, false)}
          </text>
        </g>
      ))}

      {/* Zero baseline (only if zero is in range) */}
      {minY < 0 && maxY > 0 && (
        <>
          <line x1={PAD_L} y1={zeroPx} x2={PAD_L + innerW} y2={zeroPx}
            stroke="#6b7280" strokeWidth={1} />
          <text x={PAD_L - 8} y={zeroPx + 3.5} textAnchor="end"
            fontSize={10.5} fontWeight={600} fill="#6b7280">$0</text>
        </>
      )}

      {/* Area fill under the line */}
      <path d={areaPath} fill={`url(#${fillId})`} />

      {/* Data-point dots */}
      {data.map((p, i) => (
        <circle key={`pt${i}`}
          cx={xToPx(i)} cy={yToPx(p.cumulative_pnl)}
          r={2} fill={stroke} fillOpacity={i === data.length - 1 ? 1 : 0.55} />
      ))}

      {/* Line */}
      <path d={linePath} fill="none" stroke={stroke} strokeWidth={2}
        strokeLinejoin="round" strokeLinecap="round" />

      {/* End-point dot + value chip */}
      <circle cx={lastX} cy={lastY} r={4} fill={stroke}
        stroke="#0b0b0d" strokeWidth={1.5} />
      <g transform={`translate(${lastX + 8}, ${lastY})`}>
        <rect x={0} y={-12} rx={3} ry={3} width={64} height={24}
          fill="#0b0b0d" stroke={stroke} strokeWidth={1} />
        <text x={32} y={-1} textAnchor="middle"
          fontSize={11} fontWeight={600} fill={stroke}>
          {fmtMoney(last, false)}
        </text>
        <text x={32} y={9} textAnchor="middle"
          fontSize={9} fontWeight={500} fill={stroke} fillOpacity={0.85}>
          {fmtMoney(delta, true)}
        </text>
      </g>

      {/* X-axis date ticks */}
      {data.map((p, i) => {
        const x = xToPx(i)
        const showLabel = i === 0 || i === data.length - 1 || i % labelStride === 0
        return (
          <g key={`x${i}`}>
            <line x1={x} y1={PAD_T + innerH} x2={x} y2={PAD_T + innerH + 3}
              stroke="#374151" strokeWidth={1} />
            {showLabel && (
              <text x={x} y={height - 8}
                textAnchor={i === 0 ? 'start' : i === data.length - 1 ? 'end' : 'middle'}
                fontSize={10} fontWeight={500} fill="#6b7280">
                {fmtDateShort(p.date)}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}
