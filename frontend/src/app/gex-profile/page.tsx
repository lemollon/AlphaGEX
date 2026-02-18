'use client'

/**
 * GEX Profile - Gamma Exposure Visualization
 *
 * Three views:
 *   1. Net GEX    — Horizontal bars by strike (Unusual Whales style)
 *   2. Call vs Put — Bidirectional call/put gamma by strike
 *   3. Intraday 5m — Price line + net gamma bars over time
 *
 * Plus: price-to-wall gauge, flow diagnostics, skew measures, market interpretation.
 *
 * Data sources:
 *   /api/watchtower/gex-analysis   — per-strike gamma, header metrics, flow, skew
 *   /api/watchtower/intraday-ticks — 5-minute time series
 */

import { useState, useEffect, useCallback, useMemo } from 'react'
import dynamic from 'next/dynamic'
import {
  RefreshCw, Search, ArrowUpRight, BarChart3, Activity,
  AlertCircle, TrendingUp, Info
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine
} from 'recharts'
import { apiClient } from '@/lib/api'

// Plotly for the unified candlestick + GEX overlay chart (avoid SSR)
const Plot = dynamic(() => import('react-plotly.js'), { ssr: false })

// ── Types ───────────────────────────────────────────────────────────

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
  flow_diagnostics: { cards: DiagnosticCard[]; note: string }
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

interface IntradayBar {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

type ChartView = 'net' | 'split' | 'intraday'

// ── Helpers ─────────────────────────────────────────────────────────

const COMMON_SYMBOLS = ['SPY', 'QQQ', 'IWM', 'GLD', 'DIA', 'AAPL', 'TSLA', 'NVDA', 'AMD']

function isMarketOpen(): boolean {
  const now = new Date()
  const day = now.getDay()
  if (day === 0 || day === 6) return false
  const utcMin = now.getUTCHours() * 60 + now.getUTCMinutes()
  const month = now.getUTCMonth()
  const isDST = month >= 2 && month <= 9
  const etMin = utcMin - (isDST ? 4 : 5) * 60
  return etMin >= 570 && etMin < 975 // 9:30 AM – 4:15 PM ET (= 8:30 AM – 3:15 PM CT)
}

function formatGex(num: number, decimals = 2): string {
  const abs = Math.abs(num)
  if (abs >= 1e9) return `${(num / 1e9).toFixed(decimals)}B`
  if (abs >= 1e6) return `${(num / 1e6).toFixed(decimals)}M`
  if (abs >= 1e3) return `${(num / 1e3).toFixed(decimals)}K`
  return num.toFixed(decimals)
}

function formatDollar(num: number): string {
  return `$${num.toFixed(2)}`
}

/**
 * Convert any timestamp to a Central Time display string (e.g. "8:30 AM").
 * Tradier returns ET; watchtower_snapshots may return UTC.  Using
 * toLocaleTimeString with an explicit timeZone avoids DST pitfalls.
 */
function tickTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-US', {
    timeZone: 'America/Chicago',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  })
}

/**
 * Convert a timestamp string to a CT-localized ISO-like string that Plotly
 * will render correctly on a datetime axis.  Plotly treats bare datetime
 * strings (no offset) as local time, so we emit "YYYY-MM-DD HH:MM:SS"
 * in Central Time so the x-axis labels show CT regardless of the browser's
 * timezone.
 */
function toCentralPlotly(iso: string): string {
  const d = new Date(iso)
  // Format each component in CT
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Chicago',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(d)
  const get = (t: string) => parts.find(p => p.type === t)?.value ?? '00'
  return `${get('year')}-${get('month')}-${get('day')} ${get('hour')}:${get('minute')}:${get('second')}`
}

// ── Page ────────────────────────────────────────────────────────────

