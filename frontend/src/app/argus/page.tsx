'use client'

/**
 * ARGUS (0DTE Gamma Live) - Real-time 0DTE Net Gamma Visualization
 *
 * Named after Argus Panoptes, the "all-seeing" giant with 100 eyes from Greek mythology.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Eye,
  RefreshCw,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Target,
  Zap,
  Brain,
  ChevronUp,
  ChevronDown,
  Minus,
  Bell,
  Download,
  Clock,
  Bot,
  BarChart3,
  Info
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'

// Types
interface StrikeData {
  strike: number
  net_gamma: number
  probability: number
  gamma_change_pct: number
  roc_1min: number
  roc_5min: number
  is_magnet: boolean
  magnet_rank: number | null
  is_pin: boolean
  is_danger: boolean
  danger_type: string | null
  gamma_flipped: boolean
  flip_direction: string | null
}

interface Magnet {
  rank: number
  strike: number
  net_gamma: number
  probability: number
}

interface DangerZone {
  strike: number
  danger_type: string
  roc_1min: number
  roc_5min: number
}

interface GammaFlip {
  strike: number
  direction: string
  gamma_before: number
  gamma_after: number
}

interface Alert {
  alert_type: string
  strike: number | null
  message: string
  priority: string
  triggered_at: string
}

interface Commentary {
  id: number
  text: string
  timestamp: string
  spot_price: number
  top_magnet: number
  likely_pin: number
  pin_probability: number
}

interface GammaData {
  symbol: string
  expiration_date: string
  snapshot_time: string
  spot_price: number
  expected_move: number
  vix: number
  total_net_gamma: number
  gamma_regime: string
  regime_flipped: boolean
  market_status: string
  strikes: StrikeData[]
  magnets: Magnet[]
  likely_pin: number
  pin_probability: number
  danger_zones: DangerZone[]
  gamma_flips: GammaFlip[]
}

interface Expiration {
  day: string
  date: string
  is_today: boolean
  is_past: boolean
  is_future: boolean
}

export default function ArgusPage() {
  // State
  const [gammaData, setGammaData] = useState<GammaData | null>(null)
  const [expirations, setExpirations] = useState<Expiration[]>([])
  const [activeDay, setActiveDay] = useState<string>('today')
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [commentary, setCommentary] = useState<Commentary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const refreshIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const commentaryIntervalRef = useRef<NodeJS.Timeout | null>(null)

  // Fetch gamma data
  const fetchGammaData = useCallback(async (day?: string) => {
    try {
      setLoading(true)
      setError(null)

      const expiration = day && day !== 'today' ? day.toLowerCase() : undefined
      const response = await apiClient.getArgusGamma(expiration)

      if (response.data?.success && response.data?.data) {
        setGammaData(response.data.data)
        setLastUpdated(new Date())
      } else {
        throw new Error('Invalid response format')
      }
    } catch (err: any) {
      console.error('Error fetching gamma data:', err)
      setError(err.message || 'Failed to fetch gamma data')
    } finally {
      setLoading(false)
    }
  }, [])

  // Fetch expirations
  const fetchExpirations = useCallback(async () => {
    try {
      const response = await apiClient.getArgusExpirations()
      if (response.data?.success && response.data?.data?.expirations) {
        setExpirations(response.data.data.expirations)
        const today = response.data.data.expirations.find((e: Expiration) => e.is_today)
        if (today) {
          setActiveDay(today.day)
        }
      }
    } catch (err) {
      console.error('Error fetching expirations:', err)
    }
  }, [])

  // Fetch alerts
  const fetchAlerts = useCallback(async () => {
    try {
      const response = await apiClient.getArgusAlerts()
      if (response.data?.success && response.data?.data?.alerts) {
        setAlerts(response.data.data.alerts)
      }
    } catch (err) {
      console.error('Error fetching alerts:', err)
    }
  }, [])

  // Fetch commentary
  const fetchCommentary = useCallback(async () => {
    try {
      const response = await apiClient.getArgusCommentary()
      if (response.data?.success && response.data?.data?.commentary) {
        setCommentary(response.data.data.commentary)
      }
    } catch (err) {
      console.error('Error fetching commentary:', err)
    }
  }, [])

  // Initial load
  useEffect(() => {
    fetchExpirations()
    fetchGammaData()
    fetchAlerts()
    fetchCommentary()
  }, [fetchExpirations, fetchGammaData, fetchAlerts, fetchCommentary])

  // Auto-refresh gamma data every 60 seconds
  useEffect(() => {
    if (autoRefresh) {
      refreshIntervalRef.current = setInterval(() => {
        fetchGammaData(activeDay)
        fetchAlerts()
      }, 60000)
    }

    return () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current)
      }
    }
  }, [autoRefresh, activeDay, fetchGammaData, fetchAlerts])

  // Refresh commentary every 5 minutes
  useEffect(() => {
    commentaryIntervalRef.current = setInterval(() => {
      fetchCommentary()
    }, 300000)

    return () => {
      if (commentaryIntervalRef.current) {
        clearInterval(commentaryIntervalRef.current)
      }
    }
  }, [fetchCommentary])

  // Handle day change
  const handleDayChange = (day: string) => {
    setActiveDay(day)
    fetchGammaData(day)
  }

  // Format gamma value
  const formatGamma = (value: number): string => {
    const absValue = Math.abs(value)
    if (absValue >= 1e12) return `${(value / 1e12).toFixed(1)}T`
    if (absValue >= 1e9) return `${(value / 1e9).toFixed(1)}B`
    if (absValue >= 1e6) return `${(value / 1e6).toFixed(1)}M`
    if (absValue >= 1e3) return `${(value / 1e3).toFixed(1)}K`
    return value.toFixed(0)
  }

  // Get ROC arrow component
  const ROCArrow = ({ roc }: { roc: number }) => {
    if (roc > 5) return <ChevronUp className="w-3 h-3 text-green-400" />
    if (roc > 0) return <TrendingUp className="w-3 h-3 text-green-500" />
    if (roc < -5) return <ChevronDown className="w-3 h-3 text-red-400" />
    if (roc < 0) return <TrendingDown className="w-3 h-3 text-red-500" />
    return <Minus className="w-3 h-3 text-gray-500" />
  }

  // Get bar color based on strike properties
  const getBarColor = (strike: StrikeData): string => {
    if (strike.is_pin) return 'bg-purple-500'
    if (strike.is_magnet && strike.magnet_rank === 1) return 'bg-yellow-500'
    if (strike.is_magnet) return 'bg-yellow-600'
    if (strike.is_danger) return 'bg-orange-500'
    if (strike.gamma_flipped) return 'bg-pink-500'
    if (strike.net_gamma > 0) return 'bg-green-500'
    return 'bg-red-500'
  }

  // Calculate bar height
  const getBarHeightPx = (gamma: number, maxGamma: number): number => {
    const maxHeightPx = 140
    const minHeightPx = 15
    if (maxGamma === 0) return minHeightPx
    const height = (Math.abs(gamma) / maxGamma) * maxHeightPx
    return Math.max(minHeightPx, Math.min(maxHeightPx, height))
  }

  // Loading state
  if (loading && !gammaData) {
    return (
      <div className="min-h-screen bg-background">
        <Navigation />
        <main className="pt-24 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
          <div className="flex items-center justify-center h-64">
            <RefreshCw className="w-8 h-8 text-primary animate-spin" />
          </div>
        </main>
      </div>
    )
  }

  // Error state
  if (error && !gammaData) {
    return (
      <div className="min-h-screen bg-background">
        <Navigation />
        <main className="pt-24 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-6 text-center">
            <AlertTriangle className="w-12 h-12 text-red-500 mx-auto mb-4" />
            <h2 className="text-xl font-bold text-red-500 mb-2">Error Loading ARGUS</h2>
            <p className="text-gray-400 mb-4">{error}</p>
            <button
              onClick={() => fetchGammaData(activeDay)}
              className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/80"
            >
              <RefreshCw className="w-4 h-4 inline mr-2" />
              Retry
            </button>
          </div>
        </main>
      </div>
    )
  }

  const maxGamma = gammaData?.strikes
    ? Math.max(...gammaData.strikes.map(s => Math.abs(s.net_gamma)), 1)
    : 1

  return (
    <div className="min-h-screen bg-background">
      <Navigation />
      <main className="pt-24 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto pb-8">
        <div className="space-y-4">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <Eye className="w-8 h-8 text-purple-500" />
              <div>
                <h1 className="text-2xl font-bold text-white">ARGUS</h1>
                <p className="text-sm text-gray-400">0DTE Gamma Live - SPY</p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div className={`px-3 py-1 rounded-full text-sm font-medium ${
                gammaData?.market_status === 'open'
                  ? 'bg-green-500/20 text-green-400'
                  : gammaData?.market_status === 'pre_market'
                  ? 'bg-yellow-500/20 text-yellow-400'
                  : 'bg-gray-600/50 text-gray-400'
              }`}>
                {gammaData?.market_status?.replace('_', ' ').toUpperCase() || 'CLOSED'}
              </div>

              <button
                onClick={() => setAutoRefresh(!autoRefresh)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium ${
                  autoRefresh ? 'bg-green-500/20 text-green-400' : 'bg-gray-600/50 text-gray-400'
                }`}
              >
                <RefreshCw className={`w-4 h-4 ${autoRefresh ? 'animate-spin' : ''}`} />
                {autoRefresh ? '60s' : 'OFF'}
              </button>

              <button
                onClick={() => fetchGammaData(activeDay)}
                className="p-2 bg-gray-700 hover:bg-gray-600 rounded-lg"
                disabled={loading}
              >
                <RefreshCw className={`w-4 h-4 text-white ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>

          {/* Market Info Bar */}
          <div className="bg-gray-800/50 rounded-lg p-3 flex flex-wrap items-center gap-6 text-sm">
            <div>
              <span className="text-gray-500">Spot</span>
              <span className="ml-2 font-bold text-white text-lg">${gammaData?.spot_price.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-gray-500">Expected Move</span>
              <span className="ml-2 font-bold text-blue-400">±${gammaData?.expected_move.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-gray-500">VIX</span>
              <span className="ml-2 font-bold text-yellow-400">{gammaData?.vix.toFixed(1)}</span>
            </div>
            <div>
              <span className="text-gray-500">Regime</span>
              <span className={`ml-2 font-bold ${
                gammaData?.gamma_regime === 'POSITIVE' ? 'text-green-400' :
                gammaData?.gamma_regime === 'NEGATIVE' ? 'text-red-400' : 'text-gray-400'
              }`}>
                {gammaData?.gamma_regime}
              </span>
            </div>
            {lastUpdated && (
              <div className="ml-auto text-gray-500 flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {lastUpdated.toLocaleTimeString()}
              </div>
            )}
          </div>

          {/* Expiration Tabs */}
          <div className="flex gap-2 flex-wrap">
            {expirations.map((exp) => (
              <button
                key={exp.day}
                onClick={() => handleDayChange(exp.day)}
                className={`px-4 py-2 rounded-lg font-medium text-sm transition-all ${
                  activeDay === exp.day
                    ? 'bg-purple-500 text-white'
                    : exp.is_past
                    ? 'bg-gray-700/30 text-gray-600 cursor-not-allowed'
                    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                } ${exp.is_today ? 'ring-2 ring-purple-400/50' : ''}`}
                disabled={exp.is_past}
              >
                {exp.day}
                {exp.is_today && <span className="ml-1 text-xs opacity-70">TODAY</span>}
              </button>
            ))}
          </div>

          {/* Main Content */}
          <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
            {/* Chart Section - 3 columns */}
            <div className="xl:col-span-3 bg-gray-800/50 rounded-lg p-4">
              {/* Chart Header with Legend */}
              <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <BarChart3 className="w-5 h-5 text-blue-400" />
                  Net Gamma by Strike
                </h3>

                {/* Legend */}
                <div className="flex flex-wrap items-center gap-3 text-xs">
                  <div className="flex items-center gap-1">
                    <div className="w-3 h-3 rounded bg-purple-500"></div>
                    <span className="text-gray-400">Pin Strike</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="w-3 h-3 rounded bg-yellow-500"></div>
                    <span className="text-gray-400">Magnet</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="w-3 h-3 rounded bg-green-500"></div>
                    <span className="text-gray-400">+Gamma</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="w-3 h-3 rounded bg-red-500"></div>
                    <span className="text-gray-400">-Gamma</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="w-3 h-3 rounded bg-orange-500"></div>
                    <span className="text-gray-400">Danger Zone</span>
                  </div>
                </div>
              </div>

              {/* Bar Chart */}
              <div className="overflow-x-auto">
                <div className="min-w-[500px]">
                  {/* Chart Container */}
                  <div className="relative h-56 flex items-end justify-center gap-1 border-b border-gray-700 px-2">
                    {gammaData?.strikes.map((strike, idx) => (
                      <div
                        key={strike.strike}
                        className="flex flex-col items-center group relative"
                        style={{ flex: '1 1 0', maxWidth: '50px', minWidth: '30px' }}
                      >
                        {/* Probability */}
                        <div className="text-[10px] text-gray-500 mb-1">
                          {strike.probability.toFixed(0)}%
                        </div>

                        {/* Bar */}
                        <div
                          className={`w-full max-w-[24px] rounded-t ${getBarColor(strike)} relative transition-all hover:opacity-80 cursor-pointer`}
                          style={{ height: `${getBarHeightPx(strike.net_gamma, maxGamma)}px` }}
                        >
                          {/* Pin/Magnet indicator */}
                          {strike.is_pin && (
                            <Target className="absolute -top-5 left-1/2 -translate-x-1/2 w-4 h-4 text-purple-300" />
                          )}
                          {strike.is_magnet && strike.magnet_rank && !strike.is_pin && (
                            <span className="absolute -top-4 left-1/2 -translate-x-1/2 text-[10px] font-bold text-yellow-400">
                              #{strike.magnet_rank}
                            </span>
                          )}

                          {/* Tooltip */}
                          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-6 hidden group-hover:block z-20">
                            <div className="bg-gray-900 border border-gray-600 rounded-lg p-2 text-xs whitespace-nowrap shadow-xl">
                              <div className="font-bold text-white">${strike.strike}</div>
                              <div className="text-blue-400">γ: {formatGamma(strike.net_gamma)}</div>
                              <div className="text-gray-400">Prob: {strike.probability.toFixed(1)}%</div>
                              <div className={strike.roc_1min >= 0 ? 'text-green-400' : 'text-red-400'}>
                                1m: {strike.roc_1min > 0 ? '+' : ''}{strike.roc_1min.toFixed(1)}%
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}

                    {/* Spot Price Line */}
                    {gammaData && gammaData.strikes.length > 1 && (
                      <div
                        className="absolute bottom-0 top-0 border-l-2 border-dashed border-green-400 z-10 pointer-events-none"
                        style={{
                          left: `${((gammaData.spot_price - gammaData.strikes[0].strike) /
                            (gammaData.strikes[gammaData.strikes.length - 1].strike -
                              gammaData.strikes[0].strike)) * 100}%`
                        }}
                      >
                        <div className="absolute -top-1 left-1 text-[10px] text-green-400 font-bold bg-gray-800 px-1 rounded">
                          SPOT
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Strike Labels */}
                  <div className="flex justify-center gap-1 pt-1 px-2">
                    {gammaData?.strikes.map((strike) => (
                      <div
                        key={`label-${strike.strike}`}
                        className="text-center"
                        style={{ flex: '1 1 0', maxWidth: '50px', minWidth: '30px' }}
                      >
                        <div className={`text-xs font-mono ${
                          strike.is_pin ? 'text-purple-400 font-bold' :
                          strike.is_magnet ? 'text-yellow-400 font-bold' : 'text-gray-500'
                        }`}>
                          {strike.strike}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Key Levels Summary */}
              <div className="mt-4 pt-4 border-t border-gray-700">
                <div className="flex flex-wrap gap-4">
                  {/* Magnets */}
                  <div className="flex items-center gap-2">
                    <span className="text-gray-500 text-sm">Magnets:</span>
                    {gammaData?.magnets.slice(0, 3).map((m) => (
                      <span key={m.strike} className="px-2 py-0.5 bg-yellow-500/20 text-yellow-400 rounded text-sm">
                        {m.strike} ({m.probability.toFixed(0)}%)
                      </span>
                    ))}
                  </div>

                  {/* Pin */}
                  {gammaData?.likely_pin && (
                    <div className="flex items-center gap-2">
                      <span className="text-gray-500 text-sm">Pin:</span>
                      <span className="px-2 py-0.5 bg-purple-500/20 text-purple-400 rounded text-sm flex items-center gap-1">
                        <Target className="w-3 h-3" />
                        {gammaData.likely_pin} ({gammaData.pin_probability.toFixed(0)}%)
                      </span>
                    </div>
                  )}
                </div>
              </div>

              {/* Danger Zones - with explanation */}
              {gammaData?.danger_zones && gammaData.danger_zones.length > 0 && (
                <div className="mt-4 p-3 bg-orange-500/10 border border-orange-500/30 rounded-lg">
                  <div className="flex items-start gap-2 mb-2">
                    <AlertTriangle className="w-4 h-4 text-orange-400 mt-0.5" />
                    <div>
                      <span className="text-orange-400 font-bold">Danger Zones</span>
                      <p className="text-xs text-gray-400 mt-0.5">
                        Areas of rapid gamma change that may cause increased volatility
                      </p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {gammaData.danger_zones.map((dz) => (
                      <span key={dz.strike} className="px-2 py-1 bg-orange-500/20 text-orange-400 rounded text-xs">
                        ${dz.strike} - {dz.danger_type} ({dz.roc_5min > 0 ? '+' : ''}{dz.roc_5min.toFixed(0)}% 5min)
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Gamma Flip Alert */}
              {gammaData?.regime_flipped && (
                <div className="mt-4 p-3 bg-pink-500/10 border border-pink-500/30 rounded-lg">
                  <div className="flex items-center gap-2">
                    <Zap className="w-4 h-4 text-pink-400" />
                    <span className="text-pink-400 font-bold">Gamma Regime Flip Detected</span>
                  </div>
                  <p className="text-xs text-gray-400 mt-1">
                    Market maker positioning has shifted from {gammaData.gamma_regime === 'POSITIVE' ? 'negative to positive' : 'positive to negative'} gamma
                  </p>
                </div>
              )}
            </div>

            {/* Right Panel - 1 column */}
            <div className="xl:col-span-1 space-y-4">
              {/* AI Commentary */}
              <div className="bg-gray-800/50 rounded-lg p-4">
                <h3 className="font-bold text-white flex items-center gap-2 mb-3">
                  <Brain className="w-4 h-4 text-purple-400" />
                  ARGUS AI Intel
                </h3>
                <div className="space-y-3 max-h-64 overflow-y-auto">
                  {commentary.length > 0 ? (
                    commentary.slice(0, 5).map((c) => (
                      <div key={c.id} className="text-sm border-l-2 border-purple-500 pl-3 py-1">
                        <div className="text-gray-500 text-xs mb-1">
                          {new Date(c.timestamp).toLocaleTimeString()}
                        </div>
                        <div className="text-gray-300">{c.text}</div>
                      </div>
                    ))
                  ) : (
                    <div className="text-gray-500 text-sm py-4 text-center">
                      <Brain className="w-8 h-8 mx-auto mb-2 opacity-30" />
                      AI commentary updates every 5 minutes during market hours
                    </div>
                  )}
                </div>
              </div>

              {/* Alerts */}
              <div className="bg-gray-800/50 rounded-lg p-4">
                <h3 className="font-bold text-white flex items-center gap-2 mb-3">
                  <Bell className="w-4 h-4 text-yellow-400" />
                  Alerts
                  {alerts.length > 0 && (
                    <span className="px-1.5 py-0.5 bg-red-500 text-white text-xs rounded-full">
                      {alerts.length}
                    </span>
                  )}
                </h3>
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {alerts.length > 0 ? (
                    alerts.slice(0, 5).map((alert, idx) => (
                      <div
                        key={idx}
                        className={`text-xs p-2 rounded ${
                          alert.priority === 'HIGH'
                            ? 'bg-red-500/20 border border-red-500/30'
                            : alert.priority === 'MEDIUM'
                            ? 'bg-yellow-500/20 border border-yellow-500/30'
                            : 'bg-gray-700/50'
                        }`}
                      >
                        <div className="text-gray-300">{alert.message}</div>
                        <div className="text-gray-500 mt-1">
                          {new Date(alert.triggered_at).toLocaleTimeString()}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="text-gray-500 text-sm py-4 text-center">
                      <Bell className="w-8 h-8 mx-auto mb-2 opacity-30" />
                      No active alerts
                    </div>
                  )}
                </div>
              </div>

              {/* Bot Status */}
              <div className="bg-gray-800/50 rounded-lg p-4">
                <h3 className="font-bold text-white flex items-center gap-2 mb-3">
                  <Bot className="w-4 h-4 text-blue-400" />
                  Bot Status
                </h3>
                <div className="space-y-2 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400">ARES</span>
                    <span className="text-green-400">No Position</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400">ATHENA</span>
                    <span className="text-gray-500">Watching</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400">PHOENIX</span>
                    <span className="text-gray-500">Inactive</span>
                  </div>
                </div>
              </div>

              {/* Info Box */}
              <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-3">
                <div className="flex items-start gap-2">
                  <Info className="w-4 h-4 text-blue-400 mt-0.5" />
                  <div className="text-xs text-gray-400">
                    <p className="font-medium text-blue-400 mb-1">About Gamma</p>
                    <p>Positive γ = MM sell dips, buy rips (stabilizing)</p>
                    <p>Negative γ = MM buy dips, sell rips (volatile)</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
