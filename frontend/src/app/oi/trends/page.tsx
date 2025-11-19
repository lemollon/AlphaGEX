'use client'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import { TrendingUp, AlertTriangle, Activity, BarChart3, ArrowUp, ArrowDown } from 'lucide-react'

interface OISnapshot {
  timestamp: string
  strike: number
  expiration_date: string
  call_oi: number
  put_oi: number
  call_volume: number
  put_volume: number
  total_oi: number
  put_call_ratio: number
}

interface UnusualActivity {
  strike: number
  expiration_date: string
  call_oi_change_pct: number
  put_oi_change_pct: number
  total_oi_change_pct: number
  previous_total_oi: number
  current_total_oi: number
  detection_date: string
}

export default function OITrendsPage() {
  const [loading, setLoading] = useState(true)
  const [oiHistory, setOIHistory] = useState<OISnapshot[]>([])
  const [unusualActivity, setUnusualActivity] = useState<UnusualActivity[]>([])
  const [symbol, setSymbol] = useState('SPY')
  const [days, setDays] = useState(30)
  const [selectedStrike, setSelectedStrike] = useState<number | null>(null)

  useEffect(() => {
    fetchData()
  }, [symbol, days])

  const fetchData = async () => {
    try {
      setLoading(true)

      const [oiRes, unusualRes] = await Promise.all([
        apiClient.getOITrends(symbol, days),
        apiClient.getUnusualOIActivity(symbol, 7)
      ])

      if (oiRes.data.success) {
        setOIHistory(oiRes.data.oi_history)
      }

      if (unusualRes.data.success) {
        setUnusualActivity(unusualRes.data.unusual_activity)
      }
    } catch (error) {
      console.error('Error fetching OI data:', error)
    } finally {
      setLoading(false)
    }
  }

  // Group OI history by strike for analysis
  const getStrikeData = () => {
    const strikeMap = new Map<number, OISnapshot[]>()
    oiHistory.forEach(snapshot => {
      if (!strikeMap.has(snapshot.strike)) {
        strikeMap.set(snapshot.strike, [])
      }
      strikeMap.get(snapshot.strike)!.push(snapshot)
    })
    return Array.from(strikeMap.entries()).map(([strike, snapshots]) => ({
      strike,
      snapshots: snapshots.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()),
      latestOI: snapshots[snapshots.length - 1]?.total_oi || 0,
      latestPCR: snapshots[snapshots.length - 1]?.put_call_ratio || 0
    }))
  }

  const strikeData = getStrikeData()

  return (
    <div className="flex h-screen bg-gray-900">
      <Navigation />

      <div className="flex-1 overflow-auto p-8">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white mb-2">Open Interest Trends</h1>
            <p className="text-gray-400">
              Track OI changes across strikes and detect unusual activity
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
              {/* Unusual Activity Alert */}
              {unusualActivity.length > 0 && (
                <div className="bg-gradient-to-br from-yellow-500/20 to-orange-500/20 border border-yellow-500/30 rounded-xl p-6 mb-8">
                  <div className="flex items-center gap-3 mb-4">
                    <AlertTriangle className="h-6 w-6 text-yellow-400" />
                    <h2 className="text-xl font-semibold text-white">Unusual OI Activity Detected</h2>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {unusualActivity.slice(0, 4).map((activity, idx) => (
                      <div key={idx} className="bg-gray-800/50 rounded-lg p-4">
                        <div className="flex items-center justify-between mb-2">
                          <div>
                            <span className="text-2xl font-bold text-white">${activity.strike}</span>
                            <span className="text-sm text-gray-400 ml-2">
                              {new Date(activity.expiration_date).toLocaleDateString()}
                            </span>
                          </div>
                          <div className={`flex items-center gap-1 ${activity.total_oi_change_pct > 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {activity.total_oi_change_pct > 0 ? <ArrowUp className="h-5 w-5" /> : <ArrowDown className="h-5 w-5" />}
                            <span className="font-bold">{Math.abs(activity.total_oi_change_pct).toFixed(1)}%</span>
                          </div>
                        </div>

                        <div className="grid grid-cols-2 gap-2 text-xs">
                          <div>
                            <span className="text-gray-500">Calls:</span>
                            <span className={`ml-1 font-medium ${activity.call_oi_change_pct > 0 ? 'text-green-400' : 'text-red-400'}`}>
                              {activity.call_oi_change_pct > 0 ? '+' : ''}{activity.call_oi_change_pct.toFixed(1)}%
                            </span>
                          </div>
                          <div>
                            <span className="text-gray-500">Puts:</span>
                            <span className={`ml-1 font-medium ${activity.put_oi_change_pct > 0 ? 'text-green-400' : 'text-red-400'}`}>
                              {activity.put_oi_change_pct > 0 ? '+' : ''}{activity.put_oi_change_pct.toFixed(1)}%
                            </span>
                          </div>
                        </div>

                        <div className="mt-2 text-xs text-gray-400">
                          {activity.previous_total_oi.toLocaleString()} → {activity.current_total_oi.toLocaleString()} contracts
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* OI by Strike */}
              <div className="bg-gray-800 rounded-xl shadow-lg mb-8">
                <div className="p-6 border-b border-gray-700">
                  <div className="flex items-center gap-2">
                    <BarChart3 className="h-5 w-5 text-blue-500" />
                    <h2 className="text-xl font-semibold text-white">Open Interest by Strike</h2>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  {strikeData.length === 0 ? (
                    <div className="p-8 text-center text-gray-400">
                      <Activity className="h-12 w-12 mx-auto mb-3 text-gray-600" />
                      <p>No OI data available yet</p>
                      <p className="text-sm mt-1">OI tracking will populate as data is collected</p>
                    </div>
                  ) : (
                    <table className="w-full">
                      <thead className="bg-gray-750">
                        <tr>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Strike</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Total OI</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">P/C Ratio</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Call OI</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Put OI</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Snapshots</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-700">
                        {strikeData
                          .sort((a, b) => b.latestOI - a.latestOI)
                          .slice(0, 20)
                          .map((data, idx) => {
                            const latest = data.snapshots[data.snapshots.length - 1]
                            return (
                              <tr
                                key={idx}
                                onClick={() => setSelectedStrike(data.strike)}
                                className={`hover:bg-gray-750 cursor-pointer ${selectedStrike === data.strike ? 'bg-gray-750' : ''}`}
                              >
                                <td className="px-6 py-4 text-sm font-medium text-white">
                                  ${data.strike}
                                </td>
                                <td className="px-6 py-4 text-sm text-gray-300">
                                  {latest.total_oi.toLocaleString()}
                                </td>
                                <td className="px-6 py-4 text-sm">
                                  <span className={`font-medium ${latest.put_call_ratio > 1 ? 'text-red-400' : 'text-green-400'}`}>
                                    {latest.put_call_ratio.toFixed(2)}
                                  </span>
                                </td>
                                <td className="px-6 py-4 text-sm text-green-400">
                                  {latest.call_oi.toLocaleString()}
                                </td>
                                <td className="px-6 py-4 text-sm text-red-400">
                                  {latest.put_oi.toLocaleString()}
                                </td>
                                <td className="px-6 py-4 text-sm text-gray-400">
                                  {data.snapshots.length}
                                </td>
                              </tr>
                            )
                          })}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>

              {/* Strike Detail Timeline */}
              {selectedStrike && (
                <div className="bg-gray-800 rounded-xl shadow-lg">
                  <div className="p-6 border-b border-gray-700">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <TrendingUp className="h-5 w-5 text-purple-500" />
                        <h2 className="text-xl font-semibold text-white">
                          ${selectedStrike} Strike Timeline
                        </h2>
                      </div>
                      <button
                        onClick={() => setSelectedStrike(null)}
                        className="text-sm text-gray-400 hover:text-white"
                      >
                        Close
                      </button>
                    </div>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead className="bg-gray-750">
                        <tr>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Date</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Expiration</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Total OI</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Call OI</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Put OI</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">P/C Ratio</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Volume</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-700">
                        {strikeData
                          .find(d => d.strike === selectedStrike)
                          ?.snapshots.reverse()
                          .map((snapshot, idx) => (
                            <tr key={idx} className="hover:bg-gray-750">
                              <td className="px-6 py-4 text-sm text-gray-300">
                                {new Date(snapshot.timestamp).toLocaleDateString()}
                              </td>
                              <td className="px-6 py-4 text-sm text-gray-400">
                                {new Date(snapshot.expiration_date).toLocaleDateString()}
                              </td>
                              <td className="px-6 py-4 text-sm text-white font-medium">
                                {snapshot.total_oi.toLocaleString()}
                              </td>
                              <td className="px-6 py-4 text-sm text-green-400">
                                {snapshot.call_oi.toLocaleString()}
                              </td>
                              <td className="px-6 py-4 text-sm text-red-400">
                                {snapshot.put_oi.toLocaleString()}
                              </td>
                              <td className="px-6 py-4 text-sm">
                                <span className={`font-medium ${snapshot.put_call_ratio > 1 ? 'text-red-400' : 'text-green-400'}`}>
                                  {snapshot.put_call_ratio.toFixed(2)}
                                </span>
                              </td>
                              <td className="px-6 py-4 text-sm text-gray-400">
                                C: {snapshot.call_volume.toLocaleString()} / P: {snapshot.put_volume.toLocaleString()}
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
