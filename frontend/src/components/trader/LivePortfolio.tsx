'use client'

import { useState, useMemo } from 'react'
import { RefreshCw, TrendingUp, TrendingDown } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'

// Types for the component
export interface LivePnLData {
  total_unrealized_pnl: number
  total_realized_pnl: number
  net_pnl: number
  positions: LivePosition[]
  position_count: number
  underlying_price?: number
  last_updated: string
  error?: string
}

export interface LivePosition {
  position_id: string
  spread_type?: string  // For Athena
  long_strike?: number
  short_strike?: number
  expiration: string
  contracts?: number
  contracts_remaining?: number
  initial_contracts?: number
  entry_debit?: number
  current_spread_value?: number
  unrealized_pnl: number
  scaled_pnl?: number
  total_pnl?: number
  pnl_pct: number
  underlying_at_entry?: number
  current_underlying?: number
  // For ARES Iron Condors
  put_short_strike?: number
  put_long_strike?: number
  call_short_strike?: number
  call_long_strike?: number
  credit_received?: number
  current_value?: number
  put_distance?: number
  call_distance?: number
  risk_status?: string
}

export interface EquityDataPoint {
  date: string
  timestamp: number
  equity: number
  pnl: number
}

export type TimePeriod = '1D' | '1W' | '1M' | '3M' | 'YTD' | '1Y' | 'ALL'

interface LivePortfolioProps {
  botName: 'ATHENA' | 'ARES'
  totalValue: number
  startingCapital: number
  livePnL: LivePnLData | null
  equityData: EquityDataPoint[]
  isLoading: boolean
  onRefresh: () => void
  lastUpdated?: string
}

export default function LivePortfolio({
  botName,
  totalValue,
  startingCapital,
  livePnL,
  equityData,
  isLoading,
  onRefresh,
  lastUpdated
}: LivePortfolioProps) {
  const [selectedPeriod, setSelectedPeriod] = useState<TimePeriod>('1D')

  // Calculate today's change
  const todayChange = livePnL?.net_pnl ?? 0
  const todayChangePct = startingCapital > 0 ? (todayChange / startingCapital) * 100 : 0
  const isPositive = todayChange >= 0

  // Filter equity data based on selected period
  const filteredEquityData = useMemo(() => {
    if (!equityData || equityData.length === 0) return []

    const now = new Date()
    let startDate: Date

    switch (selectedPeriod) {
      case '1D':
        startDate = new Date(now.getTime() - 24 * 60 * 60 * 1000)
        break
      case '1W':
        startDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
        break
      case '1M':
        startDate = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
        break
      case '3M':
        startDate = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000)
        break
      case 'YTD':
        startDate = new Date(now.getFullYear(), 0, 1)
        break
      case '1Y':
        startDate = new Date(now.getTime() - 365 * 24 * 60 * 60 * 1000)
        break
      case 'ALL':
      default:
        return equityData
    }

    return equityData.filter(d => new Date(d.date) >= startDate)
  }, [equityData, selectedPeriod])

  // Determine chart color based on period performance
  const periodStartValue = filteredEquityData[0]?.equity ?? startingCapital
  const periodEndValue = filteredEquityData[filteredEquityData.length - 1]?.equity ?? totalValue
  const periodChange = periodEndValue - periodStartValue
  const chartColor = periodChange >= 0 ? '#00C805' : '#FF5000'

  const periods: TimePeriod[] = ['1D', '1W', '1M', '3M', 'YTD', '1Y', 'ALL']

  return (
    <div className="bg-[#0a0a0a] rounded-lg p-6">
      {/* Header with total value */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="text-gray-400 text-sm">{botName} Portfolio</span>
            {/* LIVE INDICATOR with pulse animation */}
            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-green-500/20 border border-green-500/50">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
              <span className="text-xs text-green-400 font-medium">LIVE</span>
            </span>
          </div>
          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="p-2 rounded-lg hover:bg-gray-800 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 text-gray-400 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* Big Portfolio Value */}
        <div className="text-4xl font-bold text-white mb-2">
          ${totalValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>

        {/* Today's Change */}
        <div className="flex items-center gap-2">
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
              Unrealized: <span className={livePnL.total_unrealized_pnl >= 0 ? 'text-[#00C805]' : 'text-[#FF5000]'}>
                {livePnL.total_unrealized_pnl >= 0 ? '+' : ''}${livePnL.total_unrealized_pnl.toFixed(2)}
              </span>
            </span>
            <span className="text-gray-500">
              Realized: <span className={livePnL.total_realized_pnl >= 0 ? 'text-[#00C805]' : 'text-[#FF5000]'}>
                {livePnL.total_realized_pnl >= 0 ? '+' : ''}${livePnL.total_realized_pnl.toFixed(2)}
              </span>
            </span>
          </div>
        )}
      </div>

      {/* Equity Chart */}
      <div className="h-64 mb-4">
        {filteredEquityData.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={filteredEquityData} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
              <defs>
                <linearGradient id={`gradient-${botName}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={chartColor} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={chartColor} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="date"
                hide
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                hide
                domain={['dataMin - 1000', 'dataMax + 1000']}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1a1a1a',
                  border: '1px solid #333',
                  borderRadius: '8px',
                  color: '#fff'
                }}
                formatter={(value: number) => [`$${value.toLocaleString('en-US', { minimumFractionDigits: 2 })}`, 'Equity']}
                labelFormatter={(label) => label}
              />
              <ReferenceLine
                y={startingCapital}
                stroke="#333"
                strokeDasharray="3 3"
              />
              <Line
                type="monotone"
                dataKey="equity"
                stroke={chartColor}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: chartColor }}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-500">
            <div className="text-center">
              <p>No equity data available</p>
              <p className="text-xs text-gray-600 mt-1">Chart will populate as trades are executed</p>
            </div>
          </div>
        )}
      </div>

      {/* Period Toggles - Robinhood Style */}
      <div className="flex justify-center gap-2">
        {periods.map((period) => (
          <button
            key={period}
            onClick={() => setSelectedPeriod(period)}
            className={`px-4 py-2 text-sm font-medium rounded-full transition-all ${
              selectedPeriod === period
                ? 'bg-[#00C805] text-black'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            }`}
          >
            {period}
          </button>
        ))}
      </div>

      {/* Last Updated - More prominent with update frequency info */}
      <div className="text-center mt-4 flex items-center justify-center gap-2">
        {lastUpdated && (
          <span className="text-xs text-gray-500">
            Updated: {new Date(lastUpdated).toLocaleTimeString()}
          </span>
        )}
        <span className="text-xs text-gray-600">•</span>
        <span className="text-xs text-green-500">Updates every 10s</span>
      </div>
    </div>
  )
}
