'use client'

import { useState, useMemo, useCallback } from 'react'
import useSWR from 'swr'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, ComposedChart, Bar
} from 'recharts'
import {
  TrendingUp, TrendingDown, AlertTriangle, Award, Trophy, Flame,
  Activity, Cpu, PauseCircle, X, Calendar, LucideIcon
} from 'lucide-react'
import { BOT_BRANDS, BotName } from '@/components/trader'

// Brand color lookup for chart theming
const getBrandColors = (botFilter?: string) => {
  if (botFilter === 'ARES') {
    return {
      primary: BOT_BRANDS.ARES.hexPrimary,  // Amber #F59E0B
      light: BOT_BRANDS.ARES.hexLight,       // Light amber
      dark: BOT_BRANDS.ARES.hexDark,         // Dark amber
    }
  }
  if (botFilter === 'ATHENA') {
    return {
      primary: BOT_BRANDS.ATHENA.hexPrimary, // Cyan #06B6D4
      light: BOT_BRANDS.ATHENA.hexLight,      // Light cyan
      dark: BOT_BRANDS.ATHENA.hexDark,        // Dark cyan
    }
  }
  if (botFilter === 'PEGASUS') {
    return {
      primary: BOT_BRANDS.PEGASUS.hexPrimary, // Blue #3B82F6
      light: BOT_BRANDS.PEGASUS.hexLight,      // Light blue
      dark: BOT_BRANDS.PEGASUS.hexDark,        // Dark blue
    }
  }
  // Default green/red for combined view
  return {
    primary: '#22C55E',
    light: '#4ADE80',
    dark: '#16A34A',
  }
}

// ============================================================================
// TYPES
// ============================================================================

interface EquityCurvePoint {
  date: string
  equity: number
  daily_pnl: number
  cumulative_pnl: number
  drawdown_pct: number
  trade_count: number
}

interface TradingEvent {
  date: string
  type: string
  severity: string
  title: string
  description: string
  value: number | null
  bot: string | null
}

interface EquityCurveSummary {
  total_pnl: number
  final_equity: number
  max_drawdown_pct: number
  total_trades: number
  starting_capital: number
}

interface EquityCurveData {
  success: boolean
  timeframe: string
  equity_curve: EquityCurvePoint[]
  events: TradingEvent[]
  summary: EquityCurveSummary
}

interface EquityCurveChartProps {
  botFilter?: string  // 'ARES', 'ATHENA', or undefined for all
  defaultTimeframe?: 'daily' | 'weekly' | 'monthly'
  defaultDays?: number
  height?: number
  showDrawdown?: boolean
  title?: string
}

// ============================================================================
// API FETCHER
// ============================================================================

const fetcher = async (url: string) => {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || ''
  const res = await fetch(`${baseUrl}${url}`)
  if (!res.ok) throw new Error('Failed to fetch')
  return res.json()
}

// ============================================================================
// EVENT ICONS & COLORS
// ============================================================================

const eventConfig: Record<string, { icon: LucideIcon; color: string; bgColor: string }> = {
  new_high: { icon: Trophy, color: 'text-green-400', bgColor: 'bg-green-500' },
  winning_streak: { icon: Flame, color: 'text-green-400', bgColor: 'bg-green-500' },
  losing_streak: { icon: AlertTriangle, color: 'text-red-400', bgColor: 'bg-red-500' },
  drawdown: { icon: TrendingDown, color: 'text-red-400', bgColor: 'bg-red-500' },
  big_win: { icon: Award, color: 'text-green-400', bgColor: 'bg-green-500' },
  big_loss: { icon: TrendingDown, color: 'text-red-400', bgColor: 'bg-red-500' },
  model_change: { icon: Cpu, color: 'text-purple-400', bgColor: 'bg-purple-500' },
  vix_spike: { icon: Activity, color: 'text-blue-400', bgColor: 'bg-blue-500' },
  circuit_breaker: { icon: PauseCircle, color: 'text-yellow-400', bgColor: 'bg-yellow-500' }
}

