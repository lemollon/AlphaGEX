'use client'

import { logger } from '@/lib/logger'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import { TrendingUp, Activity, Zap, AlertCircle, ArrowUpCircle, ArrowDownCircle } from 'lucide-react'

interface GEXSnapshot {
  timestamp: string
  symbol: string
  net_gex: number
  flip_point: number
  call_wall: number
  put_wall: number
  spot_price: number
  mm_state: string
  regime: string
  data_source: string
}

interface RegimeChange {
  change_date: string
  previous_regime: string
  new_regime: string
  net_gex_at_change: number
  spot_price_at_change: number
  duration_days: number
}

export default function GEXHistory() {
  const [loading, setLoading] = useState(true)
  const [history, setHistory] = useState<GEXSnapshot[]>([])
  const [regimeChanges, setRegimeChanges] = useState<RegimeChange[]>([])
  const [symbol, setSymbol] = useState('SPY')
  const [days, setDays] = useState(30)

  useEffect(() => {
    fetchData()
  }, [symbol, days])

  const fetchData = async () => {
    try {
      setLoading(true)

      const [historyRes, regimeRes] = await Promise.all([
        apiClient.getGEXHistory(symbol, days),
        apiClient.getGEXRegimeChanges(symbol, 90)
      ])

      if (historyRes.data.success) {
        setHistory(historyRes.data.gex_history)
      }

      if (regimeRes.data.success) {
        setRegimeChanges(regimeRes.data.regime_changes)
      }
    } catch (error) {
      logger.error('Error fetching GEX history:', error)
    } finally {
      setLoading(false)
    }
  }

  const getRegimeColor = (regime: string) => {
    switch (regime) {
      case 'POSITIVE':
        return 'text-green-400 bg-green-500/20'
      case 'NEGATIVE':
        return 'text-red-400 bg-red-500/20'
      case 'NEUTRAL':
        return 'text-yellow-400 bg-yellow-500/20'
      default:
        return 'text-gray-400 bg-gray-500/20'
    }
  }

  const getRegimeIcon = (regime: string) => {
    switch (regime) {
      case 'POSITIVE':
        return <ArrowUpCircle className="h-4 w-4" />
      case 'NEGATIVE':
        return <ArrowDownCircle className="h-4 w-4" />
      default:
        return <Activity className="h-4 w-4" />
    }
  }

  const formatGEX = (value: number) => {
    const billions = value / 1e9
    return `$${billions.toFixed(2)}B`
  }

  // Calculate summary stats
  const currentSnapshot = history.length > 0 ? history[0] : null
  const avgNetGEX = history.length > 0
    ? history.reduce((sum, s) => sum + s.net_gex, 0) / history.length
    : 0

  const positiveRegimeCount = history.filter(s => s.regime === 'POSITIVE').length
  const negativeRegimeCount = history.filter(s => s.regime === 'NEGATIVE').length
  const positiveRegimePct = history.length > 0
    ? (positiveRegimeCount / history.length) * 100
    : 0

  return (
    <div className="flex h-screen bg-gray-900">
      <Navigation />

      <div className="flex-1 overflow-auto p-8">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white mb-2">GEX History</h1>
            <p className="text-gray-400">
              Track historical Gamma Exposure and regime changes over time
            </p>
          </div>

          {/* Filters */}
          <div className="flex gap-4 mb-6">
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="px-4 py-2 bg-gray-800 border border-gray-700 text-white rounded-lg"
            >
              <option value="SPY">SPY</option>
              <option value="QQQ">QQQ</option>
              <option value="IWM">IWM</option>
            </select>

            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="px-4 py-2 bg-gray-800 border border-gray-700 text-white rounded-lg"
            >
              <option value={7}>Last 7 Days</option>
              <option value={30}>Last 30 Days</option>
              <option value={60}>Last 60 Days</option>
              <option value={90}>Last 90 Days</option>
            </select>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
            </div>
          ) : (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
                <div className="bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl p-6 shadow-lg">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-blue-100 text-sm mb-1">Current Net GEX</p>
                      <h3 className="text-2xl font-bold text-white">
                        {currentSnapshot ? formatGEX(currentSnapshot.net_gex) : 'N/A'}
                      </h3>
                    </div>
                    <Activity className="h-10 w-10 text-blue-200" />
                  </div>
                </div>

                <div className="bg-gradient-to-br from-purple-500 to-purple-600 rounded-xl p-6 shadow-lg">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-purple-100 text-sm mb-1">Avg Net GEX ({days}d)</p>
                      <h3 className="text-2xl font-bold text-white">
                        {formatGEX(avgNetGEX)}
                      </h3>
                    </div>
                    <TrendingUp className="h-10 w-10 text-purple-200" />
                  </div>
                </div>

                <div className="bg-gradient-to-br from-green-500 to-green-600 rounded-xl p-6 shadow-lg">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-green-100 text-sm mb-1">Positive Regime</p>
                      <h3 className="text-2xl font-bold text-white">
                        {positiveRegimePct.toFixed(1)}%
                      </h3>
                      <p className="text-green-100 text-xs mt-1">
                        {positiveRegimeCount} of {history.length} snapshots
                      </p>
                    </div>
                    <ArrowUpCircle className="h-10 w-10 text-green-200" />
                  </div>
                </div>

                <div className="bg-gradient-to-br from-red-500 to-red-600 rounded-xl p-6 shadow-lg">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-red-100 text-sm mb-1">Regime Changes</p>
                      <h3 className="text-2xl font-bold text-white">
                        {regimeChanges.length}
                      </h3>
                      <p className="text-red-100 text-xs mt-1">
                        Last 90 days
                      </p>
                    </div>
                    <Zap className="h-10 w-10 text-red-200" />
                  </div>
                </div>
              </div>

              {/* Regime Changes */}
              {regimeChanges.length > 0 && (
                <div className="bg-gray-800 rounded-xl shadow-lg mb-8">
                  <div className="p-6 border-b border-gray-700">
                    <div className="flex items-center gap-2">
                      <Zap className="h-5 w-5 text-yellow-500" />
                      <h2 className="text-xl font-semibold text-white">Regime Changes</h2>
                    </div>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead className="bg-gray-750">
                        <tr>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Date</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Change</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Net GEX</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">SPY Price</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Duration</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-700">
                        {regimeChanges.map((change, idx) => (
                          <tr key={idx} className="hover:bg-gray-750">
                            <td className="px-6 py-4 text-sm text-gray-300">
                              {new Date(change.change_date).toLocaleDateString()}
                            </td>
                            <td className="px-6 py-4 text-sm">
                              <div className="flex items-center gap-2">
                                <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs ${getRegimeColor(change.previous_regime)}`}>
                                  {getRegimeIcon(change.previous_regime)}
                                  {change.previous_regime}
                                </span>
                                <span className="text-gray-500">→</span>
                                <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs ${getRegimeColor(change.new_regime)}`}>
                                  {getRegimeIcon(change.new_regime)}
                                  {change.new_regime}
                                </span>
                              </div>
                            </td>
                            <td className="px-6 py-4 text-sm text-white font-medium">
                              {formatGEX(change.net_gex_at_change)}
                            </td>
                            <td className="px-6 py-4 text-sm text-gray-300">
                              ${change.spot_price_at_change.toFixed(2)}
                            </td>
                            <td className="px-6 py-4 text-sm text-gray-400">
                              {change.duration_days} days
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* GEX History Timeline */}
              <div className="bg-gray-800 rounded-xl shadow-lg">
                <div className="p-6 border-b border-gray-700">
                  <div className="flex items-center gap-2">
                    <Activity className="h-5 w-5 text-blue-500" />
                    <h2 className="text-xl font-semibold text-white">GEX Timeline</h2>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  {history.length === 0 ? (
                    <div className="p-8 text-center text-gray-400">
                      <AlertCircle className="h-12 w-12 mx-auto mb-3 text-gray-600" />
                      <p>No GEX history available yet</p>
                      <p className="text-sm mt-1">Run gex_history_snapshot_job.py to populate historical data</p>
                    </div>
                  ) : (
                    <table className="w-full">
                      <thead className="bg-gray-750">
                        <tr>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Timestamp</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Net GEX</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Regime</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">MM State</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Flip Point</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Spot Price</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Call Wall</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Put Wall</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Source</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-700">
                        {history.map((snapshot, idx) => (
                          <tr key={idx} className="hover:bg-gray-750">
                            <td className="px-6 py-4 text-sm text-gray-300">
                              {new Date(snapshot.timestamp).toLocaleString()}
                            </td>
                            <td className="px-6 py-4 text-sm">
                              <span className={`font-bold ${snapshot.net_gex >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                {formatGEX(snapshot.net_gex)}
                              </span>
                            </td>
                            <td className="px-6 py-4 text-sm">
                              <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs ${getRegimeColor(snapshot.regime)}`}>
                                {getRegimeIcon(snapshot.regime)}
                                {snapshot.regime}
                              </span>
                            </td>
                            <td className="px-6 py-4 text-sm">
                              <span className={`text-xs ${snapshot.mm_state === 'LONG_GAMMA' ? 'text-blue-400' : 'text-orange-400'}`}>
                                {snapshot.mm_state}
                              </span>
                            </td>
                            <td className="px-6 py-4 text-sm text-yellow-400 font-medium">
                              ${snapshot.flip_point.toFixed(2)}
                            </td>
                            <td className="px-6 py-4 text-sm text-white font-medium">
                              ${snapshot.spot_price.toFixed(2)}
                            </td>
                            <td className="px-6 py-4 text-sm text-green-400">
                              ${snapshot.call_wall.toFixed(2)}
                            </td>
                            <td className="px-6 py-4 text-sm text-red-400">
                              ${snapshot.put_wall.toFixed(2)}
                            </td>
                            <td className="px-6 py-4 text-sm text-gray-500 text-xs">
                              {snapshot.data_source}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