export default function GexProfilePage() {
  const paddingClass = useSidebarPadding()

  // ── State ───────────────────────────────────────────────────────
  const [symbol, setSymbol] = useState('SPY')
  const [searchInput, setSearchInput] = useState('')
  const [data, setData] = useState<GexAnalysisData | null>(null)
  const [intradayTicks, setIntradayTicks] = useState<IntradayTick[]>([])
  const [intradayBars, setIntradayBars] = useState<IntradayBar[]>([])
  const [loading, setLoading] = useState(true)
  const [intradayLoading, setIntradayLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [chartView, setChartView] = useState<ChartView>('intraday')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [nextCandleCountdown, setNextCandleCountdown] = useState('')
  const [dataSource, setDataSource] = useState<string>('tradier_live')
  const [sourceLabel, setSourceLabel] = useState<string | null>(null)
  const [isLive, setIsLive] = useState(false)
  const [sessionDate, setSessionDate] = useState<string | null>(null)

  // ── Fetch ───────────────────────────────────────────────────────
  const fetchGexData = useCallback(async (sym: string, clearFirst = false) => {
    try {
      if (clearFirst) {
        setData(null) // Only clear on symbol change — prevents blank flash on auto-refresh
        setLoading(true)
      }
      setError(null)
      const res = await apiClient.getWatchtowerGexAnalysis(sym)
      const result = res.data
      if (result?.success) {
        setData(result.data)
        setDataSource(result.source || 'tradier_live')
        setSourceLabel(result.source_label || null)
        setLastUpdated(new Date())
      } else if (result?.data_unavailable) {
        setError(result.message || 'Data unavailable — market may be closed')
      } else {
        setError('Failed to fetch GEX data')
      }
    } catch (err: any) {
      setError(err?.response?.data?.message || err?.message || 'Failed to connect')
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchIntradayTicks = useCallback(async (sym: string, clearFirst = false, useFallback = false) => {
    try {
      if (clearFirst) {
        setIntradayTicks([]) // Only clear on symbol change
        setIntradayBars([])
      }
      setIntradayLoading(true)
      const [ticksRes, barsRes] = await Promise.all([
        apiClient.getWatchtowerIntradayTicks(sym, 5, useFallback || undefined),
        apiClient.getWatchtowerIntradayBars(sym, '5min', useFallback || undefined),
      ])
      if (ticksRes.data?.success && ticksRes.data?.data?.ticks) {
        setIntradayTicks(ticksRes.data.data.ticks)
      }
      if (barsRes.data?.success && barsRes.data?.data?.bars) {
        setIntradayBars(barsRes.data.data.bars)
        if (barsRes.data.data.session_date) {
          setSessionDate(barsRes.data.data.session_date)
        }
      }
    } catch (err) {
      console.error('Intraday ticks error:', err)
    } finally {
      setIntradayLoading(false)
    }
  }, [])

  // Lightweight bar-only refresh for near-live candlestick updates (no state clearing)
  const refreshBars = useCallback(async (sym: string) => {
    try {
      const res = await apiClient.getWatchtowerIntradayBars(sym, '5min')
      if (res.data?.success && res.data?.data?.bars) {
        setIntradayBars(res.data.data.bars)
      }
    } catch (err) {
      // Silent — don't disrupt the chart on a background poll failure
    }
  }, [])

  // Initial load + symbol change (clear stale data, use fallback for instant render)
  useEffect(() => {
    fetchGexData(symbol, true)
    fetchIntradayTicks(symbol, true, true) // fallback=true: always show data on load
  }, [symbol, fetchGexData, fetchIntradayTicks])

  // Auto-refresh during market hours
  // Bars every 10s for near-live candle updates, full GEX every 30s
  useEffect(() => {
    if (!autoRefresh) return
    setIsLive(isMarketOpen())
    let tick = 0
    const id = setInterval(() => {
      const open = isMarketOpen()
      setIsLive(open)
      if (!open) return
      tick++
      refreshBars(symbol) // Every 10s — near-live candlestick updates
      if (tick % 3 === 0) { // Every 30s — full GEX + ticks refresh (no clear)
        fetchGexData(symbol, false)
        fetchIntradayTicks(symbol, false)
      }
    }, 10_000)
    return () => clearInterval(id)
  }, [autoRefresh, symbol, fetchGexData, fetchIntradayTicks, refreshBars])

  // Live countdown to next 5-minute candle
  useEffect(() => {
    const calc = () => {
      const now = new Date()
      const min = now.getMinutes()
      const sec = now.getSeconds()
      const secsIntoBar = (min % 5) * 60 + sec
      const secsLeft = 5 * 60 - secsIntoBar
      const m = Math.floor(secsLeft / 60)
      const s = secsLeft % 60
      setNextCandleCountdown(`${m}:${s.toString().padStart(2, '0')}`)
    }
    calc()
    const id = setInterval(calc, 1000)
    return () => clearInterval(id)
  }, [])

  const handleSymbolSearch = () => {
    const s = searchInput.trim().toUpperCase()
    if (s && s !== symbol) {
      setSymbol(s)
      setSearchInput('')
    }
  }

  // ── Derived data ────────────────────────────────────────────────

  // Latest tick (for gauge)
  const latestTick = useMemo(() => {
    const valid = intradayTicks.filter(t => t.spot_price !== null)
    return valid.length > 0 ? valid[valid.length - 1] : null
  }, [intradayTicks])

  // Market interpretation
  const interpretation = useMemo(() => {
    if (!data) return []
    const { gamma_form, rating, gex_flip, price } = data.header
    const { call_wall, put_wall } = data.levels
    const lines: string[] = []

    if (gamma_form === 'POSITIVE') {
      lines.push('Positive gamma regime — dealers are long gamma. Price tends to mean-revert. Favor selling premium (Iron Condors).')
    } else if (gamma_form === 'NEGATIVE') {
      lines.push('Negative gamma regime — dealers are short gamma. Price accelerates. Favor directional plays.')
    } else {
      lines.push('Neutral gamma regime — no strong dealer positioning.')
    }

    const aboveFlip = gex_flip ? price > gex_flip : null
    if (aboveFlip === true) {
      lines.push(`Price above flip ($${gex_flip?.toFixed(0)}) — positive gamma territory, upside stability.`)
    } else if (aboveFlip === false) {
      lines.push(`Price below flip ($${gex_flip?.toFixed(0)}) — negative gamma territory, vulnerable to downside.`)
    }

    if (call_wall && price) {
      const d = ((call_wall - price) / price) * 100
      if (d > 0 && d < 0.5) lines.push(`Call wall at $${call_wall.toFixed(0)} only ${d.toFixed(1)}% away — strong resistance.`)
    }
    if (put_wall && price) {
      const d = ((price - put_wall) / price) * 100
      if (d > 0 && d < 0.5) lines.push(`Put wall at $${put_wall.toFixed(0)} only ${d.toFixed(1)}% away — strong support.`)
    }

    if (rating === 'BULLISH' && gamma_form === 'NEGATIVE') {
      lines.push('Divergence: bullish flow in negative gamma — explosive if momentum continues.')
    } else if (rating === 'BEARISH' && gamma_form === 'POSITIVE') {
      lines.push('Divergence: bearish flow in positive gamma — dealers may dampen the move.')
    }

    return lines
  }, [data])

  // ── Prepared chart data ─────────────────────────────────────────

  // Build lookup of OHLC bars keyed by HH:MM label
  const barsByLabel = useMemo(() => {
    const map: Record<string, IntradayBar> = {}
    for (const bar of intradayBars) {
      if (!bar.time) continue
      // Tradier timesales returns time like "2024-01-15T09:30:00"
      const label = tickTime(bar.time)
      map[label] = bar
    }
    return map
  }, [intradayBars])

  // Intraday chart data — merge gamma ticks with OHLC bars
  const intradayChartData = useMemo(() => {
    return intradayTicks
      .filter(t => t.spot_price !== null)
      .map((t, idx, arr) => {
        const fp = t.flip_point ?? 0
        const cw = t.call_wall ?? 0
        const pw = t.put_wall ?? 0
        const label = t.time ? tickTime(t.time) : ''
        const bar = barsByLabel[label]
        return {
          ...t,
          label,
          net_gamma_display: t.net_gamma ?? 0,
          zone_base: pw,
          zone_red: fp > pw ? fp - pw : 0,
          zone_green: cw > fp ? cw - fp : 0,
          isLast: idx === arr.length - 1,
          // OHLC from Tradier (null if no bar matched)
          open: bar?.open ?? null,
          high: bar?.high ?? null,
          low: bar?.low ?? null,
          close: bar?.close ?? null,
          bar_volume: bar?.volume ?? null,
        }
      })
  }, [intradayTicks, barsByLabel])

  // Strike data for Net GEX / Split views
  // Sort by proximity to current price first, THEN slice top 40, THEN sort for display
  const sortedStrikes = useMemo(() => {
    if (!data?.gex_chart.strikes) return []
    const price = data.header.price || 0
    return [...data.gex_chart.strikes]
      .filter(s => Math.abs(s.net_gamma) > 0.00001 || Math.abs(s.call_gamma) > 0.000001)
      .sort((a, b) => Math.abs(a.strike - price) - Math.abs(b.strike - price))
      .slice(0, 40)
      .sort((a, b) => b.strike - a.strike)
      .map(s => ({
        ...s,
        // Absolute value for bar length — XAxis reversed makes bars go left
        abs_net_gamma: Math.abs(s.net_gamma),
        put_gamma_display: -(s.put_gamma || 0),
        gex_label: formatGex(s.net_gamma, 2),
      }))
  }, [data])

  // ── Render ──────────────────────────────────────────────────────

  if (loading && !data) {
    return (
      <div className={`min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 ${paddingClass}`}>
        <Navigation />
        <main className="max-w-[1800px] mx-auto px-4 py-6">
          <div className="flex items-center justify-center h-[60vh]">
            <RefreshCw className="w-8 h-8 text-cyan-400 animate-spin" />
            <span className="ml-3 text-gray-400">Loading GEX data...</span>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className={`min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 ${paddingClass}`}>
      <Navigation />

      <main className="max-w-[1800px] mx-auto px-4 py-6 space-y-5">

        {/* ═══ Title ═══ */}
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <BarChart3 className="w-7 h-7 text-cyan-400" />
            GEX Profile
            {dataSource === 'trading_volatility' && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-purple-500/20 border border-purple-500/40 text-purple-400 font-normal">
                Next-Day Profile
              </span>
            )}
          </h1>
          <p className="text-gray-500 text-sm mt-1">
            {dataSource === 'trading_volatility'
              ? 'After-hours next-day gamma positioning via TradingVolatility — switches to live Tradier data at market open'
              : 'Gamma exposure by strike, intraday dynamics, and options flow'
            }
          </p>
        </div>

        {/* ═══ Controls ═══ */}
        <div className="bg-gray-800/50 backdrop-blur rounded-xl border border-gray-700 p-4">
          <div className="flex flex-wrap items-center gap-4">
            {/* Symbol search */}
            <div className="flex items-center gap-2 bg-gray-900 rounded-lg px-3 py-2 border border-gray-700">
              <Search className="w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={searchInput}
                onChange={e => setSearchInput(e.target.value.toUpperCase())}
                onKeyDown={e => e.key === 'Enter' && handleSymbolSearch()}
                placeholder="Symbol..."
                className="bg-transparent text-white text-sm w-24 outline-none placeholder-gray-500"
              />
              <button onClick={handleSymbolSearch} className="text-cyan-400 hover:text-cyan-300">
                <ArrowUpRight className="w-4 h-4" />
              </button>
            </div>

            <span className="text-2xl font-bold text-white">{symbol}</span>

            {/* Quick symbols */}
            <div className="flex flex-wrap gap-1.5">
              {COMMON_SYMBOLS.filter(s => s !== symbol).slice(0, 6).map(s => (
                <button
                  key={s}
                  onClick={() => setSymbol(s)}
                  className="px-2 py-0.5 text-xs rounded bg-gray-700/50 text-gray-400 hover:text-white hover:bg-gray-700 transition"
                >
                  {s}
                </button>
              ))}
            </div>

            <div className="ml-auto flex items-center gap-3">
              {/* Auto-refresh toggle */}
              <button
                onClick={() => setAutoRefresh(!autoRefresh)}
                className={`text-xs px-2.5 py-1 rounded border transition ${
                  autoRefresh
                    ? 'text-green-400 border-green-500/30 bg-green-500/10'
                    : 'text-gray-500 border-gray-700 bg-gray-800'
                }`}
              >
                {autoRefresh ? 'Auto ON' : 'Auto OFF'}
              </button>
              {/* Manual refresh */}
              <button
                onClick={() => { fetchGexData(symbol); fetchIntradayTicks(symbol) }}
                className="text-gray-400 hover:text-cyan-400 transition"
                disabled={loading}
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              </button>
              {lastUpdated && (
                <span className="text-[10px] text-gray-600">
                  {lastUpdated.toLocaleTimeString('en-US', { timeZone: 'America/Chicago', hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true })} CT
                </span>
              )}
            </div>
          </div>
        </div>

        {/* ═══ Error ═══ */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />
            <span className="text-red-300 text-sm">{error}</span>
          </div>
        )}

        {data && (
          <>
            {/* ═══ Header Metrics ═══ */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              <MetricCard
                label="Price"
                value={formatDollar(data.header.price)}
                color="text-blue-400"
              />
              <MetricCard
                label="Net GEX"
                value={formatGex(data.header.net_gex)}
                color={data.header.net_gex >= 0 ? 'text-green-400' : 'text-red-400'}
                badge={data.header.gamma_form}
                badgeColor={data.header.gamma_form === 'POSITIVE' ? 'bg-green-500/20 text-green-400' : data.header.gamma_form === 'NEGATIVE' ? 'bg-red-500/20 text-red-400' : 'bg-gray-500/20 text-gray-400'}
              />
              <MetricCard
                label="Flip Point"
                value={data.levels.gex_flip ? formatDollar(data.levels.gex_flip) : '—'}
                color="text-yellow-400"
                sub={data.levels.gex_flip ? `${((data.header.price - data.levels.gex_flip) / data.header.price * 100).toFixed(1)}% from price` : undefined}
              />
              <MetricCard
                label="Call Wall"
                value={data.levels.call_wall ? formatDollar(data.levels.call_wall) : '—'}
                color="text-cyan-400"
                sub={data.levels.call_wall ? `+${((data.levels.call_wall - data.header.price) / data.header.price * 100).toFixed(1)}% away` : undefined}
              />
              <MetricCard
                label="Put Wall"
                value={data.levels.put_wall ? formatDollar(data.levels.put_wall) : '—'}
                color="text-purple-400"
                sub={data.levels.put_wall ? `-${((data.header.price - data.levels.put_wall) / data.header.price * 100).toFixed(1)}% away` : undefined}
              />
              <MetricCard
                label="Rating"
                value={data.header.rating}
                color={data.header.rating === 'BULLISH' ? 'text-green-400' : data.header.rating === 'BEARISH' ? 'text-red-400' : 'text-gray-400'}
                sub={data.header['30_day_vol'] ? `VIX ${data.header['30_day_vol'].toFixed(1)}` : undefined}
              />
            </div>

            {/* ═══ Chart Section ═══ */}
            <div className="bg-gray-800/50 backdrop-blur rounded-xl border border-gray-700 p-4">
              {/* Tab bar + title */}
              <div className="flex flex-wrap items-center justify-between mb-4 gap-3">
                <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-cyan-400" />
                  {chartView === 'intraday'
                    ? `${symbol} Intraday 5m — Price + Net Gamma`
                    : `${symbol} ${chartView === 'net' ? 'Net' : 'Call vs Put'} GEX by Strike — ${data.expiration}`
                  }
                  {chartView === 'intraday' && isLive && (
                    <span className="flex items-center gap-1 ml-2 text-xs text-green-400">
                      <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                      LIVE
                    </span>
                  )}
                  {chartView === 'intraday' && !isLive && intradayBars.length > 0 && (
                    <span className="ml-2 text-xs text-gray-400">
                      Market Closed
                      {sessionDate && <span className="text-gray-500"> · Showing {sessionDate} session</span>}
                      {dataSource === 'trading_volatility' && (
                        <span className="text-purple-400"> · Next-day GEX via TradingVolatility</span>
                      )}
                    </span>
                  )}
                  {chartView === 'intraday' && nextCandleCountdown && (
                    <span className="ml-3 text-xs font-mono bg-gray-900 border border-gray-600 rounded px-2 py-0.5 text-cyan-400">
                      Next candle: {nextCandleCountdown}
                    </span>
                  )}
                </h3>
                <div className="flex items-center gap-1 bg-gray-900 rounded-lg p-0.5 border border-gray-700">
                  {(['net', 'split', 'intraday'] as ChartView[]).map(view => (
                    <button
                      key={view}
                      onClick={() => setChartView(view)}
                      className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                        chartView === view
                          ? 'bg-cyan-500/20 text-cyan-400'
                          : 'text-gray-400 hover:text-white'
                      }`}
                    >
                      {view === 'net' ? 'Net GEX' : view === 'split' ? 'Call vs Put' : 'Intraday 5m'}
                    </button>
                  ))}
                </div>
              </div>

              {/* ── INTRADAY 5M — Unified Candlestick + GEX Overlay (Plotly) ── */}
              {chartView === 'intraday' && (
                intradayBars.length === 0 && intradayChartData.length === 0 ? (
                  <div className="text-center py-12 text-yellow-400">
                    <AlertCircle className="w-8 h-8 mx-auto mb-2" />
                    <p className="text-sm">
                      {intradayLoading
                        ? 'Loading intraday data...'
                        : 'No intraday data yet — ticks accumulate during market hours.'}
                    </p>
                  </div>
                ) : (() => {
                  // ── Build Plotly data ──
                  // Candlestick trace from Tradier OHLC bars — convert to CT for x-axis
                  const candleTimes = intradayBars.map(b => toCentralPlotly(b.time))
                  const candleOpen = intradayBars.map(b => b.open)
                  const candleHigh = intradayBars.map(b => b.high)
                  const candleLow = intradayBars.map(b => b.low)
                  const candleClose = intradayBars.map(b => b.close)

                  // If no candle data, use spot_price as a line trace
                  const hasCandleData = intradayBars.length > 0
                  const spotTimes = intradayChartData.map(d => toCentralPlotly(d.time))
                  const spotPrices = intradayChartData.map(d => d.spot_price)

                  // GEX bar shapes — horizontal rectangles at each strike price,
                  // extending from right edge leftward proportional to gamma magnitude.
                  // xref='paper' (0=left, 1=right), yref='y' (price axis)
                  // Filter to strikes within the visible price range to avoid Y-axis distortion
                  const priceValues = hasCandleData
                    ? [...candleHigh, ...candleLow]
                    : spotPrices.filter((p): p is number => p !== null)
                  const priceMin = priceValues.length > 0 ? Math.min(...priceValues) : 0
                  const priceMax = priceValues.length > 0 ? Math.max(...priceValues) : 0
                  const priceRange = priceMax - priceMin || 1
                  const visibleStrikes = sortedStrikes.filter(s =>
                    s.strike >= priceMin - priceRange * 1.5 &&
                    s.strike <= priceMax + priceRange * 1.5
                  )

                  const maxGamma = visibleStrikes.length > 0
                    ? Math.max(...visibleStrikes.map(s => s.abs_net_gamma), 0.001)
                    : 1
                  const barMaxWidth = 0.35 // max 35% of chart width from right edge
                  // Strike spacing for bar height
                  const strikeSpacing = visibleStrikes.length > 1
                    ? Math.abs(visibleStrikes[0].strike - visibleStrikes[1].strike) * 0.35
                    : 0.5

                  const gexShapes: any[] = visibleStrikes.map(s => {
                    const pct = (s.abs_net_gamma / maxGamma) * barMaxWidth
                    const color = s.net_gamma >= 0 ? 'rgba(34,197,94,0.6)' : 'rgba(239,68,68,0.6)'
                    const borderColor = s.net_gamma >= 0 ? 'rgba(34,197,94,0.9)' : 'rgba(239,68,68,0.9)'
                    return {
                      type: 'rect',
                      xref: 'paper',
                      yref: 'y',
                      x0: 1,
                      x1: 1 - pct,
                      y0: s.strike - strikeSpacing,
                      y1: s.strike + strikeSpacing,
                      fillcolor: color,
                      line: { color: borderColor, width: 1 },
                      layer: 'above',
                    }
                  })

                  // GEX value annotations on the bars
                  const gexAnnotations: any[] = visibleStrikes
                    .filter(s => s.abs_net_gamma / maxGamma > 0.08) // only label visible bars
                    .map(s => {
                      const pct = (s.abs_net_gamma / maxGamma) * barMaxWidth
                      return {
                        xref: 'paper',
                        yref: 'y',
                        x: 1 - pct - 0.005,
                        y: s.strike,
                        text: `${formatGex(s.net_gamma, 1)} [$${s.strike}]`,
                        showarrow: false,
                        font: {
                          color: s.net_gamma >= 0 ? '#22c55e' : '#ef4444',
                          size: 9,
                          family: 'monospace',
                        },
                        xanchor: 'right',
                        yanchor: 'middle',
                      }
                    })

                  // Reference level lines (horizontal) — thick enough to see
                  const refLines: any[] = []
                  const { gex_flip: flip, call_wall: cw, put_wall: pw, upper_1sd, lower_1sd, expected_move } = data.levels
                  if (flip) refLines.push({
                    type: 'line', xref: 'paper', yref: 'y',
                    x0: 0, x1: 1, y0: flip, y1: flip,
                    line: { color: '#eab308', width: 2.5, dash: 'dash' },
                  })
                  if (cw) refLines.push({
                    type: 'line', xref: 'paper', yref: 'y',
                    x0: 0, x1: 1, y0: cw, y1: cw,
                    line: { color: '#06b6d4', width: 2.5, dash: 'dot' },
                  })
                  if (pw) refLines.push({
                    type: 'line', xref: 'paper', yref: 'y',
                    x0: 0, x1: 1, y0: pw, y1: pw,
                    line: { color: '#a855f7', width: 2.5, dash: 'dot' },
                  })
                  // ±1 Standard Deviation lines
                  if (upper_1sd) refLines.push({
                    type: 'line', xref: 'paper', yref: 'y',
                    x0: 0, x1: 1, y0: upper_1sd, y1: upper_1sd,
                    line: { color: '#f97316', width: 1.5, dash: 'dashdot' },
                  })
                  if (lower_1sd) refLines.push({
                    type: 'line', xref: 'paper', yref: 'y',
                    x0: 0, x1: 1, y0: lower_1sd, y1: lower_1sd,
                    line: { color: '#f97316', width: 1.5, dash: 'dashdot' },
                  })
                  // Expected Move shaded band (between ±1SD)
                  if (upper_1sd && lower_1sd) refLines.push({
                    type: 'rect', xref: 'paper', yref: 'y',
                    x0: 0, x1: 1, y0: lower_1sd, y1: upper_1sd,
                    fillcolor: 'rgba(249,115,22,0.06)',
                    line: { width: 0 },
                    layer: 'below',
                  })

                  // Compute Y-axis range: include price data + reference levels + padding
                  const yPoints = [...priceValues]
                  if (flip) yPoints.push(flip)
                  if (cw) yPoints.push(cw)
                  if (pw) yPoints.push(pw)
                  if (upper_1sd) yPoints.push(upper_1sd)
                  if (lower_1sd) yPoints.push(lower_1sd)
                  const yMin = yPoints.length > 0 ? Math.min(...yPoints) : 0
                  const yMax = yPoints.length > 0 ? Math.max(...yPoints) : 0
                  const yPad = (yMax - yMin) * 0.35 || 4
                  const yRange: [number, number] = [yMin - yPad, yMax + yPad]

                  // Reference level annotations (on right edge)
                  const refAnnotations: any[] = []
                  if (flip) refAnnotations.push({
                    xref: 'paper', yref: 'y', x: 0.01, y: flip,
                    text: `FLIP $${flip.toFixed(0)}`, showarrow: false,
                    font: { color: '#eab308', size: 10 },
                    xanchor: 'left', yanchor: 'bottom',
                    bgcolor: 'rgba(0,0,0,0.7)', borderpad: 2,
                  })
                  if (cw) refAnnotations.push({
                    xref: 'paper', yref: 'y', x: 0.01, y: cw,
                    text: `CALL WALL $${cw.toFixed(0)}`, showarrow: false,
                    font: { color: '#06b6d4', size: 10 },
                    xanchor: 'left', yanchor: 'bottom',
                    bgcolor: 'rgba(0,0,0,0.7)', borderpad: 2,
                  })
                  if (pw) refAnnotations.push({
                    xref: 'paper', yref: 'y', x: 0.01, y: pw,
                    text: `PUT WALL $${pw.toFixed(0)}`, showarrow: false,
                    font: { color: '#a855f7', size: 10 },
                    xanchor: 'left', yanchor: 'top',
                    bgcolor: 'rgba(0,0,0,0.7)', borderpad: 2,
                  })
                  if (upper_1sd) refAnnotations.push({
                    xref: 'paper', yref: 'y', x: 0.99, y: upper_1sd,
                    text: `+1σ $${upper_1sd.toFixed(0)}${expected_move ? ` (EM $${expected_move.toFixed(1)})` : ''}`,
                    showarrow: false,
                    font: { color: '#f97316', size: 9 },
                    xanchor: 'right', yanchor: 'bottom',
                    bgcolor: 'rgba(0,0,0,0.7)', borderpad: 2,
                  })
                  if (lower_1sd) refAnnotations.push({
                    xref: 'paper', yref: 'y', x: 0.99, y: lower_1sd,
                    text: `-1σ $${lower_1sd.toFixed(0)}`,
                    showarrow: false,
                    font: { color: '#f97316', size: 9 },
                    xanchor: 'right', yanchor: 'top',
                    bgcolor: 'rgba(0,0,0,0.7)', borderpad: 2,
                  })

                  // Price trace
                  const traces: any[] = []
                  if (hasCandleData) {
                    traces.push({
                      x: candleTimes,
                      open: candleOpen,
                      high: candleHigh,
                      low: candleLow,
                      close: candleClose,
                      type: 'candlestick',
                      increasing: { line: { color: '#22c55e' }, fillcolor: 'rgba(34,197,94,0.3)' },
                      decreasing: { line: { color: '#ef4444' }, fillcolor: 'rgba(239,68,68,0.8)' },
                      name: 'Price',
                      hoverinfo: 'x+text',
                      text: intradayBars.map(b =>
                        `O:${b.open.toFixed(2)} H:${b.high.toFixed(2)} L:${b.low.toFixed(2)} C:${b.close.toFixed(2)}<br>Vol:${b.volume.toLocaleString()}`
                      ),
                    })
                  } else {
                    traces.push({
                      x: spotTimes,
                      y: spotPrices,
                      type: 'scatter',
                      mode: 'lines',
                      line: { color: '#3b82f6', width: 2.5 },
                      name: 'Price',
                    })
                  }

                  return (
                    <>
                      <div style={{ height: 550 }}>
                        <Plot
                          data={traces}
                          layout={{
                            height: 550,
                            paper_bgcolor: '#111827',
                            plot_bgcolor: '#1a2332',
                            font: { color: '#9ca3af', family: 'Arial, sans-serif', size: 11 },
                            xaxis: {
                              type: 'date',
                              gridcolor: '#1f2937',
                              showgrid: true,
                              rangeslider: { visible: false },
                              hoverformat: '%I:%M %p CT',
                              tickformat: '%I:%M %p',
                            },
                            yaxis: {
                              title: { text: 'Price', font: { size: 11, color: '#6b7280' } },
                              gridcolor: '#1f2937',
                              showgrid: true,
                              side: 'right',
                              tickformat: '$,.0f',
                              range: yRange,
                              autorange: false,
                            },
                            shapes: [...gexShapes, ...refLines],
                            annotations: [...gexAnnotations, ...refAnnotations],
                            margin: { t: 10, b: 40, l: 10, r: 60 },
                            hovermode: 'x unified',
                            showlegend: false,
                            transition: { duration: 300, easing: 'cubic-in-out' },
                          }}
                          config={{ displayModeBar: false, responsive: true }}
                          style={{ width: '100%', height: '100%' }}
                        />
                      </div>

                      {/* Legend */}
                      <div className="flex flex-wrap gap-4 mt-3 text-xs">
                        {hasCandleData
                          ? <><LegendItem color="bg-green-500" label="Bullish" /><LegendItem color="bg-red-500" label="Bearish" /></>
                          : <LegendItem color="bg-blue-500" label="Price" line />
                        }
                        <span className="text-gray-700">|</span>
                        <span className="text-green-400 font-semibold">■ +GEX Bar</span>
                        <span className="text-red-400 font-semibold">■ -GEX Bar</span>
                        <span className="text-gray-700">|</span>
                        <span className="text-yellow-400">╌╌ Flip</span>
                        <span className="text-cyan-400">┄┄ Call Wall</span>
                        <span className="text-purple-400">┄┄ Put Wall</span>
                        <span className="text-orange-400">-·- ±1σ</span>
                        <span className="text-orange-400/50">░ Expected Move</span>
                        <span className="text-gray-700">|</span>
                        {isLive
                          ? <span className="flex items-center gap-1 text-green-400"><span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />LIVE</span>
                          : <span className="text-gray-500">Market Closed</span>
                        }
                        <span className="text-gray-700">|</span>
                        <span className="text-gray-500">{intradayBars.length} bars{sessionDate ? ` · ${sessionDate}` : ''}</span>
                      </div>
                    </>
                  )
                })()
              )}

              {/* ── NET GEX BY STRIKE ── */}
              {chartView === 'net' && (
                sortedStrikes.length === 0 ? (
                  <NoStrikeData />
                ) : (
                  <>
                    {/* Pure CSS bars — zero on right, bars grow left */}
                    <div className="h-[550px] overflow-y-auto">
                      {(() => {
                        const maxGamma = Math.max(...sortedStrikes.map(s => s.abs_net_gamma), 0.001)
                        const { price, gex_flip: flip, call_wall: cw, put_wall: pw, upper_1sd, lower_1sd } = data.levels
                        const rowH = Math.max(Math.floor(540 / sortedStrikes.length), 12)

                        // Find closest strike index for each reference level
                        const nearest = (target: number | null | undefined) => {
                          if (!target || !sortedStrikes.length) return -1
                          let best = 0, bestD = Infinity
                          sortedStrikes.forEach((s, i) => { const d = Math.abs(s.strike - target); if (d < bestD) { bestD = d; best = i } })
                          return best
                        }
                        const priceIdx = nearest(price)
                        const flipIdx = nearest(flip)
                        const cwIdx = nearest(cw)
                        const pwIdx = nearest(pw)

                        return sortedStrikes.map((entry, i) => {
                          const pct = (entry.abs_net_gamma / maxGamma) * 100
                          const pos = entry.net_gamma >= 0

                          // Reference level markers
                          const atPrice = i === priceIdx
                          const atFlip = i === flipIdx && flipIdx !== priceIdx
                          const atCW = i === cwIdx && cwIdx !== priceIdx
                          const atPW = i === pwIdx && pwIdx !== priceIdx

                          // Row border + background for reference levels
                          const refBorder = atPrice ? 'border-y-2 border-blue-500'
                            : atFlip ? 'border-y-2 border-yellow-500/60'
                            : atCW ? 'border-y-2 border-cyan-500/60'
                            : atPW ? 'border-y-2 border-purple-500/60'
                            : ''

                          const refBg = atPrice ? 'bg-blue-500/15'
                            : atFlip ? 'bg-yellow-500/10'
                            : atCW ? 'bg-cyan-500/10'
                            : atPW ? 'bg-purple-500/10'
                            : ''

                          // Special strike decorations
                          const barRing = entry.is_magnet ? 'ring-1 ring-yellow-500'
                            : entry.is_pin ? 'ring-1 ring-purple-500'
                            : entry.is_danger ? 'ring-1 ring-red-500/60' : ''

                          return (
                            <div
                              key={entry.strike}
                              className={`flex items-center group relative ${refBorder} ${refBg}`}
                              style={{ height: `${rowH}px` }}
                            >
                              {/* Reference level label — left side */}
                              <div className="w-24 flex-shrink-0 text-[9px] font-semibold text-right pr-2 truncate">
                                {atPrice && <span className="text-blue-400">PRICE ${price?.toFixed(0)}</span>}
                                {atFlip && <span className="text-yellow-400">FLIP ${flip?.toFixed(0)}</span>}
                                {atCW && <span className="text-cyan-400">CALL WALL</span>}
                                {atPW && <span className="text-purple-400">PUT WALL</span>}
                              </div>

                              {/* Zero line (thin vertical line between bar area and strike label) */}
                              {/* Bar area — justify-end pushes bar to the RIGHT edge, then bar grows LEFT via width% */}
                              <div className="flex-1 flex justify-end items-center h-full border-r border-gray-600">
                                <div
                                  className={`rounded-l-sm ${pos ? 'bg-green-500' : 'bg-red-500'} ${barRing}`}
                                  style={{
                                    width: `${Math.max(pct, 0.5)}%`,
                                    height: `${Math.min(Math.max(rowH - 4, 6), 18)}px`,
                                    opacity: entry.is_magnet ? 1 : entry.is_danger ? 0.9 : 0.75,
                                  }}
                                />
                              </div>

                              {/* Strike price on RIGHT (touching zero line) */}
                              <div className={`w-12 text-right text-[10px] font-mono pl-1.5 flex-shrink-0 ${
                                atPrice ? 'text-blue-400 font-bold'
                                : atFlip ? 'text-yellow-400'
                                : atCW ? 'text-cyan-400'
                                : atPW ? 'text-purple-400'
                                : 'text-gray-500'
                              }`}>
                                {entry.strike}
                              </div>

                              {/* Hover tooltip */}
                              <div className="hidden group-hover:block absolute right-14 top-0 z-50 bg-gray-900/95 border border-gray-600 rounded-lg p-2.5 shadow-2xl text-xs min-w-[200px] pointer-events-none">
                                <div className="font-bold text-white mb-1">${entry.strike}</div>
                                <div className={`font-semibold mb-1 ${pos ? 'text-green-400' : 'text-red-400'}`}>
                                  Net GEX: {entry.gex_label}
                                </div>
                                <div className="space-y-0.5 text-gray-400">
                                  <div>Call GEX: <span className="text-green-400">{formatGex(entry.call_gamma, 2)}</span></div>
                                  <div>Put GEX: <span className="text-red-400">{formatGex(entry.put_gamma, 2)}</span></div>
                                  {entry.call_iv && <div>Call IV: {(entry.call_iv * 100).toFixed(1)}%</div>}
                                  {entry.put_iv && <div>Put IV: {(entry.put_iv * 100).toFixed(1)}%</div>}
                                  <div>Volume: {entry.total_volume?.toLocaleString()}</div>
                                </div>
                                {entry.is_magnet && <div className="text-yellow-400 mt-1 font-semibold">Magnet Strike</div>}
                                {entry.is_pin && <div className="text-purple-400 mt-1 font-semibold">Pin Strike</div>}
                                {entry.is_danger && <div className="text-red-400 mt-1 font-semibold">{entry.danger_type}</div>}
                              </div>
                            </div>
                          )
                        })
                      })()}
                    </div>

                    {/* Legend */}
                    <div className="flex flex-wrap gap-4 mt-3 text-xs">
                      <LegendItem color="bg-green-500" label="Positive Gamma" />
                      <LegendItem color="bg-red-500" label="Negative Gamma" />
                      <span className="text-gray-700">|</span>
                      <span className="text-blue-400">── Price</span>
                      <span className="text-yellow-400">╌╌ Flip</span>
                      <span className="text-cyan-400">╌╌ Call Wall</span>
                      <span className="text-purple-400">╌╌ Put Wall</span>
                      <span className="text-gray-700">|</span>
                      <LegendItem color="bg-yellow-500 ring-2 ring-yellow-500" label="Magnet" small />
                      <LegendItem color="bg-purple-500 ring-2 ring-purple-500" label="Pin" small />
                    </div>
                  </>
                )
              )}

              {/* ── CALL VS PUT ── */}
              {chartView === 'split' && (
                sortedStrikes.length === 0 ? (
                  <NoStrikeData />
                ) : (
                  <>
                    <div className="h-[550px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={sortedStrikes} layout="vertical" margin={{ top: 5, right: 90, left: 60, bottom: 5 }}>
                          <XAxis type="number" tick={{ fill: '#6b7280', fontSize: 10 }} tickFormatter={v => formatGex(v, 4)} axisLine={{ stroke: '#374151' }} />
                          <YAxis type="category" dataKey="strike" tick={{ fill: '#9ca3af', fontSize: 10 }} width={50} axisLine={{ stroke: '#374151' }} />
                          <Tooltip content={<StrikeTooltip />} />

                          {data.levels.gex_flip && (
                            <ReferenceLine y={data.levels.gex_flip} stroke="#eab308" strokeDasharray="5 3"
                              label={{ value: `Flip ${data.levels.gex_flip}`, fill: '#eab308', fontSize: 9, position: 'right' }} />
                          )}
                          <ReferenceLine y={data.levels.price} stroke="#3b82f6" strokeWidth={2}
                            label={{ value: `Price ${data.levels.price}`, fill: '#3b82f6', fontSize: 9, position: 'right' }} />
                          {data.levels.call_wall && (
                            <ReferenceLine y={data.levels.call_wall} stroke="#06b6d4" strokeDasharray="3 3"
                              label={{ value: `Call Wall`, fill: '#06b6d4', fontSize: 9, position: 'right' }} />
                          )}
                          {data.levels.put_wall && (
                            <ReferenceLine y={data.levels.put_wall} stroke="#a855f7" strokeDasharray="3 3"
                              label={{ value: `Put Wall`, fill: '#a855f7', fontSize: 9, position: 'right' }} />
                          )}

                          <Bar dataKey="call_gamma" name="Call Gamma" fill="#22c55e" fillOpacity={0.75} />
                          <Bar dataKey="put_gamma_display" name="Put Gamma" fill="#ef4444" fillOpacity={0.75} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>

                    {/* Legend */}
                    <div className="flex flex-wrap gap-4 mt-3 text-xs">
                      <LegendItem color="bg-green-500" label="Call Gamma" />
                      <LegendItem color="bg-red-500" label="Put Gamma" />
                    </div>
                  </>
                )
              )}
            </div>

            {/* ═══ Price Position Gauge ═══ */}
            <PriceGauge
              price={latestTick?.spot_price ?? data.header.price}
              flipPoint={latestTick?.flip_point ?? data.levels.gex_flip ?? 0}
              callWall={latestTick?.call_wall ?? data.levels.call_wall ?? 0}
              putWall={latestTick?.put_wall ?? data.levels.put_wall ?? 0}
            />

            {/* ═══ Market Interpretation ═══ */}
            {interpretation.length > 0 && (
              <div className="bg-gray-800/50 backdrop-blur rounded-xl border border-gray-700 p-4">
                <h3 className="text-sm font-semibold text-white flex items-center gap-2 mb-3">
                  <Info className="w-4 h-4 text-cyan-400" />
                  Market Interpretation
                </h3>
                <div className="space-y-2">
                  {interpretation.map((line, i) => (
                    <p key={i} className="text-sm text-gray-300 leading-relaxed">{line}</p>
                  ))}
                </div>
              </div>
            )}

            {/* ═══ Flow Diagnostics ═══ */}
            {data.flow_diagnostics?.cards?.length > 0 && (
              <div className="bg-gray-800/50 backdrop-blur rounded-xl border border-gray-700 p-4">
                <h3 className="text-sm font-semibold text-white flex items-center gap-2 mb-3">
                  <Activity className="w-4 h-4 text-cyan-400" />
                  Options Flow Diagnostics
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                  {data.flow_diagnostics.cards.map(card => (
                    <div key={card.id} className={`rounded-lg p-3 border ${getCardBorder(card)}`}>
                      <div className="text-[10px] text-gray-400 uppercase mb-1">{card.label}</div>
                      <div className="text-lg font-bold text-white">{card.metric_value}</div>
                      <div className="text-[10px] text-gray-500 mt-1">{card.description}</div>
                    </div>
                  ))}
                </div>
                {data.flow_diagnostics.note && (
                  <p className="text-[10px] text-gray-600 mt-2">{data.flow_diagnostics.note}</p>
                )}
              </div>
            )}

            {/* ═══ Skew Measures ═══ */}
            {data.skew_measures && (
              <div className="bg-gray-800/50 backdrop-blur rounded-xl border border-gray-700 p-4">
                <h3 className="text-sm font-semibold text-white flex items-center gap-2 mb-3">
                  <TrendingUp className="w-4 h-4 text-cyan-400" />
                  Skew Measures
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <SkewCard label="Skew Ratio" value={data.skew_measures.skew_ratio.toFixed(3)} desc={data.skew_measures.skew_ratio_description} />
                  <SkewCard label="Call Skew" value={data.skew_measures.call_skew.toFixed(3)} desc={data.skew_measures.call_skew_description} />
                  <SkewCard
                    label="ATM IV"
                    value={`C: ${data.skew_measures.atm_call_iv?.toFixed(1) ?? '—'}% / P: ${data.skew_measures.atm_put_iv?.toFixed(1) ?? '—'}%`}
                    desc="At-the-money implied volatility"
                  />
                  <SkewCard
                    label="OTM Avg IV"
                    value={`C: ${data.skew_measures.avg_otm_call_iv?.toFixed(1) ?? '—'}% / P: ${data.skew_measures.avg_otm_put_iv?.toFixed(1) ?? '—'}%`}
                    desc="Out-of-the-money average IV"
                  />
                </div>
              </div>
            )}

            {/* ═══ Summary Stats ═══ */}
            {data.summary && (
              <div className="bg-gray-800/50 backdrop-blur rounded-xl border border-gray-700 p-4">
                <h3 className="text-sm font-semibold text-white flex items-center gap-2 mb-3">
                  <BarChart3 className="w-4 h-4 text-cyan-400" />
                  Volume & Open Interest
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                  <StatCard label="Total Volume" value={data.summary.total_volume.toLocaleString()} />
                  <StatCard label="Call Volume" value={data.summary.total_call_volume.toLocaleString()} color="text-green-400" />
                  <StatCard label="Put Volume" value={data.summary.total_put_volume.toLocaleString()} color="text-red-400" />
                  <StatCard label="Total OI" value={(data.summary.total_call_oi + data.summary.total_put_oi).toLocaleString()} />
                  <StatCard label="P/C Ratio" value={data.summary.put_call_ratio.toFixed(2)} color={data.summary.put_call_ratio > 1 ? 'text-red-400' : 'text-green-400'} />
                  <StatCard label="Net GEX" value={formatGex(data.summary.net_gex)} color={data.summary.net_gex >= 0 ? 'text-green-400' : 'text-red-400'} />
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}

// ── Sub-Components ──────────────────────────────────────────────────

function MetricCard({ label, value, color, badge, badgeColor, sub }: {
  label: string; value: string; color: string; badge?: string; badgeColor?: string; sub?: string
}) {
  return (
    <div className="bg-gray-800/60 rounded-lg p-3 border border-gray-700">
      <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-xl font-bold ${color} flex items-center gap-2`}>
        {value}
        {badge && <span className={`text-[10px] px-1.5 py-0.5 rounded ${badgeColor}`}>{badge}</span>}
      </div>
      {sub && <div className="text-[10px] text-gray-500 mt-0.5">{sub}</div>}
    </div>
  )
}

function PriceGauge({ price, flipPoint, callWall, putWall }: {
  price: number; flipPoint: number; callWall: number; putWall: number
}) {
  if (!price || !callWall || !putWall || callWall <= putWall) return null

  const range = callWall - putWall
  const pricePos = Math.max(0, Math.min(100, ((price - putWall) / range) * 100))
  const flipPos = Math.max(0, Math.min(100, ((flipPoint - putWall) / range) * 100))
  const aboveFlip = price > flipPoint
  const distToCall = ((callWall - price) / price * 100).toFixed(1)
  const distToPut = ((price - putWall) / price * 100).toFixed(1)

  return (
    <div className="bg-gray-800/50 backdrop-blur rounded-xl border border-gray-700 p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-gray-400 font-medium uppercase tracking-wider">Price Position in GEX Structure</span>
        <span className={`text-xs font-bold ${aboveFlip ? 'text-green-400' : 'text-red-400'}`}>
          {aboveFlip ? 'POSITIVE GAMMA ZONE' : 'NEGATIVE GAMMA ZONE'}
        </span>
      </div>

      {/* Gauge bar */}
      <div className="relative h-7 rounded-full overflow-hidden bg-gray-900 border border-gray-700">
        {/* Red zone */}
        <div className="absolute top-0 h-full bg-red-500/15" style={{ left: 0, width: `${flipPos}%` }} />
        {/* Green zone */}
        <div className="absolute top-0 h-full bg-green-500/15" style={{ left: `${flipPos}%`, width: `${100 - flipPos}%` }} />
        {/* Flip marker */}
        <div className="absolute top-0 h-full w-0.5 bg-yellow-400/80" style={{ left: `${flipPos}%` }} />
        {/* Price marker */}
        <div
          className="absolute top-0.5 w-3.5 h-6 rounded-sm bg-blue-500 border border-blue-300 shadow-lg shadow-blue-500/30"
          style={{ left: `calc(${pricePos}% - 7px)` }}
        />
      </div>

      {/* Labels */}
      <div className="flex justify-between mt-2 text-[10px]">
        <span className="text-purple-400">
          Put Wall ${putWall.toFixed(0)} <span className="text-gray-600">({distToPut}% away)</span>
        </span>
        <span className="text-yellow-400">Flip ${flipPoint.toFixed(0)}</span>
        <span className="text-cyan-400">
          <span className="text-gray-600">({distToCall}% away)</span> Call Wall ${callWall.toFixed(0)}
        </span>
      </div>
    </div>
  )
}

function StrikeTooltip({ active, payload, label }: any) {
  if (!active || !payload || !payload.length) return null
  const s = payload[0]?.payload
  if (!s) return null

  return (
    <div className="bg-gray-900 border border-gray-600 rounded-lg p-3 shadow-xl text-xs min-w-[220px]">
      <div className="font-bold text-white text-sm mb-2 flex items-center gap-2">
        Strike: ${label}
        {s.is_magnet && <span className="bg-yellow-500/20 text-yellow-400 px-1.5 py-0.5 rounded text-[10px]">MAGNET{s.magnet_rank ? ` #${s.magnet_rank}` : ''}</span>}
        {s.is_pin && <span className="bg-purple-500/20 text-purple-400 px-1.5 py-0.5 rounded text-[10px]">PIN</span>}
        {s.is_danger && <span className="bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded text-[10px]">{s.danger_type}</span>}
      </div>
      <div className="space-y-1">
        <TipRow label="Net Gamma" value={formatGex(s.net_gamma, 4)} color={s.net_gamma >= 0 ? 'text-green-400' : 'text-red-400'} bold />
        <TipRow label="Call Gamma" value={s.call_gamma?.toFixed(6)} color="text-green-400" />
        <TipRow label="Put Gamma" value={s.put_gamma?.toFixed(6)} color="text-red-400" />
        <div className="border-t border-gray-700 pt-1 mt-1">
          <TipRow label="Call Vol / Put Vol" value={`${(s.call_volume || 0).toLocaleString()} / ${(s.put_volume || 0).toLocaleString()}`} color="text-white" />
          <TipRow label="Call OI / Put OI" value={`${(s.call_oi || 0).toLocaleString()} / ${(s.put_oi || 0).toLocaleString()}`} color="text-white" />
        </div>
        {(s.call_iv || s.put_iv) && (
          <div className="border-t border-gray-700 pt-1 mt-1">
            <TipRow label="Call IV / Put IV" value={`${s.call_iv ? `${s.call_iv}%` : 'N/A'} / ${s.put_iv ? `${s.put_iv}%` : 'N/A'}`} color="text-white" />
          </div>
        )}
      </div>
    </div>
  )
}

function TipRow({ label, value, color, bold }: { label: string; value: string; color: string; bold?: boolean }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-gray-400">{label}:</span>
      <span className={`font-mono ${bold ? 'font-bold' : ''} ${color}`}>{value}</span>
    </div>
  )
}

function LegendItem({ color, label, line, dashed, small }: {
  color: string; label: string; line?: boolean; dashed?: boolean; small?: boolean
}) {
  return (
    <div className="flex items-center gap-1.5">
      {line ? (
        <div className={`w-5 h-0 ${dashed ? 'border-t border-dashed' : 'border-t-2'} ${color.replace('bg-', 'border-')}`} />
      ) : (
        <div className={`${small ? 'w-2.5 h-2.5' : 'w-3 h-3'} rounded-sm ${color}`} />
      )}
      <span className="text-gray-400">{label}</span>
    </div>
  )
}

function SkewCard({ label, value, desc }: { label: string; value: string; desc: string }) {
  return (
    <div className="bg-gray-900/60 rounded-lg p-3 border border-gray-700">
      <div className="text-[10px] text-gray-500 uppercase mb-1">{label}</div>
      <div className="text-lg font-bold text-white">{value}</div>
      <div className="text-[10px] text-gray-500 mt-1">{desc}</div>
    </div>
  )
}

function StatCard({ label, value, color = 'text-white' }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-gray-900/60 rounded-lg p-3 border border-gray-700">
      <div className="text-[10px] text-gray-500 uppercase mb-1">{label}</div>
      <div className={`text-lg font-bold ${color}`}>{value}</div>
    </div>
  )
}

function NoStrikeData() {
  return (
    <div className="text-center py-12 text-yellow-400">
      <AlertCircle className="w-8 h-8 mx-auto mb-2" />
      <p className="text-sm">Real-time data not available outside market hours (8:30 AM – 3:00 PM CT)</p>
    </div>
  )
}

function getCardBorder(card: DiagnosticCard): string {
  if (card.id === 'volume_pressure' && card.raw_value > 0.1) return 'border-cyan-500/50 bg-cyan-500/5'
  if (card.id === 'call_share' && card.raw_value > 55) return 'border-cyan-500/50 bg-cyan-500/5'
  if (card.id === 'short_dte_share' && card.raw_value > 50) return 'border-cyan-500/50 bg-cyan-500/5'
  if (card.id === 'volume_pressure' && card.raw_value < -0.1) return 'border-red-500/50 bg-red-500/5'
  if (card.id === 'lotto_turnover' && card.raw_value > 0.3) return 'border-yellow-500/50 bg-yellow-500/5'
  return 'border-gray-700 bg-gray-800/50'
}
