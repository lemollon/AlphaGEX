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
import {
  RefreshCw, Search, ArrowUpRight, BarChart3, Activity,
  AlertCircle, TrendingUp, TrendingDown, Minus, Clock, Info
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, Cell, ComposedChart, Line, Area, CartesianGrid, Legend
} from 'recharts'
import { apiClient } from '@/lib/api'

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
  return etMin >= 570 && etMin < 975 // 9:30 AM – 4:15 PM ET
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

function tickTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })
}

// ── Page ────────────────────────────────────────────────────────────

export default function GexProfilePage() {
  const paddingClass = useSidebarPadding()

  // ── State ───────────────────────────────────────────────────────
  const [symbol, setSymbol] = useState('SPY')
  const [searchInput, setSearchInput] = useState('')
  const [data, setData] = useState<GexAnalysisData | null>(null)
  const [intradayTicks, setIntradayTicks] = useState<IntradayTick[]>([])
  const [loading, setLoading] = useState(true)
  const [intradayLoading, setIntradayLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [chartView, setChartView] = useState<ChartView>('intraday')
  const [autoRefresh, setAutoRefresh] = useState(true)

  // ── Fetch ───────────────────────────────────────────────────────
  const fetchGexData = useCallback(async (sym: string) => {
    try {
      setLoading(true)
      setError(null)
      const res = await apiClient.getWatchtowerGexAnalysis(sym)
      const result = res.data
      if (result?.success) {
        setData(result.data)
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

  const fetchIntradayTicks = useCallback(async (sym: string) => {
    try {
      setIntradayLoading(true)
      const res = await apiClient.getWatchtowerIntradayTicks(sym, 5)
      if (res.data?.success && res.data?.data?.ticks) {
        setIntradayTicks(res.data.data.ticks)
      }
    } catch (err) {
      console.error('Intraday ticks error:', err)
    } finally {
      setIntradayLoading(false)
    }
  }, [])

  // Initial load
  useEffect(() => {
    fetchGexData(symbol)
    fetchIntradayTicks(symbol)
  }, [symbol, fetchGexData, fetchIntradayTicks])

  // Auto-refresh during market hours
  useEffect(() => {
    if (!autoRefresh) return
    const id = setInterval(() => {
      if (isMarketOpen()) {
        fetchGexData(symbol)
        if (chartView === 'intraday') fetchIntradayTicks(symbol)
      }
    }, 30_000)
    return () => clearInterval(id)
  }, [autoRefresh, symbol, chartView, fetchGexData, fetchIntradayTicks])

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

  // Intraday chart data
  const intradayChartData = useMemo(() => {
    return intradayTicks
      .filter(t => t.spot_price !== null)
      .map((t, idx, arr) => {
        const fp = t.flip_point ?? 0
        const cw = t.call_wall ?? 0
        const pw = t.put_wall ?? 0
        return {
          ...t,
          label: t.time ? tickTime(t.time) : '',
          net_gamma_display: t.net_gamma ?? 0,
          zone_base: pw,
          zone_red: fp > pw ? fp - pw : 0,
          zone_green: cw > fp ? cw - fp : 0,
          isLast: idx === arr.length - 1,
        }
      })
  }, [intradayTicks])

  // Price range for intraday chart
  const intradayPriceRange = useMemo(() => {
    const all = intradayChartData.flatMap(t =>
      [t.spot_price, t.flip_point, t.call_wall, t.put_wall]
        .filter((v): v is number => v !== null && v !== undefined && v > 0)
    )
    if (all.length === 0) return { min: 0, max: 0 }
    const min = Math.min(...all)
    const max = Math.max(...all)
    const pad = (max - min) * 0.1 || 1
    return { min: min - pad, max: max + pad }
  }, [intradayChartData])

  // Strike data for Net GEX / Split views
  const sortedStrikes = useMemo(() => {
    if (!data?.gex_chart.strikes) return []
    return [...data.gex_chart.strikes]
      .filter(s => Math.abs(s.net_gamma) > 0.00001 || Math.abs(s.call_gamma) > 0.000001)
      .slice(0, 40)
      .sort((a, b) => b.strike - a.strike)
      .map(s => ({
        ...s,
        // Negative absolute value — bars extend left from 0, color encodes sign
        abs_net_gamma: -Math.abs(s.net_gamma),
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
          </h1>
          <p className="text-gray-500 text-sm mt-1">
            Gamma exposure by strike, intraday dynamics, and options flow
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
                  {lastUpdated.toLocaleTimeString()}
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

              {/* ── INTRADAY 5M CHART ── */}
              {chartView === 'intraday' && (
                intradayChartData.length === 0 ? (
                  <div className="text-center py-12 text-yellow-400">
                    <AlertCircle className="w-8 h-8 mx-auto mb-2" />
                    <p className="text-sm">
                      {intradayLoading
                        ? 'Loading intraday ticks...'
                        : 'No intraday data yet — ticks accumulate during market hours.'}
                    </p>
                  </div>
                ) : (
                  <>
                    <div className="h-[500px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={intradayChartData} margin={{ top: 10, right: 60, left: 10, bottom: 5 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />

                          <XAxis
                            dataKey="label"
                            tick={{ fill: '#6b7280', fontSize: 10 }}
                            interval="preserveStartEnd"
                            axisLine={{ stroke: '#374151' }}
                          />

                          {/* Left Y — Net Gamma */}
                          <YAxis
                            yAxisId="gamma"
                            orientation="left"
                            tick={{ fill: '#6b7280', fontSize: 10 }}
                            tickFormatter={v => formatGex(v, 1)}
                            label={{ value: 'Net Gamma', angle: -90, position: 'insideLeft', fill: '#4b5563', fontSize: 10 }}
                            axisLine={{ stroke: '#374151' }}
                          />

                          {/* Right Y — Price */}
                          <YAxis
                            yAxisId="price"
                            orientation="right"
                            domain={[intradayPriceRange.min, intradayPriceRange.max]}
                            tick={{ fill: '#3b82f6', fontSize: 10 }}
                            tickFormatter={v => `$${v.toFixed(0)}`}
                            label={{ value: 'Price', angle: 90, position: 'insideRight', fill: '#3b82f6', fontSize: 10 }}
                            axisLine={{ stroke: '#1e3a5f' }}
                          />

                          {/* Tooltip */}
                          <Tooltip content={<IntradayTooltip />} />

                          {/* Zone bands (stacked on price axis) */}
                          <Area yAxisId="price" type="stepAfter" dataKey="zone_base" stackId="zones" fill="transparent" stroke="none" />
                          <Area yAxisId="price" type="stepAfter" dataKey="zone_red" stackId="zones" fill="#ef4444" fillOpacity={0.06} stroke="none" />
                          <Area yAxisId="price" type="stepAfter" dataKey="zone_green" stackId="zones" fill="#22c55e" fillOpacity={0.06} stroke="none" />

                          {/* Net gamma bars */}
                          <Bar yAxisId="gamma" dataKey="net_gamma_display" name="Net Gamma" barSize={14}>
                            {intradayChartData.map((entry, i) => (
                              <Cell
                                key={`g-${i}`}
                                fill={entry.net_gamma_display >= 0 ? '#22c55e' : '#ef4444'}
                                fillOpacity={0.75}
                              />
                            ))}
                          </Bar>

                          {/* Price line */}
                          <Line
                            yAxisId="price"
                            type="monotone"
                            dataKey="spot_price"
                            stroke="#3b82f6"
                            strokeWidth={2.5}
                            dot={(props: any) => {
                              const { cx, cy, payload } = props
                              if (!payload?.isLast) return <circle key="h" r={0} />
                              return <circle key="last" cx={cx} cy={cy} r={5} fill="#3b82f6" stroke="#1e3a5f" strokeWidth={2} />
                            }}
                            name="Price"
                          />

                          {/* Key level lines */}
                          <Line yAxisId="price" type="stepAfter" dataKey="flip_point" stroke="#eab308" strokeWidth={1.5} strokeDasharray="5 3" dot={false} name="Flip Point" />
                          <Line yAxisId="price" type="stepAfter" dataKey="call_wall" stroke="#06b6d4" strokeWidth={1.5} strokeDasharray="3 3" dot={false} name="Call Wall" />
                          <Line yAxisId="price" type="stepAfter" dataKey="put_wall" stroke="#a855f7" strokeWidth={1.5} strokeDasharray="3 3" dot={false} name="Put Wall" />
                        </ComposedChart>
                      </ResponsiveContainer>
                    </div>

                    {/* Legend */}
                    <div className="flex flex-wrap gap-4 mt-3 text-xs">
                      <LegendItem color="bg-green-500" label="+ Gamma Bar" />
                      <LegendItem color="bg-red-500" label="- Gamma Bar" />
                      <span className="text-gray-700">|</span>
                      <LegendItem color="bg-blue-500" label="Price" line />
                      <LegendItem color="bg-yellow-400" label="Flip" line dashed />
                      <LegendItem color="bg-cyan-400" label="Call Wall" line dashed />
                      <LegendItem color="bg-purple-400" label="Put Wall" line dashed />
                      <span className="text-gray-700">|</span>
                      <LegendItem color="bg-green-500/20 border border-green-500/40" label="+ Zone" />
                      <LegendItem color="bg-red-500/20 border border-red-500/40" label="- Zone" />
                      <span className="text-gray-700">|</span>
                      <span className="text-gray-500">{intradayTicks.length} ticks today</span>
                    </div>
                  </>
                )
              )}

              {/* ── NET GEX BY STRIKE ── */}
              {chartView === 'net' && (
                sortedStrikes.length === 0 ? (
                  <NoStrikeData />
                ) : (
                  <>
                    <div className="h-[550px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={sortedStrikes} layout="vertical" margin={{ top: 5, right: 30, left: 60, bottom: 5 }}>
                          {/* X-axis: bars extend left from 0 — show absolute magnitude in labels */}
                          <XAxis
                            type="number"
                            tick={{ fill: '#6b7280', fontSize: 10 }}
                            tickFormatter={v => formatGex(Math.abs(v), 1)}
                            axisLine={{ stroke: '#374151' }}
                            domain={['auto', 0]}
                          />
                          {/* Strike prices on left side */}
                          <YAxis type="category" dataKey="strike" tick={{ fill: '#9ca3af', fontSize: 10 }} width={50} axisLine={{ stroke: '#374151' }} />
                          <Tooltip content={<StrikeTooltip />} />

                          {/* Reference lines */}
                          {data.levels.gex_flip && (
                            <ReferenceLine y={data.levels.gex_flip} stroke="#eab308" strokeDasharray="5 3"
                              label={{ value: `Flip ${data.levels.gex_flip}`, fill: '#eab308', fontSize: 9, position: 'right' }} />
                          )}
                          <ReferenceLine y={data.levels.price} stroke="#3b82f6" strokeWidth={2}
                            label={{ value: `Price ${data.levels.price}`, fill: '#3b82f6', fontSize: 9, position: 'right' }} />
                          {data.levels.call_wall && (
                            <ReferenceLine y={data.levels.call_wall} stroke="#06b6d4" strokeDasharray="3 3"
                              label={{ value: `Call Wall ${data.levels.call_wall}`, fill: '#06b6d4', fontSize: 9, position: 'right' }} />
                          )}
                          {data.levels.put_wall && (
                            <ReferenceLine y={data.levels.put_wall} stroke="#a855f7" strokeDasharray="3 3"
                              label={{ value: `Put Wall ${data.levels.put_wall}`, fill: '#a855f7', fontSize: 9, position: 'right' }} />
                          )}
                          {data.levels.upper_1sd && (
                            <ReferenceLine y={data.levels.upper_1sd} stroke="#22c55e" strokeDasharray="2 4"
                              label={{ value: '+1\u03C3', fill: '#22c55e', fontSize: 9, position: 'left' }} />
                          )}
                          {data.levels.lower_1sd && (
                            <ReferenceLine y={data.levels.lower_1sd} stroke="#ef4444" strokeDasharray="2 4"
                              label={{ value: '-1\u03C3', fill: '#ef4444', fontSize: 9, position: 'left' }} />
                          )}

                          {/* Bars use absolute value — color encodes positive (green) vs negative (red) */}
                          <Bar dataKey="abs_net_gamma" name="Net Gamma">
                            {sortedStrikes.map((entry, i) => (
                              <Cell
                                key={`n-${i}`}
                                fill={entry.net_gamma >= 0 ? '#22c55e' : '#ef4444'}
                                fillOpacity={entry.is_magnet ? 1 : entry.is_danger ? 0.9 : 0.75}
                                stroke={entry.is_magnet ? '#eab308' : entry.is_pin ? '#a855f7' : entry.is_danger ? '#ef4444' : 'none'}
                                strokeWidth={entry.is_magnet || entry.is_pin || entry.is_danger ? 2 : 0}
                              />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>

                    {/* Legend */}
                    <div className="flex flex-wrap gap-4 mt-3 text-xs">
                      <LegendItem color="bg-green-500" label="Positive Gamma (support)" />
                      <LegendItem color="bg-red-500" label="Negative Gamma (momentum)" />
                      <span className="text-gray-700">|</span>
                      <LegendItem color="bg-yellow-500 ring-2 ring-yellow-500" label="Magnet" small />
                      <LegendItem color="bg-purple-500 ring-2 ring-purple-500" label="Pin" small />
                      <LegendItem color="bg-red-500 ring-2 ring-red-500" label="Danger Zone" small />
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

function IntradayTooltip({ active, payload, label: tipLabel }: any) {
  if (!active || !payload || !payload.length) return null
  const tick = payload[0]?.payload
  if (!tick) return null

  const sp = tick.spot_price ?? 0
  const fp = tick.flip_point ?? 0
  const cw = tick.call_wall ?? 0
  const pw = tick.put_wall ?? 0

  let zone = 'Unknown'
  let zoneColor = 'text-gray-400'
  if (sp > cw && cw > 0) { zone = 'Above Call Wall'; zoneColor = 'text-cyan-400' }
  else if (sp > fp && fp > 0) { zone = 'Positive Gamma Zone'; zoneColor = 'text-green-400' }
  else if (sp < pw && pw > 0) { zone = 'Below Put Wall'; zoneColor = 'text-purple-400' }
  else if (fp > 0) { zone = 'Negative Gamma Zone'; zoneColor = 'text-red-400' }

  const distFlip = fp > 0 ? ((sp - fp) / sp * 100).toFixed(2) : null
  const distCall = cw > 0 ? ((cw - sp) / sp * 100).toFixed(2) : null
  const distPut = pw > 0 ? ((sp - pw) / sp * 100).toFixed(2) : null

  return (
    <div className="bg-gray-900 border border-gray-600 rounded-lg p-3 shadow-xl text-xs min-w-[240px]">
      <div className="font-bold text-white text-sm mb-2">{tipLabel}</div>
      <div className="space-y-1">
        <TipRow label="Price" value={`$${sp.toFixed(2)}`} color="text-blue-400" bold />
        <TipRow label="Zone" value={zone} color={zoneColor} bold />
        <TipRow
          label="Net Gamma"
          value={formatGex(tick.net_gamma ?? 0, 2)}
          color={(tick.net_gamma ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}
          bold
        />

        <div className="border-t border-gray-700 pt-1 mt-1 space-y-1">
          {distFlip !== null && (
            <TipRow label="vs Flip" value={`${Number(distFlip) >= 0 ? '+' : ''}${distFlip}% ($${fp.toFixed(0)})`} color="text-yellow-400" />
          )}
          {distCall !== null && (
            <TipRow label="to Call Wall" value={`+${distCall}% ($${cw.toFixed(0)})`} color="text-cyan-400" />
          )}
          {distPut !== null && (
            <TipRow label="to Put Wall" value={`-${distPut}% ($${pw.toFixed(0)})`} color="text-purple-400" />
          )}
        </div>

        {tick.vix != null && (
          <div className="border-t border-gray-700 pt-1 mt-1">
            <TipRow label="VIX" value={tick.vix?.toFixed(2)} color="text-white" />
          </div>
        )}
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
      <p className="text-sm">Real-time data not available outside market hours (8:30am–4:15pm ET)</p>
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
