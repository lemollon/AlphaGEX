'use client'

import { useState, useEffect, useMemo } from 'react'
import { Calendar, TrendingDown, AlertTriangle, Info, RefreshCw, Target } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell, ReferenceLine } from 'recharts'
import { apiClient } from '@/lib/api'

interface ExpirationData {
  expiration_date: string
  dte: number
  expiration_type: string
  total_gamma_expiring: number
  strikes_count: number
}

interface StrikeData {
  strike: number
  total_gamma: number
  distance_pct: number
  call_gamma: number
  put_gamma: number
}

interface GammaWaterfallData {
  expirations: ExpirationData[]
  strikes_by_expiration: Record<string, StrikeData[]>
  current_price: number
  net_gex: number
  summary: {
    total_expirations: number
    total_gamma_next_7d: number
    total_gamma_next_30d: number
    major_expiration: string
    major_expiration_gamma: number
  }
}

interface WaterfallChartData {
  date: string
  dte: number
  type: string
  gamma: number
  gammaB: number
  persistence: number
  label: string
}

export default function GammaExpirationWaterfall({ symbol = 'SPY' }: { symbol?: string }) {
  const [data, setData] = useState<GammaWaterfallData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedExpiration, setSelectedExpiration] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'timeline' | 'persistence'>('timeline')

  const fetchData = async () => {
    try {
      setLoading(true)
      setError(null)

      const response = await apiClient.getGammaExpirationWaterfall(symbol)

      // Handle both success:true pattern and direct data response
      if (response.data.success !== false) {
        const result = response.data.data || response.data
        setData(result)
      } else {
        throw new Error('Failed to load gamma expiration data')
      }
    } catch (err: any) {
      console.error('Error fetching waterfall data:', err)
      setError(err.message || 'Failed to load gamma expiration data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    // Refresh every 5 minutes
    const interval = setInterval(fetchData, 5 * 60 * 1000)
    return () => clearInterval(interval)
  }, [symbol])

  // Prepare waterfall chart data
  const waterfallChartData = useMemo(() => {
    if (!data?.expirations) return []

    let cumulativeGamma = 0
    const chartData: WaterfallChartData[] = []

    for (const exp of data.expirations.slice(0, 10)) {
      const gammaB = exp.total_gamma_expiring / 1e9
      cumulativeGamma += gammaB

      // Calculate persistence (gamma remaining after this expiration)
      const totalGamma = data.expirations.reduce((sum, e) => sum + e.total_gamma_expiring, 0)
      const remainingGamma = totalGamma - (cumulativeGamma * 1e9)
      const persistence = (remainingGamma / totalGamma) * 100

      chartData.push({
        date: new Date(exp.expiration_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        dte: exp.dte,
        type: exp.expiration_type,
        gamma: exp.total_gamma_expiring,
        gammaB: gammaB,
        persistence: persistence,
        label: `${exp.dte}d`
      })
    }

    return chartData
  }, [data])

  // Calculate cumulative decay
  const decayAnalysis = useMemo(() => {
    if (!data?.expirations) return []

    const totalGamma = data.expirations.reduce((sum, e) => sum + e.total_gamma_expiring, 0)
    let cumulative = 0

    return data.expirations.slice(0, 10).map((exp) => {
      cumulative += exp.total_gamma_expiring
      const percentDecayed = (cumulative / totalGamma) * 100

      return {
        date: exp.expiration_date,
        dte: exp.dte,
        type: exp.expiration_type,
        gammaExpiring: exp.total_gamma_expiring / 1e9,
        percentDecayed: percentDecayed,
        percentRemaining: 100 - percentDecayed
      }
    })
  }, [data])

  const getTypeColor = (type: string) => {
    switch (type) {
      case '0dte': return '#ef4444' // red
      case 'weekly': return '#f97316' // orange
      case 'monthly': return '#8b5cf6' // purple
      default: return '#6b7280' // gray
    }
  }

  if (loading) {
    return (
      <div className="rounded-lg border border-gray-800 bg-gray-900/50 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <Calendar className="w-5 h-5 text-purple-500" />
            Gamma Expiration Waterfall
          </h2>
        </div>
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="rounded-lg border border-gray-800 bg-gray-900/50 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <Calendar className="w-5 h-5 text-purple-500" />
            Gamma Expiration Waterfall
          </h2>
        </div>
        <div className="bg-red-500/10 border border-red-500/30 rounded p-4">
          <p className="text-red-400 text-sm">{error || 'No data available'}</p>
          <button onClick={fetchData} className="mt-2 px-3 py-1 text-xs bg-red-500/20 hover:bg-red-500/30 rounded">
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-purple-500/30 bg-gradient-to-br from-purple-500/5 to-blue-500/5 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <Calendar className="w-6 h-6 text-purple-500" />
            Gamma Expiration Waterfall
            <span className="text-sm font-normal text-gray-400">({symbol})</span>
          </h2>
          <p className="text-sm text-gray-400 mt-1">
            How gamma decays day-by-day across expirations
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setViewMode('timeline')}
            className={`px-3 py-1 text-xs rounded ${viewMode === 'timeline' ? 'bg-purple-500 text-white' : 'bg-gray-800 text-gray-400'}`}
          >
            Timeline
          </button>
          <button
            onClick={() => setViewMode('persistence')}
            className={`px-3 py-1 text-xs rounded ${viewMode === 'persistence' ? 'bg-purple-500 text-white' : 'bg-gray-800 text-gray-400'}`}
          >
            Persistence
          </button>
          <button onClick={fetchData} className="p-2 rounded-lg hover:bg-white/5 transition-colors">
            <RefreshCw className="w-4 h-4 text-gray-400 hover:text-white" />
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      {data.summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
            <div className="text-xs text-gray-400 mb-1">Expirations (60d)</div>
            <div className="text-2xl font-bold text-white">{data.summary.total_expirations}</div>
          </div>

          <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
            <div className="text-xs text-gray-400 mb-1">Gamma Next 7d</div>
            <div className="text-2xl font-bold text-orange-400">
              ${(data.summary.total_gamma_next_7d / 1e9).toFixed(1)}B
            </div>
          </div>

          <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
            <div className="text-xs text-gray-400 mb-1">Gamma Next 30d</div>
            <div className="text-2xl font-bold text-purple-400">
              ${(data.summary.total_gamma_next_30d / 1e9).toFixed(1)}B
            </div>
          </div>

          <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
            <div className="text-xs text-gray-400 mb-1">Major OPEX</div>
            <div className="text-xs font-semibold text-purple-400 truncate">
              {new Date(data.summary.major_expiration).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
              <span className="text-gray-500"> (${(data.summary.major_expiration_gamma / 1e9).toFixed(1)}B)</span>
            </div>
          </div>
        </div>
      )}

      {/* Info Banner */}
      <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4 mb-6 flex items-start gap-3">
        <Info className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
        <div className="text-sm text-blue-200">
          <strong>What this shows:</strong> As gamma expires, market structure changes. Walls disappear, price becomes "free" to move.
          High bars = major expirations that will significantly change dynamics.
        </div>
      </div>

      {/* Main Waterfall Chart */}
      <div className="bg-gray-800/30 rounded-lg p-4 mb-6">
        <h3 className="text-sm font-semibold text-gray-300 mb-4">
          {viewMode === 'timeline' ? 'Gamma Expiring by Date' : 'Gamma Persistence Over Time'}
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={waterfallChartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis
              dataKey="date"
              stroke="#9ca3af"
              tick={{ fill: '#9ca3af', fontSize: 12 }}
            />
            <YAxis
              stroke="#9ca3af"
              tick={{ fill: '#9ca3af', fontSize: 12 }}
              label={{ value: viewMode === 'timeline' ? 'Gamma ($B)' : 'Persistence (%)', angle: -90, position: 'insideLeft', fill: '#9ca3af' }}
            />
            <Tooltip
              contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
              labelStyle={{ color: '#f3f4f6' }}
              itemStyle={{ color: '#f3f4f6' }}
              formatter={(value: any, name: string, props: any) => {
                if (viewMode === 'timeline') {
                  return [`$${value.toFixed(2)}B`, `${props.payload.type} (${props.payload.dte}d)`]
                } else {
                  return [`${value.toFixed(1)}%`, 'Remaining']
                }
              }}
            />
            <Legend
              wrapperStyle={{ paddingTop: '20px' }}
              formatter={(value) => <span style={{ color: '#9ca3af' }}>{value}</span>}
            />
            {viewMode === 'timeline' ? (
              <Bar dataKey="gammaB" name="Gamma Expiring" radius={[8, 8, 0, 0]}>
                {waterfallChartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={getTypeColor(entry.type)} />
                ))}
              </Bar>
            ) : (
              <Bar dataKey="persistence" name="Gamma Remaining" fill="#8b5cf6" radius={[8, 8, 0, 0]} />
            )}
            {data.current_price && (
              <ReferenceLine y={0} stroke="#6b7280" strokeDasharray="3 3" />
            )}
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Decay Analysis Table */}
      <div className="bg-gray-800/30 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <TrendingDown className="w-4 h-4" />
          Cumulative Decay Analysis
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700">
                <th className="text-left text-gray-400 font-medium py-2 px-3">Date</th>
                <th className="text-right text-gray-400 font-medium py-2 px-3">DTE</th>
                <th className="text-center text-gray-400 font-medium py-2 px-3">Type</th>
                <th className="text-right text-gray-400 font-medium py-2 px-3">Γ Expiring</th>
                <th className="text-right text-gray-400 font-medium py-2 px-3">% Decayed</th>
                <th className="text-right text-gray-400 font-medium py-2 px-3">% Remaining</th>
                <th className="text-left text-gray-400 font-medium py-2 px-3">Impact</th>
              </tr>
            </thead>
            <tbody>
              {decayAnalysis.map((row, idx) => (
                <tr key={idx} className="border-b border-gray-800 hover:bg-gray-700/30 transition-colors">
                  <td className="py-2 px-3 text-white">
                    {new Date(row.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  </td>
                  <td className="py-2 px-3 text-right text-gray-300">{row.dte}d</td>
                  <td className="py-2 px-3 text-center">
                    <span
                      className="px-2 py-1 rounded text-xs font-medium"
                      style={{ backgroundColor: `${getTypeColor(row.type)}20`, color: getTypeColor(row.type) }}
                    >
                      {row.type}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right text-purple-400 font-medium">
                    ${row.gammaExpiring.toFixed(2)}B
                  </td>
                  <td className="py-2 px-3 text-right text-red-400">
                    {row.percentDecayed.toFixed(1)}%
                  </td>
                  <td className="py-2 px-3 text-right text-green-400">
                    {row.percentRemaining.toFixed(1)}%
                  </td>
                  <td className="py-2 px-3 text-gray-400 text-xs">
                    {row.percentRemaining < 30 && <span className="text-red-400">🔴 Major decay</span>}
                    {row.percentRemaining >= 30 && row.percentRemaining < 60 && <span className="text-orange-400">🟠 Moderate</span>}
                    {row.percentRemaining >= 60 && <span className="text-green-400">🟢 Minimal</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Legend */}
      <div className="mt-4 flex items-center justify-center gap-6 text-xs text-gray-400">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded" style={{ backgroundColor: '#ef4444' }}></div>
          <span>0DTE</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded" style={{ backgroundColor: '#f97316' }}></div>
          <span>Weekly</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded" style={{ backgroundColor: '#8b5cf6' }}></div>
          <span>Monthly</span>
        </div>
      </div>

      {/* Footer */}
      <div className="mt-4 text-xs text-gray-500 text-center">
        Current Price: ${data.current_price?.toFixed(2)} | Net GEX: ${(data.net_gex / 1e9).toFixed(2)}B
      </div>
    </div>
  )
}
