'use client'

import { useMemo } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, ReferenceDot
} from 'recharts'
import {
  TrendingUp, TrendingDown, AlertTriangle, Award,
  Layers, Calendar, DollarSign, Target
} from 'lucide-react'

interface EquityCurvePoint {
  date: string
  equity: number
  drawdown_pct: number
  daily_pnl?: number
}

interface TierTransition {
  date: string
  from_tier: string
  to_tier: string
  equity: number
}

interface Trade {
  trade_date: string
  net_pnl: number
  tier_name: string
  outcome: string
  vix?: number
}

interface EnhancedEquityCurveProps {
  equityCurve: EquityCurvePoint[]
  tierTransitions?: TierTransition[]
  allTrades?: Trade[]
  initialCapital: number
}

interface ChartEvent {
  date: string
  type: 'tier_up' | 'tier_down' | 'new_high' | 'big_win' | 'big_loss' | 'drawdown_start' | 'drawdown_end' | 'recovery'
  label: string
  value?: number
  description: string
  color: string
  icon: React.ReactNode
}

export default function EnhancedEquityCurve({
  equityCurve,
  tierTransitions = [],
  allTrades = [],
  initialCapital
}: EnhancedEquityCurveProps) {

  // Calculate key events from the data
  const events = useMemo(() => {
    const chartEvents: ChartEvent[] = []

    if (!equityCurve || equityCurve.length === 0) return chartEvents

    let highWaterMark = initialCapital
    let inDrawdown = false
    let drawdownStartDate = ''
    let maxDrawdownPct = 0

    // Track for milestones
    const milestones = [1.5, 2, 3, 5, 10] // 50% gain, 2x, 3x, etc.
    const hitMilestones = new Set<number>()

    equityCurve.forEach((point, index) => {
      const equity = point.equity
      const date = point.date
      const dailyPnl = point.daily_pnl || 0
      const drawdownPct = point.drawdown_pct || 0

      // New high watermark
      if (equity > highWaterMark) {
        if (inDrawdown && drawdownPct < 1) {
          // Recovery from drawdown
          chartEvents.push({
            date,
            type: 'recovery',
            label: 'Recovery',
            value: equity,
            description: `Recovered from ${maxDrawdownPct.toFixed(1)}% drawdown`,
            color: '#22C55E',
            icon: <TrendingUp className="w-4 h-4" />
          })
          inDrawdown = false
          maxDrawdownPct = 0
        }
        highWaterMark = equity
      }

      // Drawdown detection (>5%)
      if (drawdownPct > 5 && !inDrawdown) {
        inDrawdown = true
        drawdownStartDate = date
        maxDrawdownPct = drawdownPct
        chartEvents.push({
          date,
          type: 'drawdown_start',
          label: 'Drawdown',
          value: drawdownPct,
          description: `Drawdown started: -${drawdownPct.toFixed(1)}%`,
          color: '#EF4444',
          icon: <AlertTriangle className="w-4 h-4" />
        })
      } else if (inDrawdown && drawdownPct > maxDrawdownPct) {
        maxDrawdownPct = drawdownPct
      }

      // Big wins (>2% of equity)
      if (dailyPnl > equity * 0.02) {
        chartEvents.push({
          date,
          type: 'big_win',
          label: 'Big Win',
          value: dailyPnl,
          description: `+$${dailyPnl.toLocaleString()} (${(dailyPnl / equity * 100).toFixed(1)}%)`,
          color: '#22C55E',
          icon: <Award className="w-4 h-4" />
        })
      }

      // Big losses (>2% of equity)
      if (dailyPnl < -equity * 0.02) {
        chartEvents.push({
          date,
          type: 'big_loss',
          label: 'Big Loss',
          value: dailyPnl,
          description: `$${dailyPnl.toLocaleString()} (${(dailyPnl / equity * 100).toFixed(1)}%)`,
          color: '#EF4444',
          icon: <TrendingDown className="w-4 h-4" />
        })
      }

      // Milestones
      const multiplier = equity / initialCapital
      milestones.forEach(m => {
        if (multiplier >= m && !hitMilestones.has(m)) {
          hitMilestones.add(m)
          const label = m === 1.5 ? '+50%' : `${m}x`
          chartEvents.push({
            date,
            type: 'new_high',
            label: `${label} Capital`,
            value: equity,
            description: `Reached ${label} initial capital ($${equity.toLocaleString()})`,
            color: '#8B5CF6',
            icon: <Target className="w-4 h-4" />
          })
        }
      })
    })

    // Add tier transitions
    tierTransitions.forEach(t => {
      const isUpgrade = t.to_tier > t.from_tier
      chartEvents.push({
        date: t.date,
        type: isUpgrade ? 'tier_up' : 'tier_down',
        label: isUpgrade ? 'Tier Upgrade' : 'Tier Downgrade',
        value: t.equity,
        description: `${t.from_tier} → ${t.to_tier}`,
        color: isUpgrade ? '#3B82F6' : '#F59E0B',
        icon: <Layers className="w-4 h-4" />
      })
    })

    // Sort by date
    chartEvents.sort((a, b) => a.date.localeCompare(b.date))

    return chartEvents
  }, [equityCurve, tierTransitions, initialCapital])

  // Calculate summary stats
  const stats = useMemo(() => {
    if (!equityCurve || equityCurve.length === 0 || !allTrades || allTrades.length === 0) {
      return null
    }

    const finalEquity = equityCurve[equityCurve.length - 1]?.equity || initialCapital
    const maxDrawdown = Math.max(...equityCurve.map(p => p.drawdown_pct || 0))

    const sortedByPnl = [...allTrades].sort((a, b) => b.net_pnl - a.net_pnl)
    const biggestWin = sortedByPnl[0]
    const biggestLoss = sortedByPnl[sortedByPnl.length - 1]

    // Consecutive losses
    let maxConsecLosses = 0
    let currentConsecLosses = 0
    allTrades.forEach(t => {
      if (t.net_pnl < 0) {
        currentConsecLosses++
        maxConsecLosses = Math.max(maxConsecLosses, currentConsecLosses)
      } else {
        currentConsecLosses = 0
      }
    })

    // Best/worst months
    const monthlyPnl: Record<string, number> = {}
    allTrades.forEach(t => {
      const month = t.trade_date.slice(0, 7)
      monthlyPnl[month] = (monthlyPnl[month] || 0) + t.net_pnl
    })
    const months = Object.entries(monthlyPnl).sort((a, b) => b[1] - a[1])
    const bestMonth = months[0]
    const worstMonth = months[months.length - 1]

    return {
      finalEquity,
      totalReturn: ((finalEquity - initialCapital) / initialCapital * 100),
      maxDrawdown,
      biggestWin,
      biggestLoss,
      maxConsecLosses,
      bestMonth,
      worstMonth,
      totalTrades: allTrades.length,
      winRate: (allTrades.filter(t => t.net_pnl > 0).length / allTrades.length * 100)
    }
  }, [equityCurve, allTrades, initialCapital])

  // Custom tooltip
  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload
      return (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 shadow-xl">
          <p className="text-gray-400 text-xs mb-1">{data.date}</p>
          <p className="text-white font-bold">${data.equity?.toLocaleString()}</p>
          {data.daily_pnl !== undefined && (
            <p className={`text-sm ${data.daily_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {data.daily_pnl >= 0 ? '+' : ''}${data.daily_pnl?.toLocaleString()}
            </p>
          )}
          {data.drawdown_pct > 0 && (
            <p className="text-red-400 text-xs">DD: -{data.drawdown_pct?.toFixed(1)}%</p>
          )}
        </div>
      )
    }
    return null
  }

  if (!equityCurve || equityCurve.length === 0) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
        <p className="text-gray-400 text-center">No equity curve data available</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Enhanced Equity Curve Chart */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-green-400" />
            Equity Curve
          </h3>
          {stats && (
            <div className="flex items-center gap-4 text-sm">
              <span className={stats.totalReturn >= 0 ? 'text-green-400' : 'text-red-400'}>
                {stats.totalReturn >= 0 ? '+' : ''}{stats.totalReturn.toFixed(1)}% Total Return
              </span>
              <span className="text-red-400">
                -{stats.maxDrawdown.toFixed(1)}% Max DD
              </span>
            </div>
          )}
        </div>

        <div className="h-96">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={equityCurve}>
              <defs>
                <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#22C55E" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#22C55E" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis
                dataKey="date"
                stroke="#9CA3AF"
                fontSize={10}
                tickFormatter={(date) => date?.slice(2, 7)}
                interval="preserveStartEnd"
              />
              <YAxis
                stroke="#9CA3AF"
                fontSize={12}
                tickFormatter={(v) => `$${(v / 1000000).toFixed(1)}M`}
                domain={['auto', 'auto']}
              />
              <Tooltip content={<CustomTooltip />} />

              {/* Initial capital reference line */}
              <ReferenceLine
                y={initialCapital}
                stroke="#6B7280"
                strokeDasharray="5 5"
                label={{ value: 'Initial', position: 'left', fill: '#6B7280', fontSize: 10 }}
              />

              {/* Tier transition markers */}
              {tierTransitions.map((t, i) => (
                <ReferenceLine
                  key={`tier-${i}`}
                  x={t.date}
                  stroke="#3B82F6"
                  strokeDasharray="3 3"
                  strokeWidth={1}
                />
              ))}

              <Area
                type="monotone"
                dataKey="equity"
                stroke="#22C55E"
                strokeWidth={2}
                fill="url(#equityGradient)"
              />

              {/* Event dots */}
              {events.filter(e => ['tier_up', 'tier_down', 'new_high'].includes(e.type)).map((event, i) => {
                const point = equityCurve.find(p => p.date === event.date)
                if (!point) return null
                return (
                  <ReferenceDot
                    key={`event-${i}`}
                    x={event.date}
                    y={point.equity}
                    r={5}
                    fill={event.color}
                    stroke="#fff"
                    strokeWidth={1}
                  />
                )
              })}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Key Events Timeline */}
      {events.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <h3 className="font-bold mb-4 flex items-center gap-2">
            <Calendar className="w-5 h-5 text-blue-400" />
            Key Events Timeline
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-400 border-b border-gray-800">
                  <th className="pb-2 pr-4">Date</th>
                  <th className="pb-2 pr-4">Event</th>
                  <th className="pb-2 pr-4">Details</th>
                  <th className="pb-2 text-right">Value</th>
                </tr>
              </thead>
              <tbody>
                {events.slice(0, 20).map((event, i) => (
                  <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="py-2 pr-4 text-gray-400">{event.date}</td>
                    <td className="py-2 pr-4">
                      <span
                        className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium"
                        style={{ backgroundColor: `${event.color}20`, color: event.color }}
                      >
                        {event.icon}
                        {event.label}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-gray-300">{event.description}</td>
                    <td className="py-2 text-right font-mono">
                      {event.value !== undefined && (
                        typeof event.value === 'number' && event.type.includes('loss')
                          ? <span className="text-red-400">${event.value.toLocaleString()}</span>
                          : event.type === 'drawdown_start'
                          ? <span className="text-red-400">-{event.value}%</span>
                          : <span className="text-green-400">${event.value?.toLocaleString()}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {events.length > 20 && (
              <p className="text-gray-500 text-xs mt-2">Showing first 20 of {events.length} events</p>
            )}
          </div>
        </div>
      )}

      {/* Summary Stats Cards */}
      {stats && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <h3 className="font-bold mb-4 flex items-center gap-2">
            <DollarSign className="w-5 h-5 text-yellow-400" />
            Performance Highlights
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {/* Biggest Win */}
            {stats.biggestWin && (
              <div className="bg-gray-800 rounded-lg p-4">
                <div className="text-gray-400 text-xs mb-1">Biggest Win</div>
                <div className="text-green-400 font-bold text-lg">
                  +${stats.biggestWin.net_pnl.toLocaleString()}
                </div>
                <div className="text-gray-500 text-xs">{stats.biggestWin.trade_date}</div>
              </div>
            )}

            {/* Biggest Loss */}
            {stats.biggestLoss && (
              <div className="bg-gray-800 rounded-lg p-4">
                <div className="text-gray-400 text-xs mb-1">Biggest Loss</div>
                <div className="text-red-400 font-bold text-lg">
                  ${stats.biggestLoss.net_pnl.toLocaleString()}
                </div>
                <div className="text-gray-500 text-xs">{stats.biggestLoss.trade_date}</div>
              </div>
            )}

            {/* Max Consecutive Losses */}
            <div className="bg-gray-800 rounded-lg p-4">
              <div className="text-gray-400 text-xs mb-1">Max Consec. Losses</div>
              <div className="text-orange-400 font-bold text-lg">
                {stats.maxConsecLosses}
              </div>
              <div className="text-gray-500 text-xs">trades in a row</div>
            </div>

            {/* Max Drawdown */}
            <div className="bg-gray-800 rounded-lg p-4">
              <div className="text-gray-400 text-xs mb-1">Max Drawdown</div>
              <div className="text-red-400 font-bold text-lg">
                -{stats.maxDrawdown.toFixed(1)}%
              </div>
              <div className="text-gray-500 text-xs">from peak</div>
            </div>

            {/* Best Month */}
            {stats.bestMonth && (
              <div className="bg-gray-800 rounded-lg p-4">
                <div className="text-gray-400 text-xs mb-1">Best Month</div>
                <div className="text-green-400 font-bold text-lg">
                  +${stats.bestMonth[1].toLocaleString()}
                </div>
                <div className="text-gray-500 text-xs">{stats.bestMonth[0]}</div>
              </div>
            )}

            {/* Worst Month */}
            {stats.worstMonth && (
              <div className="bg-gray-800 rounded-lg p-4">
                <div className="text-gray-400 text-xs mb-1">Worst Month</div>
                <div className={stats.worstMonth[1] >= 0 ? 'text-green-400 font-bold text-lg' : 'text-red-400 font-bold text-lg'}>
                  {stats.worstMonth[1] >= 0 ? '+' : ''}${stats.worstMonth[1].toLocaleString()}
                </div>
                <div className="text-gray-500 text-xs">{stats.worstMonth[0]}</div>
              </div>
            )}

            {/* Win Rate */}
            <div className="bg-gray-800 rounded-lg p-4">
              <div className="text-gray-400 text-xs mb-1">Win Rate</div>
              <div className="text-blue-400 font-bold text-lg">
                {stats.winRate.toFixed(1)}%
              </div>
              <div className="text-gray-500 text-xs">{stats.totalTrades} trades</div>
            </div>

            {/* Final Equity */}
            <div className="bg-gray-800 rounded-lg p-4">
              <div className="text-gray-400 text-xs mb-1">Final Equity</div>
              <div className={stats.finalEquity >= initialCapital ? 'text-green-400 font-bold text-lg' : 'text-red-400 font-bold text-lg'}>
                ${stats.finalEquity.toLocaleString()}
              </div>
              <div className="text-gray-500 text-xs">
                {stats.totalReturn >= 0 ? '+' : ''}{stats.totalReturn.toFixed(1)}%
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