// ============================================================================
// CUSTOM TOOLTIP
// ============================================================================

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload || !payload.length) return null

  const data = payload[0]?.payload as EquityCurvePoint
  if (!data) return null

  return (
    <div className="bg-gray-900/95 backdrop-blur-sm border border-gray-700 rounded-lg p-3 shadow-xl shadow-black/50">
      <p className="text-gray-400 text-xs mb-2 flex items-center gap-1">
        <Calendar className="w-3 h-3" />
        {data.date}
      </p>
      <p className="text-white font-bold text-lg">
        ${data.equity?.toLocaleString()}
      </p>
      {data.daily_pnl !== undefined && (
        <p className={`text-sm font-medium ${data.daily_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {data.daily_pnl >= 0 ? '+' : ''}${data.daily_pnl?.toLocaleString()} today
        </p>
      )}
      {data.drawdown_pct > 0 && (
        <p className="text-red-400 text-xs mt-1">
          Drawdown: -{data.drawdown_pct?.toFixed(1)}%
        </p>
      )}
      {data.trade_count > 0 && (
        <p className="text-gray-500 text-xs mt-1">
          {data.trade_count} trade{data.trade_count > 1 ? 's' : ''}
        </p>
      )}
    </div>
  )
}

// ============================================================================
// EVENT MARKER POPUP
// ============================================================================

function EventPopup({
  event,
  position,
  onClose
}: {
  event: TradingEvent
  position: { x: number; y: number }
  onClose: () => void
}) {
  const config = eventConfig[event.type] || eventConfig.new_high
  const Icon = config.icon

  return (
    <div
      className="fixed z-50 bg-gray-900/95 backdrop-blur-sm border border-gray-700 rounded-lg p-4 shadow-2xl shadow-black/50 min-w-[250px] animate-in fade-in slide-in-from-bottom-2 duration-200"
      style={{
        left: Math.min(position.x, window.innerWidth - 280),
        top: position.y + 10
      }}
    >
      <button
        onClick={onClose}
        className="absolute top-2 right-2 text-gray-500 hover:text-white transition-colors"
      >
        <X className="w-4 h-4" />
      </button>

      <div className="flex items-center gap-2 mb-3">
        <div className={`w-8 h-8 rounded-full ${config.bgColor}/20 flex items-center justify-center`}>
          <Icon className={`w-4 h-4 ${config.color}`} />
        </div>
        <div>
          <p className="font-bold text-white">{event.title}</p>
          <p className="text-xs text-gray-400">{event.date}</p>
        </div>
      </div>

      <p className="text-gray-300 text-sm">{event.description}</p>

      {event.bot && (
        <p className="text-xs text-gray-500 mt-2">
          Bot: <span className="text-purple-400">{event.bot}</span>
        </p>
      )}
    </div>
  )
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export default function EquityCurveChart({
  botFilter,
  defaultTimeframe = 'daily',
  defaultDays = 90,
  height = 400,
  showDrawdown = true,
  title = 'Equity Curve'
}: EquityCurveChartProps) {
  const [timeframe, setTimeframe] = useState<'daily' | 'weekly' | 'monthly'>(defaultTimeframe)
  const [days, setDays] = useState(defaultDays)
  const [selectedEvent, setSelectedEvent] = useState<{ event: TradingEvent; position: { x: number; y: number } } | null>(null)
  const [hoveredEventDate, setHoveredEventDate] = useState<string | null>(null)

  // Fetch data
  const { data, error, isLoading } = useSWR<EquityCurveData>(
    `/api/events/equity-curve?days=${days}&timeframe=${timeframe}${botFilter ? `&bot=${botFilter}` : ''}`,
    fetcher,
    { refreshInterval: 60000 }
  )

  // Process equity curve for gradient
  const processedData = useMemo(() => {
    if (!data?.equity_curve) return []

    return data.equity_curve.map((point, i, arr) => {
      const prevEquity = i > 0 ? arr[i - 1].equity : point.equity
      return {
        ...point,
        isRising: point.equity >= prevEquity
      }
    })
  }, [data?.equity_curve])

  // Get events for the visible date range
  const visibleEvents = useMemo(() => {
    if (!data?.events || !processedData.length) return []

    const dates = new Set(processedData.map(p => p.date))
    return data.events.filter(e => dates.has(e.date))
  }, [data?.events, processedData])

  // Handle event marker click
  const handleEventClick = useCallback((event: TradingEvent, e: React.MouseEvent) => {
    e.stopPropagation()
    setSelectedEvent({
      event,
      position: { x: e.clientX, y: e.clientY }
    })
  }, [])

  // Chart bounds
  const { minEquity, maxEquity, minDrawdown, maxDrawdown } = useMemo(() => {
    if (!processedData.length) return { minEquity: 0, maxEquity: 100000, minDrawdown: 0, maxDrawdown: 10 }

    const equities = processedData.map(p => p.equity)
    const drawdowns = processedData.map(p => p.drawdown_pct)

    return {
      minEquity: Math.min(...equities) * 0.98,
      maxEquity: Math.max(...equities) * 1.02,
      minDrawdown: 0,
      maxDrawdown: Math.max(...drawdowns, 5) * 1.2
    }
  }, [processedData])

  // Render event markers
  const renderEventMarkers = () => {
    if (!processedData.length) return null

    return visibleEvents.map((event, i) => {
      const point = processedData.find(p => p.date === event.date)
      if (!point) return null

      const config = eventConfig[event.type] || eventConfig.new_high
      const Icon = config.icon
      const isHovered = hoveredEventDate === event.date

      // Calculate position based on chart (guard against single data point)
      const dataLength = processedData.length > 1 ? processedData.length - 1 : 1
      const xPercent = (processedData.findIndex(p => p.date === event.date) / dataLength) * 100

      return (
        <div
          key={`event-${i}-${event.date}`}
          className="absolute cursor-pointer transition-transform duration-200 hover:scale-125"
          style={{
            left: `${xPercent}%`,
            top: '10px',
            transform: 'translateX(-50%)'
          }}
          onClick={(e) => handleEventClick(event, e)}
          onMouseEnter={() => setHoveredEventDate(event.date)}
          onMouseLeave={() => setHoveredEventDate(null)}
        >
          <div
            className={`w-6 h-6 rounded-full ${config.bgColor}/30 border-2 border-current ${config.color} flex items-center justify-center shadow-lg ${isHovered ? 'ring-2 ring-white/30' : ''}`}
            style={{
              boxShadow: isHovered ? `0 0 20px ${config.bgColor.replace('bg-', '')}` : undefined
            }}
          >
            <Icon className="w-3 h-3" />
          </div>
          {isHovered && (
            <div className="absolute top-8 left-1/2 -translate-x-1/2 whitespace-nowrap bg-gray-900 text-white text-xs px-2 py-1 rounded shadow-lg">
              {event.title}
            </div>
          )}
        </div>
      )
    })
  }

  if (error) {
    const brandColors = getBrandColors(botFilter)
    return (
      <div className={`bg-[#0a0a0a] border rounded-lg p-6 ${
        botFilter === 'ARES' ? 'border-amber-700/50' :
        botFilter === 'ATHENA' ? 'border-cyan-700/50' :
        botFilter === 'PEGASUS' ? 'border-blue-700/50' :
        'border-gray-800'
      }`}>
        <div className="text-center py-8">
          <div className={`w-16 h-16 mx-auto mb-4 rounded-full flex items-center justify-center ${
            botFilter === 'ARES' ? 'bg-amber-900/30' :
            botFilter === 'ATHENA' ? 'bg-cyan-900/30' :
            botFilter === 'PEGASUS' ? 'bg-blue-900/30' :
            'bg-gray-800/50'
          }`}>
            <TrendingUp className={`w-8 h-8 ${
              botFilter === 'ARES' ? 'text-amber-400' :
              botFilter === 'ATHENA' ? 'text-cyan-400' :
              botFilter === 'PEGASUS' ? 'text-blue-400' :
              'text-gray-400'
            }`} />
          </div>
          <p className={`font-medium mb-2 ${
            botFilter === 'ARES' ? 'text-amber-400' :
            botFilter === 'ATHENA' ? 'text-cyan-400' :
            botFilter === 'PEGASUS' ? 'text-blue-400' :
            'text-gray-300'
          }`}>No Equity Data Available</p>
          <p className="text-gray-500 text-sm">
            {botFilter ? `${botFilter} hasn't completed any trades yet.` : 'No trading history found.'}
          </p>
          <p className="text-gray-600 text-xs mt-2">
            Data will appear once trades are executed and closed.
          </p>
        </div>
      </div>
    )
  }

  if (isLoading || !data) {
    return (
      <div className={`bg-[#0a0a0a] border rounded-lg p-6 ${
        botFilter === 'ARES' ? 'border-amber-700/50' :
        botFilter === 'ATHENA' ? 'border-cyan-700/50' :
        botFilter === 'PEGASUS' ? 'border-blue-700/50' :
        'border-gray-800'
      }`}>
        <div className="animate-pulse space-y-4">
          <div className={`h-6 rounded w-1/3 ${
            botFilter === 'ARES' ? 'bg-amber-900/30' :
            botFilter === 'ATHENA' ? 'bg-cyan-900/30' :
            botFilter === 'PEGASUS' ? 'bg-blue-900/30' :
            'bg-gray-800'
          }`} />
          <div className={`h-64 rounded ${
            botFilter === 'ARES' ? 'bg-amber-900/20' :
            botFilter === 'ATHENA' ? 'bg-cyan-900/20' :
            botFilter === 'PEGASUS' ? 'bg-blue-900/20' :
            'bg-gray-800'
          }`} />
        </div>
      </div>
    )
  }

  const summary = data.summary

  return (
    <div className={`bg-[#0a0a0a] border rounded-lg overflow-hidden ${
      botFilter === 'ARES' ? 'border-amber-700/50' :
      botFilter === 'ATHENA' ? 'border-cyan-700/50' :
      botFilter === 'PEGASUS' ? 'border-blue-700/50' :
      'border-gray-800'
    }`}>
      {/* Header */}
      <div className="p-4 border-b border-gray-800">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <TrendingUp className={`w-5 h-5 ${botFilter === 'ARES' ? 'text-amber-400' : botFilter === 'ATHENA' ? 'text-cyan-400' : botFilter === 'PEGASUS' ? 'text-blue-400' : 'text-green-400'}`} />
            <h3 className="font-bold text-white">{title}</h3>
            {botFilter && (
              <span className={`px-2 py-0.5 text-xs rounded ${
                botFilter === 'ARES' ? 'bg-amber-500/20 text-amber-400' :
                botFilter === 'ATHENA' ? 'bg-cyan-500/20 text-cyan-400' :
                botFilter === 'PEGASUS' ? 'bg-blue-500/20 text-blue-400' :
                'bg-purple-500/20 text-purple-400'
              }`}>
                {botFilter}
              </span>
            )}
          </div>

          {/* Stats */}
          <div className="flex items-center gap-4 text-sm">
            <span className={summary.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
              {summary.total_pnl >= 0 ? '+' : ''}${summary.total_pnl?.toLocaleString() || 0}
            </span>
            <span className="text-red-400">
              -{summary.max_drawdown_pct?.toFixed(1) || 0}% DD
            </span>
            <span className="text-gray-400">
              {summary.total_trades || 0} trades
            </span>
          </div>

          {/* Timeframe Selector */}
          <div className="flex items-center gap-1 bg-gray-800 rounded-lg p-1">
            {(['daily', 'weekly', 'monthly'] as const).map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                  timeframe === tf
                    ? 'bg-purple-600 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-gray-700'
                }`}
              >
                {tf.charAt(0).toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Event Markers Row */}
      {visibleEvents.length > 0 && (
        <div className="relative h-10 border-b border-gray-800 bg-gray-900/50">
          {renderEventMarkers()}
        </div>
      )}

      {/* Main Chart */}
      <div className="p-4" style={{ height }}>
        {processedData.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={processedData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
              <defs>
                {/* Brand-colored gradient */}
                <linearGradient id={`equityGradient-${botFilter || 'default'}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={getBrandColors(botFilter).primary} stopOpacity={0.4} />
                  <stop offset="50%" stopColor={getBrandColors(botFilter).primary} stopOpacity={0.1} />
                  <stop offset="95%" stopColor={getBrandColors(botFilter).primary} stopOpacity={0} />
                </linearGradient>
                {/* Glow filter */}
                <filter id={`glow-${botFilter || 'default'}`}>
                  <feGaussianBlur stdDeviation="2" result="coloredBlur" />
                  <feMerge>
                    <feMergeNode in="coloredBlur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>

              <CartesianGrid strokeDasharray="3 3" stroke="#374151" strokeOpacity={0.5} />

              <XAxis
                dataKey="date"
                stroke="#6B7280"
                fontSize={10}
                tickFormatter={(date) => {
                  if (timeframe === 'daily') return date?.slice(5) || ''
                  if (timeframe === 'weekly') return date?.slice(5) || ''
                  return date?.slice(0, 7) || ''
                }}
                interval="preserveStartEnd"
                tickMargin={8}
              />

              <YAxis
                stroke="#6B7280"
                fontSize={11}
                tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                domain={[minEquity, maxEquity]}
                tickMargin={8}
              />

              <Tooltip content={<CustomTooltip />} />

              {/* Starting capital reference line */}
              <ReferenceLine
                y={summary.starting_capital}
                stroke="#6B7280"
                strokeDasharray="5 5"
                label={{
                  value: 'Start',
                  position: 'insideLeft',
                  fill: '#6B7280',
                  fontSize: 10
                }}
              />

              {/* Main equity area with brand colors */}
              <Area
                type="monotone"
                dataKey="equity"
                stroke={getBrandColors(botFilter).primary}
                strokeWidth={2}
                fill={`url(#equityGradient-${botFilter || 'default'})`}
                filter={`url(#glow-${botFilter || 'default'})`}
                animationDuration={1000}
                animationEasing="ease-out"
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className={`w-12 h-12 mx-auto mb-3 rounded-full flex items-center justify-center ${
                botFilter === 'ARES' ? 'bg-amber-900/30' :
                botFilter === 'ATHENA' ? 'bg-cyan-900/30' :
                botFilter === 'PEGASUS' ? 'bg-blue-900/30' :
                'bg-gray-800/50'
              }`}>
                <TrendingUp className={`w-6 h-6 ${
                  botFilter === 'ARES' ? 'text-amber-400/70' :
                  botFilter === 'ATHENA' ? 'text-cyan-400/70' :
                  botFilter === 'PEGASUS' ? 'text-blue-400/70' :
                  'text-gray-500'
                }`} />
              </div>
              <p className="text-gray-500 text-sm">No equity data available</p>
              <p className="text-gray-600 text-xs mt-1">
                Chart will populate once trades are closed
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Drawdown Chart */}
      {showDrawdown && processedData.length > 0 && (
        <div className="border-t border-gray-800">
          <div className="px-4 py-2 flex items-center gap-2 text-xs text-gray-400">
            <TrendingDown className="w-3 h-3 text-red-400" />
            <span>Drawdown</span>
          </div>
          <div className="px-4 pb-4" style={{ height: 100 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={processedData} margin={{ top: 0, right: 20, left: 10, bottom: 0 }}>
                <defs>
                  <linearGradient id="drawdownGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#EF4444" stopOpacity={0.5} />
                    <stop offset="95%" stopColor="#EF4444" stopOpacity={0} />
                  </linearGradient>
                </defs>

                <XAxis dataKey="date" hide />
                <YAxis
                  stroke="#6B7280"
                  fontSize={10}
                  tickFormatter={(v) => `-${v.toFixed(0)}%`}
                  domain={[0, maxDrawdown]}
                  reversed
                  tickMargin={8}
                  width={40}
                />

                <Area
                  type="monotone"
                  dataKey="drawdown_pct"
                  stroke="#EF4444"
                  strokeWidth={1}
                  fill="url(#drawdownGradient)"
                  animationDuration={1000}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Event Legend */}
      {visibleEvents.length > 0 && (
        <div className="px-4 pb-4 flex flex-wrap gap-2">
          {Object.entries(
            visibleEvents.reduce((acc, e) => {
              acc[e.type] = (acc[e.type] || 0) + 1
              return acc
            }, {} as Record<string, number>)
          ).map(([type, count]) => {
            const config = eventConfig[type] || eventConfig.new_high
            const Icon = config.icon
            return (
              <span
                key={type}
                className={`flex items-center gap-1 px-2 py-1 rounded text-xs ${config.bgColor}/10 ${config.color}`}
              >
                <Icon className="w-3 h-3" />
                {type.replace(/_/g, ' ')} ({count})
              </span>
            )
          })}
        </div>
      )}

      {/* Event Popup */}
      {selectedEvent && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setSelectedEvent(null)}
          />
          <EventPopup
            event={selectedEvent.event}
            position={selectedEvent.position}
            onClose={() => setSelectedEvent(null)}
          />
        </>
      )}
    </div>
  )
}
