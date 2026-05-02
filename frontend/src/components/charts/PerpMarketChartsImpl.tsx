'use client'

import { useMemo } from 'react'
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts'

interface PricePoint { time: number; close: number; high: number; low: number; volume: number }
interface LSPoint { time: number; ratio: number; long_pct: number; short_pct: number }
interface OIPoint { time: number; total_usd: number }
interface FundingPoint { time: number; rate: number }

export interface PerpChartData {
  ticker: string
  price: PricePoint[]
  ls_ratio: LSPoint[]
  open_interest: OIPoint[]
  funding: FundingPoint[]
  fetched_at: number
  cache_age_seconds: number
  interval: string
  lookback_days: number
}

const fmtTimeShort = (ms: number) => {
  const d = new Date(ms)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'America/Chicago' })
}
const fmtTimeFull = (ms: number) => {
  const d = new Date(ms)
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', timeZone: 'America/Chicago' })
}

const fmtUSD = (n: number) => {
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`
  if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`
  if (n >= 1e3) return `$${(n / 1e3).toFixed(1)}K`
  return `$${n.toFixed(2)}`
}

// Merge two timestamped series into one array of {time, priceClose, otherField}
// for ComposedChart (overlay charts need unified rows).
function mergeSeries<T extends { time: number }, U extends { time: number }>(
  primary: T[], secondary: U[],
): Array<T & Partial<U>> {
  if (!primary.length) return []
  // Build a lookup of secondary values keyed by nearest hour
  const secMap = new Map<number, U>()
  secondary.forEach((s) => secMap.set(Math.floor(s.time / 3600000), s))
  return primary.map((p) => {
    const key = Math.floor(p.time / 3600000)
    // walk backward up to 4 hours to find a matching point
    let match: U | undefined
    for (let k = 0; k <= 4; k++) {
      match = secMap.get(key - k)
      if (match) break
    }
    return { ...p, ...(match || {}) } as T & Partial<U>
  })
}

interface Props { data: PerpChartData | null; loading?: boolean }

