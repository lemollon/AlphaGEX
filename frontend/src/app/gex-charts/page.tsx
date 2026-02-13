'use client'

/**
 * GEX Charts - Trading Volatility Style Analysis
 *
 * Replicates the Trading Volatility GEX page with:
 * - Header metrics (Price, GEX Flip, 30-Day Vol, Call Structure, Rating)
 * - Options Flow Diagnostics (6 cards)
 * - Skew Measures panel
 * - GEX by Strike charts
 * - Symbol-aware expiration selection (0DTE for SPY, weekly/OPEX for others)
 */

import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Minus,
  Info,
  Activity,
  BarChart3,
  Search,
  AlertCircle,
  ArrowUpRight,
  ArrowDownRight,
  Gauge,
  Target,
  Percent,
  DollarSign,
  Clock,
  Calendar,
  ChevronDown
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell, Legend,
  LineChart, Line, CartesianGrid, Area, ComposedChart
} from 'recharts'
import { apiClient } from '@/lib/api'

// Types
interface DiagnosticCard {
  id: string
  label: string
  metric_name: string
  metric_value: string
  description: string
  raw_value: number
}

interface SkewMeasures {
  skew_ratio: number
  skew_ratio_description: string
  call_skew: number
  call_skew_description: string
  atm_call_iv: number | null
  atm_put_iv: number | null
  avg_otm_call_iv: number | null
  avg_otm_put_iv: number | null
}

interface Rating {
  rating: string
  confidence: string
  bullish_score: number
  bearish_score: number
  net_score: number
}

interface CallStructure {
  structure: string
  description: string
  call_buying_pressure: number
  is_hedging: boolean
  is_overwrite: boolean
  is_speculation: boolean
}

interface StrikeGex {
  strike: number
  net_gamma: number
  call_gamma: number
  put_gamma: number
  call_volume: number
  put_volume: number
  total_volume: number
  call_iv: number | null
  put_iv: number | null
  call_oi: number
  put_oi: number
  is_magnet: boolean
  magnet_rank: number | null
  is_pin: boolean
  is_danger: boolean
  danger_type: string | null
}

interface CallStructureDetails {
  structure: string
  description: string
  call_buying_pressure: number
  is_hedging: boolean
  is_overwrite: boolean
  is_speculation: boolean
}

interface GexAnalysisData {
  symbol: string
  timestamp: string
  expiration: string
  header: {
    price: number
    gex_flip: number | null
    '30_day_vol': number | null
    call_structure: string
    gex_at_expiration: number
    net_gex: number
    rating: string
    gamma_form: string
    previous_regime: string | null
    regime_flipped: boolean
  }
  call_structure_details?: CallStructureDetails
  flow_diagnostics: {
    cards: DiagnosticCard[]
    note: string
  }
  skew_measures: SkewMeasures
  rating: Rating
  levels: {
    price: number
    upper_1sd: number | null
    lower_1sd: number | null
    gex_flip: number | null
    call_wall: number | null
    put_wall: number | null
    expected_move: number | null
  }
  gex_chart: {
    expiration: string
    strikes: StrikeGex[]
    total_net_gamma: number
    gamma_regime: string
  }
  summary: {
    total_call_volume: number
    total_put_volume: number
    total_volume: number
    total_call_oi: number
    total_put_oi: number
    put_call_ratio: number
    net_gex: number
  }
}

interface ExpirationInfo {
  date: string
  dte: number
  day: string
  category: string
  is_opex: boolean
  is_today: boolean
}

interface SymbolExpirations {
  symbol: string
  expiration_type: string
  nearest: ExpirationInfo | null
  next_opex: string | null
  weekly: string[]
  monthly_opex: string[]
  all_expirations: ExpirationInfo[]
  total_available: number
  pattern_detection?: {
    method: string
    description: string
  }
}

// Intraday tick data from watchtower_snapshots
interface IntradayTick {
  time: string
  spot_price: number | null
  net_gamma: number | null
  vix: number | null
  expected_move: number | null
  gamma_regime: string | null
  flip_point: number | null
  call_wall: number | null
  put_wall: number | null
  samples: number
}

// Common symbols for quick selection
const COMMON_SYMBOLS = ['SPY', 'QQQ', 'IWM', 'GLD', 'SLV', 'USO', 'TLT', 'DIA', 'AAPL', 'TSLA', 'NVDA', 'AMD']

// Check if US market is currently open (9:30 AM - 4:15 PM ET on weekdays)
// Uses 4:15 PM to cover the options settlement window after the 4 PM close
function isMarketOpen(): boolean {
  const now = new Date()
  const day = now.getDay()
  // Weekend check
  if (day === 0 || day === 6) return false
  // Convert to ET (UTC-5 or UTC-4 during DST)
  const utcHours = now.getUTCHours()
  const utcMinutes = now.getUTCMinutes()
  const totalUtcMinutes = utcHours * 60 + utcMinutes
  // Determine EST/EDT offset: EDT (UTC-4) from 2nd Sun March to 1st Sun Nov
  const month = now.getUTCMonth() // 0-indexed
  const isDST = month >= 2 && month <= 9 // Approximate: March-October
  const etOffset = isDST ? 4 : 5
  const totalEtMinutes = totalUtcMinutes - etOffset * 60
  // Market hours: 9:30 AM ET (570 min) to 4:15 PM ET (975 min)
  return totalEtMinutes >= 570 && totalEtMinutes < 975
}

