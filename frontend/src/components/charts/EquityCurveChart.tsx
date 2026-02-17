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
  if (botFilter === 'FORTRESS') {
    return {
      primary: BOT_BRANDS.FORTRESS.hexPrimary,  // Amber #F59E0B
      light: BOT_BRANDS.FORTRESS.hexLight,       // Light amber
      dark: BOT_BRANDS.FORTRESS.hexDark,         // Dark amber
    }
  }
  if (botFilter === 'SOLOMON') {
    return {
      primary: BOT_BRANDS.SOLOMON.hexPrimary, // Cyan #06B6D4
      light: BOT_BRANDS.SOLOMON.hexLight,      // Light cyan
      dark: BOT_BRANDS.SOLOMON.hexDark,        // Dark cyan
    }
  }
  if (botFilter === 'ANCHOR') {
    return {
      primary: BOT_BRANDS.ANCHOR.hexPrimary, // Blue #3B82F6
      light: BOT_BRANDS.ANCHOR.hexLight,      // Light blue
      dark: BOT_BRANDS.ANCHOR.hexDark,        // Dark blue
    }
  }
  if (botFilter === 'GIDEON') {
    return {
      primary: BOT_BRANDS.GIDEON.hexPrimary, // Orange #F97316
      light: BOT_BRANDS.GIDEON.hexLight,      // Light orange
      dark: BOT_BRANDS.GIDEON.hexDark,        // Dark orange
    }
  }
  if (botFilter === 'SAMSON') {
    return {
      primary: BOT_BRANDS.SAMSON.hexPrimary, // Violet #8B5CF6
      light: BOT_BRANDS.SAMSON.hexLight,      // Light violet
      dark: BOT_BRANDS.SAMSON.hexDark,        // Dark violet
    }
  }
  if (botFilter === 'AGAPE') {
    return {
      primary: BOT_BRANDS.AGAPE.hexPrimary, // Fuchsia #D946EF
      light: BOT_BRANDS.AGAPE.hexLight,      // Light fuchsia
      dark: BOT_BRANDS.AGAPE.hexDark,        // Dark fuchsia
    }
  }
  if (botFilter === 'FAITH') {
    return {
      primary: BOT_BRANDS.FAITH.hexPrimary, // Sky #0EA5E9
      light: BOT_BRANDS.FAITH.hexLight,      // Light sky
      dark: BOT_BRANDS.FAITH.hexDark,        // Dark sky
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
  day_realized?: number    // Only present in intraday view
  day_unrealized?: number  // Only present in intraday view
}

interface EquityCurveData {
  success: boolean
  timeframe: string
  equity_curve: EquityCurvePoint[]
  events: TradingEvent[]
  summary: EquityCurveSummary
}

interface IntradayEquityPoint {
  timestamp: string
  time: string
  equity: number
  cumulative_pnl: number
  open_positions: number
  unrealized_pnl: number
}

interface IntradayEquityData {
  success: boolean
  date: string
  bot?: string
  data_points: IntradayEquityPoint[]
  current_equity: number
  day_pnl: number
  day_realized: number
  day_unrealized: number
  starting_equity: number
  high_of_day: number
  low_of_day: number
  snapshots_count: number
  today_closed_count?: number  // Number of trades closed today
  open_positions_count?: number  // Number of currently open positions
}

interface EquityCurveChartProps {
  botFilter?: string  // 'FORTRESS', 'SOLOMON', or undefined for all
  defaultTimeframe?: 'daily' | 'weekly' | 'monthly'
  defaultDays?: number
  height?: number
  showDrawdown?: boolean
  title?: string
  showIntradayOption?: boolean  // Whether to show intraday toggle
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
          {data.daily_pnl >= 0 ? '+' : ''}${data.daily_pnl?.toLocaleString()} {data.trade_count === 1 ? 'trade' : 'day'}
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
  title = 'Equity Curve',
  showIntradayOption = true
}: EquityCurveChartProps) {
  // Default to intraday when botFilter is set (bot-specific pages), historical otherwise
  const [viewMode, setViewMode] = useState<'historical' | 'intraday'>(botFilter ? 'intraday' : 'historical')
  const [timeframe, setTimeframe] = useState<'daily' | 'weekly' | 'monthly'>(defaultTimeframe)
  const [days, setDays] = useState(defaultDays)
  const [selectedEvent, setSelectedEvent] = useState<{ event: TradingEvent; position: { x: number; y: number } } | null>(null)
  const [hoveredEventDate, setHoveredEventDate] = useState<string | null>(null)

  // Fetch historical data
  // UNIFIED: Use unified metrics endpoint when bot-specific, falls back to events endpoint for combined view
  const historicalEndpoint = botFilter
    ? `/api/metrics/${botFilter}/equity-curve?days=${days}`  // UNIFIED endpoint with consistent capital
    : `/api/events/equity-curve?days=${days}&timeframe=${timeframe}`  // Legacy endpoint for combined view
  const { data, error, isLoading } = useSWR<EquityCurveData>(
    viewMode === 'historical' ? historicalEndpoint : null,
    fetcher,
    { refreshInterval: 30000 }  // Refresh every 30 seconds for more responsive updates
  )

  // Fetch intraday data (only when botFilter is set and viewMode is intraday)
  // Use bot-specific endpoints which have LIVE mark-to-market calculation
  // Bot routes calculate unrealized P&L using real option pricing, not stale snapshots
  const intradayEndpoint = botFilter ? `/api/${botFilter.toLowerCase()}/equity-curve/intraday` : null
  const { data: intradayData, error: intradayError, isLoading: intradayLoading } = useSWR<IntradayEquityData>(
    viewMode === 'intraday' && intradayEndpoint ? intradayEndpoint : null,
    fetcher,
    { refreshInterval: 30000 }  // Refresh every 30 seconds for more responsive updates
  )

  // Helper: Get week key from date string (YYYY-WW format)
  const getWeekKey = (dateStr: string): string => {
    const d = new Date(dateStr)
    const startOfYear = new Date(d.getFullYear(), 0, 1)
    const days = Math.floor((d.getTime() - startOfYear.getTime()) / (24 * 60 * 60 * 1000))
    const weekNum = Math.ceil((days + startOfYear.getDay() + 1) / 7)
    return `${d.getFullYear()}-W${weekNum.toString().padStart(2, '0')}`
  }

  // Helper: Get month key from date string (YYYY-MM format)
  const getMonthKey = (dateStr: string): string => {
    return dateStr.slice(0, 7) // YYYY-MM
  }

  // Helper: Get week start date for display (e.g., "Jan 6")
  const getWeekLabel = (dateStr: string): string => {
    const d = new Date(dateStr)
    const dayOfWeek = d.getDay()
    const diff = d.getDate() - dayOfWeek + (dayOfWeek === 0 ? -6 : 1) // Monday start
    const monday = new Date(d.setDate(diff))
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    return `${months[monday.getMonth()]} ${monday.getDate()}`
  }

  // Helper: Get month label for display (e.g., "Jan")
  const getMonthLabel = (dateStr: string): string => {
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    const monthIndex = parseInt(dateStr.slice(5, 7), 10) - 1
    return months[monthIndex] || dateStr.slice(5, 7)
  }

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

  // Aggregate data by timeframe (weekly/monthly)
  const aggregatedData = useMemo(() => {
    if (!processedData.length) return []

    // Daily: return as-is (but dedupe by date, taking last point per day)
    if (timeframe === 'daily') {
      const byDate = new Map<string, typeof processedData[0]>()
      processedData.forEach(point => {
        const dateKey = point.date?.slice(0, 10) || ''
        byDate.set(dateKey, point) // Last point for each date wins
      })
      return Array.from(byDate.values()).map(point => ({
        ...point,
        displayDate: point.date?.slice(5, 10) || '' // MM-DD
      }))
    }

    // Weekly: aggregate by week
    if (timeframe === 'weekly') {
      const byWeek = new Map<string, typeof processedData[0]>()
      processedData.forEach(point => {
        const weekKey = getWeekKey(point.date || '')
        byWeek.set(weekKey, point) // Last point for each week wins
      })
      return Array.from(byWeek.entries()).map(([weekKey, point]) => ({
        ...point,
        displayDate: getWeekLabel(point.date || '')
      }))
    }

    // Monthly: aggregate by month
    if (timeframe === 'monthly') {
      const byMonth = new Map<string, typeof processedData[0]>()
      processedData.forEach(point => {
        const monthKey = getMonthKey(point.date || '')
        byMonth.set(monthKey, point) // Last point for each month wins
      })
      return Array.from(byMonth.entries()).map(([monthKey, point]) => ({
        ...point,
        displayDate: getMonthLabel(monthKey)
      }))
    }

    return processedData
  }, [processedData, timeframe])

  // Process intraday data
  const processedIntradayData = useMemo(() => {
    if (!intradayData?.data_points) return []

    return intradayData.data_points.map((point, i, arr) => {
      const prevEquity = i > 0 ? arr[i - 1].equity : point.equity
      return {
        ...point,
        isRising: point.equity >= prevEquity,
        date: point.time, // For tooltip compatibility
        daily_pnl: point.cumulative_pnl,
        drawdown_pct: 0,
        trade_count: point.open_positions
      }
    })
  }, [intradayData?.data_points])

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

  // Chart bounds (handles both historical and intraday)
  const { minEquity, maxEquity, minDrawdown, maxDrawdown } = useMemo(() => {
    const dataToUse = viewMode === 'intraday' ? processedIntradayData : aggregatedData
    // Use bot-appropriate starting capital for empty chart bounds
    const defaultCapital = (botFilter === 'SAMSON' || botFilter === 'ANCHOR') ? 200000 : 100000
    if (!dataToUse.length) return { minEquity: 0, maxEquity: defaultCapital, minDrawdown: 0, maxDrawdown: 10 }

    const equities = dataToUse.map(p => p.equity)
    const drawdowns = viewMode === 'intraday' ? [0] : aggregatedData.map(p => p.drawdown_pct)

    return {
      minEquity: Math.min(...equities) * 0.98,
      maxEquity: Math.max(...equities) * 1.02,
      minDrawdown: 0,
      maxDrawdown: Math.max(...drawdowns, 5) * 1.2
    }
  }, [aggregatedData, processedIntradayData, viewMode, botFilter])

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

  // Handle error state
  const hasError = viewMode === 'intraday' ? intradayError : error
  const isCurrentlyLoading = viewMode === 'intraday' ? intradayLoading : isLoading
  const currentData = viewMode === 'intraday' ? processedIntradayData : processedData

  if (hasError) {
    const brandColors = getBrandColors(botFilter)
    return (
      <div className={`bg-[#0a0a0a] border rounded-lg p-6 ${
        botFilter === 'FORTRESS' ? 'border-amber-700/50' :
        botFilter === 'SOLOMON' ? 'border-cyan-700/50' :
        botFilter === 'ANCHOR' ? 'border-blue-700/50' :
        botFilter === 'SAMSON' ? 'border-violet-700/50' :
        botFilter === 'GIDEON' ? 'border-orange-700/50' :
        botFilter === 'FAITH' ? 'border-sky-700/50' :
        'border-gray-800'
      }`}>
        <div className="text-center py-8">
          <div className={`w-16 h-16 mx-auto mb-4 rounded-full flex items-center justify-center ${
            botFilter === 'FORTRESS' ? 'bg-amber-900/30' :
            botFilter === 'SOLOMON' ? 'bg-cyan-900/30' :
            botFilter === 'ANCHOR' ? 'bg-blue-900/30' :
            botFilter === 'SAMSON' ? 'bg-violet-900/30' :
            botFilter === 'GIDEON' ? 'bg-orange-900/30' :
            botFilter === 'FAITH' ? 'bg-sky-900/30' :
            'bg-gray-800/50'
          }`}>
            <TrendingUp className={`w-8 h-8 ${
              botFilter === 'FORTRESS' ? 'text-amber-400' :
              botFilter === 'SOLOMON' ? 'text-cyan-400' :
              botFilter === 'ANCHOR' ? 'text-blue-400' :
              botFilter === 'SAMSON' ? 'text-violet-400' :
              botFilter === 'GIDEON' ? 'text-orange-400' :
              botFilter === 'FAITH' ? 'text-sky-400' :
              'text-gray-400'
            }`} />
          </div>
          <p className={`font-medium mb-2 ${
            botFilter === 'FORTRESS' ? 'text-amber-400' :
            botFilter === 'SOLOMON' ? 'text-cyan-400' :
            botFilter === 'ANCHOR' ? 'text-blue-400' :
            botFilter === 'SAMSON' ? 'text-violet-400' :
            botFilter === 'GIDEON' ? 'text-orange-400' :
            botFilter === 'FAITH' ? 'text-sky-400' :
            'text-gray-300'
          }`}>No Equity Data Available</p>
          <p className="text-gray-500 text-sm">
            {viewMode === 'intraday'
              ? `No intraday snapshots recorded yet today.`
              : (botFilter ? `${botFilter} hasn't completed any trades yet.` : 'No trading history found.')
            }
          </p>
          <p className="text-gray-600 text-xs mt-2">
            {viewMode === 'intraday'
              ? 'Intraday data is captured every 5 minutes during market hours.'
              : 'Data will appear once trades are executed and closed.'
            }
          </p>
          {viewMode === 'intraday' && (
            <button
              onClick={() => setViewMode('historical')}
              className="mt-4 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm rounded-lg transition-colors"
            >
              View Historical Data
            </button>
          )}
        </div>
      </div>
    )
  }

  const shouldShowLoading = viewMode === 'intraday'
    ? (intradayLoading || !intradayData)
    : (isLoading || !data)

  if (shouldShowLoading) {
    return (
      <div className={`bg-[#0a0a0a] border rounded-lg p-6 ${
        botFilter === 'FORTRESS' ? 'border-amber-700/50' :
        botFilter === 'SOLOMON' ? 'border-cyan-700/50' :
        botFilter === 'ANCHOR' ? 'border-blue-700/50' :
        botFilter === 'SAMSON' ? 'border-violet-700/50' :
        botFilter === 'GIDEON' ? 'border-orange-700/50' :
        botFilter === 'FAITH' ? 'border-sky-700/50' :
        'border-gray-800'
      }`}>
        <div className="animate-pulse space-y-4">
          <div className={`h-6 rounded w-1/3 ${
            botFilter === 'FORTRESS' ? 'bg-amber-900/30' :
            botFilter === 'SOLOMON' ? 'bg-cyan-900/30' :
            botFilter === 'ANCHOR' ? 'bg-blue-900/30' :
            botFilter === 'SAMSON' ? 'bg-violet-900/30' :
            botFilter === 'GIDEON' ? 'bg-orange-900/30' :
            botFilter === 'FAITH' ? 'bg-sky-900/30' :
            'bg-gray-800'
          }`} />
          <div className={`h-64 rounded ${
            botFilter === 'FORTRESS' ? 'bg-amber-900/20' :
            botFilter === 'SOLOMON' ? 'bg-cyan-900/20' :
            botFilter === 'ANCHOR' ? 'bg-blue-900/20' :
            botFilter === 'SAMSON' ? 'bg-violet-900/20' :
            botFilter === 'GIDEON' ? 'bg-orange-900/20' :
            botFilter === 'FAITH' ? 'bg-sky-900/20' :
            'bg-gray-800'
          }`} />
        </div>
      </div>
    )
  }

  // Get default starting capital based on bot type
  // SPX bots (SAMSON, ANCHOR) use $200k, SPY bots (FORTRESS, SOLOMON, GIDEON) use $100k
  const defaultStartingCapital = (botFilter === 'SAMSON' || botFilter === 'ANCHOR') ? 200000 : 100000

  // Get summary based on view mode
  const summary = viewMode === 'intraday' && intradayData
    ? {
        total_pnl: intradayData.day_pnl,
        day_realized: intradayData.day_realized ?? 0,
        day_unrealized: intradayData.day_unrealized ?? 0,
        final_equity: intradayData.current_equity,
        max_drawdown_pct: 0,
        total_trades: intradayData.snapshots_count,
        starting_capital: intradayData.starting_equity
      }
    : data?.summary || { total_pnl: 0, final_equity: 0, max_drawdown_pct: 0, total_trades: 0, starting_capital: defaultStartingCapital }

  return (
    <div className={`bg-[#0a0a0a] border rounded-lg overflow-hidden ${
      botFilter === 'FORTRESS' ? 'border-amber-700/50' :
      botFilter === 'SOLOMON' ? 'border-cyan-700/50' :
      botFilter === 'ANCHOR' ? 'border-blue-700/50' :
      botFilter === 'SAMSON' ? 'border-violet-700/50' :
      botFilter === 'GIDEON' ? 'border-orange-700/50' :
      botFilter === 'FAITH' ? 'border-sky-700/50' :
      'border-gray-800'
    }`}>
      {/* Header */}
      <div className="p-4 border-b border-gray-800">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <TrendingUp className={`w-5 h-5 ${botFilter === 'FORTRESS' ? 'text-amber-400' : botFilter === 'SOLOMON' ? 'text-cyan-400' : botFilter === 'ANCHOR' ? 'text-blue-400' : botFilter === 'SAMSON' ? 'text-violet-400' : botFilter === 'GIDEON' ? 'text-orange-400' : botFilter === 'FAITH' ? 'text-sky-400' : 'text-green-400'}`} />
            <h3 className="font-bold text-white">{title}</h3>
            {botFilter && (
              <span className={`px-2 py-0.5 text-xs rounded ${
                botFilter === 'FORTRESS' ? 'bg-amber-500/20 text-amber-400' :
                botFilter === 'SOLOMON' ? 'bg-cyan-500/20 text-cyan-400' :
                botFilter === 'ANCHOR' ? 'bg-blue-500/20 text-blue-400' :
                botFilter === 'SAMSON' ? 'bg-violet-500/20 text-violet-400' :
                botFilter === 'GIDEON' ? 'bg-orange-500/20 text-orange-400' :
                botFilter === 'FAITH' ? 'bg-sky-500/20 text-sky-400' :
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
            {/* Show realized/unrealized breakdown for intraday view */}
            {viewMode === 'intraday' && intradayData && (
              <span className="text-gray-400 text-xs">
                (<span className={(summary.day_realized ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}>
                  {(summary.day_realized ?? 0) >= 0 ? '+' : ''}${(summary.day_realized ?? 0).toLocaleString()}
                </span>
                {' '}realized,{' '}
                <span className={(summary.day_unrealized ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}>
                  {(summary.day_unrealized ?? 0) >= 0 ? '+' : ''}${(summary.day_unrealized ?? 0).toLocaleString()}
                </span>
                {' '}unrealized)
              </span>
            )}
            {viewMode === 'historical' && (
              <span className="text-red-400">
                -{summary.max_drawdown_pct?.toFixed(1) || 0}% DD
              </span>
            )}
            <span className="text-gray-400">
              {viewMode === 'intraday'
                ? `${summary.total_trades || 0} snapshots`
                : `${summary.total_trades || 0} trades`
              }
            </span>
          </div>

          {/* View Mode Toggle + Timeframe Selector */}
          <div className="flex items-center gap-2">
            {/* Historical / Intraday Toggle */}
            {showIntradayOption && botFilter && (
              <div className="flex items-center gap-1 bg-gray-800 rounded-lg p-1">
                <button
                  onClick={() => setViewMode('historical')}
                  className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                    viewMode === 'historical'
                      ? 'bg-purple-600 text-white'
                      : 'text-gray-400 hover:text-white hover:bg-gray-700'
                  }`}
                >
                  Historical
                </button>
                <button
                  onClick={() => setViewMode('intraday')}
                  className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                    viewMode === 'intraday'
                      ? 'bg-green-600 text-white'
                      : 'text-gray-400 hover:text-white hover:bg-gray-700'
                  }`}
                >
                  Intraday
                </button>
              </div>
            )}

            {/* Timeframe Selector (only for historical view) */}
            {viewMode === 'historical' && (
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
            )}

            {/* Intraday date indicator */}
            {viewMode === 'intraday' && intradayData?.date && (
              <span className="text-xs text-gray-400 flex items-center gap-1">
                <Calendar className="w-3 h-3" />
                {intradayData.date}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Event Markers Row (historical only) */}
      {viewMode === 'historical' && visibleEvents.length > 0 && (
        <div className="relative h-10 border-b border-gray-800 bg-gray-900/50">
          {renderEventMarkers()}
        </div>
      )}

      {/* Intraday P&L Breakdown Panel - Shows CLEAR distinction between realized and unrealized */}
      {viewMode === 'intraday' && intradayData && (() => {
        // Use backend-provided counts (preferred) or fall back to last data point
        const lastDataPoint = intradayData.data_points?.[intradayData.data_points.length - 1]
        const openPositionsCount = intradayData.open_positions_count ?? lastDataPoint?.open_positions ?? 0
        const closedTradesCount = intradayData.today_closed_count ?? 0
        const dayRealized = intradayData.day_realized ?? 0
        const dayUnrealized = intradayData.day_unrealized ?? 0
        const hasClosedTrades = closedTradesCount > 0 || dayRealized !== 0
        const hasOpenPositions = openPositionsCount > 0

        return (
        <div className="px-4 py-3 border-b border-gray-800 bg-gray-900/50">
          {/* P&L Breakdown Cards */}
          <div className="grid grid-cols-2 gap-3 mb-3">
            {/* Realized P&L - Closed Trades */}
            <div className={`rounded-lg p-3 border ${
              !hasClosedTrades
                ? 'bg-gray-500/10 border-gray-500/30'
                : dayRealized >= 0
                  ? 'bg-green-500/10 border-green-500/30'
                  : 'bg-red-500/10 border-red-500/30'
            }`}>
              <div className="flex items-center gap-2 mb-1">
                <div className={`w-2 h-2 rounded-full ${
                  !hasClosedTrades
                    ? 'bg-gray-400'
                    : dayRealized >= 0 ? 'bg-green-400' : 'bg-red-400'
                }`} />
                <span className="text-xs text-gray-400 font-medium uppercase tracking-wide">
                  Realized P&L
                </span>
                <span className={`text-xs px-1.5 py-0.5 rounded border ${
                  hasClosedTrades
                    ? 'bg-gray-800 text-gray-300 border-gray-700'
                    : 'bg-gray-800 text-gray-500 border-gray-700'
                }`}>
                  {hasClosedTrades
                    ? `${closedTradesCount} Trade${closedTradesCount !== 1 ? 's' : ''} Closed Today`
                    : 'No Trades Closed'}
                </span>
              </div>
              <div className={`text-xl font-bold ${
                !hasClosedTrades
                  ? 'text-gray-400'
                  : dayRealized >= 0 ? 'text-green-400' : 'text-red-400'
              }`}>
                {!hasClosedTrades
                  ? '$0'
                  : `${dayRealized >= 0 ? '+' : ''}$${dayRealized.toLocaleString()}`}
              </div>
              <p className="text-xs text-gray-500 mt-1">
                {!hasClosedTrades
                  ? '— No trades closed today yet'
                  : dayRealized >= 0
                    ? `✓ Profit${closedTradesCount !== 1 ? 's' : ''} locked in from ${closedTradesCount} closed trade${closedTradesCount !== 1 ? 's' : ''}`
                    : `✗ Loss${closedTradesCount !== 1 ? 'es' : ''} realized from ${closedTradesCount} closed trade${closedTradesCount !== 1 ? 's' : ''}`}
              </p>
            </div>

            {/* Unrealized P&L - Open Positions */}
            <div className={`rounded-lg p-3 border ${
              !hasOpenPositions
                ? 'bg-gray-500/10 border-gray-500/30'
                : dayUnrealized >= 0
                  ? 'bg-green-500/10 border-green-500/30'
                  : 'bg-red-500/10 border-red-500/30'
            }`}>
              <div className="flex items-center gap-2 mb-1">
                <div className={`w-2 h-2 rounded-full ${
                  !hasOpenPositions
                    ? 'bg-gray-400'
                    : dayUnrealized >= 0 ? 'bg-green-400 animate-pulse' : 'bg-red-400 animate-pulse'
                }`} />
                <span className="text-xs text-gray-400 font-medium uppercase tracking-wide">
                  Unrealized P&L
                </span>
                <span className={`text-xs px-1.5 py-0.5 rounded border ${
                  hasOpenPositions
                    ? 'bg-blue-500/20 text-blue-400 border-blue-500/30'
                    : 'bg-gray-800 text-gray-400 border-gray-700'
                }`}>
                  {hasOpenPositions
                    ? `${openPositionsCount} Open Position${openPositionsCount > 1 ? 's' : ''}`
                    : 'No Open Positions'}
                </span>
              </div>
              <div className={`text-xl font-bold ${
                !hasOpenPositions
                  ? 'text-gray-400'
                  : dayUnrealized >= 0 ? 'text-green-400' : 'text-red-400'
              }`}>
                {!hasOpenPositions
                  ? '$0'
                  : `${dayUnrealized >= 0 ? '+' : ''}$${dayUnrealized.toLocaleString()}`}
              </div>
              <p className="text-xs text-gray-500 mt-1">
                {!hasOpenPositions
                  ? '— No open positions currently'
                  : dayUnrealized >= 0
                    ? `↑ Open position${openPositionsCount > 1 ? 's are' : ' is'} profitable`
                    : `↓ Open position${openPositionsCount > 1 ? 's are' : ' is'} underwater`}
              </p>
            </div>
          </div>

          {/* Explanation Banner - Shows when realized positive but unrealized negative */}
          {(intradayData.day_realized ?? 0) > 0 && (intradayData.day_unrealized ?? 0) < 0 && (
            <div className="mb-3 p-2 rounded-lg bg-blue-500/10 border border-blue-500/30">
              <p className="text-xs text-blue-300">
                <span className="font-semibold">Why is the curve going up?</span> You've locked in{' '}
                <span className="text-green-400 font-bold">+${(intradayData.day_realized ?? 0).toLocaleString()}</span>{' '}
                from closed trades today. The open position is{' '}
                <span className="text-red-400 font-bold">${(intradayData.day_unrealized ?? 0).toLocaleString()}</span>{' '}
                underwater, but that hasn't erased your realized gains. Net P&L:{' '}
                <span className={`font-bold ${(intradayData.day_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {(intradayData.day_pnl ?? 0) >= 0 ? '+' : ''}${(intradayData.day_pnl ?? 0).toLocaleString()}
                </span>
              </p>
            </div>
          )}

          {/* Explanation Banner - Shows when realized negative but unrealized positive */}
          {(intradayData.day_realized ?? 0) < 0 && (intradayData.day_unrealized ?? 0) > 0 && (
            <div className="mb-3 p-2 rounded-lg bg-yellow-500/10 border border-yellow-500/30">
              <p className="text-xs text-yellow-300">
                <span className="font-semibold">P&L Breakdown:</span> Closed trades show{' '}
                <span className="text-red-400 font-bold">${(intradayData.day_realized ?? 0).toLocaleString()}</span>{' '}
                in realized losses. However, your open position is currently{' '}
                <span className="text-green-400 font-bold">+${(intradayData.day_unrealized ?? 0).toLocaleString()}</span>{' '}
                in profit (unrealized). Net P&L:{' '}
                <span className={`font-bold ${(intradayData.day_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {(intradayData.day_pnl ?? 0) >= 0 ? '+' : ''}${(intradayData.day_pnl ?? 0).toLocaleString()}
                </span>
              </p>
            </div>
          )}

          {/* High/Low/Current Stats Row */}
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-4">
              <span className="text-gray-400">
                High: <span className="text-green-400 font-medium">${intradayData.high_of_day?.toLocaleString()}</span>
              </span>
              <span className="text-gray-400">
                Low: <span className="text-red-400 font-medium">${intradayData.low_of_day?.toLocaleString()}</span>
              </span>
              <span className="text-gray-400">
                Current: <span className="text-white font-medium">${intradayData.current_equity?.toLocaleString()}</span>
                {/* Show note if snapshots might be stale */}
                {intradayData.snapshots_count === 0 && (
                  <span className="text-yellow-500 ml-1" title="No snapshots recorded today - showing realized P&L only">
                    (realized only)
                  </span>
                )}
              </span>
            </div>
            <span className="text-gray-500">
              Snapshots every 5 min, refreshing every 30 sec
            </span>
          </div>
        </div>
        )
      })()}

      {/* Main Chart */}
      <div className="p-4" style={{ height }}>
        {(viewMode === 'intraday' ? processedIntradayData.length : aggregatedData.length) > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={viewMode === 'intraday' ? processedIntradayData : aggregatedData}
              margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
            >
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
                dataKey={viewMode === 'intraday' ? 'time' : 'displayDate'}
                stroke="#6B7280"
                fontSize={10}
                tickFormatter={(value) => {
                  if (viewMode === 'intraday') {
                    // Format time like "9:30" or "14:00"
                    return value || ''
                  }
                  // displayDate is already formatted: MM-DD for daily, "Jan 6" for weekly, "Jan" for monthly
                  return value || ''
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
                  value: viewMode === 'intraday' ? 'Open' : 'Start',
                  position: 'insideLeft',
                  fill: '#6B7280',
                  fontSize: 10
                }}
              />

              {/* Main equity area with brand colors - baseValue ensures fill is relative to starting capital */}
              <Area
                type="monotone"
                dataKey="equity"
                stroke={getBrandColors(botFilter).primary}
                strokeWidth={2}
                fill={`url(#equityGradient-${botFilter || 'default'})`}
                filter={`url(#glow-${botFilter || 'default'})`}
                baseValue={summary.starting_capital}
                animationDuration={1000}
                animationEasing="ease-out"
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className={`w-12 h-12 mx-auto mb-3 rounded-full flex items-center justify-center ${
                botFilter === 'FORTRESS' ? 'bg-amber-900/30' :
                botFilter === 'SOLOMON' ? 'bg-cyan-900/30' :
                botFilter === 'ANCHOR' ? 'bg-blue-900/30' :
                botFilter === 'SAMSON' ? 'bg-violet-900/30' :
                botFilter === 'GIDEON' ? 'bg-orange-900/30' :
                botFilter === 'FAITH' ? 'bg-sky-900/30' :
                'bg-gray-800/50'
              }`}>
                <TrendingUp className={`w-6 h-6 ${
                  botFilter === 'FORTRESS' ? 'text-amber-400/70' :
                  botFilter === 'SOLOMON' ? 'text-cyan-400/70' :
                  botFilter === 'ANCHOR' ? 'text-blue-400/70' :
                  botFilter === 'SAMSON' ? 'text-violet-400/70' :
                  botFilter === 'GIDEON' ? 'text-orange-400/70' :
                  botFilter === 'FAITH' ? 'text-sky-400/70' :
                  'text-gray-500'
                }`} />
              </div>
              <p className="text-gray-500 text-sm">
                {viewMode === 'intraday' ? 'No intraday data available' : 'No equity data available'}
              </p>
              <p className="text-gray-600 text-xs mt-1">
                {viewMode === 'intraday'
                  ? 'Snapshots are taken every 5 minutes during market hours'
                  : 'Chart will populate once trades are closed'
                }
              </p>
              {viewMode === 'intraday' && (
                <button
                  onClick={() => setViewMode('historical')}
                  className="mt-3 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs rounded-lg transition-colors"
                >
                  View Historical
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Drawdown Chart (historical only) */}
      {showDrawdown && viewMode === 'historical' && aggregatedData.length > 0 && (
        <div className="border-t border-gray-800">
          <div className="px-4 py-2 flex items-center gap-2 text-xs text-gray-400">
            <TrendingDown className="w-3 h-3 text-red-400" />
            <span>Drawdown</span>
          </div>
          <div className="px-4 pb-4" style={{ height: 100 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={aggregatedData} margin={{ top: 0, right: 20, left: 10, bottom: 0 }}>
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

      {/* Event Legend (historical only) */}
      {viewMode === 'historical' && visibleEvents.length > 0 && (
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
