'use client'

import { useEffect, useMemo, useState } from 'react'
import useSWR from 'swr'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'
import { TrendingUp } from 'lucide-react'

const API = process.env.NEXT_PUBLIC_API_URL || ''

const fetcher = (url: string) =>
  fetch(url).then(r => {
    if (!r.ok) throw new Error(`API error ${r.status}`)
    return r.json()
  })

export type ChartBot = {
  bot_id: string
  label: string
  color: string
  apiPrefix: string
}

export type Mode = 'indexed' | 'percent'
export type WindowKey = '7d' | '30d' | '90d' | 'all'

const WINDOW_DAYS: Record<WindowKey, number> = {
  '7d': 7,
  '30d': 30,
  '90d': 90,
  all: 3650,
}

type EquityCurvePoint = { date: string; equity: number }
type EquityCurveResponse = {
  data?: { equity_curve?: EquityCurvePoint[]; starting_capital?: number }
  equity_curve?: EquityCurvePoint[]
  starting_capital?: number
}

type SeriesInput = {
  bot_id: string
  label: string
  color?: string
  starting_capital: number
  equity_curve: EquityCurvePoint[]
}

type SeriesOutput = {
  bot_id: string
  label: string
  color: string
  points: { date: string; value: number }[]
}

const HIDDEN_KEY = 'agape-perp-chart-hidden-bots'

/**
 * Pure normalization helper, exported for testing.
 * - 'indexed' rebases each bot's first in-window point to 100.
 * - 'percent' computes (equity - starting_capital) / starting_capital * 100.
 * Bots with no in-window points are excluded.
 */
export function normalizeForChart(
  bots: SeriesInput[],
  opts: { mode: Mode; windowDays: number },
): SeriesOutput[] {
  const cutoff = Date.now() - opts.windowDays * 86_400_000
  const series: SeriesOutput[] = []
  for (const b of bots) {
    const inWindow = b.equity_curve.filter(p => new Date(p.date).getTime() >= cutoff)
    if (inWindow.length === 0) continue
    const color = b.color || '#888'
    if (opts.mode === 'indexed') {
      const base = inWindow[0].equity
      if (!base || base <= 0) continue
      series.push({
        bot_id: b.bot_id,
        label: b.label,
        color,
        points: inWindow.map(p => ({ date: p.date, value: (p.equity / base) * 100 })),
      })
    } else {
      const start = b.starting_capital
      if (!start || start <= 0) continue
      series.push({
        bot_id: b.bot_id,
        label: b.label,
        color,
        points: inWindow.map(p => ({
          date: p.date,
          value: ((p.equity - start) / start) * 100,
        })),
      })
    }
  }
  return series
}

function useEquityCurves(bots: ChartBot[], days: number) {
  // One useSWR per bot index. Bots array length is stable per parent contract.
  return bots.map(b =>
    // eslint-disable-next-line react-hooks/rules-of-hooks
    useSWR<EquityCurveResponse>(
      `${API}${b.apiPrefix}/equity-curve?days=${days}`,
      fetcher,
      { refreshInterval: 60_000, dedupingInterval: 30_000 },
    ),
  )
}

type Props = {
  bots: ChartBot[]
  defaultMode?: Mode
  defaultWindow?: WindowKey
  height?: number
}

