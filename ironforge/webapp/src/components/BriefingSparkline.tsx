import type { SparklinePoint } from '@/lib/forgeBriefings/types'

/**
 * 7-day cumulative-P&L chart shown at the bottom of every briefing card and
 * inside the weekly synthesis hero. Compact but readable: zero baseline,
 * Y-axis min/max, X-axis date endpoints, end-point dot + value chip,
 * subtle area fill in the line color.
 */
interface Props {
  data: SparklinePoint[] | null
  /** When true (default), renders the full chart with axes/labels. When false,
   *  renders a tiny line-only sparkline (used as a calendar-cell glyph). */
  withAxes?: boolean
  width?: number
  height?: number
}

const PAD_L = 38   // room for Y-axis $ labels
const PAD_R = 56   // room for end-of-line $ chip
const PAD_T = 10
const PAD_B = 22   // room for X-axis date labels

function fmtMoney(n: number): string {
  const sign = n >= 0 ? '+' : '−'
  const abs = Math.abs(n)
  if (abs >= 1000) return `${sign}$${(abs / 1000).toFixed(1)}k`
  return `${sign}$${abs.toFixed(0)}`
}

function fmtDateShort(iso: string): string {
  // Expecting YYYY-MM-DD
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!m) return iso
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  return `${months[Number(m[2]) - 1]} ${Number(m[3])}`
}

export default function BriefingSparkline({
  data,
  withAxes = true,
  width = 480,
  height = 140,
}: Props) {
  if (!data || data.length < 2) {
    return (
      <div className="text-xs text-gray-500 italic">No equity data yet.</div>
    )
  }

  const ys = data.map(p => p.cumulative_pnl)
  // Pad the y-range so the line never sits flush against the top/bottom.
  let minY = Math.min(0, ...ys)
  let maxY = Math.max(0, ...ys)
  if (minY === maxY) { minY -= 1; maxY += 1 }
  const yPad = (maxY - minY) * 0.1
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

  // Area fill underneath the line, clipped to the zero baseline.
  const zeroPx = yToPx(0)
  const areaPath = `${linePath} L${xToPx(data.length - 1).toFixed(1)},${zeroPx.toFixed(1)} L${xToPx(0).toFixed(1)},${zeroPx.toFixed(1)} Z`

  const last = ys[ys.length - 1]
  const first = ys[0]
  const positive = last >= first
  const stroke = positive ? '#34d399' : '#f87171'
  const fillId = positive ? 'sparkFillUp' : 'sparkFillDown'

  // Tiny variant: line only, no decorations.
  if (!withAxes) {
    return (
      <svg width={width} height={height} className="overflow-visible">
        <path d={linePath} fill="none" stroke={stroke} strokeWidth={1.5} />
      </svg>
    )
  }

  const lastX = xToPx(data.length - 1)
  const lastY = yToPx(last)

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      style={{ maxWidth: width, display: 'block' }}
      className="overflow-visible"
    >
      <defs>
        <linearGradient id="sparkFillUp" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#34d399" stopOpacity={0.30} />
          <stop offset="100%" stopColor="#34d399" stopOpacity={0.0} />
        </linearGradient>
        <linearGradient id="sparkFillDown" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#f87171" stopOpacity={0.30} />
          <stop offset="100%" stopColor="#f87171" stopOpacity={0.0} />
        </linearGradient>
      </defs>

      {/* Y-axis min/max labels */}
      <text x={PAD_L - 6} y={PAD_T + 4} textAnchor="end" fontSize={10} fill="#9ca3af">{fmtMoney(maxY)}</text>
      <text x={PAD_L - 6} y={PAD_T + innerH + 2} textAnchor="end" fontSize={10} fill="#9ca3af">{fmtMoney(minY)}</text>

      {/* Zero baseline */}
      {minY < 0 && maxY > 0 && (
        <>
          <line x1={PAD_L} y1={zeroPx} x2={PAD_L + innerW} y2={zeroPx}
            stroke="#374151" strokeDasharray="3,3" strokeWidth={1} />
          <text x={PAD_L - 6} y={zeroPx + 3} textAnchor="end" fontSize={10} fill="#6b7280">0</text>
        </>
      )}

      {/* Faint vertical guides at first and last point */}
      <line x1={PAD_L} y1={PAD_T} x2={PAD_L} y2={PAD_T + innerH} stroke="#1f2937" strokeWidth={1} />
      <line x1={PAD_L + innerW} y1={PAD_T} x2={PAD_L + innerW} y2={PAD_T + innerH} stroke="#1f2937" strokeWidth={1} />

      {/* Area under line */}
      <path d={areaPath} fill={`url(#${fillId})`} />

      {/* Line */}
      <path d={linePath} fill="none" stroke={stroke} strokeWidth={1.75}
        strokeLinejoin="round" strokeLinecap="round" />

      {/* End-point dot */}
      <circle cx={lastX} cy={lastY} r={3.5} fill={stroke} stroke="#0b0b0d" strokeWidth={1.5} />

      {/* End-of-line value chip */}
      <g transform={`translate(${lastX + 6}, ${lastY})`}>
        <rect x={0} y={-9} rx={3} ry={3} width={50} height={18} fill={stroke} fillOpacity={0.18} stroke={stroke} strokeWidth={0.75} />
        <text x={25} y={4} textAnchor="middle" fontSize={11} fontWeight={600} fill={stroke}>{fmtMoney(last)}</text>
      </g>

      {/* X-axis date endpoints */}
      <text x={PAD_L} y={height - 6} textAnchor="start" fontSize={10} fill="#6b7280">
        {fmtDateShort(data[0].date)}
      </text>
      <text x={PAD_L + innerW} y={height - 6} textAnchor="end" fontSize={10} fill="#6b7280">
        {fmtDateShort(data[data.length - 1].date)}
      </text>
    </svg>
  )
}
