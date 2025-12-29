'use client'

/**
 * HYPERION (Weekly Gamma) - Weekly Options Gamma Visualization
 * Named after the Titan of Watchfulness - watching longer-term gamma setups
 *
 * HYPERION focuses on weekly options for stocks/ETFs that don't have 0DTE,
 * providing gamma visualization for weekly expirations.
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
  ChevronUp,
  ChevronDown,
  Minus,
  Clock,
  Info,
  Activity,
  Shield,
  Flame,
  Search,
  CheckCircle2,
  Calendar
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

interface GammaData {
  symbol: string
  expiration_date: string
  snapshot_time: string
  spot_price: number
  expected_move: number
  expected_move_change?: {
    current: number
    prior_day: number | null
    signal: string
    sentiment: string
    interpretation: string
    pct_change_prior: number
  }
  vix: number
  total_net_gamma: number
  gamma_regime: string
  regime_flipped: boolean
  market_status: string
  is_mock: boolean
  is_cached?: boolean
  cache_age_seconds?: number
  fetched_at: string
  data_timestamp?: string
  strikes: StrikeData[]
  magnets: Magnet[]
  likely_pin: number | null
  pin_probability: number | null
  danger_zones: DangerZone[]
  gamma_flips: any[]
  is_stale?: boolean
}

interface ExpirationInfo {
  date: string
  dte: number
  is_weekly: boolean
  is_monthly: boolean
}

// Weekly options symbols (stocks/ETFs with weekly options but NOT 0DTE)
const WEEKLY_SYMBOLS = [
  { symbol: 'AAPL', name: 'Apple Inc.', sector: 'Technology' },
  { symbol: 'MSFT', name: 'Microsoft Corp.', sector: 'Technology' },
  { symbol: 'GOOGL', name: 'Alphabet Inc.', sector: 'Technology' },
  { symbol: 'AMZN', name: 'Amazon.com Inc.', sector: 'Consumer' },
  { symbol: 'NVDA', name: 'NVIDIA Corp.', sector: 'Technology' },
  { symbol: 'META', name: 'Meta Platforms', sector: 'Technology' },
  { symbol: 'TSLA', name: 'Tesla Inc.', sector: 'Consumer' },
  { symbol: 'AMD', name: 'AMD Inc.', sector: 'Technology' },
  { symbol: 'NFLX', name: 'Netflix Inc.', sector: 'Communication' },
  { symbol: 'XLF', name: 'Financial Select ETF', sector: 'ETF' },
  { symbol: 'XLE', name: 'Energy Select ETF', sector: 'ETF' },
  { symbol: 'GLD', name: 'Gold ETF', sector: 'Commodity' },
  { symbol: 'SLV', name: 'Silver ETF', sector: 'Commodity' },
  { symbol: 'TLT', name: 'Treasury Bond ETF', sector: 'Fixed Income' },
]

export default function HyperionPage() {
  const [gammaData, setGammaData] = useState<GammaData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)

  // Symbol selection
  const [selectedSymbol, setSelectedSymbol] = useState<string>('AAPL')
  const [symbolSearch, setSymbolSearch] = useState<string>('')
  const [showSymbolDropdown, setShowSymbolDropdown] = useState(false)

  // Expiration selection
  const [expirations, setExpirations] = useState<ExpirationInfo[]>([])
  const [selectedExpiration, setSelectedExpiration] = useState<string>('')

  // Refs for polling and initial load tracking
  const pollRef = useRef<NodeJS.Timeout | null>(null)
  const initialLoadRef = useRef(true)

  // Check if market is currently open
  const isMarketOpen = useCallback(() => {
    const now = new Date()
    const ct = new Date(now.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
    const day = ct.getDay()
    if (day === 0 || day === 6) return false

    const hour = ct.getHours()
    const minutes = ct.getMinutes()
    const totalMinutes = hour * 60 + minutes

    // Market hours: 8:30 AM - 3:00 PM CT
    return totalMinutes >= 510 && totalMinutes < 900
  }, [])

  // Fetch gamma data
  const fetchGammaData = useCallback(async (expiration?: string) => {
    try {
      // Only show loading on initial load, not on refresh
      if (initialLoadRef.current) {
        setLoading(true)
      }
      // Use dedicated HYPERION endpoint for weekly options
      const exp = expiration || selectedExpiration || undefined
      const response = await apiClient.getHyperionGamma(selectedSymbol, exp)

      if (response.data?.success && response.data?.data) {
        const newData = response.data.data
        setGammaData(newData)
        setLastUpdated(new Date(newData.fetched_at || new Date()))
        setError(null)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch gamma data')
    } finally {
      setLoading(false)
      initialLoadRef.current = false
    }
  }, [selectedSymbol, selectedExpiration])

  // Fetch available expirations for the selected symbol
  const fetchExpirations = useCallback(async () => {
    try {
      const response = await apiClient.getHyperionExpirations(selectedSymbol, 4)

      if (response.data?.success && response.data?.data?.expirations) {
        const exps = response.data.data.expirations as ExpirationInfo[]
        setExpirations(exps)
        // Set default expiration if none selected
        if (exps.length > 0) {
          setSelectedExpiration(prev => prev || exps[0].date)
        }
      } else {
        // Fallback to generating mock expirations
        const today = new Date()
        const mockExpirations: ExpirationInfo[] = []

        for (let i = 0; i < 4; i++) {
          const daysUntilFriday = (5 - today.getDay() + 7) % 7 || 7
          const friday = new Date(today)
          friday.setDate(today.getDate() + daysUntilFriday + (i * 7))

          const dte = Math.ceil((friday.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
          const dateStr = friday.toISOString().split('T')[0]

          mockExpirations.push({
            date: dateStr,
            dte: dte,
            is_weekly: true,
            is_monthly: friday.getDate() > 14 && friday.getDate() <= 21
          })
        }

        setExpirations(mockExpirations)
        // Set default expiration if none selected
        if (mockExpirations.length > 0) {
          setSelectedExpiration(prev => prev || mockExpirations[0].date)
        }
      }
    } catch (err) {
      console.error('[HYPERION] Error fetching expirations:', err)
    }
  }, [selectedSymbol])

  // Reset data when symbol changes
  useEffect(() => {
    setGammaData(null)
    setError(null)
    setSelectedExpiration('')
    initialLoadRef.current = true
    fetchExpirations()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSymbol])

  // Fetch gamma data when expiration changes
  useEffect(() => {
    if (selectedExpiration) {
      fetchGammaData(selectedExpiration)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedExpiration, selectedSymbol])

  // Auto-refresh polling - recreate interval when symbol/expiration changes to avoid stale closures
  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current)

    if (autoRefresh && selectedExpiration) {
      console.log('[HYPERION] Starting auto-refresh polling for', selectedSymbol, selectedExpiration)
      pollRef.current = setInterval(() => {
        fetchGammaData(selectedExpiration)
      }, 30000) // 30 second refresh for weekly data
    }

    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, selectedSymbol, selectedExpiration]) // Include symbol/expiration to avoid stale closures

  // Helpers
  const formatGamma = (value: number): string => {
    const absValue = Math.abs(value)
    if (absValue >= 1e9) return `${(value / 1e9).toFixed(1)}B`
    if (absValue >= 1e6) return `${(value / 1e6).toFixed(1)}M`
    if (absValue >= 1e3) return `${(value / 1e3).toFixed(1)}K`
    return value.toFixed(0)
  }

  const getGammaColor = (value: number): string => {
    if (value > 0) return 'text-emerald-400'
    if (value < 0) return 'text-red-400'
    return 'text-gray-400'
  }

  const getRegimeColor = (regime: string): string => {
    switch (regime?.toUpperCase()) {
      case 'POSITIVE': return 'text-emerald-400'
      case 'NEGATIVE': return 'text-red-400'
      case 'NEUTRAL': return 'text-yellow-400'
      default: return 'text-gray-400'
    }
  }

  // Calculate bar width based on max value in data
  const getBarWidth = (value: number, maxValue: number): number => {
    if (maxValue === 0) return 0
    return Math.min(100, (Math.abs(value) / maxValue) * 100)
  }

  // Filter symbols by search
  const filteredSymbols = WEEKLY_SYMBOLS.filter(s =>
    s.symbol.toLowerCase().includes(symbolSearch.toLowerCase()) ||
    s.name.toLowerCase().includes(symbolSearch.toLowerCase()) ||
    s.sector.toLowerCase().includes(symbolSearch.toLowerCase())
  )

  // Get max gamma for bar scaling
  const maxGamma = gammaData?.strikes?.length
    ? Math.max(...gammaData.strikes.map(s => Math.abs(s.net_gamma)))
    : 1

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
              <h1 className="text-2xl font-bold text-white">HYPERION</h1>
              <p className="text-gray-400 text-sm">Weekly Gamma Intelligence</p>
            </div>

            {/* Symbol Selector */}
            <div className="relative">
              <button
                onClick={() => setShowSymbolDropdown(!showSymbolDropdown)}
                className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 rounded-lg text-white font-bold transition-all"
              >
                <Search className="w-4 h-4" />
                {selectedSymbol}
                <ChevronDown className={`w-4 h-4 transition-transform ${showSymbolDropdown ? 'rotate-180' : ''}`} />
              </button>

              {showSymbolDropdown && (
                <div className="absolute top-full left-0 mt-2 w-72 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50 overflow-hidden">
                  <div className="p-2 border-b border-gray-700">
                    <input
                      type="text"
                      placeholder="Search symbols..."
                      value={symbolSearch}
                      onChange={(e) => setSymbolSearch(e.target.value)}
                      className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:border-purple-500"
                      autoFocus
                    />
                  </div>
                  <div className="max-h-60 overflow-y-auto">
                    {filteredSymbols.map(s => (
                      <button
                        key={s.symbol}
                        onClick={() => {
                          setSelectedSymbol(s.symbol)
                          setShowSymbolDropdown(false)
                          setSymbolSearch('')
                        }}
                        className={`w-full px-4 py-3 flex items-center justify-between transition-colors ${
                          selectedSymbol === s.symbol ? 'bg-purple-500/20' : 'hover:bg-gray-700'
                        }`}
                      >
                        <div className="text-left">
                          <div className="font-bold text-white">{s.symbol}</div>
                          <div className="text-xs text-gray-400">
                            {s.name}
                            <span className="ml-2 text-purple-400/60">({s.sector})</span>
                          </div>
                        </div>
                        {selectedSymbol === s.symbol && (
                          <CheckCircle2 className="w-5 h-5 text-purple-400" />
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Expiration Selector */}
            <div className="flex items-center gap-2 bg-gray-800/50 rounded-lg p-1">
              {expirations.map((exp) => (
                <button
                  key={exp.date}
                  onClick={() => setSelectedExpiration(exp.date)}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                    selectedExpiration === exp.date
                      ? 'bg-purple-500 text-white'
                      : 'text-gray-400 hover:text-white hover:bg-gray-700'
                  }`}
                >
                  <div className="flex items-center gap-1">
                    <Calendar className="w-3 h-3" />
                    <span>{exp.dte}d</span>
                    {exp.is_monthly && <span className="text-xs text-purple-300">(M)</span>}
                  </div>
                </button>
              ))}
            </div>

            {/* Auto-refresh toggle */}
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm ${
                autoRefresh ? 'bg-green-500/20 text-green-400' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
              }`}
            >
              <RefreshCw className={`w-4 h-4 ${autoRefresh ? 'animate-spin' : ''}`} />
              {autoRefresh ? 'Live' : 'Paused'}
            </button>

            {/* Manual refresh */}
            <button
              onClick={() => fetchGammaData()}
              disabled={loading}
              className="px-3 py-1.5 bg-purple-500/20 text-purple-400 rounded-lg text-sm font-medium hover:bg-purple-500/30 transition-colors disabled:opacity-50"
            >
              Refresh
            </button>

            {/* Last Updated */}
            {lastUpdated && (
              <div className="text-xs text-gray-500 flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {lastUpdated.toLocaleTimeString()}
              </div>
            )}
          </div>
        </div>

        {/* Error State */}
        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
            <div className="flex items-center gap-2 text-red-400">
              <AlertTriangle className="w-5 h-5" />
              <span>{error}</span>
            </div>
          </div>
        )}

        {/* Loading State */}
        {loading && !gammaData && (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <RefreshCw className="w-10 h-10 text-purple-500 animate-spin mx-auto mb-4" />
              <p className="text-gray-400">Loading HYPERION data for {selectedSymbol}...</p>
            </div>
          </div>
        )}

        {/* Main Content */}
        {gammaData && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left Column - Summary Cards */}
            <div className="space-y-4">
              {/* Price & Gamma Card */}
              <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-medium text-gray-400">Current Price</h3>
                  <Activity className="w-4 h-4 text-purple-400" />
                </div>
                <div className="text-3xl font-bold text-white mb-2">
                  ${gammaData.spot_price.toFixed(2)}
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-gray-400">Expected Move:</span>
                  <span className="text-purple-400">±${gammaData.expected_move.toFixed(2)}</span>
                </div>
              </div>

              {/* Gamma Regime Card */}
              <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-medium text-gray-400">Gamma Regime</h3>
                  <Zap className={getRegimeColor(gammaData.gamma_regime)} />
                </div>
                <div className={`text-2xl font-bold ${getRegimeColor(gammaData.gamma_regime)}`}>
                  {gammaData.gamma_regime}
                </div>
                <div className="text-sm text-gray-400 mt-1">
                  Net Gamma: {formatGamma(gammaData.total_net_gamma)}
                </div>
                {gammaData.regime_flipped && (
                  <div className="mt-2 px-2 py-1 bg-yellow-500/20 text-yellow-400 text-xs rounded inline-block">
                    Regime Flipped!
                  </div>
                )}
              </div>

              {/* Top Magnets Card */}
              <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-medium text-gray-400">Top Gamma Magnets</h3>
                  <Target className="w-4 h-4 text-purple-400" />
                </div>
                {gammaData.magnets?.length > 0 ? (
                  <div className="space-y-2">
                    {gammaData.magnets.slice(0, 3).map((magnet, idx) => (
                      <div key={idx} className="flex items-center justify-between text-sm">
                        <div className="flex items-center gap-2">
                          <span className="text-purple-400 font-bold">#{magnet.rank}</span>
                          <span className="text-white">${magnet.strike}</span>
                        </div>
                        <span className="text-gray-400">{magnet.probability.toFixed(0)}%</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-gray-500 text-sm">No magnets detected</p>
                )}
              </div>

              {/* Pin Prediction Card */}
              {gammaData.likely_pin && (
                <div className="bg-gray-900/50 border border-purple-500/30 rounded-xl p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-medium text-gray-400">Pin Prediction</h3>
                    <Shield className="w-4 h-4 text-purple-400" />
                  </div>
                  <div className="text-2xl font-bold text-purple-400">
                    ${gammaData.likely_pin}
                  </div>
                  <div className="text-sm text-gray-400 mt-1">
                    Probability: {gammaData.pin_probability?.toFixed(0)}%
                  </div>
                </div>
              )}

              {/* Danger Zones Card */}
              {gammaData.danger_zones?.length > 0 && (
                <div className="bg-gray-900/50 border border-red-500/30 rounded-xl p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-medium text-gray-400">Danger Zones</h3>
                    <Flame className="w-4 h-4 text-red-400" />
                  </div>
                  <div className="space-y-2">
                    {gammaData.danger_zones.slice(0, 3).map((dz, idx) => (
                      <div key={idx} className="flex items-center justify-between text-sm">
                        <span className="text-red-400">${dz.strike}</span>
                        <span className="text-gray-400 text-xs">{dz.danger_type}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Right Column - Strike Chart */}
            <div className="lg:col-span-2">
              <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-white">Net Gamma by Strike</h3>
                  <div className="flex items-center gap-4 text-xs">
                    <div className="flex items-center gap-1">
                      <div className="w-3 h-3 bg-emerald-500 rounded" />
                      <span className="text-gray-400">Positive (Support)</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <div className="w-3 h-3 bg-red-500 rounded" />
                      <span className="text-gray-400">Negative (Resistance)</span>
                    </div>
                  </div>
                </div>

                {/* Strike bars */}
                <div className="space-y-1 max-h-[500px] overflow-y-auto">
                  {gammaData.strikes
                    ?.sort((a, b) => b.strike - a.strike)
                    .map((strike) => {
                      const barWidth = getBarWidth(strike.net_gamma, maxGamma)
                      const isPositive = strike.net_gamma > 0
                      const isAtSpot = Math.abs(strike.strike - gammaData.spot_price) < 0.5

                      return (
                        <div
                          key={strike.strike}
                          className={`flex items-center gap-2 py-1.5 px-2 rounded ${
                            isAtSpot ? 'bg-purple-500/10 border border-purple-500/30' : ''
                          } ${strike.is_magnet ? 'bg-blue-500/10' : ''}`}
                        >
                          {/* Strike Price */}
                          <div className="w-16 text-right">
                            <span className={`text-sm font-medium ${
                              isAtSpot ? 'text-purple-400' : 'text-gray-300'
                            }`}>
                              ${strike.strike}
                            </span>
                          </div>

                          {/* Bar Container */}
                          <div className="flex-1 h-6 flex items-center">
                            <div className="w-full flex">
                              {/* Negative bar (left side) */}
                              <div className="w-1/2 flex justify-end">
                                {!isPositive && (
                                  <div
                                    className="h-5 bg-gradient-to-l from-red-500 to-red-500/30 rounded-l"
                                    style={{ width: `${barWidth}%` }}
                                  />
                                )}
                              </div>
                              {/* Center line */}
                              <div className="w-px bg-gray-600" />
                              {/* Positive bar (right side) */}
                              <div className="w-1/2 flex justify-start">
                                {isPositive && (
                                  <div
                                    className="h-5 bg-gradient-to-r from-emerald-500 to-emerald-500/30 rounded-r"
                                    style={{ width: `${barWidth}%` }}
                                  />
                                )}
                              </div>
                            </div>
                          </div>

                          {/* Gamma Value */}
                          <div className="w-20 text-right">
                            <span className={`text-sm ${getGammaColor(strike.net_gamma)}`}>
                              {formatGamma(strike.net_gamma)}
                            </span>
                          </div>

                          {/* Indicators */}
                          <div className="w-8 flex items-center justify-end gap-1">
                            {strike.is_magnet && (
                              <Target className="w-3 h-3 text-blue-400" />
                            )}
                            {strike.is_pin && (
                              <Shield className="w-3 h-3 text-purple-400" />
                            )}
                            {strike.is_danger && (
                              <Flame className="w-3 h-3 text-red-400" />
                            )}
                          </div>
                        </div>
                      )
                    })}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Info Footer */}
        <div className="mt-6 p-4 bg-gray-900/30 border border-gray-800 rounded-lg">
          <div className="flex items-start gap-2">
            <Info className="w-5 h-5 text-purple-400 mt-0.5 flex-shrink-0" />
            <div className="text-sm text-gray-400">
              <p className="mb-1">
                <strong className="text-purple-400">HYPERION</strong> provides weekly gamma visualization for stocks and ETFs with weekly options.
              </p>
              <p>
                Unlike ARGUS (0DTE), HYPERION focuses on longer-dated weekly expirations, helping identify
                key support/resistance levels and gamma magnets for swing trading setups.
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