export function MultiBotPerpEquityChart({
  bots,
  defaultMode = 'indexed',
  defaultWindow = '30d',
  height = 360,
}: Props) {
  const [mode, setMode] = useState<Mode>(defaultMode)
  const [windowKey, setWindowKey] = useState<WindowKey>(defaultWindow)
  const [hidden, setHidden] = useState<Set<string>>(() => {
    if (typeof window === 'undefined') return new Set()
    try {
      const raw = window.localStorage.getItem(HIDDEN_KEY)
      return new Set(raw ? JSON.parse(raw) : [])
    } catch {
      return new Set()
    }
  })

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(HIDDEN_KEY, JSON.stringify(Array.from(hidden)))
    } catch {
      // ignore quota / privacy mode
    }
  }, [hidden])

  const days = WINDOW_DAYS[windowKey]
  const responses = useEquityCurves(bots, days)

  const inputs: SeriesInput[] = useMemo(
    () =>
      bots.map((b, i) => {
        const r = responses[i].data
        const ec = r?.data?.equity_curve ?? r?.equity_curve ?? []
        const start = r?.data?.starting_capital ?? r?.starting_capital ?? 0
        return {
          bot_id: b.bot_id,
          label: b.label,
          color: b.color,
          starting_capital: start,
          equity_curve: ec,
        }
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [bots, ...responses.map(r => r.data)],
  )

  const series = useMemo(
    () => normalizeForChart(inputs, { mode, windowDays: days }),
    [inputs, mode, days],
  )

  // Build a unified date axis: union of all visible bots' dates.
  const merged = useMemo(() => {
    const dates = new Set<string>()
    series.forEach(s => {
      if (!hidden.has(s.bot_id)) s.points.forEach(p => dates.add(p.date))
    })
    const sortedDates = Array.from(dates).sort()
    return sortedDates.map(d => {
      const row: Record<string, any> = { date: d }
      series.forEach(s => {
        if (hidden.has(s.bot_id)) return
        const pt = s.points.find(p => p.date === d)
        row[s.bot_id] = pt ? pt.value : null
      })
      return row
    })
  }, [series, hidden])

  const isLoading = responses.some(r => r.isLoading)

  function toggleBot(bot_id: string) {
    setHidden(h => {
      const next = new Set(h)
      if (next.has(bot_id)) next.delete(bot_id)
      else next.add(bot_id)
      return next
    })
  }

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800">
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-gray-800 flex-wrap">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-cyan-400" />
          <h3 className="text-sm font-medium text-gray-200">Bot Performance Comparison</h3>
          <span className="text-xs text-gray-500">
            {mode === 'indexed' ? 'Indexed (100 = window start)' : '% from inception'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            {(['7d', '30d', '90d', 'all'] as WindowKey[]).map(w => (
              <button
                key={w}
                type="button"
                onClick={() => setWindowKey(w)}
                className={`px-2 py-1 text-xs rounded border ${
                  windowKey === w
                    ? 'bg-cyan-600/30 border-cyan-500 text-cyan-200'
                    : 'border-gray-700 text-gray-400 hover:bg-gray-800'
                }`}
              >
                {w === 'all' ? 'All' : w}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setMode('indexed')}
              className={`px-2 py-1 text-xs rounded border ${
                mode === 'indexed'
                  ? 'bg-fuchsia-600/30 border-fuchsia-500 text-fuchsia-200'
                  : 'border-gray-700 text-gray-400 hover:bg-gray-800'
              }`}
            >
              Indexed
            </button>
            <button
              type="button"
              onClick={() => setMode('percent')}
              className={`px-2 py-1 text-xs rounded border ${
                mode === 'percent'
                  ? 'bg-fuchsia-600/30 border-fuchsia-500 text-fuchsia-200'
                  : 'border-gray-700 text-gray-400 hover:bg-gray-800'
              }`}
            >
              % from inception
            </button>
          </div>
        </div>
      </div>

      <div className="p-4">
        {isLoading && merged.length === 0 ? (
          <div className="text-gray-500 text-sm text-center py-12">Loading equity curves…</div>
        ) : merged.length === 0 ? (
          <div className="text-gray-500 text-sm text-center py-12">
            No equity data in this window for the selected bots.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={height}>
            <LineChart data={merged} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
              <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
              <XAxis dataKey="date" stroke="#6b7280" tick={{ fontSize: 11 }} />
              <YAxis
                stroke="#6b7280"
                tick={{ fontSize: 11 }}
                tickFormatter={(v: number) =>
                  mode === 'indexed' ? `${v.toFixed(0)}` : `${v.toFixed(1)}%`
                }
              />
              <Tooltip
                contentStyle={{ background: '#0b1020', border: '1px solid #1f2937', fontSize: 12 }}
                formatter={(v: any) =>
                  mode === 'indexed' ? `${Number(v).toFixed(2)}` : `${Number(v).toFixed(2)}%`
                }
              />
              <Legend
                onClick={(e: any) => toggleBot(e.dataKey)}
                wrapperStyle={{ fontSize: 12, cursor: 'pointer' }}
              />
              {series.map(s => (
                <Line
                  key={s.bot_id}
                  type="monotone"
                  dataKey={s.bot_id}
                  name={s.label}
                  stroke={s.color}
                  dot={false}
                  strokeWidth={2}
                  hide={hidden.has(s.bot_id)}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
