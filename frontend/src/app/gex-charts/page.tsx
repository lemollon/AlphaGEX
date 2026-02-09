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

import { useState, useEffect, useCallback } from 'react'
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
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from 'recharts'
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
  }
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

// Common symbols for quick selection
const COMMON_SYMBOLS = ['SPY', 'QQQ', 'IWM', 'GLD', 'SLV', 'USO', 'TLT', 'DIA', 'AAPL', 'TSLA', 'NVDA', 'AMD']

export default function GexChartsPage() {
  const paddingClass = useSidebarPadding()
  const [symbol, setSymbol] = useState('SPY')
  const [searchInput, setSearchInput] = useState('')
  const [data, setData] = useState<GexAnalysisData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)

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

  // Auto-refresh every 30 seconds during market hours
  useEffect(() => {
    if (!autoRefresh) return

    const interval = setInterval(() => {
      fetchData(symbol, selectedExpiration)
    }, 30000)

    return () => clearInterval(interval)
  }, [symbol, selectedExpiration, autoRefresh, fetchData])

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
                autoRefresh ? 'bg-green-500/20 text-green-400 border border-green-500/30' : 'bg-gray-800 text-gray-400 border border-gray-700'
              }`}
            >
              <Clock className="w-4 h-4" />
              {autoRefresh ? 'Auto 30s' : 'Manual'}
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
                  <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                    <BarChart3 className="w-4 h-4 text-cyan-400" />
                    {symbol} Net GEX for {data.expiration} Expiration, by Strike
                  </h3>

                  {data.gex_chart.strikes.length === 0 ? (
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
                            .filter(s => Math.abs(s.net_gamma) > 0.00001)
                            .slice(0, 40)
                            .sort((a, b) => b.strike - a.strike)
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
                            <Tooltip
                              contentStyle={{
                                backgroundColor: '#1f2937',
                                border: '1px solid #374151',
                                borderRadius: '8px'
                              }}
                              formatter={(value: number) => [formatNumber(value, 4), 'Net Gamma']}
                              labelFormatter={(label) => `Strike: ${label}`}
                            />
                            {data.levels.gex_flip && (
                              <ReferenceLine
                                y={data.levels.gex_flip}
                                stroke="#ef4444"
                                strokeDasharray="3 3"
                                label={{ value: 'GEX Flip', fill: '#ef4444', fontSize: 10 }}
                              />
                            )}
                            <Bar dataKey="net_gamma" name="Net Gamma at Strike">
                              {sortedStrikes.map((entry, index) => (
                                <Cell
                                  key={`cell-${index}`}
                                  fill={entry.net_gamma >= 0 ? '#06b6d4' : '#06b6d4'}
                                />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                          )
                        })()}
                      </div>

                      {/* Key Levels Legend */}
                      <div className="flex flex-wrap gap-4 mt-4 text-xs">
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 bg-cyan-400"></div>
                          <span className="text-gray-400">Net Gamma at Strike</span>
                        </div>
                        {data.levels.upper_1sd && (
                          <div className="flex items-center gap-2">
                            <div className="w-8 h-0.5 bg-green-400"></div>
                            <span className="text-gray-400">+1σ: {data.levels.upper_1sd}</span>
                          </div>
                        )}
                        <div className="flex items-center gap-2">
                          <div className="w-8 h-0.5 bg-blue-400"></div>
                          <span className="text-gray-400">Price: {data.levels.price}</span>
                        </div>
                        {data.levels.lower_1sd && (
                          <div className="flex items-center gap-2">
                            <div className="w-8 h-0.5 bg-red-400"></div>
                            <span className="text-gray-400">-1σ: {data.levels.lower_1sd}</span>
                          </div>
                        )}
                        {data.levels.gex_flip && (
                          <div className="flex items-center gap-2">
                            <div className="w-8 h-0.5 bg-yellow-400 border-dashed"></div>
                            <span className="text-gray-400">GEX Flip: {data.levels.gex_flip}</span>
                          </div>
                        )}
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

                {/* Call Structure */}
                <div className="bg-gray-800/50 backdrop-blur rounded-xl border border-gray-700 p-4">
                  <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                    <Target className="w-4 h-4 text-cyan-400" />
                    CALL STRUCTURE
                  </h3>

                  <div className="text-lg font-bold text-yellow-400 mb-2">
                    {data.header.call_structure}
                  </div>

                  <div className="text-xs text-gray-400">
                    {data.summary.total_call_volume > data.summary.total_put_volume
                      ? 'Call activity dominates, suggesting bullish positioning or covered call writing.'
                      : 'Put activity leads, indicating hedging demand or bearish sentiment.'}
                  </div>
                </div>

                {/* Volume Summary */}
                <div className="bg-gray-800/50 backdrop-blur rounded-xl border border-gray-700 p-4">
                  <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                    <Activity className="w-4 h-4 text-cyan-400" />
                    VOLUME SUMMARY
                  </h3>

                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-400">Total Call Volume:</span>
                      <span className="text-green-400 font-mono">{data.summary.total_call_volume.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Total Put Volume:</span>
                      <span className="text-red-400 font-mono">{data.summary.total_put_volume.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between border-t border-gray-700 pt-2 mt-2">
                      <span className="text-gray-400">Put/Call Ratio:</span>
                      <span className="text-white font-mono">{data.summary.put_call_ratio.toFixed(3)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Net GEX (MM):</span>
                      <span className={`font-mono ${data.summary.net_gex >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        ${data.summary.net_gex.toFixed(2)}M
                      </span>
                    </div>
                  </div>
                </div>

                {/* Key Levels */}
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
                    <div className="flex justify-between">
                      <span className="text-gray-400">GEX Flip:</span>
                      <span className="text-yellow-400 font-mono">{data.levels.gex_flip?.toFixed(2) || 'N/A'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">+1σ (Upper):</span>
                      <span className="text-green-400 font-mono">{data.levels.upper_1sd?.toFixed(2) || 'N/A'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">-1σ (Lower):</span>
                      <span className="text-red-400 font-mono">{data.levels.lower_1sd?.toFixed(2) || 'N/A'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Call Wall:</span>
                      <span className="text-cyan-400 font-mono">{data.levels.call_wall?.toFixed(2) || 'N/A'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Put Wall:</span>
                      <span className="text-purple-400 font-mono">{data.levels.put_wall?.toFixed(2) || 'N/A'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Expected Move:</span>
                      <span className="text-white font-mono">${data.levels.expected_move?.toFixed(2) || 'N/A'}</span>
                    </div>
                  </div>
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
