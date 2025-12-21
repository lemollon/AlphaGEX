'use client'

/**
 * ARGUS (0DTE Gamma Live) - Real-time 0DTE Net Gamma Visualization
 * Premium design with actionable insights
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
  Clock,
  Bot,
  BarChart3,
  Info,
  Activity,
  Shield,
  Flame,
  ArrowRight,
  ChevronRight
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
  gamma_flips: any[]
}

interface Expiration {
  day: string
  date: string
  is_today: boolean
  is_past: boolean
  is_future: boolean
}

export default function ArgusPage() {
  const [gammaData, setGammaData] = useState<GammaData | null>(null)
  const [expirations, setExpirations] = useState<Expiration[]>([])
  const [activeDay, setActiveDay] = useState<string>('today')
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [commentary, setCommentary] = useState<Commentary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [selectedStrike, setSelectedStrike] = useState<StrikeData | null>(null)

  const refreshIntervalRef = useRef<NodeJS.Timeout | null>(null)

  // Fetch functions
  const fetchGammaData = useCallback(async (day?: string) => {
    try {
      setLoading(true)
      const expiration = day && day !== 'today' ? day.toLowerCase() : undefined
      const response = await apiClient.getArgusGamma(expiration)
      if (response.data?.success && response.data?.data) {
        setGammaData(response.data.data)
        setLastUpdated(new Date())
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch data')
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchExpirations = useCallback(async () => {
    try {
      const response = await apiClient.getArgusExpirations()
      if (response.data?.success && response.data?.data?.expirations) {
        setExpirations(response.data.data.expirations)
        const today = response.data.data.expirations.find((e: Expiration) => e.is_today)
        if (today) setActiveDay(today.day)
      }
    } catch (err) {}
  }, [])

  const fetchAlerts = useCallback(async () => {
    try {
      const response = await apiClient.getArgusAlerts()
      if (response.data?.success && response.data?.data?.alerts) {
        setAlerts(response.data.data.alerts)
      }
    } catch (err) {}
  }, [])

  const fetchCommentary = useCallback(async () => {
    try {
      const response = await apiClient.getArgusCommentary()
      if (response.data?.success && response.data?.data?.commentary) {
        setCommentary(response.data.data.commentary)
      }
    } catch (err) {}
  }, [])

  useEffect(() => {
    fetchExpirations()
    fetchGammaData()
    fetchAlerts()
    fetchCommentary()
  }, [fetchExpirations, fetchGammaData, fetchAlerts, fetchCommentary])

  useEffect(() => {
    if (autoRefresh) {
      refreshIntervalRef.current = setInterval(() => {
        fetchGammaData(activeDay)
        fetchAlerts()
      }, 60000)
    }
    return () => {
      if (refreshIntervalRef.current) clearInterval(refreshIntervalRef.current)
    }
  }, [autoRefresh, activeDay, fetchGammaData, fetchAlerts])

  const handleDayChange = (day: string) => {
    setActiveDay(day)
    fetchGammaData(day)
  }

  // Helpers
  const formatGamma = (value: number): string => {
    const absValue = Math.abs(value)
    if (absValue >= 1e9) return `${(value / 1e9).toFixed(1)}B`
    if (absValue >= 1e6) return `${(value / 1e6).toFixed(1)}M`
    if (absValue >= 1e3) return `${(value / 1e3).toFixed(1)}K`
    return value.toFixed(0)
  }

  const getBarColor = (strike: StrikeData): string => {
    if (strike.is_pin) return 'bg-purple-500'
    if (strike.is_magnet && strike.magnet_rank === 1) return 'bg-yellow-400'
    if (strike.is_magnet) return 'bg-yellow-500'
    if (strike.is_danger) return 'bg-orange-500'
    if (strike.net_gamma > 0) return 'bg-emerald-500'
    return 'bg-rose-500'
  }

  const getBarHeightPx = (gamma: number, maxGamma: number): number => {
    if (maxGamma === 0) return 20
    return Math.max(20, Math.min(160, (Math.abs(gamma) / maxGamma) * 160))
  }

  // Generate AI insight based on current data
  const generateInsight = (): string => {
    if (!gammaData) return "Loading market analysis..."

    const { spot_price, gamma_regime, magnets, likely_pin, danger_zones, vix } = gammaData
    const topMagnet = magnets[0]
    const dangerCount = danger_zones?.length || 0

    let insight = ""

    if (gamma_regime === 'POSITIVE') {
      insight = `Market makers are in POSITIVE gamma territory. This typically means price action will be more stable with dealers selling into rallies and buying dips. `
    } else if (gamma_regime === 'NEGATIVE') {
      insight = `Market makers are in NEGATIVE gamma territory. Expect amplified moves as dealers must buy into rallies and sell into dips. Increased volatility likely. `
    } else {
      insight = `Market is in NEUTRAL gamma regime near the flip point. Watch for directional breaks. `
    }

    if (topMagnet) {
      const distance = ((topMagnet.strike - spot_price) / spot_price * 100).toFixed(2)
      insight += `The strongest magnet is at $${topMagnet.strike} (${distance > '0' ? '+' : ''}${distance}% from spot) with ${topMagnet.probability.toFixed(0)}% probability. `
    }

    if (likely_pin && likely_pin !== topMagnet?.strike) {
      insight += `Pin risk at $${likely_pin} for expiration. `
    }

    if (dangerCount > 3) {
      insight += `⚠️ ${dangerCount} danger zones detected - gamma is shifting rapidly at multiple strikes. Exercise caution with directional trades.`
    } else if (dangerCount > 0) {
      insight += `${dangerCount} strike(s) showing unusual gamma activity.`
    }

    if (vix > 25) {
      insight += ` Elevated VIX (${vix.toFixed(1)}) suggests options are pricing significant moves.`
    }

    return insight
  }

  // Loading
  if (loading && !gammaData) {
    return (
      <div className="min-h-screen bg-background">
        <Navigation />
        <main className="pt-24 px-4 max-w-7xl mx-auto">
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <RefreshCw className="w-10 h-10 text-purple-500 animate-spin mx-auto mb-4" />
              <p className="text-gray-400">Loading ARGUS data...</p>
            </div>
          </div>
        </main>
      </div>
    )
  }

  const maxGamma = gammaData?.strikes
    ? Math.max(...gammaData.strikes.map(s => Math.abs(s.net_gamma)), 1)
    : 1

  const highPriorityAlerts = alerts.filter(a => a.priority === 'HIGH' || a.priority === 'MEDIUM')
  const buildingZones = gammaData?.danger_zones?.filter(d => d.danger_type === 'BUILDING') || []
  const collapsingZones = gammaData?.danger_zones?.filter(d => d.danger_type === 'COLLAPSING') || []

  return (
    <div className="min-h-screen bg-background">
      <Navigation />
      <main className="pt-24 px-4 sm:px-6 lg:px-8 max-w-[1600px] mx-auto pb-8">

        {/* Header */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-6">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-purple-500/20 flex items-center justify-center">
              <Eye className="w-6 h-6 text-purple-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">ARGUS</h1>
              <p className="text-gray-400 text-sm">0DTE Gamma Intelligence • SPY</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Expiration Tabs */}
            <div className="flex bg-gray-800/50 rounded-lg p-1">
              {expirations.map((exp) => (
                <button
                  key={exp.day}
                  onClick={() => handleDayChange(exp.day)}
                  disabled={exp.is_past}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                    activeDay === exp.day
                      ? 'bg-purple-500 text-white'
                      : exp.is_past
                      ? 'text-gray-600 cursor-not-allowed'
                      : 'text-gray-400 hover:text-white hover:bg-gray-700'
                  }`}
                >
                  {exp.day}
                  {exp.is_today && <span className="ml-1 text-[10px] opacity-70">•</span>}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => setAutoRefresh(!autoRefresh)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm ${
                  autoRefresh ? 'bg-emerald-500/20 text-emerald-400' : 'bg-gray-700 text-gray-400'
                }`}
              >
                <RefreshCw className={`w-4 h-4 ${autoRefresh ? 'animate-spin' : ''}`} />
                {autoRefresh ? 'Live' : 'Paused'}
              </button>
              <button
                onClick={() => fetchGammaData(activeDay)}
                className="p-2 bg-gray-700 hover:bg-gray-600 rounded-lg"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>
        </div>

        {/* Key Metrics Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-6">
          <div className="bg-gray-800/50 rounded-xl p-4">
            <div className="text-gray-500 text-xs mb-1">SPY Spot</div>
            <div className="text-xl font-bold text-white">${gammaData?.spot_price.toFixed(2)}</div>
          </div>
          <div className="bg-gray-800/50 rounded-xl p-4">
            <div className="text-gray-500 text-xs mb-1">Expected Move</div>
            <div className="text-xl font-bold text-blue-400">±${gammaData?.expected_move.toFixed(2)}</div>
          </div>
          <div className="bg-gray-800/50 rounded-xl p-4">
            <div className="text-gray-500 text-xs mb-1">VIX</div>
            <div className={`text-xl font-bold ${(gammaData?.vix || 0) > 20 ? 'text-orange-400' : 'text-emerald-400'}`}>
              {gammaData?.vix.toFixed(1)}
            </div>
          </div>
          <div className="bg-gray-800/50 rounded-xl p-4">
            <div className="text-gray-500 text-xs mb-1">Gamma Regime</div>
            <div className={`text-xl font-bold ${
              gammaData?.gamma_regime === 'POSITIVE' ? 'text-emerald-400' :
              gammaData?.gamma_regime === 'NEGATIVE' ? 'text-rose-400' : 'text-gray-400'
            }`}>
              {gammaData?.gamma_regime}
            </div>
          </div>
          <div className="bg-gray-800/50 rounded-xl p-4">
            <div className="text-gray-500 text-xs mb-1">Top Magnet</div>
            <div className="text-xl font-bold text-yellow-400">
              ${gammaData?.magnets[0]?.strike || '-'}
            </div>
          </div>
          <div className="bg-gray-800/50 rounded-xl p-4">
            <div className="text-gray-500 text-xs mb-1">Pin Strike</div>
            <div className="text-xl font-bold text-purple-400">
              ${gammaData?.likely_pin || '-'}
            </div>
          </div>
        </div>

        {/* AI Analysis Banner */}
        <div className="bg-gradient-to-r from-purple-900/40 to-blue-900/40 border border-purple-500/30 rounded-xl p-5 mb-6">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center flex-shrink-0">
              <Brain className="w-5 h-5 text-purple-400" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <h3 className="font-bold text-white">ARGUS AI Analysis</h3>
                <span className="text-xs bg-purple-500/20 text-purple-400 px-2 py-0.5 rounded">Live</span>
              </div>
              <p className="text-gray-300 leading-relaxed">{generateInsight()}</p>
            </div>
            {lastUpdated && (
              <div className="text-xs text-gray-500 flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {lastUpdated.toLocaleTimeString()}
              </div>
            )}
          </div>
        </div>

        {/* Main Grid */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">

          {/* Left Column - Chart & Strikes */}
          <div className="xl:col-span-2 space-y-6">

            {/* Chart Section */}
            <div className="bg-gray-800/50 rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-bold text-white flex items-center gap-2">
                  <BarChart3 className="w-5 h-5 text-blue-400" />
                  Net Gamma by Strike
                </h3>
                <div className="flex items-center gap-4 text-xs">
                  <div className="flex items-center gap-1.5">
                    <div className="w-3 h-3 rounded bg-purple-500"></div>
                    <span className="text-gray-400">Pin</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-3 h-3 rounded bg-yellow-400"></div>
                    <span className="text-gray-400">Magnet</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-3 h-3 rounded bg-emerald-500"></div>
                    <span className="text-gray-400">+γ</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-3 h-3 rounded bg-rose-500"></div>
                    <span className="text-gray-400">-γ</span>
                  </div>
                </div>
              </div>

              {/* Chart */}
              <div className="relative h-52 flex items-end justify-center gap-1 border-b border-gray-700 mb-2">
                {gammaData?.strikes.map((strike) => (
                  <div
                    key={strike.strike}
                    className="flex flex-col items-center group cursor-pointer"
                    style={{ flex: '1 1 0', maxWidth: '60px' }}
                    onClick={() => setSelectedStrike(strike)}
                  >
                    <div className="text-[10px] text-gray-500 mb-1">
                      {strike.probability > 0 ? `${strike.probability.toFixed(0)}%` : ''}
                    </div>
                    <div
                      className={`w-6 rounded-t ${getBarColor(strike)} transition-all hover:opacity-80 relative`}
                      style={{ height: `${getBarHeightPx(strike.net_gamma, maxGamma)}px` }}
                    >
                      {strike.is_pin && (
                        <Target className="absolute -top-5 left-1/2 -translate-x-1/2 w-4 h-4 text-purple-300" />
                      )}
                      {strike.is_magnet && strike.magnet_rank && !strike.is_pin && (
                        <span className="absolute -top-4 left-1/2 -translate-x-1/2 text-[9px] font-bold text-yellow-400">
                          #{strike.magnet_rank}
                        </span>
                      )}
                    </div>
                  </div>
                ))}

                {/* Spot Line */}
                {gammaData && gammaData.strikes.length > 1 && (
                  <div
                    className="absolute bottom-0 top-0 border-l-2 border-dashed border-emerald-400/60 z-10"
                    style={{
                      left: `${((gammaData.spot_price - gammaData.strikes[0].strike) /
                        (gammaData.strikes[gammaData.strikes.length - 1].strike - gammaData.strikes[0].strike)) * 100}%`
                    }}
                  >
                    <div className="absolute -top-1 left-1 text-[9px] text-emerald-400 font-bold bg-gray-900 px-1 rounded">
                      SPOT
                    </div>
                  </div>
                )}
              </div>

              {/* Strike Labels */}
              <div className="flex justify-center gap-1">
                {gammaData?.strikes.map((strike) => (
                  <div
                    key={`label-${strike.strike}`}
                    className={`text-[11px] font-mono text-center ${
                      strike.is_pin ? 'text-purple-400 font-bold' :
                      strike.is_magnet ? 'text-yellow-400 font-bold' : 'text-gray-500'
                    }`}
                    style={{ flex: '1 1 0', maxWidth: '60px' }}
                  >
                    {strike.strike}
                  </div>
                ))}
              </div>
            </div>

            {/* Strike Details Table */}
            <div className="bg-gray-800/50 rounded-xl p-5">
              <h3 className="font-bold text-white mb-4 flex items-center gap-2">
                <Activity className="w-5 h-5 text-blue-400" />
                Strike Analysis
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-700">
                      <th className="text-left py-2 px-2 text-gray-500 font-medium">Strike</th>
                      <th className="text-right py-2 px-2 text-gray-500 font-medium">Net Gamma</th>
                      <th className="text-right py-2 px-2 text-gray-500 font-medium">Prob %</th>
                      <th className="text-right py-2 px-2 text-gray-500 font-medium">1m ROC</th>
                      <th className="text-right py-2 px-2 text-gray-500 font-medium">5m ROC</th>
                      <th className="text-center py-2 px-2 text-gray-500 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {gammaData?.strikes.map((strike) => (
                      <tr
                        key={strike.strike}
                        className={`border-b border-gray-700/50 hover:bg-gray-700/30 cursor-pointer ${
                          selectedStrike?.strike === strike.strike ? 'bg-purple-500/10' : ''
                        }`}
                        onClick={() => setSelectedStrike(strike)}
                      >
                        <td className="py-2 px-2">
                          <span className={`font-mono font-bold ${
                            strike.is_pin ? 'text-purple-400' :
                            strike.is_magnet ? 'text-yellow-400' : 'text-white'
                          }`}>
                            ${strike.strike}
                          </span>
                        </td>
                        <td className={`py-2 px-2 text-right font-mono ${
                          strike.net_gamma > 0 ? 'text-emerald-400' : 'text-rose-400'
                        }`}>
                          {formatGamma(strike.net_gamma)}
                        </td>
                        <td className="py-2 px-2 text-right text-gray-300">
                          {strike.probability.toFixed(1)}%
                        </td>
                        <td className={`py-2 px-2 text-right font-mono ${
                          strike.roc_1min > 0 ? 'text-emerald-400' : strike.roc_1min < 0 ? 'text-rose-400' : 'text-gray-500'
                        }`}>
                          {strike.roc_1min > 0 ? '+' : ''}{strike.roc_1min.toFixed(1)}%
                        </td>
                        <td className={`py-2 px-2 text-right font-mono ${
                          strike.roc_5min > 0 ? 'text-emerald-400' : strike.roc_5min < 0 ? 'text-rose-400' : 'text-gray-500'
                        }`}>
                          {strike.roc_5min > 0 ? '+' : ''}{strike.roc_5min.toFixed(1)}%
                        </td>
                        <td className="py-2 px-2 text-center">
                          <div className="flex items-center justify-center gap-1">
                            {strike.is_pin && (
                              <span className="px-1.5 py-0.5 bg-purple-500/20 text-purple-400 rounded text-[10px]">PIN</span>
                            )}
                            {strike.is_magnet && (
                              <span className="px-1.5 py-0.5 bg-yellow-500/20 text-yellow-400 rounded text-[10px]">MAG</span>
                            )}
                            {strike.is_danger && (
                              <span className="px-1.5 py-0.5 bg-orange-500/20 text-orange-400 rounded text-[10px]">{strike.danger_type}</span>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Right Column - Alerts & Info */}
          <div className="space-y-6">

            {/* Live Alerts */}
            <div className="bg-gray-800/50 rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-bold text-white flex items-center gap-2">
                  <Bell className="w-5 h-5 text-yellow-400" />
                  Live Alerts
                </h3>
                {alerts.length > 0 && (
                  <span className="px-2 py-0.5 bg-rose-500 text-white text-xs rounded-full font-bold">
                    {alerts.length}
                  </span>
                )}
              </div>
              <div className="space-y-3 max-h-64 overflow-y-auto">
                {alerts.length > 0 ? (
                  alerts.slice(0, 8).map((alert, idx) => (
                    <div
                      key={idx}
                      className={`p-3 rounded-lg border-l-4 ${
                        alert.priority === 'HIGH'
                          ? 'bg-rose-500/10 border-rose-500'
                          : alert.priority === 'MEDIUM'
                          ? 'bg-yellow-500/10 border-yellow-500'
                          : 'bg-gray-700/30 border-gray-600'
                      }`}
                    >
                      <div className="text-sm text-white">{alert.message}</div>
                      <div className="text-xs text-gray-500 mt-1">
                        {new Date(alert.triggered_at).toLocaleTimeString()}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-center py-6 text-gray-500">
                    <Bell className="w-8 h-8 mx-auto mb-2 opacity-30" />
                    <p className="text-sm">No active alerts</p>
                  </div>
                )}
              </div>
            </div>

            {/* Danger Zones Summary */}
            {(buildingZones.length > 0 || collapsingZones.length > 0) && (
              <div className="bg-gray-800/50 rounded-xl p-5">
                <h3 className="font-bold text-white flex items-center gap-2 mb-4">
                  <AlertTriangle className="w-5 h-5 text-orange-400" />
                  Danger Zones
                </h3>

                {buildingZones.length > 0 && (
                  <div className="mb-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Flame className="w-4 h-4 text-orange-400" />
                      <span className="text-sm text-orange-400 font-medium">Building (+ROC)</span>
                    </div>
                    <p className="text-xs text-gray-400 mb-2">Gamma increasing rapidly - potential support/resistance forming</p>
                    <div className="flex flex-wrap gap-1.5">
                      {buildingZones.slice(0, 5).map(dz => (
                        <span key={dz.strike} className="px-2 py-1 bg-orange-500/20 text-orange-400 rounded text-xs">
                          ${dz.strike} (+{dz.roc_5min.toFixed(0)}%)
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {collapsingZones.length > 0 && (
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <TrendingDown className="w-4 h-4 text-rose-400" />
                      <span className="text-sm text-rose-400 font-medium">Collapsing (-ROC)</span>
                    </div>
                    <p className="text-xs text-gray-400 mb-2">Gamma decreasing - support/resistance weakening</p>
                    <div className="flex flex-wrap gap-1.5">
                      {collapsingZones.slice(0, 5).map(dz => (
                        <span key={dz.strike} className="px-2 py-1 bg-rose-500/20 text-rose-400 rounded text-xs">
                          ${dz.strike} ({dz.roc_5min.toFixed(0)}%)
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Key Levels */}
            <div className="bg-gray-800/50 rounded-xl p-5">
              <h3 className="font-bold text-white flex items-center gap-2 mb-4">
                <Target className="w-5 h-5 text-purple-400" />
                Key Levels
              </h3>

              <div className="space-y-4">
                {/* Pin Strike */}
                {gammaData?.likely_pin && (
                  <div className="flex items-center justify-between p-3 bg-purple-500/10 rounded-lg border border-purple-500/30">
                    <div>
                      <div className="text-xs text-purple-400 mb-1">PIN STRIKE</div>
                      <div className="text-lg font-bold text-white">${gammaData.likely_pin}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-gray-500">Probability</div>
                      <div className="text-lg font-bold text-purple-400">{gammaData.pin_probability.toFixed(0)}%</div>
                    </div>
                  </div>
                )}

                {/* Top Magnets */}
                {gammaData?.magnets.slice(0, 3).map((m, idx) => (
                  <div key={m.strike} className="flex items-center justify-between p-3 bg-yellow-500/10 rounded-lg border border-yellow-500/30">
                    <div>
                      <div className="text-xs text-yellow-400 mb-1">MAGNET #{idx + 1}</div>
                      <div className="text-lg font-bold text-white">${m.strike}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-gray-500">Attraction</div>
                      <div className="text-lg font-bold text-yellow-400">{m.probability.toFixed(0)}%</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Bot Status */}
            <div className="bg-gray-800/50 rounded-xl p-5">
              <h3 className="font-bold text-white flex items-center gap-2 mb-4">
                <Bot className="w-5 h-5 text-blue-400" />
                Bot Status
              </h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between p-2 bg-gray-700/30 rounded-lg">
                  <span className="text-gray-300">ARES</span>
                  <span className="text-emerald-400 text-sm">No Position</span>
                </div>
                <div className="flex items-center justify-between p-2 bg-gray-700/30 rounded-lg">
                  <span className="text-gray-300">ATHENA</span>
                  <span className="text-gray-500 text-sm">Watching</span>
                </div>
                <div className="flex items-center justify-between p-2 bg-gray-700/30 rounded-lg">
                  <span className="text-gray-300">PHOENIX</span>
                  <span className="text-gray-500 text-sm">Inactive</span>
                </div>
              </div>
            </div>

            {/* Education */}
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4">
              <div className="flex items-start gap-3">
                <Info className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
                <div className="text-xs text-gray-400 space-y-2">
                  <p className="font-medium text-blue-400">Understanding Gamma</p>
                  <p><strong className="text-emerald-400">+Gamma:</strong> MMs sell rallies, buy dips → stabilizing effect</p>
                  <p><strong className="text-rose-400">-Gamma:</strong> MMs buy rallies, sell dips → amplifies moves</p>
                  <p><strong className="text-yellow-400">Magnets:</strong> High gamma = price attraction zones</p>
                  <p><strong className="text-purple-400">Pin:</strong> Max pain strike for options expiration</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