export default function PerpMarketChartsImpl({ data, loading }: Props) {
  const lsMerged = useMemo(() => mergeSeries(data?.price || [], data?.ls_ratio || []), [data])
  const oiMerged = useMemo(() => mergeSeries(data?.price || [], data?.open_interest || []), [data])
  const fundingData = data?.funding || []

  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-[#0a0a0a] border border-gray-800 rounded-lg p-6 animate-pulse">
            <div className="h-6 bg-gray-800 rounded w-1/3 mb-4" />
            <div className="h-72 bg-gray-800/50 rounded" />
          </div>
        ))}
      </div>
    )
  }

  if (!data || (!data.price.length && !data.ls_ratio.length)) {
    return (
      <div className="bg-[#0a0a0a] border border-gray-800 rounded-lg p-6 text-center text-gray-400">
        No chart data yet. CoinGlass v4 history may take a few minutes after first fetch.
      </div>
    )
  }

  const ticker = data.ticker

  return (
    <div className="space-y-6">
      {/* L/S Ratio overlaid on price */}
      <div className="bg-[#0a0a0a] border border-gray-800 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-lg font-semibold text-white">L/S Ratio vs Price ({ticker})</h3>
            <p className="text-xs text-gray-400">
              Green line: % of accounts long. Above 60% = crowded longs (contrarian short). Below 40% = crowded shorts (contrarian long).
            </p>
          </div>
          <div className="text-xs text-gray-500">{data.lookback_days}d / {data.interval}</div>
        </div>
        <ResponsiveContainer width="100%" height={300}>
          <ComposedChart data={lsMerged}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="time" tickFormatter={fmtTimeShort} stroke="#6b7280" fontSize={11} />
            <YAxis yAxisId="price" orientation="left" stroke="#9ca3af" fontSize={11}
              tickFormatter={(v) => `$${v < 1 ? v.toFixed(4) : v.toFixed(0)}`} />
            <YAxis yAxisId="ls" orientation="right" stroke="#22c55e" fontSize={11}
              domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
            <Tooltip
              labelFormatter={fmtTimeFull}
              contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: 6 }}
              formatter={(v: number, name: string) => {
                if (name === 'close') return [`$${v < 1 ? v.toFixed(6) : v.toFixed(2)}`, 'Price']
                if (name === 'long_pct') return [`${v.toFixed(1)}%`, '% Long Accounts']
                return [v, name]
              }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <ReferenceLine yAxisId="ls" y={50} stroke="#475569" strokeDasharray="4 4" label={{ value: '50% (balanced)', fill: '#64748b', fontSize: 10 }} />
            <Line yAxisId="price" type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} dot={false} name="Price" />
            <Line yAxisId="ls" type="monotone" dataKey="long_pct" stroke="#22c55e" strokeWidth={2} dot={false} name="% Long" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* OI overlaid on price */}
      <div className="bg-[#0a0a0a] border border-gray-800 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-lg font-semibold text-white">Open Interest vs Price ({ticker})</h3>
            <p className="text-xs text-gray-400">
              Rising OI + rising price = real trend. Rising OI + falling price = aggressive shorts. Falling OI = positions unwinding.
            </p>
          </div>
          <div className="text-xs text-gray-500">{data.lookback_days}d / {data.interval}</div>
        </div>
        <ResponsiveContainer width="100%" height={300}>
          <ComposedChart data={oiMerged}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="time" tickFormatter={fmtTimeShort} stroke="#6b7280" fontSize={11} />
            <YAxis yAxisId="price" orientation="left" stroke="#9ca3af" fontSize={11}
              tickFormatter={(v) => `$${v < 1 ? v.toFixed(4) : v.toFixed(0)}`} />
            <YAxis yAxisId="oi" orientation="right" stroke="#a855f7" fontSize={11}
              tickFormatter={fmtUSD} />
            <Tooltip
              labelFormatter={fmtTimeFull}
              contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: 6 }}
              formatter={(v: number, name: string) => {
                if (name === 'close') return [`$${v < 1 ? v.toFixed(6) : v.toFixed(2)}`, 'Price']
                if (name === 'total_usd') return [fmtUSD(v), 'Open Interest']
                return [v, name]
              }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Area yAxisId="oi" type="monotone" dataKey="total_usd" stroke="#a855f7" fill="#a855f7" fillOpacity={0.15} name="Open Interest" />
            <Line yAxisId="price" type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} dot={false} name="Price" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Funding rate timeline */}
      <div className="bg-[#0a0a0a] border border-gray-800 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-lg font-semibold text-white">Funding Rate ({ticker})</h3>
            <p className="text-xs text-gray-400">
              Positive = longs pay shorts (longs over-leveraged). Negative = shorts pay longs (shorts over-leveraged). Sustained extremes precede reversals.
            </p>
          </div>
          <div className="text-xs text-gray-500">{data.lookback_days}d / {data.interval}</div>
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <ComposedChart data={fundingData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="time" tickFormatter={fmtTimeShort} stroke="#6b7280" fontSize={11} />
            <YAxis stroke="#9ca3af" fontSize={11}
              tickFormatter={(v) => `${(v * 100).toFixed(3)}%`} />
            <Tooltip
              labelFormatter={fmtTimeFull}
              contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: 6 }}
              formatter={(v: number) => [`${(v * 100).toFixed(4)}% (annualized ${(v * 3 * 365 * 100).toFixed(1)}%)`, 'Funding']}
            />
            <ReferenceLine y={0} stroke="#64748b" strokeDasharray="2 2" />
            <Area type="monotone" dataKey="rate" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.2} name="Funding Rate" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="text-right text-xs text-gray-500">
        Cache age: {data.cache_age_seconds}s · Fetched: {fmtTimeFull(data.fetched_at)}
      </div>
    </div>
  )
}
