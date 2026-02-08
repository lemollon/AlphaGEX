'use client'

import { useState, useMemo } from 'react'
import useSWR from 'swr'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { TrendingUp, RefreshCw, Eye, EyeOff } from 'lucide-react'
import { BOT_BRANDS, BotName } from '@/components/trader/BotBranding'

// Default starting capitals - used ONLY if API doesn't return starting_capital
// These should match the config table defaults in the backend
const DEFAULT_STARTING_CAPITALS: Record<BotName, number> = {
  FORTRESS: 100000,
  SOLOMON: 100000,
  ICARUS: 100000,
  PEGASUS: 200000,
  SAMSON: 200000,
  PHOENIX: 100000,
  ATLAS: 100000,
  PROMETHEUS: 100000,
  HERACLES: 100000,
  AGAPE: 5000,
}

// Bot configuration with colors
const LIVE_BOTS: { name: BotName; endpoint: string }[] = [
  { name: 'FORTRESS', endpoint: '/api/fortress/equity-curve' },
  { name: 'SOLOMON', endpoint: '/api/solomon/equity-curve' },
  { name: 'ICARUS', endpoint: '/api/icarus/equity-curve' },
  { name: 'PEGASUS', endpoint: '/api/pegasus/equity-curve' },
  { name: 'SAMSON', endpoint: '/api/samson/equity-curve' },
  { name: 'PROMETHEUS', endpoint: '/api/prometheus-box/ic/equity-curve' },
  { name: 'HERACLES', endpoint: '/api/heracles/paper-equity-curve' },
  { name: 'AGAPE', endpoint: '/api/agape/equity-curve' },
]

interface EquityCurvePoint {
  date: string
  equity: number
  pnl?: number
  daily_pnl?: number
  return_pct?: number
}

interface BotEquityData {
  success: boolean
  data?: {
    equity_curve: EquityCurvePoint[]
    starting_capital: number
    current_equity: number
    total_pnl: number
    total_return_pct: number
  }
}

interface MultiBotEquityCurveProps {
  days?: number
  height?: number
  showPercentage?: boolean // If true, show % returns instead of $ values
}