export default function GexChartsPage() {
  const paddingClass = useSidebarPadding()
  const [symbol, setSymbol] = useState('SPY')
  const [searchInput, setSearchInput] = useState('')
  const [data, setData] = useState<GexAnalysisData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)

  // Chart view toggle: 'net' = single net gamma, 'split' = call vs put, 'intraday' = 5m price+gamma
  const [chartView, setChartView] = useState<'net' | 'split' | 'intraday'>('net')

  // Intraday tick data for stacked chart
  const [intradayTicks, setIntradayTicks] = useState<IntradayTick[]>([])
  const [intradayLoading, setIntradayLoading] = useState(false)

  // Expiration state
  const [expirations, setExpirations] = useState<SymbolExpirations | null>(null)
  const [selectedExpiration, setSelectedExpiration] = useState<string | null>(null)
  const [expirationMode, setExpirationMode] = useState<'nearest' | 'opex' | 'custom'>('nearest')
  const [showExpirationDropdown, setShowExpirationDropdown] = useState(false)

  // Fetch available expirations for symbol
  const fetchExpirations = useCallback(async (sym: string) => {
    try {
      const response = await apiClient.getWatchtowerSymbolExpirations(sym)
      if (response.data?.success && response.data?.data) {
        setExpirations(response.data.data)
        // Auto-select nearest expiration
        if (response.data.data.nearest) {
          setSelectedExpiration(response.data.data.nearest.date)
          setExpirationMode('nearest')
        }
      }
    } catch (err) {
      console.error('Error fetching expirations:', err)
    }
  }, [])

  // Fetch GEX data
  const fetchData = useCallback(async (sym: string, exp?: string | null) => {
    try {
      setLoading(true)
      setError(null)

      const response = await apiClient.getWatchtowerGexAnalysis(sym, exp || undefined)
      const result = response.data

      if (result?.success) {
        setData(result.data)
        setLastUpdated(new Date())
      } else if (result?.data_unavailable) {
        setError(result.message || 'Data unavailable - market may be closed')
      } else {
        setError(result?.message || 'Failed to fetch GEX data')
      }
    } catch (err: any) {
      console.error('Fetch error:', err)
      if (err.response?.data?.message) {
        setError(err.response.data.message)
      } else if (err.message) {
        setError(err.message)
      } else {
        setError('Failed to connect to API')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  // Fetch intraday ticks for the stacked chart
  const fetchIntradayTicks = useCallback(async (sym: string) => {
    try {
      setIntradayLoading(true)
      const response = await apiClient.getWatchtowerIntradayTicks(sym, 5)
      if (response.data?.success && response.data?.data?.ticks) {
        setIntradayTicks(response.data.data.ticks)
      }
    } catch (err) {
      console.error('Error fetching intraday ticks:', err)
    } finally {
      setIntradayLoading(false)
    }
  }, [])

  // Fetch expirations when symbol changes
  useEffect(() => {
    fetchExpirations(symbol)
  }, [symbol, fetchExpirations])

  // Fetch data when symbol or expiration changes
  useEffect(() => {
    if (selectedExpiration) {
      fetchData(symbol, selectedExpiration)
    } else {
      fetchData(symbol)
    }
  }, [symbol, selectedExpiration, fetchData])

  // Fetch intraday ticks when switching to intraday view or symbol changes
  useEffect(() => {
    if (chartView === 'intraday') {
      fetchIntradayTicks(symbol)
    }
  }, [chartView, symbol, fetchIntradayTicks])

  // Auto-refresh every 30 seconds during market hours only
  useEffect(() => {
    if (!autoRefresh) return

    const interval = setInterval(() => {
      // Only poll when market is open — no point refreshing stale after-hours data
      if (isMarketOpen()) {
        fetchData(symbol, selectedExpiration)
        if (chartView === 'intraday') {
          fetchIntradayTicks(symbol)
        }
      }
    }, 30000)

    return () => clearInterval(interval)
  }, [symbol, selectedExpiration, autoRefresh, fetchData, chartView, fetchIntradayTicks])

  const handleSymbolChange = (newSymbol: string) => {
    setSymbol(newSymbol)
    setSelectedExpiration(null)
    setExpirationMode('nearest')
  }

  const handleSymbolSearch = () => {
    const sym = searchInput.toUpperCase().trim()
    if (sym) {
      handleSymbolChange(sym)
      setSearchInput('')
    }
  }

  const handleExpirationSelect = (exp: string, mode: 'nearest' | 'opex' | 'custom') => {
    setSelectedExpiration(exp)
    setExpirationMode(mode)
    setShowExpirationDropdown(false)
  }

  const formatNumber = (num: number, decimals: number = 2) => {
    if (Math.abs(num) >= 1e9) return `${(num / 1e9).toFixed(decimals)}B`
    if (Math.abs(num) >= 1e6) return `${(num / 1e6).toFixed(decimals)}M`
    if (Math.abs(num) >= 1e3) return `${(num / 1e3).toFixed(decimals)}K`
    return num.toFixed(decimals)
  }

  const getRatingColor = (rating: string) => {
    switch (rating) {
      case 'BULLISH': return 'text-green-400'
      case 'BEARISH': return 'text-red-400'
      default: return 'text-gray-400'
    }
  }

  const getRatingBg = (rating: string) => {
    switch (rating) {
      case 'BULLISH': return 'bg-green-500/10 border-green-500/30'
      case 'BEARISH': return 'bg-red-500/10 border-red-500/30'
      default: return 'bg-gray-500/10 border-gray-500/30'
    }
  }

  const getCardColor = (card: DiagnosticCard) => {
    if (card.id === 'volume_pressure' && card.raw_value > 0.1) return 'border-cyan-500/50 bg-cyan-500/5'
    if (card.id === 'call_share' && card.raw_value > 55) return 'border-cyan-500/50 bg-cyan-500/5'
    if (card.id === 'short_dte_share' && card.raw_value > 50) return 'border-cyan-500/50 bg-cyan-500/5'
    if (card.id === 'volume_pressure' && card.raw_value < -0.1) return 'border-red-500/50 bg-red-500/5'
    if (card.id === 'lotto_turnover' && card.raw_value > 0.3) return 'border-yellow-500/50 bg-yellow-500/5'
    return 'border-gray-700 bg-gray-800/50'
  }

  const formatExpDate = (dateStr: string) => {
    const date = new Date(dateStr + 'T12:00:00')
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  // Distance from price to a level as percentage
  const distancePct = (level: number | null) => {
    if (!level || !data?.levels.price) return null
    return ((level - data.levels.price) / data.levels.price * 100)
  }

  const formatDistance = (level: number | null) => {
    const pct = distancePct(level)
    if (pct === null) return ''
    const sign = pct >= 0 ? '+' : ''
    return `(${sign}${pct.toFixed(1)}%)`
  }

  // Generate market interpretation from combined signals
  const getMarketInterpretation = useMemo(() => {
    if (!data) return null
    const { gamma_form, rating, gex_flip, price, net_gex } = data.header
    const { call_wall, put_wall } = data.levels
    const regime = gamma_form
    const priceAboveFlip = gex_flip ? price > gex_flip : null

    const lines: string[] = []

    // Regime interpretation
    if (regime === 'POSITIVE') {
      lines.push('Positive gamma regime — dealers are long gamma. Price tends to mean-revert toward the flip point. Favor selling premium (Iron Condors).')
    } else if (regime === 'NEGATIVE') {
      lines.push('Negative gamma regime — dealers are short gamma. Price moves tend to accelerate. Favor directional plays and expect wider ranges.')
    } else {
      lines.push('Neutral gamma regime — no strong dealer positioning. Market may lack a clear directional catalyst from gamma.')
    }

    // Price vs flip
    if (priceAboveFlip === true) {
      lines.push(`Price is above the GEX flip point ($${gex_flip?.toFixed(0)}) — in positive gamma territory, supporting upside stability.`)
    } else if (priceAboveFlip === false) {
      lines.push(`Price is below the GEX flip point ($${gex_flip?.toFixed(0)}) — in negative gamma territory, vulnerable to downside acceleration.`)
    }

    // Wall proximity warnings
    if (call_wall && price) {
      const callDist = ((call_wall - price) / price) * 100
      if (callDist < 0.5 && callDist > 0) {
        lines.push(`Call wall at $${call_wall.toFixed(0)} is only ${callDist.toFixed(1)}% away — strong resistance. Watch for rejection.`)
      }
    }
    if (put_wall && price) {
      const putDist = ((price - put_wall) / price) * 100
      if (putDist < 0.5 && putDist > 0) {
        lines.push(`Put wall at $${put_wall.toFixed(0)} is only ${putDist.toFixed(1)}% away — strong support. Watch for bounce.`)
      }
    }

    // Rating + regime agreement/divergence
    if (rating === 'BULLISH' && regime === 'NEGATIVE') {
      lines.push('Divergence: bullish flow in negative gamma — moves could be explosive if momentum continues.')
    } else if (rating === 'BEARISH' && regime === 'POSITIVE') {
      lines.push('Divergence: bearish flow in positive gamma — dealers may dampen the move. Watch for mean reversion.')
    }

    return lines
  }, [data])

  // Custom tooltip for the GEX chart
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload || !payload.length) return null
    const strike = payload[0]?.payload
    if (!strike) return null

    return (
      <div className="bg-gray-900 border border-gray-600 rounded-lg p-3 shadow-xl text-xs min-w-[200px]">
        <div className="font-bold text-white text-sm mb-2 flex items-center gap-2">
          Strike: ${label}
          {strike.is_magnet && (
            <span className="bg-yellow-500/20 text-yellow-400 px-1.5 py-0.5 rounded text-[10px]">
              MAGNET{strike.magnet_rank ? ` #${strike.magnet_rank}` : ''}
            </span>
          )}
          {strike.is_pin && (
            <span className="bg-purple-500/20 text-purple-400 px-1.5 py-0.5 rounded text-[10px]">PIN</span>
          )}
          {strike.is_danger && (
            <span className="bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded text-[10px]">{strike.danger_type}</span>
          )}
        </div>
        <div className="space-y-1.5">
          <div className="flex justify-between gap-4">
            <span className="text-gray-400">Net Gamma:</span>
            <span className={`font-mono font-bold ${strike.net_gamma >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {formatNumber(strike.net_gamma, 4)}
            </span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-gray-400">Call Gamma:</span>
            <span className="font-mono text-green-400">{strike.call_gamma?.toFixed(6)}</span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-gray-400">Put Gamma:</span>
            <span className="font-mono text-red-400">{strike.put_gamma?.toFixed(6)}</span>
          </div>
          <div className="border-t border-gray-700 pt-1.5 mt-1.5">
            <div className="flex justify-between gap-4">
              <span className="text-gray-400">Call Vol / Put Vol:</span>
              <span className="font-mono text-white">
                {(strike.call_volume || 0).toLocaleString()} / {(strike.put_volume || 0).toLocaleString()}
              </span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-gray-400">Call OI / Put OI:</span>
              <span className="font-mono text-white">
                {(strike.call_oi || 0).toLocaleString()} / {(strike.put_oi || 0).toLocaleString()}
              </span>
            </div>
          </div>
          {(strike.call_iv || strike.put_iv) && (
            <div className="border-t border-gray-700 pt-1.5 mt-1.5">
              <div className="flex justify-between gap-4">
                <span className="text-gray-400">Call IV / Put IV:</span>
                <span className="font-mono text-white">
                  {strike.call_iv ? `${strike.call_iv}%` : 'N/A'} / {strike.put_iv ? `${strike.put_iv}%` : 'N/A'}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className={`min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 ${paddingClass}`}>
      <Navigation />

      <main className="max-w-[1800px] mx-auto px-4 py-6">
        {/* Page Title */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <BarChart3 className="w-7 h-7 text-cyan-400" />
            GEX Charts
            <span className="text-sm font-normal text-gray-400">Trading Volatility Style</span>
          </h1>
          <p className="text-gray-500 text-sm mt-1">
            Options flow diagnostics, skew measures, and gamma exposure by strike
          </p>
        </div>

        {/* Controls Bar */}
        <div className="bg-gray-800/50 backdrop-blur rounded-xl border border-gray-700 p-4 mb-6 relative z-50">
          <div className="flex flex-wrap items-center gap-4">
            {/* Symbol Search */}
            <div className="flex items-center gap-2 bg-gray-900 rounded-lg px-3 py-2 border border-gray-700">
              <Search className="w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value.toUpperCase())}
                onKeyDown={(e) => e.key === 'Enter' && handleSymbolSearch()}
                placeholder="Enter symbol..."
                className="bg-transparent text-white text-sm w-28 outline-none placeholder-gray-500"
              />
              <button
                onClick={handleSymbolSearch}
                className="text-cyan-400 hover:text-cyan-300"
              >
                <ArrowUpRight className="w-4 h-4" />
              </button>
            </div>

            {/* Current Symbol */}
            <div className="flex items-center gap-2">
              <span className="text-2xl font-bold text-white">{symbol}</span>
              <a
                href={`https://tradingview.com/symbols/${symbol}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-gray-400 hover:text-cyan-400"
              >
                <ArrowUpRight className="w-4 h-4" />
              </a>
            </div>

            {/* Quick Symbol Buttons */}
            <div className="flex flex-wrap gap-1.5">
              {COMMON_SYMBOLS.map(sym => (
                <button
                  key={sym}
                  onClick={() => handleSymbolChange(sym)}
                  className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                    symbol === sym
                      ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                      : 'bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700 border border-transparent'
                  }`}
                >
                  {sym}
                </button>
              ))}
            </div>

            {/* Spacer */}
            <div className="flex-1" />

            {/* Expiration Selector */}
            <div className="relative">
              <button
                onClick={() => setShowExpirationDropdown(!showExpirationDropdown)}
                className="flex items-center gap-2 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm hover:border-cyan-500/50 transition-colors"
              >
                <Calendar className="w-4 h-4 text-cyan-400" />
                <span className="text-white">
                  {selectedExpiration ? (
                    <>
                      {formatExpDate(selectedExpiration)}
                      {expirations?.nearest?.date === selectedExpiration && (
                        <span className="ml-1 text-xs text-cyan-400">(Nearest)</span>
                      )}
                      {expirations?.next_opex === selectedExpiration && (
                        <span className="ml-1 text-xs text-yellow-400">(OPEX)</span>
                      )}
                    </>
                  ) : 'Select Expiration'}
                </span>
                <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${showExpirationDropdown ? 'rotate-180' : ''}`} />
              </button>

              {/* Expiration Dropdown */}
              {showExpirationDropdown && expirations && (
                <div className="absolute top-full left-0 mt-1 w-64 bg-gray-900 border border-gray-700 rounded-lg shadow-xl z-50 overflow-hidden">
                  {/* Nearest Expiration */}
                  {expirations.nearest && (
                    <div className="p-2 border-b border-gray-700">
                      <div className="text-xs text-gray-500 uppercase mb-1 px-2">Nearest</div>
                      <button
                        onClick={() => handleExpirationSelect(expirations.nearest!.date, 'nearest')}
                        className={`w-full text-left px-3 py-2 rounded text-sm flex items-center justify-between hover:bg-gray-800 ${
                          selectedExpiration === expirations.nearest.date ? 'bg-cyan-500/10 text-cyan-400' : 'text-white'
                        }`}
                      >
                        <span>{formatExpDate(expirations.nearest.date)} ({expirations.nearest.day})</span>
                        <span className="text-xs text-gray-500">{expirations.nearest.dte}DTE</span>
                      </button>
                    </div>
                  )}

                  {/* OPEX */}
                  {expirations.next_opex && (
                    <div className="p-2 border-b border-gray-700">
                      <div className="text-xs text-gray-500 uppercase mb-1 px-2">Monthly OPEX</div>
                      <button
                        onClick={() => handleExpirationSelect(expirations.next_opex!, 'opex')}
                        className={`w-full text-left px-3 py-2 rounded text-sm flex items-center justify-between hover:bg-gray-800 ${
                          selectedExpiration === expirations.next_opex ? 'bg-yellow-500/10 text-yellow-400' : 'text-white'
                        }`}
                      >
                        <span>{formatExpDate(expirations.next_opex)} (3rd Fri)</span>
                        <span className="text-xs text-yellow-400">OPEX</span>
                      </button>
                    </div>
                  )}

                  {/* Weekly Expirations */}
                  {expirations.weekly.length > 0 && (
                    <div className="p-2 max-h-48 overflow-y-auto">
                      <div className="text-xs text-gray-500 uppercase mb-1 px-2">
                        {expirations.expiration_type === 'daily' ? 'Daily (0DTE)' :
                         expirations.expiration_type === 'triple_weekly' ? 'Weekly (Mon/Wed/Fri)' : 'Weekly'}
                      </div>
                      {expirations.weekly.slice(0, 8).map(exp => {
                        const expInfo = expirations.all_expirations.find(e => e.date === exp)
                        return (
                          <button
                            key={exp}
                            onClick={() => handleExpirationSelect(exp, 'custom')}
                            className={`w-full text-left px-3 py-1.5 rounded text-sm flex items-center justify-between hover:bg-gray-800 ${
                              selectedExpiration === exp ? 'bg-cyan-500/10 text-cyan-400' : 'text-gray-300'
                            }`}
                          >
                            <span>{formatExpDate(exp)} ({expInfo?.day || ''})</span>
                            <span className="text-xs text-gray-500">{expInfo?.dte || 0}DTE</span>
                          </button>
                        )
                      })}
                    </div>
                  )}

                  {/* Symbol Type Info - Dynamically detected */}
                  <div className="p-2 bg-gray-800/50 border-t border-gray-700">
                    <div className="text-xs text-gray-500">
                      📅 {expirations.pattern_detection?.description || (
                        expirations.expiration_type === 'daily' ? 'Expirations on all/most weekdays (0DTE)' :
                        expirations.expiration_type === 'triple_weekly' ? 'Mon/Wed/Fri expirations' :
                        expirations.expiration_type === 'weekly' ? 'Friday expirations' :
                        'Monthly OPEX only'
                      )}
                      <span className="ml-1 text-gray-600">(auto-detected)</span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Auto Refresh Toggle */}
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`flex items-center gap-2 px-3 py-2 rounded text-sm ${
                autoRefresh
                  ? (isMarketOpen()
                    ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                    : 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30')
                  : 'bg-gray-800 text-gray-400 border border-gray-700'
              }`}
            >
              <Clock className="w-4 h-4" />
              {autoRefresh
                ? (isMarketOpen() ? 'Auto 30s' : 'Market Closed')
                : 'Manual'}
            </button>

            {/* Refresh Button */}
            <button
              onClick={() => fetchData(symbol, selectedExpiration)}
              disabled={loading}
              className="flex items-center gap-2 px-3 py-2 rounded bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 transition-colors border border-cyan-500/30"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>

          {/* Last Updated & Expiration Info */}
          {lastUpdated && (
            <div className="flex items-center gap-4 mt-3 text-xs text-gray-500">
              <span>Last updated: {lastUpdated.toLocaleTimeString()}</span>
              {!isMarketOpen() && (
                <span className="text-yellow-400">Data as of last market close</span>
              )}
              {data?.expiration && (
                <span className="text-cyan-400">Viewing: {data.expiration}</span>
              )}
              {expirations && (
                <span>({expirations.total_available} expirations available)</span>
              )}
            </div>
          )}
        </div>

        {/* Error State */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-6 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-400" />
            <span className="text-red-400">{error}</span>
          </div>
        )}

        {/* Loading State */}
        {loading && !data && (
          <div className="flex items-center justify-center h-64">
            <RefreshCw className="w-8 h-8 text-cyan-400 animate-spin" />
          </div>
        )}

        {/* Main Content */}
        {data && (
          <>
            {/* Header Metrics Bar */}
            <div className="bg-gray-800/50 backdrop-blur rounded-xl border border-gray-700 p-4 mb-6">
              <div className="flex flex-wrap items-center justify-between gap-4">
                {/* Left metrics */}
                <div className="flex flex-wrap items-center gap-6">
                  <div>
                    <div className="text-xs text-gray-500 uppercase">Price</div>
                    <div className="text-2xl font-bold text-white">{data.header.price.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 uppercase">GEX Flip</div>
                    <div className="text-2xl font-bold text-cyan-400">{data.header.gex_flip?.toFixed(2) || 'N/A'}</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 uppercase">30-Day Vol</div>
                    <div className="text-2xl font-bold text-white">{data.header['30_day_vol']?.toFixed(1) || 'N/A'}</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 uppercase">Call Structure</div>
                    <div className="text-lg font-semibold text-yellow-400">{data.header.call_structure}</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 uppercase">GEX @ {data.expiration?.slice(5) || 'Exp'}</div>
                    <div className="text-lg font-bold text-white">{formatNumber(data.header.gex_at_expiration * 1e6, 0)}</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 uppercase">Net GEX</div>
                    <div className="text-lg font-bold text-white">{formatNumber(data.header.net_gex * 1e6, 0)}</div>
                  </div>
                </div>

                {/* Right - Rating */}
                <div className="text-right">
                  <div className="text-xs text-gray-500 uppercase">Rating</div>
                  <div className={`text-2xl font-bold ${getRatingColor(data.header.rating)}`}>
                    {data.header.rating}
                  </div>
                  <div className="text-xs text-gray-500">
                    Gamma Form: {data.header.gamma_form}
                  </div>
                </div>
              </div>
            </div>

            {/* Regime Change Banner (ENH 9) */}
            {data.header.regime_flipped && data.header.previous_regime && (
              <div className="bg-orange-500/10 border border-orange-500/30 rounded-lg px-4 py-3 mb-6 flex items-center gap-3">
                <AlertCircle className="w-5 h-5 text-orange-400 flex-shrink-0" />
                <span className="text-orange-400 text-sm font-medium">
                  Gamma regime flipped: {data.header.previous_regime} → {data.header.gamma_form}
                </span>
                <span className="text-orange-400/60 text-xs">
                  {data.header.gamma_form === 'NEGATIVE'
                    ? 'Dealers now short gamma — expect accelerating moves and wider ranges.'
                    : data.header.gamma_form === 'POSITIVE'
                    ? 'Dealers now long gamma — expect mean-reverting, range-bound price action.'
                    : 'Gamma is near-zero — no strong directional dealer pressure.'}
                </span>
              </div>
            )}

            {/* Market Interpretation Panel (ENH 6) */}
            {getMarketInterpretation && getMarketInterpretation.length > 0 && (
              <div className="bg-gray-800/50 backdrop-blur rounded-xl border border-gray-700 p-4 mb-6">
                <h3 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
                  <Info className="w-4 h-4 text-cyan-400" />
                  WHAT IT MEANS
                </h3>
                <div className="space-y-2">
                  {getMarketInterpretation.map((line, i) => (
                    <p key={i} className="text-sm text-gray-300 leading-relaxed">{line}</p>
                  ))}
                </div>
              </div>
            )}

            {/* Main Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Left Column - Options Flow Diagnostics */}
              <div className="lg:col-span-2">
                {/* Flow Diagnostics Title */}
                <div className="mb-4">
                  <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                    <Activity className="w-5 h-5 text-cyan-400" />
                    OPTIONS FLOW DIAGNOSTICS
                  </h2>
                  <p className="text-xs text-gray-500 mt-1">
                    NOTE: {data.flow_diagnostics.note}
                  </p>
                </div>

                {/* Diagnostic Cards Grid (2x3) */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                  {data.flow_diagnostics.cards.map((card) => (
                    <div
                      key={card.id}
                      className={`rounded-lg border p-4 ${getCardColor(card)}`}
                    >
                      <div className="text-sm font-semibold text-white mb-1">{card.label}</div>
                      <div className="text-xs text-gray-400 uppercase mb-2">{card.metric_name}</div>
                      <div className="text-xl font-bold text-cyan-400 mb-2">{card.metric_value}</div>
                      <div className="text-xs text-gray-400">{card.description}</div>
                    </div>
                  ))}
                </div>

                {/* GEX Charts Section */}
                <div className="bg-gray-800/50 backdrop-blur rounded-xl border border-gray-700 p-4">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                      <BarChart3 className="w-4 h-4 text-cyan-400" />
                      {chartView === 'intraday'
                        ? `${symbol} Intraday 5m — Price + Net Gamma`
                        : `${symbol} ${chartView === 'net' ? 'Net' : 'Call vs Put'} GEX for ${data.expiration} Expiration, by Strike`
                      }
                    </h3>
                    {/* Chart View Toggle (ENH 7) */}
                    <div className="flex items-center gap-1 bg-gray-900 rounded-lg p-0.5 border border-gray-700">
                      <button
                        onClick={() => setChartView('net')}
                        className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                          chartView === 'net'
                            ? 'bg-cyan-500/20 text-cyan-400'
                            : 'text-gray-400 hover:text-white'
                        }`}
                      >
                        Net GEX
                      </button>
                      <button
                        onClick={() => setChartView('split')}
                        className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                          chartView === 'split'
                            ? 'bg-cyan-500/20 text-cyan-400'
                            : 'text-gray-400 hover:text-white'
                        }`}
                      >
                        Call vs Put
                      </button>
                      <button
                        onClick={() => setChartView('intraday')}
                        className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                          chartView === 'intraday'
                            ? 'bg-cyan-500/20 text-cyan-400'
                            : 'text-gray-400 hover:text-white'
                        }`}
                      >
                        Intraday 5m
                      </button>
                    </div>
                  </div>

                  {/* Intraday 5m Stacked Chart */}
                  {chartView === 'intraday' ? (
                    intradayTicks.length === 0 ? (
                      <div className="text-center py-8 text-yellow-400">
                        <AlertCircle className="w-8 h-8 mx-auto mb-2" />
                        {intradayLoading
                          ? 'Loading intraday ticks...'
                          : 'No intraday data yet — ticks accumulate during market hours as GEX Charts is viewed.'
                        }
                      </div>
                    ) : (
                      <>
                        <div className="h-[500px]">
                          {(() => {
                            // Format tick data for the chart
                            const chartData = intradayTicks
                              .filter(t => t.spot_price !== null)
                              .map(t => ({
                                ...t,
                                label: t.time ? new Date(t.time).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true }) : '',
                                net_gamma_display: t.net_gamma ?? 0,
                              }))

                            // Compute price range for right Y-axis
                            const prices = chartData.map(t => t.spot_price!).filter(Boolean)
                            const priceMin = Math.min(...prices)
                            const priceMax = Math.max(...prices)
                            const pricePad = (priceMax - priceMin) * 0.15 || 1

                            return (
                              <ResponsiveContainer width="100%" height="100%">
                                <ComposedChart
                                  data={chartData}
                                  margin={{ top: 10, right: 60, left: 10, bottom: 5 }}
                                >
                                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                  <XAxis
                                    dataKey="label"
                                    tick={{ fill: '#9ca3af', fontSize: 10 }}
                                    interval="preserveStartEnd"
                                  />
                                  {/* Left Y-axis: Net Gamma */}
                                  <YAxis
                                    yAxisId="gamma"
                                    orientation="left"
                                    tick={{ fill: '#9ca3af', fontSize: 10 }}
                                    tickFormatter={(v) => formatNumber(v, 1)}
                                    label={{ value: 'Net Gamma', angle: -90, position: 'insideLeft', fill: '#6b7280', fontSize: 10 }}
                                  />
                                  {/* Right Y-axis: Spot Price */}
                                  <YAxis
                                    yAxisId="price"
                                    orientation="right"
                                    domain={[priceMin - pricePad, priceMax + pricePad]}
                                    tick={{ fill: '#3b82f6', fontSize: 10 }}
                                    tickFormatter={(v) => `$${v.toFixed(0)}`}
                                    label={{ value: 'Price', angle: 90, position: 'insideRight', fill: '#3b82f6', fontSize: 10 }}
                                  />
                                  <Tooltip
                                    content={({ active, payload, label: tipLabel }) => {
                                      if (!active || !payload || !payload.length) return null
                                      const tick = payload[0]?.payload
                                      if (!tick) return null
                                      return (
                                        <div className="bg-gray-900 border border-gray-600 rounded-lg p-3 shadow-xl text-xs min-w-[200px]">
                                          <div className="font-bold text-white text-sm mb-2">{tipLabel}</div>
                                          <div className="space-y-1">
                                            <div className="flex justify-between gap-4">
                                              <span className="text-gray-400">Price:</span>
                                              <span className="text-blue-400 font-mono font-bold">${tick.spot_price?.toFixed(2)}</span>
                                            </div>
                                            <div className="flex justify-between gap-4">
                                              <span className="text-gray-400">Net Gamma:</span>
                                              <span className={`font-mono font-bold ${(tick.net_gamma ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                {formatNumber(tick.net_gamma ?? 0, 2)}
                                              </span>
                                            </div>
                                            <div className="flex justify-between gap-4">
                                              <span className="text-gray-400">Regime:</span>
                                              <span className={`font-mono ${
                                                tick.gamma_regime === 'POSITIVE' ? 'text-green-400' :
                                                tick.gamma_regime === 'NEGATIVE' ? 'text-red-400' : 'text-gray-400'
                                              }`}>{tick.gamma_regime || 'N/A'}</span>
                                            </div>
                                            {tick.flip_point && (
                                              <div className="flex justify-between gap-4">
                                                <span className="text-gray-400">Flip Point:</span>
                                                <span className="text-yellow-400 font-mono">${tick.flip_point?.toFixed(2)}</span>
                                              </div>
                                            )}
                                            {tick.vix && (
                                              <div className="flex justify-between gap-4">
                                                <span className="text-gray-400">VIX:</span>
                                                <span className="text-white font-mono">{tick.vix?.toFixed(2)}</span>
                                              </div>
                                            )}
                                            {(tick.call_wall || tick.put_wall) && (
                                              <div className="border-t border-gray-700 pt-1 mt-1">
                                                {tick.call_wall && (
                                                  <div className="flex justify-between gap-4">
                                                    <span className="text-gray-400">Call Wall:</span>
                                                    <span className="text-cyan-400 font-mono">${tick.call_wall?.toFixed(2)}</span>
                                                  </div>
                                                )}
                                                {tick.put_wall && (
                                                  <div className="flex justify-between gap-4">
                                                    <span className="text-gray-400">Put Wall:</span>
                                                    <span className="text-purple-400 font-mono">${tick.put_wall?.toFixed(2)}</span>
                                                  </div>
                                                )}
                                              </div>
                                            )}
                                          </div>
                                        </div>
                                      )
                                    }}
                                  />

                                  {/* Net gamma bars — color coded green/red */}
                                  <Bar yAxisId="gamma" dataKey="net_gamma_display" name="Net Gamma" barSize={12}>
                                    {chartData.map((entry, index) => (
                                      <Cell
                                        key={`intra-${index}`}
                                        fill={entry.net_gamma_display >= 0 ? '#22c55e' : '#ef4444'}
                                        fillOpacity={0.7}
                                      />
                                    ))}
                                  </Bar>

                                  {/* Price line on right axis */}
                                  <Line
                                    yAxisId="price"
                                    type="monotone"
                                    dataKey="spot_price"
                                    stroke="#3b82f6"
                                    strokeWidth={2}
                                    dot={false}
                                    name="Price"
                                  />

                                  {/* Flip point line on right axis */}
                                  <Line
                                    yAxisId="price"
                                    type="stepAfter"
                                    dataKey="flip_point"
                                    stroke="#eab308"
                                    strokeWidth={1}
                                    strokeDasharray="5 3"
                                    dot={false}
                                    name="Flip Point"
                                  />

                                  {/* Call wall reference */}
                                  <Line
                                    yAxisId="price"
                                    type="stepAfter"
                                    dataKey="call_wall"
                                    stroke="#06b6d4"
                                    strokeWidth={1}
                                    strokeDasharray="3 3"
                                    dot={false}
                                    name="Call Wall"
                                  />

                                  {/* Put wall reference */}
                                  <Line
                                    yAxisId="price"
                                    type="stepAfter"
                                    dataKey="put_wall"
                                    stroke="#a855f7"
                                    strokeWidth={1}
                                    strokeDasharray="3 3"
                                    dot={false}
                                    name="Put Wall"
                                  />
                                </ComposedChart>
                              </ResponsiveContainer>
                            )
                          })()}
                        </div>

                        {/* Intraday Legend */}
                        <div className="flex flex-wrap gap-4 mt-4 text-xs">
                          <div className="flex items-center gap-2">
                            <div className="w-3 h-3 bg-green-500 rounded-sm"></div>
                            <span className="text-gray-400">Positive Gamma</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="w-3 h-3 bg-red-500 rounded-sm"></div>
                            <span className="text-gray-400">Negative Gamma</span>
                          </div>
                          <span className="text-gray-600">|</span>
                          <div className="flex items-center gap-2">
                            <div className="w-6 h-0.5 bg-blue-500"></div>
                            <span className="text-gray-400">Price</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="w-6 h-0.5 bg-yellow-400" style={{ borderTop: '1px dashed #eab308' }}></div>
                            <span className="text-gray-400">Flip Point</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="w-6 h-0.5 bg-cyan-400" style={{ borderTop: '1px dashed #06b6d4' }}></div>
                            <span className="text-gray-400">Call Wall</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="w-6 h-0.5 bg-purple-400" style={{ borderTop: '1px dashed #a855f7' }}></div>
                            <span className="text-gray-400">Put Wall</span>
                          </div>
                          <span className="text-gray-600">|</span>
                          <span className="text-gray-500">{intradayTicks.length} ticks today</span>
                        </div>
                      </>
                    )
                  ) : data.gex_chart.strikes.length === 0 ? (
                    <div className="text-center py-8 text-yellow-400">
                      <AlertCircle className="w-8 h-8 mx-auto mb-2" />
                      Real-time data not available outside of market hours (8:30am to 4:15pm ET)
                    </div>
                  ) : (
                    <>
                      {/* Horizontal Bar Chart */}
                      <div className="h-[500px]">
                        {(() => {
                          const sortedStrikes = [...data.gex_chart.strikes]
                            .filter(s => Math.abs(s.net_gamma) > 0.00001 || Math.abs(s.call_gamma) > 0.000001)
                            .slice(0, 40)
                            .sort((a, b) => b.strike - a.strike)
                            .map(s => ({
                              ...s,
                              // For split view: negate put_gamma so it shows as negative bars
                              put_gamma_display: -(s.put_gamma || 0),
                            }))
                          return (
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart
                            data={sortedStrikes}
                            layout="vertical"
                            margin={{ top: 5, right: 30, left: 60, bottom: 5 }}
                          >
                            <XAxis
                              type="number"
                              tick={{ fill: '#9ca3af', fontSize: 10 }}
                              tickFormatter={(v) => formatNumber(v, 1)}
                            />
                            <YAxis
                              type="category"
                              dataKey="strike"
                              tick={{ fill: '#9ca3af', fontSize: 10 }}
                              width={50}
                            />
                            <Tooltip content={<CustomTooltip />} />

                            {/* Reference Lines (ENH 2) */}
                            {data.levels.gex_flip && (
                              <ReferenceLine
                                y={data.levels.gex_flip}
                                stroke="#eab308"
                                strokeDasharray="5 3"
                                label={{ value: `Flip ${data.levels.gex_flip}`, fill: '#eab308', fontSize: 9, position: 'right' }}
                              />
                            )}
                            <ReferenceLine
                              y={data.levels.price}
                              stroke="#3b82f6"
                              strokeWidth={2}
                              label={{ value: `Price ${data.levels.price}`, fill: '#3b82f6', fontSize: 9, position: 'right' }}
                            />
                            {data.levels.call_wall && (
                              <ReferenceLine
                                y={data.levels.call_wall}
                                stroke="#06b6d4"
                                strokeDasharray="3 3"
                                label={{ value: `Call Wall ${data.levels.call_wall}`, fill: '#06b6d4', fontSize: 9, position: 'right' }}
                              />
                            )}
                            {data.levels.put_wall && (
                              <ReferenceLine
                                y={data.levels.put_wall}
                                stroke="#a855f7"
                                strokeDasharray="3 3"
                                label={{ value: `Put Wall ${data.levels.put_wall}`, fill: '#a855f7', fontSize: 9, position: 'right' }}
                              />
                            )}
                            {data.levels.upper_1sd && (
                              <ReferenceLine
                                y={data.levels.upper_1sd}
                                stroke="#22c55e"
                                strokeDasharray="2 4"
                                label={{ value: `+1σ`, fill: '#22c55e', fontSize: 9, position: 'left' }}
                              />
                            )}
                            {data.levels.lower_1sd && (
                              <ReferenceLine
                                y={data.levels.lower_1sd}
                                stroke="#ef4444"
                                strokeDasharray="2 4"
                                label={{ value: `-1σ`, fill: '#ef4444', fontSize: 9, position: 'left' }}
                              />
                            )}

                            {/* Net GEX view (ENH 1: color-coded) */}
                            {chartView === 'net' && (
                              <Bar dataKey="net_gamma" name="Net Gamma">
                                {sortedStrikes.map((entry, index) => (
                                  <Cell
                                    key={`cell-${index}`}
                                    fill={entry.net_gamma >= 0 ? '#22c55e' : '#ef4444'}
                                    fillOpacity={entry.is_magnet ? 1 : entry.is_danger ? 0.9 : 0.75}
                                    stroke={entry.is_magnet ? '#eab308' : entry.is_pin ? '#a855f7' : entry.is_danger ? '#ef4444' : 'none'}
                                    strokeWidth={entry.is_magnet || entry.is_pin || entry.is_danger ? 2 : 0}
                                  />
                                ))}
                              </Bar>
                            )}

                            {/* Split Call vs Put view (ENH 7) */}
                            {chartView === 'split' && (
                              <>
                                <Bar dataKey="call_gamma" name="Call Gamma" fill="#22c55e" fillOpacity={0.75} />
                                <Bar dataKey="put_gamma_display" name="Put Gamma" fill="#ef4444" fillOpacity={0.75} />
                              </>
                            )}
                          </BarChart>
                        </ResponsiveContainer>
                          )
                        })()}
                      </div>

                      {/* Enhanced Legend */}
                      <div className="flex flex-wrap gap-4 mt-4 text-xs">
                        {chartView === 'net' ? (
                          <>
                            <div className="flex items-center gap-2">
                              <div className="w-3 h-3 bg-green-500 rounded-sm"></div>
                              <span className="text-gray-400">Positive Gamma (support)</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <div className="w-3 h-3 bg-red-500 rounded-sm"></div>
                              <span className="text-gray-400">Negative Gamma (momentum)</span>
                            </div>
                          </>
                        ) : (
                          <>
                            <div className="flex items-center gap-2">
                              <div className="w-3 h-3 bg-green-500 rounded-sm"></div>
                              <span className="text-gray-400">Call Gamma</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <div className="w-3 h-3 bg-red-500 rounded-sm"></div>
                              <span className="text-gray-400">Put Gamma</span>
                            </div>
                          </>
                        )}
                        <span className="text-gray-600">|</span>
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 rounded-sm border-2 border-yellow-400 bg-transparent"></div>
                          <span className="text-gray-400">Magnet</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 rounded-sm border-2 border-purple-400 bg-transparent"></div>
                          <span className="text-gray-400">Pin Zone</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 rounded-sm border-2 border-red-400 bg-transparent"></div>
                          <span className="text-gray-400">Danger</span>
                        </div>
                        <span className="text-gray-600">|</span>
                        <div className="flex items-center gap-2">
                          <div className="w-6 h-0.5 bg-blue-400"></div>
                          <span className="text-gray-400">Price</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="w-6 h-0.5 bg-yellow-400" style={{ borderTop: '2px dashed #eab308' }}></div>
                          <span className="text-gray-400">GEX Flip</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="w-6 h-0.5 bg-cyan-400"></div>
                          <span className="text-gray-400">Call Wall</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="w-6 h-0.5 bg-purple-400"></div>
                          <span className="text-gray-400">Put Wall</span>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>

              {/* Right Column - Skew Measures & Summary */}
              <div className="space-y-6">
                {/* Skew Measures Panel */}
                <div className="bg-gray-800/50 backdrop-blur rounded-xl border border-gray-700 p-4">
                  <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                    <Gauge className="w-4 h-4 text-cyan-400" />
                    SKEW MEASURES
                  </h3>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 uppercase">Skew Ratio</div>
                      <div className="text-2xl font-bold text-white">{data.skew_measures.skew_ratio.toFixed(3)}</div>
                      <div className="text-xs text-gray-400 mt-1">
                        {data.skew_measures.skew_ratio > 1
                          ? '25-delta risk reversal. Values >1 = downside hedging demand.'
                          : 'Values <1 = call-side skew (bullish).'}
                      </div>
                    </div>

                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 uppercase">Call Skew</div>
                      <div className="text-2xl font-bold text-white">{data.skew_measures.call_skew.toFixed(2)}</div>
                      <div className="text-xs text-gray-400 mt-1">
                        OTM call/put delta diff at ±1STD. Positive = call demand.
                      </div>
                    </div>
                  </div>

                  {/* IV Details */}
                  <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
                    <div className="flex justify-between">
                      <span className="text-gray-500">ATM Call IV:</span>
                      <span className="text-white">{data.skew_measures.atm_call_iv?.toFixed(1) || 'N/A'}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">ATM Put IV:</span>
                      <span className="text-white">{data.skew_measures.atm_put_iv?.toFixed(1) || 'N/A'}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">OTM Call IV:</span>
                      <span className="text-white">{data.skew_measures.avg_otm_call_iv?.toFixed(1) || 'N/A'}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">OTM Put IV:</span>
                      <span className="text-white">{data.skew_measures.avg_otm_put_iv?.toFixed(1) || 'N/A'}%</span>
                    </div>
                  </div>
                </div>

                {/* Overall Rating */}
                <div className={`rounded-xl border p-4 ${getRatingBg(data.rating.rating)}`}>
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-white">OVERALL RATING</h3>
                    <span className={`text-2xl font-bold ${getRatingColor(data.rating.rating)}`}>
                      {data.rating.rating}
                    </span>
                  </div>

                  <div className="flex items-center gap-4 text-sm">
                    <div className="flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-green-400" />
                      <span className="text-gray-400">Bullish: {data.rating.bullish_score}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <TrendingDown className="w-4 h-4 text-red-400" />
                      <span className="text-gray-400">Bearish: {data.rating.bearish_score}</span>
                    </div>
                  </div>

                  <div className="mt-2 text-xs text-gray-500">
                    Confidence: {data.rating.confidence} | Net Score: {data.rating.net_score}
                  </div>
                </div>

                {/* Call Structure with Detail Flags (ENH 4) */}
                <div className="bg-gray-800/50 backdrop-blur rounded-xl border border-gray-700 p-4">
                  <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                    <Target className="w-4 h-4 text-cyan-400" />
                    CALL STRUCTURE
                  </h3>

                  <div className="text-lg font-bold text-yellow-400 mb-2">
                    {data.header.call_structure}
                  </div>

                  {data.call_structure_details ? (
                    <>
                      <div className="text-xs text-gray-400 mb-3">
                        {data.call_structure_details.description}
                      </div>

                      {/* Classification flags */}
                      <div className="flex flex-wrap gap-2 mb-3">
                        {data.call_structure_details.is_hedging && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-red-500/15 text-red-400 border border-red-500/30">
                            HEDGING
                          </span>
                        )}
                        {data.call_structure_details.is_overwrite && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-yellow-500/15 text-yellow-400 border border-yellow-500/30">
                            OVERWRITE
                          </span>
                        )}
                        {data.call_structure_details.is_speculation && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-green-500/15 text-green-400 border border-green-500/30">
                            SPECULATION
                          </span>
                        )}
                        {!data.call_structure_details.is_hedging && !data.call_structure_details.is_overwrite && !data.call_structure_details.is_speculation && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-gray-500/15 text-gray-400 border border-gray-500/30">
                            MIXED
                          </span>
                        )}
                      </div>

                      {/* Buying pressure bar */}
                      <div className="mt-2">
                        <div className="flex justify-between text-[10px] text-gray-500 mb-1">
                          <span>Selling</span>
                          <span>Buying Pressure: {(data.call_structure_details.call_buying_pressure * 100).toFixed(0)}%</span>
                          <span>Buying</span>
                        </div>
                        <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden relative">
                          <div className="absolute inset-0 flex">
                            <div className="w-1/2 h-full bg-red-500/20"></div>
                            <div className="w-1/2 h-full bg-green-500/20"></div>
                          </div>
                          <div
                            className="absolute top-0 h-full w-1 bg-white rounded"
                            style={{ left: `${50 + data.call_structure_details.call_buying_pressure * 50}%` }}
                          ></div>
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="text-xs text-gray-400">
                      {data.summary.total_call_volume > data.summary.total_put_volume
                        ? 'Call activity dominates, suggesting bullish positioning or covered call writing.'
                        : 'Put activity leads, indicating hedging demand or bearish sentiment.'}
                    </div>
                  )}
                </div>

                {/* Volume & OI Summary (ENH 8) */}
                <div className="bg-gray-800/50 backdrop-blur rounded-xl border border-gray-700 p-4">
                  <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                    <Activity className="w-4 h-4 text-cyan-400" />
                    VOLUME &amp; OPEN INTEREST
                  </h3>

                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-400">Call Volume:</span>
                      <span className="text-green-400 font-mono">{data.summary.total_call_volume.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Put Volume:</span>
                      <span className="text-red-400 font-mono">{data.summary.total_put_volume.toLocaleString()}</span>
                    </div>
                    {/* Volume bar */}
                    {data.summary.total_volume > 0 && (
                      <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden flex">
                        <div
                          className="h-full bg-green-500/60"
                          style={{ width: `${(data.summary.total_call_volume / data.summary.total_volume) * 100}%` }}
                        />
                        <div
                          className="h-full bg-red-500/60"
                          style={{ width: `${(data.summary.total_put_volume / data.summary.total_volume) * 100}%` }}
                        />
                      </div>
                    )}
                    <div className="flex justify-between border-t border-gray-700 pt-2 mt-2">
                      <span className="text-gray-400">Call OI:</span>
                      <span className="text-green-400 font-mono">{data.summary.total_call_oi.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Put OI:</span>
                      <span className="text-red-400 font-mono">{data.summary.total_put_oi.toLocaleString()}</span>
                    </div>
                    {/* OI bar */}
                    {(data.summary.total_call_oi + data.summary.total_put_oi) > 0 && (
                      <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden flex">
                        <div
                          className="h-full bg-green-500/40"
                          style={{ width: `${(data.summary.total_call_oi / (data.summary.total_call_oi + data.summary.total_put_oi)) * 100}%` }}
                        />
                        <div
                          className="h-full bg-red-500/40"
                          style={{ width: `${(data.summary.total_put_oi / (data.summary.total_call_oi + data.summary.total_put_oi)) * 100}%` }}
                        />
                      </div>
                    )}
                    <div className="flex justify-between border-t border-gray-700 pt-2 mt-2">
                      <span className="text-gray-400">Put/Call Ratio:</span>
                      <span className="text-white font-mono">{data.summary.put_call_ratio.toFixed(3)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Net GEX:</span>
                      <span className={`font-mono font-bold ${data.summary.net_gex >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        ${data.summary.net_gex.toFixed(2)}M
                      </span>
                    </div>
                  </div>
                </div>

                {/* Key Levels with Distance Metrics (ENH 3) */}
                <div className="bg-gray-800/50 backdrop-blur rounded-xl border border-gray-700 p-4">
                  <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                    <Target className="w-4 h-4 text-cyan-400" />
                    KEY LEVELS
                  </h3>

                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-400">Price:</span>
                      <span className="text-white font-mono">{data.levels.price.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-gray-400">GEX Flip:</span>
                      <span className="text-yellow-400 font-mono">
                        {data.levels.gex_flip?.toFixed(2) || 'N/A'}
                        {data.levels.gex_flip && (
                          <span className="text-gray-500 text-xs ml-1.5">{formatDistance(data.levels.gex_flip)}</span>
                        )}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-gray-400">+1σ (Upper):</span>
                      <span className="text-green-400 font-mono">
                        {data.levels.upper_1sd?.toFixed(2) || 'N/A'}
                        {data.levels.upper_1sd && (
                          <span className="text-gray-500 text-xs ml-1.5">{formatDistance(data.levels.upper_1sd)}</span>
                        )}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-gray-400">-1σ (Lower):</span>
                      <span className="text-red-400 font-mono">
                        {data.levels.lower_1sd?.toFixed(2) || 'N/A'}
                        {data.levels.lower_1sd && (
                          <span className="text-gray-500 text-xs ml-1.5">{formatDistance(data.levels.lower_1sd)}</span>
                        )}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-gray-400">Call Wall:</span>
                      <span className="text-cyan-400 font-mono">
                        {data.levels.call_wall?.toFixed(2) || 'N/A'}
                        {data.levels.call_wall && (
                          <span className={`text-xs ml-1.5 ${
                            Math.abs(distancePct(data.levels.call_wall) || 99) < 0.5
                              ? 'text-orange-400 font-bold' : 'text-gray-500'
                          }`}>{formatDistance(data.levels.call_wall)}</span>
                        )}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-gray-400">Put Wall:</span>
                      <span className="text-purple-400 font-mono">
                        {data.levels.put_wall?.toFixed(2) || 'N/A'}
                        {data.levels.put_wall && (
                          <span className={`text-xs ml-1.5 ${
                            Math.abs(distancePct(data.levels.put_wall) || 99) < 0.5
                              ? 'text-orange-400 font-bold' : 'text-gray-500'
                          }`}>{formatDistance(data.levels.put_wall)}</span>
                        )}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Expected Move:</span>
                      <span className="text-white font-mono">
                        ${data.levels.expected_move?.toFixed(2) || 'N/A'}
                        {data.levels.expected_move && data.levels.price > 0 && (
                          <span className="text-gray-500 text-xs ml-1.5">
                            ({(data.levels.expected_move / data.levels.price * 100).toFixed(1)}%)
                          </span>
                        )}
                      </span>
                    </div>
                  </div>

                  {/* Wall Proximity Warning */}
                  {(() => {
                    const callDist = distancePct(data.levels.call_wall)
                    const putDist = distancePct(data.levels.put_wall)
                    const nearCall = callDist !== null && callDist > 0 && callDist < 0.5
                    const nearPut = putDist !== null && putDist < 0 && Math.abs(putDist) < 0.5
                    if (!nearCall && !nearPut) return null
                    return (
                      <div className="mt-3 p-2 rounded bg-orange-500/10 border border-orange-500/20">
                        <span className="text-orange-400 text-xs font-medium">
                          {nearCall && `Price within ${callDist?.toFixed(1)}% of Call Wall — resistance zone`}
                          {nearCall && nearPut && ' | '}
                          {nearPut && `Price within ${Math.abs(putDist!).toFixed(1)}% of Put Wall — support zone`}
                        </span>
                      </div>
                    )
                  })()}
                </div>
              </div>
            </div>
          </>
        )}
      </main>

      {/* Click outside to close dropdown */}
      {showExpirationDropdown && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => setShowExpirationDropdown(false)}
        />
      )}
    </div>
  )
}
