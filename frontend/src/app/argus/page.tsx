'use client'

/**
 * ARGUS (0DTE Gamma Live) - Real-time 0DTE Net Gamma Visualization
 *
 * Named after Argus Panoptes, the "all-seeing" giant with 100 eyes from Greek mythology.
 *
 * Features:
 * - Net gamma bar chart with 60s refresh
 * - 5 expiration tabs (Mon-Fri for SPY 0DTE)
 * - Probability % displayed above each strike
 * - Rate of change with arrows and colors
 * - Top 3 magnet highlights
 * - Likely pin strike indicator
 * - Claude AI commentary panel
 * - Gamma flip detection and alerts
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
  Maximize2,
  Minimize2,
  Clock,
  Bot,
  BarChart3
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

// Day abbreviation to full name mapping
const dayNames: Record<string, string> = {
  MON: 'Monday',
  TUE: 'Tuesday',
  WED: 'Wednesday',
  THU: 'Thursday',
  FRI: 'Friday'
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
  const [commentaryExpanded, setCommentaryExpanded] = useState(false)
  const [alertsExpanded, setAlertsExpanded] = useState(false)

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
        // Set active day to today's expiration
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
      }, 60000) // 60 seconds
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
    }, 300000) // 5 minutes

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
    if (roc > 10) return <ChevronUp className="w-4 h-4 text-green-400" />
    if (roc > 0) return <ChevronUp className="w-3 h-3 text-green-400" />
    if (roc < -10) return <ChevronDown className="w-4 h-4 text-red-400" />
    if (roc < 0) return <ChevronDown className="w-3 h-3 text-red-400" />
    return <Minus className="w-3 h-3 text-gray-400" />
  }

  // Get ROC color
  const getROCColor = (roc: number): string => {
    if (roc > 10) return 'text-green-400'
    if (roc > 0) return 'text-green-500'
    if (roc < -10) return 'text-red-400'
    if (roc < 0) return 'text-red-500'
    return 'text-gray-400'
  }

  // Get bar color based on strike properties
  const getBarColor = (strike: StrikeData): string => {
    if (strike.is_pin) return 'bg-purple-500'
    if (strike.is_magnet && strike.magnet_rank === 1) return 'bg-yellow-500'
    if (strike.is_magnet) return 'bg-yellow-600/70'
    if (strike.is_danger) return 'bg-orange-500'
    if (strike.gamma_flipped) return 'bg-pink-500'
    return 'bg-blue-500'
  }

  // Get danger badge
  const getDangerBadge = (type: string) => {
    switch (type) {
      case 'BUILDING':
        return <span className="text-xs bg-orange-500/20 text-orange-400 px-1 rounded">BUILDING</span>
      case 'COLLAPSING':
        return <span className="text-xs bg-red-500/20 text-red-400 px-1 rounded">COLLAPSING</span>
      case 'SPIKE':
        return <span className="text-xs bg-yellow-500/20 text-yellow-400 px-1 rounded">SPIKE</span>
      default:
        return null
    }
  }

  // Calculate bar height (normalized to max gamma)
  const getBarHeight = (gamma: number, maxGamma: number): number => {
    if (maxGamma === 0) return 10
    const height = (Math.abs(gamma) / maxGamma) * 100
    return Math.max(10, Math.min(100, height))
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
    ? Math.max(...gammaData.strikes.map(s => Math.abs(s.net_gamma)))
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

            <div className="flex items-center gap-4">
              {/* Market Status */}
              <div className={`px-3 py-1 rounded-full text-sm ${
                gammaData?.market_status === 'open'
                  ? 'bg-green-500/20 text-green-400'
                  : gammaData?.market_status === 'pre_market'
                  ? 'bg-yellow-500/20 text-yellow-400'
                  : 'bg-gray-500/20 text-gray-400'
              }`}>
                {gammaData?.market_status?.replace('_', ' ').toUpperCase() || 'LOADING'}
              </div>

              {/* Auto Refresh Toggle */}
              <button
                onClick={() => setAutoRefresh(!autoRefresh)}
                className={`flex items-center gap-2 px-3 py-1 rounded-lg ${
                  autoRefresh ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'
                }`}
              >
                <RefreshCw className={`w-4 h-4 ${autoRefresh ? 'animate-spin' : ''}`} />
                <span className="text-sm">{autoRefresh ? '60s' : 'OFF'}</span>
              </button>

              {/* Manual Refresh */}
              <button
                onClick={() => fetchGammaData(activeDay)}
                className="p-2 bg-gray-700 hover:bg-gray-600 rounded-lg"
                disabled={loading}
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>

          {/* Market Info Bar */}
          <div className="bg-gray-800/50 rounded-lg p-3 flex flex-wrap items-center gap-4 text-sm">
            <div>
              <span className="text-gray-400">Spot:</span>
              <span className="ml-2 font-bold text-white">${gammaData?.spot_price.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-gray-400">Expected Move:</span>
              <span className="ml-2 font-bold text-blue-400">
                ±${gammaData?.expected_move.toFixed(2)}
              </span>
            </div>
            <div>
              <span className="text-gray-400">VIX:</span>
              <span className="ml-2 font-bold text-yellow-400">{gammaData?.vix.toFixed(1)}</span>
            </div>
            <div>
              <span className="text-gray-400">Regime:</span>
              <span className={`ml-2 font-bold ${
                gammaData?.gamma_regime === 'POSITIVE'
                  ? 'text-green-400'
                  : gammaData?.gamma_regime === 'NEGATIVE'
                  ? 'text-red-400'
                  : 'text-gray-400'
              }`}>
                {gammaData?.gamma_regime}
                {gammaData?.regime_flipped && (
                  <span className="ml-1 text-pink-400">(FLIPPED!)</span>
                )}
              </span>
            </div>
            {lastUpdated && (
              <div className="ml-auto text-gray-500">
                <Clock className="w-3 h-3 inline mr-1" />
                {lastUpdated.toLocaleTimeString()}
              </div>
            )}
          </div>

          {/* Expiration Tabs */}
          <div className="flex gap-2">
            {expirations.map((exp) => (
              <button
                key={exp.day}
                onClick={() => handleDayChange(exp.day)}
                className={`px-4 py-2 rounded-lg font-medium transition-all ${
                  activeDay === exp.day
                    ? 'bg-purple-500 text-white'
                    : exp.is_past
                    ? 'bg-gray-700/50 text-gray-500'
                    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                } ${exp.is_today ? 'ring-2 ring-purple-400' : ''}`}
              >
                {exp.day}
                {exp.is_today && <span className="ml-1 text-xs opacity-75">TODAY</span>}
              </button>
            ))}
          </div>

          {/* Main Content Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
            {/* Gamma Chart - 3 columns */}
            <div className="lg:col-span-3 bg-gray-800/50 rounded-lg p-4">
              <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-blue-400" />
                Net Gamma by Strike
              </h3>

              {/* Bar Chart */}
              <div className="overflow-x-auto">
                <div className="min-w-[600px] flex items-end justify-center gap-1 h-64 pb-8 relative">
                  {gammaData?.strikes.map((strike) => (
                    <div
                      key={strike.strike}
                      className="flex flex-col items-center group relative"
                      style={{ width: `${100 / (gammaData?.strikes.length || 1)}%`, maxWidth: '60px' }}
                    >
                      {/* Probability Label */}
                      <div className="text-xs text-gray-400 mb-1">
                        {strike.probability.toFixed(0)}%
                      </div>

                      {/* Bar */}
                      <div
                        className={`w-full rounded-t transition-all ${getBarColor(strike)} relative`}
                        style={{ height: `${getBarHeight(strike.net_gamma, maxGamma)}%` }}
                      >
                        {/* Magnet/Pin Badge */}
                        {strike.is_pin && (
                          <div className="absolute -top-6 left-1/2 -translate-x-1/2">
                            <Target className="w-4 h-4 text-purple-400" />
                          </div>
                        )}
                        {strike.is_magnet && strike.magnet_rank && (
                          <div className="absolute -top-5 left-1/2 -translate-x-1/2 text-xs font-bold text-yellow-400">
                            #{strike.magnet_rank}
                          </div>
                        )}
                        {strike.gamma_flipped && (
                          <div className="absolute top-1 left-1/2 -translate-x-1/2">
                            <Zap className="w-3 h-3 text-pink-400" />
                          </div>
                        )}
                        {strike.is_danger && (
                          <div className="absolute top-1 right-0">
                            <AlertTriangle className="w-3 h-3 text-orange-400" />
                          </div>
                        )}

                        {/* Tooltip */}
                        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block z-10">
                          <div className="bg-gray-900 border border-gray-700 rounded-lg p-2 text-xs whitespace-nowrap">
                            <div className="font-bold text-white">${strike.strike}</div>
                            <div className="text-gray-400">
                              Gamma: {formatGamma(strike.net_gamma)}
                            </div>
                            <div className="text-gray-400">
                              Prob: {strike.probability.toFixed(1)}%
                            </div>
                            <div className={getROCColor(strike.roc_1min)}>
                              1m: {strike.roc_1min > 0 ? '+' : ''}{strike.roc_1min.toFixed(1)}%
                            </div>
                            <div className={getROCColor(strike.roc_5min)}>
                              5m: {strike.roc_5min > 0 ? '+' : ''}{strike.roc_5min.toFixed(1)}%
                            </div>
                            {strike.is_danger && strike.danger_type && (
                              <div className="mt-1">{getDangerBadge(strike.danger_type)}</div>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Strike Label */}
                      <div className={`text-xs mt-1 ${
                        strike.is_pin
                          ? 'text-purple-400 font-bold'
                          : strike.is_magnet
                          ? 'text-yellow-400 font-bold'
                          : 'text-gray-400'
                      }`}>
                        {strike.strike}
                      </div>

                      {/* ROC Indicator */}
                      <div className="flex items-center gap-0.5">
                        <ROCArrow roc={strike.roc_1min} />
                      </div>
                    </div>
                  ))}

                  {/* Spot Price Line */}
                  {gammaData && (
                    <div
                      className="absolute bottom-8 h-full border-l-2 border-dashed border-green-500/50"
                      style={{
                        left: `${((gammaData.spot_price - (gammaData.strikes[0]?.strike || 0)) /
                          ((gammaData.strikes[gammaData.strikes.length - 1]?.strike || 1) -
                            (gammaData.strikes[0]?.strike || 0))) * 100}%`
                      }}
                    >
                      <div className="absolute -top-2 left-1 text-xs text-green-400 whitespace-nowrap">
                        SPOT ${gammaData.spot_price.toFixed(2)}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Magnets & Pin Summary */}
              <div className="mt-4 flex flex-wrap gap-4 text-sm">
                <div className="flex items-center gap-2">
                  <span className="text-gray-400">MAGNETS:</span>
                  {gammaData?.magnets.map((m) => (
                    <span
                      key={m.strike}
                      className="px-2 py-1 bg-yellow-500/20 text-yellow-400 rounded"
                    >
                      #{m.rank} {m.strike} ({m.probability.toFixed(0)}%)
                    </span>
                  ))}
                </div>
                {gammaData?.likely_pin && (
                  <div className="flex items-center gap-2">
                    <span className="text-gray-400">PIN:</span>
                    <span className="px-2 py-1 bg-purple-500/20 text-purple-400 rounded">
                      <Target className="w-3 h-3 inline mr-1" />
                      {gammaData.likely_pin} ({gammaData.pin_probability.toFixed(0)}%)
                    </span>
                  </div>
                )}
              </div>

              {/* Danger Zones */}
              {gammaData?.danger_zones && gammaData.danger_zones.length > 0 && (
                <div className="mt-4 p-3 bg-orange-500/10 border border-orange-500/30 rounded-lg">
                  <div className="flex items-center gap-2 text-orange-400 font-bold mb-2">
                    <AlertTriangle className="w-4 h-4" />
                    DANGER ZONES
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {gammaData.danger_zones.map((dz) => (
                      <span
                        key={dz.strike}
                        className="px-2 py-1 bg-orange-500/20 text-orange-400 rounded text-sm"
                      >
                        {dz.strike} {getDangerBadge(dz.danger_type)} ({dz.roc_5min > 0 ? '+' : ''}{dz.roc_5min.toFixed(0)}%)
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Gamma Flips */}
              {gammaData?.gamma_flips && gammaData.gamma_flips.length > 0 && (
                <div className="mt-4 p-3 bg-pink-500/10 border border-pink-500/30 rounded-lg">
                  <div className="flex items-center gap-2 text-pink-400 font-bold mb-2">
                    <Zap className="w-4 h-4" />
                    GAMMA FLIPS DETECTED
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {gammaData.gamma_flips.map((flip) => (
                      <span
                        key={flip.strike}
                        className="px-2 py-1 bg-pink-500/20 text-pink-400 rounded text-sm"
                      >
                        {flip.strike}: {flip.direction === 'POS_TO_NEG' ? '+ → -' : '- → +'}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* AI Commentary Panel - 1 column */}
            <div className="lg:col-span-1 space-y-4">
              {/* Commentary */}
              <div className="bg-gray-800/50 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-bold text-white flex items-center gap-2">
                    <Brain className="w-4 h-4 text-purple-400" />
                    ARGUS AI INTEL
                  </h3>
                  <div className="flex gap-1">
                    <button
                      onClick={() => setCommentaryExpanded(!commentaryExpanded)}
                      className="p-1 hover:bg-gray-700 rounded"
                    >
                      {commentaryExpanded ? (
                        <Minimize2 className="w-4 h-4 text-gray-400" />
                      ) : (
                        <Maximize2 className="w-4 h-4 text-gray-400" />
                      )}
                    </button>
                    <button className="p-1 hover:bg-gray-700 rounded">
                      <Download className="w-4 h-4 text-gray-400" />
                    </button>
                  </div>
                </div>

                <div className={`space-y-3 ${commentaryExpanded ? 'max-h-96' : 'max-h-48'} overflow-y-auto`}>
                  {commentary.length > 0 ? (
                    commentary.slice(0, commentaryExpanded ? 10 : 3).map((c) => (
                      <div key={c.id} className="text-sm border-l-2 border-purple-500 pl-3 py-1">
                        <div className="text-gray-500 text-xs mb-1">
                          {new Date(c.timestamp).toLocaleTimeString()}
                        </div>
                        <div className="text-gray-300 whitespace-pre-line">{c.text}</div>
                      </div>
                    ))
                  ) : (
                    <div className="text-gray-500 text-sm">
                      Commentary updates every 5 minutes...
                    </div>
                  )}
                </div>
              </div>

              {/* Alerts */}
              <div className="bg-gray-800/50 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-bold text-white flex items-center gap-2">
                    <Bell className="w-4 h-4 text-yellow-400" />
                    ALERTS
                    {alerts.length > 0 && (
                      <span className="px-2 py-0.5 bg-red-500 text-white text-xs rounded-full">
                        {alerts.length}
                      </span>
                    )}
                  </h3>
                  <button
                    onClick={() => setAlertsExpanded(!alertsExpanded)}
                    className="p-1 hover:bg-gray-700 rounded"
                  >
                    {alertsExpanded ? (
                      <Minimize2 className="w-4 h-4 text-gray-400" />
                    ) : (
                      <Maximize2 className="w-4 h-4 text-gray-400" />
                    )}
                  </button>
                </div>

                <div className={`space-y-2 ${alertsExpanded ? 'max-h-64' : 'max-h-32'} overflow-y-auto`}>
                  {alerts.length > 0 ? (
                    alerts.slice(0, alertsExpanded ? 10 : 3).map((alert, idx) => (
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
                        <div className="flex items-center gap-2">
                          <span className={`font-bold ${
                            alert.priority === 'HIGH'
                              ? 'text-red-400'
                              : alert.priority === 'MEDIUM'
                              ? 'text-yellow-400'
                              : 'text-gray-400'
                          }`}>
                            [{alert.priority}]
                          </span>
                          <span className="text-gray-500">
                            {new Date(alert.triggered_at).toLocaleTimeString()}
                          </span>
                        </div>
                        <div className="text-gray-300 mt-1">{alert.message}</div>
                      </div>
                    ))
                  ) : (
                    <div className="text-gray-500 text-sm">No active alerts</div>
                  )}
                </div>
              </div>

              {/* Bot Status */}
              <div className="bg-gray-800/50 rounded-lg p-4">
                <h3 className="font-bold text-white flex items-center gap-2 mb-3">
                  <Bot className="w-4 h-4 text-blue-400" />
                  BOT STATUS
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
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