const fetcher = async (url: string): Promise<BotEquityData> => {
  try {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}${url}`)
    if (!res.ok) throw new Error('Failed to fetch')
    return res.json()
  } catch {
    return { success: false }
  }
}

export default function MultiBotEquityCurve({
  days = 30,
  height = 400,
  showPercentage = true,
}: MultiBotEquityCurveProps) {
  const [visibleBots, setVisibleBots] = useState<Record<BotName, boolean>>({
    FORTRESS: true,
    SOLOMON: true,
    ICARUS: true,
    PEGASUS: true,
    SAMSON: true,
    PROMETHEUS: true,
    HERACLES: true,
    AGAPE: true,
    PHOENIX: false,
    ATLAS: false,
  })
  const [selectedDays, setSelectedDays] = useState(days)

  // Fetch data for all bots in parallel
  const { data: aresData, isLoading: aresLoading } = useSWR<BotEquityData>(
    `${LIVE_BOTS[0].endpoint}?days=${selectedDays}`,
    fetcher,
    { refreshInterval: 300000 }
  )
  const { data: solomonData, isLoading: solomonLoading } = useSWR<BotEquityData>(
    `${LIVE_BOTS[1].endpoint}?days=${selectedDays}`,
    fetcher,
    { refreshInterval: 300000 }
  )
  const { data: icarusData, isLoading: icarusLoading } = useSWR<BotEquityData>(
    `${LIVE_BOTS[2].endpoint}?days=${selectedDays}`,
    fetcher,
    { refreshInterval: 300000 }
  )
  const { data: pegasusData, isLoading: pegasusLoading } = useSWR<BotEquityData>(
    `${LIVE_BOTS[3].endpoint}?days=${selectedDays}`,
    fetcher,
    { refreshInterval: 300000 }
  )
  const { data: titanData, isLoading: titanLoading } = useSWR<BotEquityData>(
    `${LIVE_BOTS[4].endpoint}?days=${selectedDays}`,
    fetcher,
    { refreshInterval: 300000 }
  )
  const { data: prometheusData, isLoading: prometheusLoading } = useSWR<BotEquityData>(
    `${LIVE_BOTS[5].endpoint}?days=${selectedDays}`,
    fetcher,
    { refreshInterval: 300000 }
  )
  const { data: heraclesData, isLoading: heraclesLoading } = useSWR<BotEquityData>(
    `${LIVE_BOTS[6].endpoint}?days=${selectedDays}`,
    fetcher,
    { refreshInterval: 300000 }
  )
  const { data: agapeData, isLoading: agapeLoading } = useSWR<BotEquityData>(
    `${LIVE_BOTS[7].endpoint}?days=${selectedDays}`,
    fetcher,
    { refreshInterval: 300000 }
  )

  const isLoading = aresLoading || solomonLoading || icarusLoading || pegasusLoading || titanLoading || prometheusLoading || heraclesLoading || agapeLoading

  // Store all bot data
  const botDataMap: Record<BotName, BotEquityData | undefined> = {
    FORTRESS: aresData,
    SOLOMON: solomonData,
    ICARUS: icarusData,
    PEGASUS: pegasusData,
    SAMSON: titanData,
    PROMETHEUS: prometheusData,
    HERACLES: heraclesData,
    AGAPE: agapeData,
    PHOENIX: undefined,
    ATLAS: undefined,
  }

  // Combine all data into a single chart dataset
  const chartData = useMemo(() => {
    // Collect all dates
    const allDates = new Set<string>()
    LIVE_BOTS.forEach(bot => {
      const data = botDataMap[bot.name]
      if (data?.success && data.data?.equity_curve) {
        data.data.equity_curve.forEach(point => {
          allDates.add(point.date)
        })
      }
    })

    // Sort dates
    const sortedDates = Array.from(allDates).sort()

    // Build chart data with all bots
    return sortedDates.map(date => {
      const point: Record<string, string | number | null> = { date }

      LIVE_BOTS.forEach(bot => {
        const data = botDataMap[bot.name]
        if (data?.success && data.data?.equity_curve) {
          const curvePoint = data.data.equity_curve.find(p => p.date === date)
          // CRITICAL FIX: Use bot-specific default instead of generic 100000
          const startingCapital = data.data.starting_capital || DEFAULT_STARTING_CAPITALS[bot.name]

          if (curvePoint) {
            if (showPercentage) {
              // Calculate percentage return from starting capital
              const returnPct = ((curvePoint.equity - startingCapital) / startingCapital) * 100
              point[bot.name] = parseFloat(returnPct.toFixed(2))
            } else {
              point[bot.name] = curvePoint.equity
            }
          } else {
            point[bot.name] = null
          }
        }
      })

      return point
    })
  }, [aresData, solomonData, icarusData, pegasusData, titanData, prometheusData, heraclesData, agapeData, showPercentage])

  // Calculate summary stats for each bot
  const botStats = useMemo(() => {
    const stats: Record<BotName, { totalReturn: number; currentEquity: number; startingCapital: number } | null> = {
      FORTRESS: null,
      SOLOMON: null,
      ICARUS: null,
      PEGASUS: null,
      SAMSON: null,
      PROMETHEUS: null,
      HERACLES: null,
      AGAPE: null,
      PHOENIX: null,
      ATLAS: null,
    }

    LIVE_BOTS.forEach(bot => {
      const data = botDataMap[bot.name]
      if (data?.success && data.data) {
        // CRITICAL FIX: Use bot-specific default instead of generic 100000
        const startingCapital = data.data.starting_capital || DEFAULT_STARTING_CAPITALS[bot.name]
        stats[bot.name] = {
          totalReturn: data.data.total_return_pct || ((data.data.current_equity - startingCapital) / startingCapital) * 100,
          currentEquity: data.data.current_equity || startingCapital,
          startingCapital,
        }
      }
    })

    return stats
  }, [aresData, solomonData, icarusData, pegasusData, titanData, prometheusData, heraclesData, agapeData])

  // Toggle bot visibility
  const toggleBot = (botName: BotName) => {
    setVisibleBots(prev => ({ ...prev, [botName]: !prev[botName] }))
  }

  // Format date for X-axis
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  // Custom tooltip
  const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: Array<{ name: string; value: number; color: string }>; label?: string }) => {
    if (!active || !payload || !label) return null

    return (
      <div className="bg-gray-900 border border-gray-700 rounded-lg p-3 shadow-xl">
        <p className="text-gray-400 text-xs mb-2">{formatDate(label)}</p>
        <div className="space-y-1">
          {payload
            .filter(p => p.value !== null && p.value !== undefined)
            .sort((a, b) => b.value - a.value)
            .map((entry, idx) => (
              <div key={idx} className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-2">
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: entry.color }}
                  />
                  <span className="text-gray-300 text-sm">{entry.name}</span>
                </div>
                <span
                  className={`text-sm font-medium ${
                    entry.value >= 0 ? 'text-green-400' : 'text-red-400'
                  }`}
                >
                  {showPercentage
                    ? `${entry.value >= 0 ? '+' : ''}${entry.value.toFixed(2)}%`
                    : `$${entry.value.toLocaleString()}`}
                </span>
              </div>
            ))}
        </div>
      </div>
    )
  }

  return (
    <div className="bg-[#0a0a0a] rounded-xl border border-gray-800 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <TrendingUp className="w-5 h-5 text-primary" />
            <div>
              <h3 className="font-semibold text-white">Bot Performance Comparison</h3>
              <p className="text-xs text-gray-500">
                {showPercentage ? 'Percentage returns' : 'Equity value'} over time
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* Timeframe selector */}
            <select
              value={selectedDays}
              onChange={(e) => setSelectedDays(Number(e.target.value))}
              className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-300"
            >
              <option value={7}>7 Days</option>
              <option value={14}>14 Days</option>
              <option value={30}>30 Days</option>
              <option value={60}>60 Days</option>
              <option value={90}>90 Days</option>
            </select>
            {isLoading && <RefreshCw className="w-4 h-4 text-gray-500 animate-spin" />}
          </div>
        </div>
      </div>

      {/* Bot Toggle Pills */}
      <div className="px-4 py-3 border-b border-gray-800 flex flex-wrap gap-2">
        {LIVE_BOTS.map(bot => {
          const brand = BOT_BRANDS[bot.name]
          const stats = botStats[bot.name]
          const isVisible = visibleBots[bot.name]

          return (
            <button
              key={bot.name}
              onClick={() => toggleBot(bot.name)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm transition-all ${
                isVisible
                  ? 'bg-opacity-20 border'
                  : 'bg-gray-800 border border-gray-700 opacity-50'
              }`}
              style={{
                backgroundColor: isVisible ? `${brand.hexPrimary}20` : undefined,
                borderColor: isVisible ? brand.hexPrimary : undefined,
              }}
            >
              {isVisible ? (
                <Eye className="w-3 h-3" style={{ color: brand.hexPrimary }} />
              ) : (
                <EyeOff className="w-3 h-3 text-gray-500" />
              )}
              <span style={{ color: isVisible ? brand.hexPrimary : '#6b7280' }}>
                {bot.name}
              </span>
              {stats && (
                <span
                  className={`text-xs ${
                    stats.totalReturn >= 0 ? 'text-green-400' : 'text-red-400'
                  }`}
                >
                  {stats.totalReturn >= 0 ? '+' : ''}
                  {stats.totalReturn.toFixed(1)}%
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Chart */}
      <div className="p-4">
        {chartData.length === 0 ? (
          <div className="flex items-center justify-center h-64 text-gray-500">
            {isLoading ? 'Loading equity curves...' : 'No data available'}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={height}>
            <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis
                dataKey="date"
                tickFormatter={formatDate}
                stroke="#6b7280"
                tick={{ fontSize: 12 }}
              />
              <YAxis
                stroke="#6b7280"
                tick={{ fontSize: 12 }}
                tickFormatter={(value) =>
                  showPercentage ? `${value}%` : `$${(value / 1000).toFixed(0)}k`
                }
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend
                wrapperStyle={{ paddingTop: '10px' }}
                formatter={(value) => <span className="text-gray-300">{value}</span>}
              />

              {/* Zero line for percentage view */}
              {showPercentage && (
                <Line
                  type="monotone"
                  dataKey={() => 0}
                  stroke="#4b5563"
                  strokeDasharray="5 5"
                  dot={false}
                  isAnimationActive={false}
                  legendType="none"
                />
              )}

              {/* Bot lines */}
              {LIVE_BOTS.map(bot => {
                const brand = BOT_BRANDS[bot.name]
                if (!visibleBots[bot.name]) return null

                return (
                  <Line
                    key={bot.name}
                    type="monotone"
                    dataKey={bot.name}
                    name={bot.name}
                    stroke={brand.hexPrimary}
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                    isAnimationActive={true}
                    animationDuration={500}
                  />
                )
              })}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Summary Stats Table */}
      <div className="px-4 pb-4">
        <div className="grid grid-cols-4 gap-2">
          {LIVE_BOTS.map(bot => {
            const brand = BOT_BRANDS[bot.name]
            const stats = botStats[bot.name]
            const Icon = brand.icon

            return (
              <div
                key={bot.name}
                className={`p-3 rounded-lg border transition-opacity ${
                  visibleBots[bot.name] ? 'opacity-100' : 'opacity-40'
                }`}
                style={{
                  backgroundColor: `${brand.hexPrimary}10`,
                  borderColor: `${brand.hexPrimary}40`,
                }}
              >
                <div className="flex items-center gap-2 mb-2">
                  <span style={{ color: brand.hexPrimary }}>
                    <Icon className="w-4 h-4" />
                  </span>
                  <span className="text-sm font-medium" style={{ color: brand.hexPrimary }}>
                    {bot.name}
                  </span>
                </div>
                {stats ? (
                  <>
                    <div
                      className={`text-lg font-bold ${
                        stats.totalReturn >= 0 ? 'text-green-400' : 'text-red-400'
                      }`}
                    >
                      {stats.totalReturn >= 0 ? '+' : ''}
                      {stats.totalReturn.toFixed(2)}%
                    </div>
                    <div className="text-xs text-gray-500">
                      ${stats.currentEquity.toLocaleString()}
                    </div>
                  </>
                ) : (
                  <div className="text-sm text-gray-500">No data</div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
