'use client'

import { useState, useMemo, useEffect, useRef } from 'react'
import { RefreshCw, TrendingUp, TrendingDown, Clock, Zap } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Area, AreaChart } from 'recharts'

export interface EquityPoint {
  date: string
  timestamp: number
  equity: number
  pnl: number
  daily_pnl?: number
  type?: 'historical' | 'live' | 'intraday'
}

export interface LivePnLData {
  total_unrealized_pnl: number
  total_realized_pnl: number
  net_pnl: number
  position_count: number
  underlying_price?: number
  last_updated: string
}

export type TimePeriod = '1D' | '1W' | '1M' | '3M' | 'YTD' | '1Y' | 'ALL'

interface LiveEquityCurveProps {
  botName: 'ATHENA' | 'ARES'
  startingCapital: number
  historicalData: EquityPoint[]  // Closed trade points
  livePnL: LivePnLData | null     // Current live P&L
  intradayPoints?: EquityPoint[]  // Intraday P&L snapshots (optional)
  isLoading: boolean
  onRefresh: () => void
  lastUpdated?: string
  refreshInterval?: number  // in seconds
}

export default function LiveEquityCurve({
  botName,
  startingCapital,
  historicalData,
  livePnL,
  intradayPoints = [],
  isLoading,
  onRefresh,
  lastUpdated,
  refreshInterval = 10
}: LiveEquityCurveProps) {
  const [selectedPeriod, setSelectedPeriod] = useState<TimePeriod>('1D')
  const [localIntradayPoints, setLocalIntradayPoints] = useState<EquityPoint[]>([])
  const lastPnLRef = useRef<number | null>(null)
  const [pnlFlash, setPnlFlash] = useState<'up' | 'down' | null>(null)

  // Track intraday P&L changes for live updates
  useEffect(() => {
    if (!livePnL) return

    const now = Date.now()
    const currentEquity = startingCapital + livePnL.net_pnl

    // Flash animation on P&L change
    if (lastPnLRef.current !== null && lastPnLRef.current !== livePnL.net_pnl) {
      setPnlFlash(livePnL.net_pnl > lastPnLRef.current ? 'up' : 'down')
      setTimeout(() => setPnlFlash(null), 500)
    }
    lastPnLRef.current = livePnL.net_pnl

    // Add new intraday point (limit to last 100 points for performance)
    setLocalIntradayPoints(prev => {
      const newPoint: EquityPoint = {
        date: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
        timestamp: now,
        equity: currentEquity,
        pnl: livePnL.net_pnl,
        type: 'intraday'
      }

      // Only add if different from last point (avoid duplicates)
      const lastPoint = prev[prev.length - 1]
      if (lastPoint && Math.abs(lastPoint.equity - currentEquity) < 1) {
        return prev
      }

      const updated = [...prev, newPoint].slice(-100)
      return updated
    })
  }, [livePnL, startingCapital])

  // Reset intraday points at start of day
  useEffect(() => {
    const now = new Date()
    const marketOpen = new Date()
    marketOpen.setHours(8, 30, 0, 0)  // 8:30 AM CT

    if (now.getTime() < marketOpen.getTime() + 60000) {
      setLocalIntradayPoints([])
    }
  }, [])

  // Combine all data points
  const allEquityData = useMemo(() => {
    const points: EquityPoint[] = []

    // Add historical data (closed trades)
    historicalData.forEach(p => {
      points.push({ ...p, type: 'historical' })
    })

    // Add external intraday points if provided
    intradayPoints.forEach(p => {
      points.push({ ...p, type: 'intraday' })
    })

    // Add locally tracked intraday points
    localIntradayPoints.forEach(p => {
      points.push(p)
    })

    // Add current live point
    if (livePnL) {
      const currentEquity = startingCapital + livePnL.net_pnl
      points.push({
        date: 'Now',
        timestamp: Date.now(),
        equity: currentEquity,
        pnl: livePnL.net_pnl,
        type: 'live'
      })
    }

    // Sort by timestamp
    return points.sort((a, b) => a.timestamp - b.timestamp)
  }, [historicalData, intradayPoints, localIntradayPoints, livePnL, startingCapital])

  // Filter by period
  const filteredData = useMemo(() => {
    if (!allEquityData.length) return []

    const now = Date.now()
    let startTime: number

    switch (selectedPeriod) {
      case '1D':
        // Show today from market open (8:30 AM CT)
        const today = new Date()
        today.setHours(8, 30, 0, 0)
        startTime = today.getTime()
        break
      case '1W':
        startTime = now - 7 * 24 * 60 * 60 * 1000
        break
      case '1M':
        startTime = now - 30 * 24 * 60 * 60 * 1000
        break
      case '3M':
        startTime = now - 90 * 24 * 60 * 60 * 1000
        break
      case 'YTD':
        const yearStart = new Date(new Date().getFullYear(), 0, 1)
        startTime = yearStart.getTime()
        break
      case '1Y':
        startTime = now - 365 * 24 * 60 * 60 * 1000
        break
      case 'ALL':
      default:
        return allEquityData
    }

    return allEquityData.filter(d => d.timestamp >= startTime)
  }, [allEquityData, selectedPeriod])

  // Calculate stats
  const totalValue = startingCapital + (livePnL?.net_pnl || 0)
  const todayChange = livePnL?.net_pnl || 0
  const todayChangePct = startingCapital > 0 ? (todayChange / startingCapital) * 100 : 0
  const isPositive = todayChange >= 0

  // Chart color based on performance
  const chartColor = isPositive ? '#00C805' : '#FF5000'

  // Period stats
  const periodStartValue = filteredData[0]?.equity ?? startingCapital
  const periodEndValue = filteredData[filteredData.length - 1]?.equity ?? totalValue
  const periodChange = periodEndValue - periodStartValue
  const periodChangePct = periodStartValue > 0 ? (periodChange / periodStartValue) * 100 : 0

  const periods: TimePeriod[] = ['1D', '1W', '1M', '3M', 'YTD', '1Y', 'ALL']

  return (
    <div className="bg-[#0a0a0a] rounded-lg p-6 border border-gray-800">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="text-gray-400 text-sm">{botName} Portfolio</span>
            {/* Live indicator */}
            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-green-500/20 border border-green-500/50">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
              <span className="text-xs text-green-400 font-medium">LIVE</span>
            </span>
            {livePnL?.position_count && livePnL.position_count > 0 && (
              <span className="text-xs text-purple-400 bg-purple-500/20 px-2 py-0.5 rounded-full">
                {livePnL.position_count} open
              </span>
            )}
          </div>
          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="p-2 rounded-lg hover:bg-gray-800 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 text-gray-400 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* Big Portfolio Value with flash animation */}
        <div className={`text-4xl font-bold transition-colors duration-200 ${
          pnlFlash === 'up' ? 'text-green-400' : pnlFlash === 'down' ? 'text-red-400' : 'text-white'
        }`}>
          ${totalValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>

        {/* Today's Change */}
        <div className="flex items-center gap-2 mt-1">
          {isPositive ? (
            <TrendingUp className="w-4 h-4 text-[#00C805]" />
          ) : (
            <TrendingDown className="w-4 h-4 text-[#FF5000]" />
          )}
          <span className={`font-semibold ${isPositive ? 'text-[#00C805]' : 'text-[#FF5000]'}`}>
            {isPositive ? '+' : ''}${todayChange.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            {' '}({isPositive ? '+' : ''}{todayChangePct.toFixed(2)}%)
          </span>
          <span className="text-gray-500 text-sm">Today</span>
        </div>

        {/* Unrealized/Realized breakdown */}
        {livePnL && (
          <div className="flex gap-4 mt-2 text-sm">
            <span className="text-gray-500">
              Unrealized:{' '}
              <span className={`font-medium ${livePnL.total_unrealized_pnl >= 0 ? 'text-[#00C805]' : 'text-[#FF5000]'}`}>
                {livePnL.total_unrealized_pnl >= 0 ? '+' : ''}${livePnL.total_unrealized_pnl.toFixed(2)}
              </span>
            </span>
            <span className="text-gray-500">
              Realized:{' '}
              <span className={`font-medium ${livePnL.total_realized_pnl >= 0 ? 'text-[#00C805]' : 'text-[#FF5000]'}`}>
                {livePnL.total_realized_pnl >= 0 ? '+' : ''}${livePnL.total_realized_pnl.toFixed(2)}
              </span>
            </span>
          </div>
        )}
      </div>

      {/* Chart */}
      <div className="h-64 mb-4">
        {filteredData.length > 1 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={filteredData} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
              <defs>
                <linearGradient id={`gradient-${botName}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={chartColor} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={chartColor} stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="date"
                axisLine={false}
                tickLine={false}
                tick={{ fill: '#666', fontSize: 10 }}
                interval="preserveStartEnd"
              />
              <YAxis
                hide
                domain={['dataMin - 500', 'dataMax + 500']}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1a1a1a',
                  border: '1px solid #333',
                  borderRadius: '8px',
                  color: '#fff'
                }}
                formatter={(value: number, name: string) => {
                  if (name === 'equity') {
                    return [`$${value.toLocaleString('en-US', { minimumFractionDigits: 2 })}`, 'Equity']
                  }
                  return [value, name]
                }}
                labelFormatter={(label) => {
                  const point = filteredData.find(d => d.date === label)
                  if (point?.type === 'live') return 'Live'
                  if (point?.type === 'intraday') return `Intraday: ${label}`
                  return label
                }}
              />
              <ReferenceLine
                y={startingCapital}
                stroke="#333"
                strokeDasharray="3 3"
                label={{ value: 'Start', fill: '#666', fontSize: 10 }}
              />
              <Area
                type="monotone"
                dataKey="equity"
                stroke={chartColor}
                strokeWidth={2}
                fill={`url(#gradient-${botName})`}
                dot={(props: any) => {
                  const { cx, cy, payload } = props
                  if (payload?.type === 'live') {
                    return (
                      <circle
                        cx={cx}
                        cy={cy}
                        r={6}
                        fill={chartColor}
                        stroke="white"
                        strokeWidth={2}
                      />
                    )
                  }
                  return <circle cx={cx} cy={cy} r={0} fill="transparent" />
                }}
                activeDot={{ r: 4, fill: chartColor }}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : filteredData.length === 1 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-br from-green-500/20 to-green-500/5 flex items-center justify-center">
                <Zap className="w-8 h-8 text-green-400" />
              </div>
              <p className="text-gray-400">Position opened</p>
              <p className="text-2xl font-bold text-white mt-1">
                ${totalValue.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </p>
              <p className={`text-sm mt-1 ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                {isPositive ? '+' : ''}${todayChange.toFixed(2)} unrealized
              </p>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-500">
            <div className="text-center">
              <p>No equity data yet</p>
              <p className="text-xs text-gray-600 mt-1">Chart will populate as trades are executed</p>
            </div>
          </div>
        )}
      </div>

      {/* Period Selector */}
      <div className="flex justify-center gap-2">
        {periods.map((period) => (
          <button
            key={period}
            onClick={() => setSelectedPeriod(period)}
            className={`px-4 py-2 text-sm font-medium rounded-full transition-all ${
              selectedPeriod === period
                ? `${isPositive ? 'bg-[#00C805]' : 'bg-[#FF5000]'} text-black`
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            }`}
          >
            {period}
          </button>
        ))}
      </div>

      {/* Period Stats */}
      {selectedPeriod !== '1D' && filteredData.length > 1 && (
        <div className="text-center mt-3 text-sm">
          <span className="text-gray-500">{selectedPeriod} change: </span>
          <span className={periodChange >= 0 ? 'text-green-400' : 'text-red-400'}>
            {periodChange >= 0 ? '+' : ''}${periodChange.toFixed(2)} ({periodChangePct >= 0 ? '+' : ''}{periodChangePct.toFixed(2)}%)
          </span>
        </div>
      )}

      {/* Last Updated */}
      <div className="text-center mt-4 flex items-center justify-center gap-2">
        <Clock className="w-3 h-3 text-gray-600" />
        {lastUpdated && (
          <span className="text-xs text-gray-500">
            Updated: {new Date(lastUpdated).toLocaleTimeString()}
          </span>
        )}
        <span className="text-xs text-gray-600">•</span>
        <span className="text-xs text-green-500">Updates every {refreshInterval}s</span>
      </div>
    </div>
  )
}
