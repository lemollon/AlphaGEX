import type { SparklinePoint } from '@/lib/forgeBriefings/types'

export default function BriefingSparkline({ data, width = 220, height = 40 }: { data: SparklinePoint[] | null; width?: number; height?: number }) {
  if (!data || data.length < 2) return null
  const ys = data.map(p => p.cumulative_pnl)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const range = (maxY - minY) || 1
  const path = data.map((p, i) => {
    const x = (i / (data.length - 1)) * width
    const y = height - ((p.cumulative_pnl - minY) / range) * height
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  const last = ys[ys.length - 1]
  const positive = last >= ys[0]
  return (
    <div className="flex items-center gap-3">
      <svg width={width} height={height}>
        <path d={path} fill="none" stroke={positive ? '#34d399' : '#f87171'} strokeWidth={2} />
      </svg>
      <span className={`text-sm ${positive ? 'text-emerald-400' : 'text-red-400'}`}>
        {positive ? '+' : ''}${last.toFixed(2)}
      </span>
    </div>
  )
}
