'use client'

/**
 * JoshuaEquityChart - intraday + historical equity curve for /api/joshua/.
 *
 * Split out from page.tsx so Recharts is dynamic-imported (per common-mistakes
 * rule 9.2: "Lazy-load heavy pages") and not pulled into the JOSHUA route's
 * initial bundle.
 */

import React, { useState } from 'react'
import useSWR from 'swr'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, ReferenceLine,
} from 'recharts'
import { TrendingUp, RefreshCw } from 'lucide-react'
import { api } from '@/lib/api'

const SWR_OPTS = {
  revalidateOnFocus: false,
  revalidateOnReconnect: false,
  dedupingInterval: 60_000,
  keepPreviousData: true,
} as const

async function fetcher(url: string) {
  try {
    const res = await api.get(url)
    return res.data
  } catch {
    return { success: false, data: null }
  }
}

function formatCurrency(value: number | null | undefined): string {
  const v = typeof value === 'number' && !isNaN(value) ? value : 0
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(v)
}

function formatCurrencyDetail(value: number | null | undefined): string {
  const v = typeof value === 'number' && !isNaN(value) ? value : 0
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(v)
}

function formatTimeCT(ts: string | null | undefined): string {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleTimeString('en-US', {
      timeZone: 'America/Chicago',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    }) + ' CT'
  } catch {
    return ts
  }
}

export default function JoshuaEquityChart() {
  const [mode, setMode] = useState<'intraday' | 'historical'>('intraday')

  const intradayResp = useSWR(
    'joshua-equity-intraday-chart',
    () => fetcher('/api/joshua/equity-curve/intraday'),
    { ...SWR_OPTS, refreshInterval: 30_000 }
  )
  const historicalResp = useSWR(
    'joshua-equity-curve-chart',
    () => fetcher('/api/joshua/equity-curve'),
    { ...SWR_OPTS, refreshInterval: 60_000 }
  )

  const startingCapital = (mode === 'intraday'
    ? (intradayResp.data?.starting_capital ?? 0)
    : (historicalResp.data?.starting_capital ?? 0)) || 0

  const points: Array<{ timestamp: string; equity: number; label: string }> = mode === 'intraday'
    ? (intradayResp.data?.data_points ?? []).map((p: any) => ({
        timestamp: p?.timestamp ?? '',
        equity: typeof p?.equity === 'number' ? p.equity : 0,
        label: formatTimeCT(p?.timestamp),
      }))
    : (historicalResp.data?.data ?? []).map((p: any) => ({
        timestamp: p?.timestamp ?? '',
        equity: typeof p?.equity === 'number' ? p.equity : 0,
        label: p?.timestamp
          ? new Date(p.timestamp).toLocaleDateString('en-US', {
              timeZone: 'America/Chicago', month: 'short', day: '2-digit',
            })
          : '',
      }))

  const isLoading = mode === 'intraday' ? intradayResp.isLoading : historicalResp.isLoading

  return (
    <div className="bg-[#0a0a0a] rounded-xl border border-gray-800 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <div className="flex items-center gap-3 text-emerald-400">
          <TrendingUp className="w-5 h-5" />
          <h3 className="font-semibold text-white">JOSHUA Equity Curve</h3>
        </div>
        <div className="flex gap-1 bg-gray-900/50 rounded-md p-0.5">
          <button
            className={`text-xs px-2.5 py-1 rounded transition-colors ${
              mode === 'intraday' ? 'bg-emerald-500/20 text-emerald-300' : 'text-gray-500 hover:text-gray-300'
            }`}
            onClick={() => setMode('intraday')}
          >
            Intraday
          </button>
          <button
            className={`text-xs px-2.5 py-1 rounded transition-colors ${
              mode === 'historical' ? 'bg-emerald-500/20 text-emerald-300' : 'text-gray-500 hover:text-gray-300'
            }`}
            onClick={() => setMode('historical')}
          >
            Historical
          </button>
        </div>
      </div>
      <div className="p-4">
        {isLoading ? (
          <div className="h-64 flex items-center justify-center text-gray-500">
            <RefreshCw className="w-5 h-5 animate-spin mr-2" /> Loading...
          </div>
        ) : points.length === 0 ? (
          <div className="text-center py-8 px-4">
            <div className="flex justify-center mb-3 text-gray-600">
              <TrendingUp className="w-8 h-8" />
            </div>
            <h4 className="text-lg font-medium text-gray-300 mb-1">
              {mode === 'intraday' ? 'No intraday data yet' : 'No closed trades yet'}
            </h4>
            <p className="text-sm text-gray-500">
              {mode === 'intraday'
                ? 'Snapshots will appear here once the bot runs today'
                : 'The equity curve will draw after the first closed trade'}
            </p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={points} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis
                dataKey="label"
                tick={{ fill: '#9ca3af', fontSize: 11 }}
                stroke="#374151"
              />
              <YAxis
                tick={{ fill: '#9ca3af', fontSize: 11 }}
                stroke="#374151"
                tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
                domain={['auto', 'auto']}
              />
              <Tooltip
                contentStyle={{ background: '#0a0a0a', border: '1px solid #1f2937', borderRadius: 6 }}
                labelStyle={{ color: '#9ca3af' }}
                formatter={(value: number) => [formatCurrencyDetail(value), 'Equity']}
              />
              {startingCapital > 0 && (
                <ReferenceLine
                  y={startingCapital}
                  stroke="#6b7280"
                  strokeDasharray="3 3"
                  label={{
                    value: `Start ${formatCurrency(startingCapital)}`,
                    fill: '#6b7280',
                    fontSize: 10,
                    position: 'right',
                  }}
                />
              )}
              <Line
                type="monotone"
                dataKey="equity"
                stroke="#10b981"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: '#10b981' }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
