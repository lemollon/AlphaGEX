'use client'

/**
 * HYPERION (Weekly Gamma) - Weekly Options Gamma Visualization (Enhanced)
 * Named after the Titan of Watchfulness - watching longer-term gamma setups
 *
 * HYPERION focuses on weekly options for stocks/ETFs that don't have 0DTE,
 * providing gamma visualization for weekly expirations.
 *
 * Enhanced Features (matching ARGUS):
 * - Market structure panel (9 signals)
 * - Alerts system
 * - Pattern matching
 * - Strike trends
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import {
  Eye,
  RefreshCw,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Target,
  Zap,
  ChevronDown,
  ChevronUp,
  Clock,
  Info,
  Activity,
  Shield,
  Flame,
  Search,
  CheckCircle2,
  Calendar,
  BarChart3,
  Brain,
  Bell,
  LayoutGrid,
  GitCompare,
  ArrowRight,
  ArrowUp,
  ArrowDown,
  Minus,
  AlertCircle
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import OrionStatusBadge from '@/components/OrionStatusBadge'
import { HyperionEnhancedPanel } from '@/components/HyperionEnhancements'
import { apiClient } from '@/lib/api'

// Types
interface StrikeData {
  strike: number
  net_gamma: number
  probability: number
  gamma_change_pct: number
  roc_1min: number
  roc_5min: number
  roc_30min: number
  roc_1hr: number
  roc_4hr: number
  roc_trading_day: number
  is_magnet: boolean
  magnet_rank: number | null
  is_pin: boolean
  is_danger: boolean
  danger_type: string | null
  gamma_flipped: boolean
  flip_direction: string | null
}

// ROC timeframe options for dropdown (longer timeframes only)
type RocTimeframe = '4hr' | 'day'

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

interface MarketStructure {
  flip_point: {
    current: number | null
    prior: number | null
    direction: string
    implication: string
  }
  bounds: {
    current_upper: number
    current_lower: number
    direction: string
    implication: string
  }
  width: {
    current_width: number
    direction: string
    implication: string
  }
  walls: {
    current_call_wall: number | null
    current_put_wall: number | null
    implication: string
  }
  vix_regime: {
    vix: number
    regime: string
    implication: string
  }
  gamma_regime: {
    current_regime: string
    alignment: string
    implication: string
  }
  gex_momentum: {
    direction: string
    conviction: string
    implication: string
  }
  wall_break: {
    call_wall_risk: string
    put_wall_risk: string
    implication: string
  }
  combined: {
    signal: string
    bias: string
    confidence: string
    strategy: string
    warnings: string[]
  }
}

interface Alert {
  id: number
  alert_type: string
  strike: number | null
  message: string
  priority: string
  spot_price: number
  triggered_at: string
  acknowledged: boolean
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
  is_mock: boolean
  is_cached?: boolean
  fetched_at: string
  strikes: StrikeData[]
  magnets: Magnet[]
  likely_pin: number | null
  pin_probability: number | null
  danger_zones: DangerZone[]
  gamma_flips: any[]
  pinning_status?: {
    is_pinning: boolean
    pin_strike?: number
    distance_to_pin_pct?: number
    avg_roc?: number
    message?: string
    trade_idea?: string
  }
  market_structure?: MarketStructure | null
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
  const sidebarPadding = useSidebarPadding()
  const [gammaData, setGammaData] = useState<GammaData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [selectedStrike, setSelectedStrike] = useState<StrikeData | null>(null)

  // Symbol selection
  const [selectedSymbol, setSelectedSymbol] = useState<string>('AAPL')
  const [symbolSearch, setSymbolSearch] = useState<string>('')
  const [showSymbolDropdown, setShowSymbolDropdown] = useState(false)

  // ROC timeframe selection
  const [selectedRocTimeframe, setSelectedRocTimeframe] = useState<RocTimeframe>('4hr')
  const rocTimeframeOptions: { value: RocTimeframe; label: string; shortLabel: string }[] = [
    { value: '4hr', label: '4 Hours', shortLabel: '4h' },
    { value: 'day', label: 'Trading Day', shortLabel: 'Day' },
  ]

  // Expiration selection
  const [expirations, setExpirations] = useState<ExpirationInfo[]>([])
  const [selectedExpiration, setSelectedExpiration] = useState<string>('')

  // Panel expansion state
  const [alertsExpanded, setAlertsExpanded] = useState(true)
  const [marketStructureExpanded, setMarketStructureExpanded] = useState(true)

  // Alerts state
  const [alerts, setAlerts] = useState<Alert[]>([])

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
      if (initialLoadRef.current) {
        setLoading(true)
      }
      const exp = expiration || selectedExpiration || undefined
      const response = await apiClient.getHyperionGamma(selectedSymbol, exp)

      if (response.data?.success && response.data?.data) {
        const newData = response.data.data

        // Handle data unavailable response (no mock data - show clear error)
        if (newData.data_unavailable) {
          console.log('[HYPERION] Data unavailable:', newData.reason, newData.message)
          setError(newData.message || 'Data unavailable')
          setGammaData(null)
          return
        }

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

  // Fetch alerts
  const fetchAlerts = useCallback(async () => {
    try {
      const response = await apiClient.getHyperionAlerts(selectedSymbol, 20, false)
      if (response.data?.success && response.data?.data?.alerts) {
        setAlerts(response.data.data.alerts)
      }
    } catch (err) {
      console.error('[HYPERION] Error fetching alerts:', err)
    }
  }, [selectedSymbol])

  // Track if we're doing a fresh symbol load
  const symbolChangeRef = useRef<string | null>(null)

  // Fetch available expirations for the selected symbol
  const fetchExpirations = useCallback(async () => {
    try {
      const fetchSymbol = selectedSymbol
      symbolChangeRef.current = fetchSymbol

      const response = await apiClient.getHyperionExpirations(selectedSymbol, 4)

      if (symbolChangeRef.current !== fetchSymbol) {
        return
      }

      if (response.data?.success && response.data?.data?.expirations) {
        const exps = response.data.data.expirations as ExpirationInfo[]
        setExpirations(exps)
        if (exps.length > 0) {
          setSelectedExpiration(exps[0].date)
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
        if (mockExpirations.length > 0) {
          setSelectedExpiration(mockExpirations[0].date)
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
    setAlerts([])
    initialLoadRef.current = true
    fetchExpirations()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSymbol])

  // Fetch gamma data when expiration changes
  useEffect(() => {
    if (selectedExpiration) {
      fetchGammaData(selectedExpiration)
      fetchAlerts()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedExpiration, selectedSymbol])

  // Auto-refresh polling
  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current)

    if (autoRefresh && selectedExpiration) {
      pollRef.current = setInterval(() => {
        fetchGammaData(selectedExpiration)
        fetchAlerts()
      }, 30000) // 30 second refresh for weekly data
    }

    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, selectedSymbol, selectedExpiration])

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
    if (strike.is_magnet) return 'bg-yellow-400'
    if (strike.net_gamma > 0) return 'bg-emerald-500'
    return 'bg-rose-500'
  }

  const getBarHeightPx = (value: number, maxValue: number): number => {
    if (maxValue === 0) return 4
    return Math.max(4, Math.min(160, (Math.abs(value) / maxValue) * 160))
  }

  // Memoize filtered symbols
  const filteredSymbols = useMemo(() =>
    WEEKLY_SYMBOLS.filter(s =>
      s.symbol.toLowerCase().includes(symbolSearch.toLowerCase()) ||
      s.name.toLowerCase().includes(symbolSearch.toLowerCase()) ||
      s.sector.toLowerCase().includes(symbolSearch.toLowerCase())
    ),
    [symbolSearch]
  )

  // Memoize filtered strikes - only recenter when strikes change, NOT on spot price changes
  // This ensures the spot line moves visibly within the stable strike window
  const filteredStrikes = useMemo(() => {
    if (!gammaData?.strikes?.length) return []

    const sorted = [...gammaData.strikes].sort((a, b) => a.strike - b.strike)
    const spotIdx = sorted.findIndex(s => s.strike >= gammaData.spot_price)
    const startIdx = Math.max(0, spotIdx - 7)
    const endIdx = Math.min(sorted.length, spotIdx + 8)

    return sorted.slice(startIdx, endIdx)
  }, [gammaData?.strikes]) // eslint-disable-line react-hooks/exhaustive-deps

  // Memoize danger zone filtering
  const { buildingZones, collapsingZones, spikeZones } = useMemo(() => ({
    buildingZones: gammaData?.danger_zones?.filter(d => d.danger_type === 'BUILDING') || [],
    collapsingZones: gammaData?.danger_zones?.filter(d => d.danger_type === 'COLLAPSING') || [],
    spikeZones: gammaData?.danger_zones?.filter(d => d.danger_type === 'SPIKE') || []
  }), [gammaData?.danger_zones])

  // Memoize high priority alerts
  const highPriorityAlerts = useMemo(() =>
    alerts.filter(a => a.priority === 'HIGH' || a.priority === 'MEDIUM'),
    [alerts]
  )

  // Get max gamma for bar scaling
  const maxGamma = filteredStrikes.length
    ? Math.max(...filteredStrikes.map(s => Math.abs(s.net_gamma)), 1)
    : 1

  // Generate AI insight
  const generateInsight = () => {
    if (!gammaData) return ''

    const regime = gammaData.gamma_regime
    const pin = gammaData.likely_pin
    const topMagnet = gammaData.magnets?.[0]
    const spotDistance = topMagnet ? ((topMagnet.strike - gammaData.spot_price) / gammaData.spot_price * 100).toFixed(2) : 0

    if (regime === 'POSITIVE') {
      return `${gammaData.symbol} is in a POSITIVE gamma regime, suggesting mean-reversion and range-bound behavior. Price is likely to gravitate toward ${pin ? `$${pin}` : 'the pin strike'} by expiration. Top magnet at $${topMagnet?.strike || 'N/A'} (${spotDistance}% away).`
    } else if (regime === 'NEGATIVE') {
      return `${gammaData.symbol} is in a NEGATIVE gamma regime, indicating potential for amplified moves. Dealers are short gamma and will hedge in the same direction as price moves. Watch for breakouts beyond expected move.`
    }
    return `${gammaData.symbol} is in a NEUTRAL gamma regime. Market makers have balanced exposure. Price action likely to be choppy without strong directional bias.`
  }

  // Get signal color and icon
  const getSignalDisplay = (direction: string) => {
    switch (direction) {
      case 'RISING':
      case 'SHIFTED_UP':
      case 'WIDENING':
      case 'EXPANDING':
      case 'STRONG_BULLISH':
      case 'BULLISH':
        return { color: 'text-emerald-400', icon: <ArrowUp className="w-4 h-4" />, bg: 'bg-emerald-500/20' }
      case 'FALLING':
      case 'SHIFTED_DOWN':
      case 'NARROWING':
      case 'CONTRACTING':
      case 'STRONG_BEARISH':
      case 'BEARISH':
        return { color: 'text-rose-400', icon: <ArrowDown className="w-4 h-4" />, bg: 'bg-rose-500/20' }
      case 'HIGH':
        return { color: 'text-red-400', icon: <AlertCircle className="w-4 h-4" />, bg: 'bg-red-500/20' }
      case 'ELEVATED':
        return { color: 'text-orange-400', icon: <AlertTriangle className="w-4 h-4" />, bg: 'bg-orange-500/20' }
      default:
        return { color: 'text-gray-400', icon: <Minus className="w-4 h-4" />, bg: 'bg-gray-500/20' }
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <Navigation />

      <main className={`pt-24 px-4 sm:px-6 lg:px-8 max-w-[1600px] mx-auto pb-8 ${sidebarPadding}`}>
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

            {/* ORION ML Status */}
            <OrionStatusBadge />

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
                {lastUpdated.toLocaleTimeString('en-US', { timeZone: 'America/Chicago', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true })} CT
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
          <>
            {/* Key Metrics Cards - Horizontal Row */}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 mb-6">
              <div className="bg-gray-800/50 rounded-xl p-4">
                <div className="text-gray-500 text-xs mb-1">Spot Price</div>
                <div className="text-xl font-bold text-white">${gammaData.spot_price.toFixed(2)}</div>
              </div>
              <div className="bg-gray-800/50 rounded-xl p-4">
                <div className="text-gray-500 text-xs mb-1">Expected Move</div>
                <div className="text-xl font-bold text-blue-400">±${gammaData.expected_move.toFixed(2)}</div>
              </div>
              <div className="bg-gray-800/50 rounded-xl p-4">
                <div className="text-gray-500 text-xs mb-1">VIX</div>
                <div className={`text-xl font-bold ${(gammaData.vix || 0) > 20 ? 'text-orange-400' : 'text-emerald-400'}`}>
                  {gammaData.vix?.toFixed(1) || 'N/A'}
                </div>
              </div>
              <div className="bg-gray-800/50 rounded-xl p-4">
                <div className="text-gray-500 text-xs mb-1">Net GEX</div>
                <div className={`text-xl font-bold ${
                  (gammaData.total_net_gamma || 0) > 0 ? 'text-emerald-400' : 'text-rose-400'
                }`}>
                  {formatGamma(gammaData.total_net_gamma || 0)}
                </div>
              </div>
              <div className="bg-gray-800/50 rounded-xl p-4">
                <div className="text-gray-500 text-xs mb-1">Gamma Regime</div>
                <div className={`text-xl font-bold ${
                  gammaData.gamma_regime === 'POSITIVE' ? 'text-emerald-400' :
                  gammaData.gamma_regime === 'NEGATIVE' ? 'text-rose-400' : 'text-gray-400'
                }`}>
                  {gammaData.gamma_regime}
                </div>
              </div>
              <div className="bg-gray-800/50 rounded-xl p-4">
                <div className="text-gray-500 text-xs mb-1">Top Magnet</div>
                <div className="text-xl font-bold text-yellow-400">
                  ${gammaData.magnets?.[0]?.strike || '-'}
                </div>
              </div>
              <div className="bg-gray-800/50 rounded-xl p-4">
                <div className="text-gray-500 text-xs mb-1">Pin Strike</div>
                <div className="text-xl font-bold text-purple-400">
                  ${gammaData.likely_pin || '-'}
                </div>
              </div>
            </div>

            {/* Alerts Banner (if any high priority alerts) */}
            {highPriorityAlerts.length > 0 && (
              <div className="mb-6">
                <div
                  className="bg-gradient-to-r from-red-900/40 to-orange-900/40 border border-red-500/30 rounded-xl p-4 cursor-pointer"
                  onClick={() => setAlertsExpanded(!alertsExpanded)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <Bell className="w-5 h-5 text-red-400" />
                      <span className="font-bold text-white">Active Alerts</span>
                      <span className="px-2 py-0.5 bg-red-500/20 text-red-400 text-xs rounded-full">
                        {highPriorityAlerts.length}
                      </span>
                    </div>
                    {alertsExpanded ? <ChevronUp className="w-5 h-5 text-gray-400" /> : <ChevronDown className="w-5 h-5 text-gray-400" />}
                  </div>
                  {alertsExpanded && (
                    <div className="mt-4 space-y-2">
                      {highPriorityAlerts.slice(0, 5).map((alert) => (
                        <div key={alert.id} className="flex items-center justify-between p-2 bg-gray-900/50 rounded-lg">
                          <div className="flex items-center gap-2">
                            <span className={`px-2 py-0.5 text-xs rounded ${
                              alert.priority === 'HIGH' ? 'bg-red-500/20 text-red-400' : 'bg-orange-500/20 text-orange-400'
                            }`}>
                              {alert.priority}
                            </span>
                            <span className="text-sm text-gray-300">{alert.message}</span>
                          </div>
                          <span className="text-xs text-gray-500">
                            {new Date(alert.triggered_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Market Structure Panel */}
            {gammaData.market_structure && (
              <div className="mb-6">
                <div
                  className="bg-gray-800/50 border border-purple-500/30 rounded-xl cursor-pointer"
                  onClick={() => setMarketStructureExpanded(!marketStructureExpanded)}
                >
                  <div className="p-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <LayoutGrid className="w-5 h-5 text-purple-400" />
                      <span className="font-bold text-white">Market Structure Signals</span>
                      {gammaData.market_structure.combined && (
                        <span className={`px-2 py-0.5 text-xs rounded ${
                          gammaData.market_structure.combined.bias === 'BULLISH' ? 'bg-emerald-500/20 text-emerald-400' :
                          gammaData.market_structure.combined.bias === 'BEARISH' ? 'bg-rose-500/20 text-rose-400' :
                          'bg-gray-500/20 text-gray-400'
                        }`}>
                          {gammaData.market_structure.combined.signal}
                        </span>
                      )}
                    </div>
                    {marketStructureExpanded ? <ChevronUp className="w-5 h-5 text-gray-400" /> : <ChevronDown className="w-5 h-5 text-gray-400" />}
                  </div>

                  {marketStructureExpanded && (
                    <div className="px-4 pb-4">
                      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                        {/* VIX Regime */}
                        <div className="p-3 bg-gray-900/50 rounded-lg">
                          <div className="text-xs text-gray-500 mb-1">VIX Regime</div>
                          <div className={`font-bold ${
                            gammaData.market_structure.vix_regime.regime === 'LOW' ? 'text-emerald-400' :
                            gammaData.market_structure.vix_regime.regime === 'NORMAL' ? 'text-blue-400' :
                            gammaData.market_structure.vix_regime.regime === 'ELEVATED' ? 'text-orange-400' :
                            'text-red-400'
                          }`}>
                            {gammaData.market_structure.vix_regime.regime}
                          </div>
                          <div className="text-xs text-gray-500 mt-1">{gammaData.market_structure.vix_regime.vix?.toFixed(1)}</div>
                        </div>

                        {/* Gamma Regime */}
                        <div className="p-3 bg-gray-900/50 rounded-lg">
                          <div className="text-xs text-gray-500 mb-1">Gamma Alignment</div>
                          <div className={`font-bold ${
                            gammaData.market_structure.gamma_regime.alignment === 'MEAN_REVERSION' ? 'text-emerald-400' :
                            gammaData.market_structure.gamma_regime.alignment === 'MOMENTUM' ? 'text-rose-400' :
                            'text-gray-400'
                          }`}>
                            {gammaData.market_structure.gamma_regime.alignment}
                          </div>
                        </div>

                        {/* Flip Point */}
                        {gammaData.market_structure.flip_point.direction !== 'UNKNOWN' && (
                          <div className="p-3 bg-gray-900/50 rounded-lg">
                            <div className="text-xs text-gray-500 mb-1">Flip Point</div>
                            <div className="flex items-center gap-1">
                              {getSignalDisplay(gammaData.market_structure.flip_point.direction).icon}
                              <span className={`font-bold ${getSignalDisplay(gammaData.market_structure.flip_point.direction).color}`}>
                                {gammaData.market_structure.flip_point.direction}
                              </span>
                            </div>
                            {gammaData.market_structure.flip_point.current && (
                              <div className="text-xs text-gray-500 mt-1">${gammaData.market_structure.flip_point.current.toFixed(2)}</div>
                            )}
                          </div>
                        )}

                        {/* Bounds */}
                        {gammaData.market_structure.bounds.direction !== 'UNKNOWN' && (
                          <div className="p-3 bg-gray-900/50 rounded-lg">
                            <div className="text-xs text-gray-500 mb-1">Bounds</div>
                            <div className="flex items-center gap-1">
                              {getSignalDisplay(gammaData.market_structure.bounds.direction).icon}
                              <span className={`font-bold ${getSignalDisplay(gammaData.market_structure.bounds.direction).color}`}>
                                {gammaData.market_structure.bounds.direction}
                              </span>
                            </div>
                          </div>
                        )}

                        {/* Width */}
                        {gammaData.market_structure.width.direction !== 'UNKNOWN' && (
                          <div className="p-3 bg-gray-900/50 rounded-lg">
                            <div className="text-xs text-gray-500 mb-1">Range Width</div>
                            <div className="flex items-center gap-1">
                              {getSignalDisplay(gammaData.market_structure.width.direction).icon}
                              <span className={`font-bold ${getSignalDisplay(gammaData.market_structure.width.direction).color}`}>
                                {gammaData.market_structure.width.direction}
                              </span>
                            </div>
                          </div>
                        )}

                        {/* Walls */}
                        {gammaData.market_structure.walls.current_call_wall && (
                          <div className="p-3 bg-gray-900/50 rounded-lg">
                            <div className="text-xs text-gray-500 mb-1">Gamma Walls</div>
                            <div className="text-xs">
                              <span className="text-emerald-400">C: ${gammaData.market_structure.walls.current_call_wall?.toFixed(0)}</span>
                              {' / '}
                              <span className="text-rose-400">P: ${gammaData.market_structure.walls.current_put_wall?.toFixed(0)}</span>
                            </div>
                          </div>
                        )}

                        {/* Wall Break Risk */}
                        {(gammaData.market_structure.wall_break.call_wall_risk === 'HIGH' ||
                          gammaData.market_structure.wall_break.put_wall_risk === 'HIGH') && (
                          <div className="p-3 bg-red-900/30 border border-red-500/30 rounded-lg">
                            <div className="text-xs text-gray-500 mb-1">Wall Break Risk</div>
                            <div className="flex items-center gap-1">
                              <AlertCircle className="w-4 h-4 text-red-400" />
                              <span className="font-bold text-red-400">HIGH</span>
                            </div>
                          </div>
                        )}

                        {/* GEX Momentum */}
                        {gammaData.market_structure.gex_momentum.direction !== 'UNKNOWN' && (
                          <div className="p-3 bg-gray-900/50 rounded-lg">
                            <div className="text-xs text-gray-500 mb-1">GEX Momentum</div>
                            <div className="flex items-center gap-1">
                              {getSignalDisplay(gammaData.market_structure.gex_momentum.direction).icon}
                              <span className={`font-bold ${getSignalDisplay(gammaData.market_structure.gex_momentum.direction).color}`}>
                                {gammaData.market_structure.gex_momentum.direction}
                              </span>
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Combined Strategy */}
                      {gammaData.market_structure.combined && (
                        <div className="mt-4 p-3 bg-purple-500/10 border border-purple-500/30 rounded-lg">
                          <div className="flex items-center gap-2 mb-2">
                            <Brain className="w-4 h-4 text-purple-400" />
                            <span className="text-sm font-medium text-purple-400">Suggested Strategy</span>
                            <span className={`px-2 py-0.5 text-xs rounded ${
                              gammaData.market_structure.combined.confidence === 'HIGH' ? 'bg-emerald-500/20 text-emerald-400' :
                              gammaData.market_structure.combined.confidence === 'MEDIUM' ? 'bg-yellow-500/20 text-yellow-400' :
                              'bg-gray-500/20 text-gray-400'
                            }`}>
                              {gammaData.market_structure.combined.confidence} Confidence
                            </span>
                          </div>
                          <p className="text-sm text-gray-300">{gammaData.market_structure.combined.strategy}</p>
                          {gammaData.market_structure.combined.warnings?.length > 0 && (
                            <div className="mt-2 flex flex-wrap gap-2">
                              {gammaData.market_structure.combined.warnings.map((w, i) => (
                                <span key={i} className="px-2 py-0.5 bg-red-500/20 text-red-400 text-xs rounded">
                                  {w}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* AI Analysis Banner */}
            <div className="bg-gradient-to-r from-purple-900/40 to-blue-900/40 border border-purple-500/30 rounded-xl p-5 mb-6">
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center flex-shrink-0">
                  <Brain className="w-5 h-5 text-purple-400" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <h3 className="font-bold text-white">HYPERION AI Analysis</h3>
                    <span className="text-xs bg-purple-500/20 text-purple-400 px-2 py-0.5 rounded">
                      {gammaData.is_mock ? 'Simulated' : 'Live'}
                    </span>
                  </div>
                  <p className="text-gray-300 leading-relaxed">{generateInsight()}</p>
                </div>
              </div>
            </div>

            {/* Main Grid */}
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
              {/* Left Column - Chart & Table */}
              <div className="xl:col-span-2 space-y-6">
                {/* Horizontal Bar Chart */}
                <div className="bg-gray-800/50 rounded-xl p-5">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <h3 className="font-bold text-white flex items-center gap-2">
                        <BarChart3 className="w-5 h-5 text-blue-400" />
                        Net Gamma by Strike
                      </h3>
                      {gammaData.is_mock && (
                        <span className="px-2 py-0.5 bg-orange-500/20 text-orange-400 text-[10px] font-medium rounded border border-orange-500/30">
                          SIMULATED
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-xs flex-wrap">
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
                        <span className="text-gray-400">+gamma</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <div className="w-3 h-3 rounded bg-rose-500"></div>
                        <span className="text-gray-400">-gamma</span>
                      </div>
                    </div>
                  </div>

                  {/* Chart */}
                  <div className="relative h-52 flex items-end justify-center gap-1 border-b border-gray-700 mb-2">
                    {filteredStrikes.map((strike) => (
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
                            <span className="absolute -top-7 left-1/2 -translate-x-1/2 text-[9px] font-bold text-yellow-400 whitespace-nowrap">
                              #{strike.magnet_rank}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}

                    {/* Spot Line - key forces re-render when spot_price changes */}
                    {filteredStrikes.length > 1 && (
                      <div
                        key={`spot-line-${gammaData.spot_price.toFixed(2)}`}
                        className="absolute bottom-0 top-0 border-l-2 border-dashed border-emerald-400/60 z-10 transition-all duration-500 ease-out"
                        style={{
                          left: `${((gammaData.spot_price - filteredStrikes[0].strike) /
                            (filteredStrikes[filteredStrikes.length - 1].strike - filteredStrikes[0].strike)) * 100}%`
                        }}
                      >
                        <div className="absolute -top-1 left-1 text-[9px] text-emerald-400 font-bold bg-gray-900 px-1 rounded whitespace-nowrap">
                          SPOT ${gammaData.spot_price.toFixed(2)}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Strike Labels */}
                  <div className="flex justify-center gap-1">
                    {filteredStrikes.map((strike) => (
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
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-bold text-white flex items-center gap-2">
                      <Activity className="w-5 h-5 text-blue-400" />
                      Strike Analysis
                    </h3>
                    {/* ROC Timeframe Selector */}
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-500">ROC:</span>
                      <select
                        value={selectedRocTimeframe}
                        onChange={(e) => setSelectedRocTimeframe(e.target.value as RocTimeframe)}
                        className="px-2 py-1 bg-gray-700 border border-gray-600 rounded text-xs text-white focus:outline-none focus:border-purple-500"
                      >
                        {rocTimeframeOptions.map((opt) => (
                          <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-gray-700">
                          <th className="text-left py-2 px-2 text-gray-500 font-medium">Strike</th>
                          <th className="text-right py-2 px-2 text-gray-500 font-medium">Dist</th>
                          <th className="text-right py-2 px-2 text-gray-500 font-medium">Net Gamma</th>
                          <th className="text-right py-2 px-2 text-gray-500 font-medium">1m</th>
                          <th className="text-right py-2 px-2 text-gray-500 font-medium">5m</th>
                          <th className="text-right py-2 px-2 text-gray-500 font-medium">30m</th>
                          <th className="text-right py-2 px-2 text-gray-500 font-medium">1hr</th>
                          <th className="text-right py-2 px-2 text-gray-500 font-medium">
                            {rocTimeframeOptions.find(o => o.value === selectedRocTimeframe)?.shortLabel}
                          </th>
                          <th className="text-center py-2 px-2 text-gray-500 font-medium">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredStrikes.map((strike) => (
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
                            <td className={`py-2 px-2 text-right font-mono text-xs ${
                              ((strike.strike - gammaData.spot_price) / gammaData.spot_price * 100) > 0 ? 'text-emerald-400' :
                              ((strike.strike - gammaData.spot_price) / gammaData.spot_price * 100) < 0 ? 'text-rose-400' : 'text-gray-500'
                            }`}>
                              {((strike.strike - gammaData.spot_price) / gammaData.spot_price * 100) > 0 ? '+' : ''}
                              {((strike.strike - gammaData.spot_price) / gammaData.spot_price * 100).toFixed(2)}%
                            </td>
                            <td className={`py-2 px-2 text-right font-mono ${
                              strike.net_gamma > 0 ? 'text-emerald-400' : 'text-rose-400'
                            }`}>
                              {formatGamma(strike.net_gamma)}
                            </td>
                            <td className={`py-2 px-2 text-right font-mono text-xs ${
                              (strike.roc_1min || 0) > 0 ? 'text-emerald-400' : (strike.roc_1min || 0) < 0 ? 'text-rose-400' : 'text-gray-500'
                            }`}>
                              {(strike.roc_1min || 0) > 0 ? '+' : ''}{(strike.roc_1min || 0).toFixed(1)}%
                            </td>
                            <td className={`py-2 px-2 text-right font-mono text-xs ${
                              (strike.roc_5min || 0) > 0 ? 'text-emerald-400' : (strike.roc_5min || 0) < 0 ? 'text-rose-400' : 'text-gray-500'
                            }`}>
                              {(strike.roc_5min || 0) > 0 ? '+' : ''}{(strike.roc_5min || 0).toFixed(1)}%
                            </td>
                            <td className={`py-2 px-2 text-right font-mono text-xs ${
                              (strike.roc_30min || 0) > 0 ? 'text-emerald-400' : (strike.roc_30min || 0) < 0 ? 'text-rose-400' : 'text-gray-500'
                            }`}>
                              {(strike.roc_30min || 0) > 0 ? '+' : ''}{(strike.roc_30min || 0).toFixed(1)}%
                            </td>
                            <td className={`py-2 px-2 text-right font-mono text-xs ${
                              (strike.roc_1hr || 0) > 0 ? 'text-emerald-400' : (strike.roc_1hr || 0) < 0 ? 'text-rose-400' : 'text-gray-500'
                            }`}>
                              {(strike.roc_1hr || 0) > 0 ? '+' : ''}{(strike.roc_1hr || 0).toFixed(1)}%
                            </td>
                            <td className={`py-2 px-2 text-right font-mono text-xs ${
                              (() => {
                                const rocValue = selectedRocTimeframe === '4hr' ? strike.roc_4hr : strike.roc_trading_day
                                return (rocValue || 0) > 0 ? 'text-emerald-400' : (rocValue || 0) < 0 ? 'text-rose-400' : 'text-gray-500'
                              })()
                            }`}>
                              {(() => {
                                const rocValue = selectedRocTimeframe === '4hr' ? strike.roc_4hr : strike.roc_trading_day
                                return `${(rocValue || 0) > 0 ? '+' : ''}${(rocValue || 0).toFixed(1)}%`
                              })()}
                            </td>
                            <td className="py-2 px-2 text-center">
                              <div className="flex items-center justify-center gap-1 flex-wrap">
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

              {/* Right Column - Summary Cards */}
              <div className="space-y-4">
                {/* Top Magnets Card */}
                <div className="bg-gray-800/50 rounded-xl p-5">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-bold text-white flex items-center gap-2">
                      <Target className="w-5 h-5 text-yellow-400" />
                      Top Gamma Magnets
                    </h3>
                  </div>
                  {gammaData.magnets?.length > 0 ? (
                    <div className="space-y-3">
                      {gammaData.magnets.slice(0, 5).map((magnet, idx) => (
                        <div key={idx} className="flex items-center justify-between p-3 bg-gray-900/50 rounded-lg">
                          <div className="flex items-center gap-3">
                            <span className="w-6 h-6 flex items-center justify-center bg-yellow-500/20 text-yellow-400 rounded-full text-xs font-bold">
                              {magnet.rank}
                            </span>
                            <span className="text-white font-mono font-bold">${magnet.strike}</span>
                          </div>
                          <div className="text-right">
                            <div className={`font-mono text-sm ${magnet.net_gamma > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                              {formatGamma(magnet.net_gamma)}
                            </div>
                            <div className="text-xs text-gray-500">{magnet.probability?.toFixed(0) || 0}% prob</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-gray-500 text-sm text-center py-4">No magnets detected</p>
                  )}
                </div>

                {/* Pin Prediction Card */}
                {gammaData.likely_pin && (
                  <div className="bg-gradient-to-br from-purple-900/30 to-blue-900/30 border border-purple-500/30 rounded-xl p-5">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="font-bold text-white flex items-center gap-2">
                        <Shield className="w-5 h-5 text-purple-400" />
                        Pin Prediction
                      </h3>
                    </div>
                    <div className="text-center">
                      <div className="text-4xl font-bold text-purple-400 mb-2">
                        ${gammaData.likely_pin}
                      </div>
                      <div className="text-sm text-gray-400">
                        {gammaData.pin_probability?.toFixed(0) || 0}% probability
                      </div>
                      <div className="mt-3 text-xs text-gray-500">
                        Distance: {((gammaData.likely_pin - gammaData.spot_price) / gammaData.spot_price * 100).toFixed(2)}%
                      </div>
                    </div>
                  </div>
                )}

                {/* Danger Zones Card */}
                {gammaData.danger_zones?.length > 0 && (
                  <div className="bg-gray-800/50 border border-red-500/30 rounded-xl p-5">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="font-bold text-white flex items-center gap-2">
                        <Flame className="w-5 h-5 text-red-400" />
                        Danger Zones
                      </h3>
                    </div>
                    <div className="space-y-2">
                      {gammaData.danger_zones.slice(0, 5).map((dz, idx) => (
                        <div key={idx} className="flex items-center justify-between p-2 bg-red-500/10 rounded-lg">
                          <span className="text-red-400 font-mono">${dz.strike}</span>
                          <span className="text-xs text-gray-400 px-2 py-0.5 bg-gray-800 rounded">{dz.danger_type}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Pinning Status Card */}
                {gammaData.pinning_status?.is_pinning && (
                  <div className="bg-gray-800/50 border border-emerald-500/30 rounded-xl p-5">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="font-bold text-white flex items-center gap-2">
                        <Target className="w-5 h-5 text-emerald-400" />
                        Pinning Detected
                      </h3>
                      <span className="px-2 py-0.5 bg-emerald-500/20 text-emerald-400 text-xs rounded-full">
                        Stable Gamma
                      </span>
                    </div>
                    <div className="space-y-3">
                      <div className="p-3 bg-emerald-500/10 rounded-lg">
                        <p className="text-sm text-emerald-300">{gammaData.pinning_status.message}</p>
                      </div>
                      {gammaData.pinning_status.trade_idea && (
                        <div className="p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg">
                          <div className="flex items-center gap-2 mb-1">
                            <Info className="w-4 h-4 text-blue-400" />
                            <span className="text-xs font-medium text-blue-400">Trade Idea</span>
                          </div>
                          <p className="text-sm text-blue-300">{gammaData.pinning_status.trade_idea}</p>
                        </div>
                      )}
                      <div className="flex justify-between text-xs text-gray-400">
                        <span>Avg ROC: {gammaData.pinning_status.avg_roc?.toFixed(1)}%</span>
                        <span>Distance to Pin: {gammaData.pinning_status.distance_to_pin_pct?.toFixed(2)}%</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Expiration Info */}
                <div className="bg-gray-800/50 rounded-xl p-5">
                  <div className="flex items-center gap-2 mb-3">
                    <Calendar className="w-5 h-5 text-purple-400" />
                    <h3 className="font-bold text-white">Expiration</h3>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-white mb-1">
                      {selectedExpiration}
                    </div>
                    <div className="text-sm text-gray-400">
                      {expirations.find(e => e.date === selectedExpiration)?.dte || 0} days to expiry
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Enhanced Analysis Panel - NEW */}
            <div className="mt-6">
              <HyperionEnhancedPanel symbol={selectedSymbol} />
            </div>

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
          </>
        )}
      </main>
    </div>
  )
}
