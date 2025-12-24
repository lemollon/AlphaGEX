'use client'

import { TrendingUp, TrendingDown, Target, Award, Calendar, BarChart3 } from 'lucide-react'

interface PerformanceComparisonProps {
  // Today's metrics
  todayPnl: number
  todayTrades: number
  todayWinRate: number

  // Historical averages
  avgDailyPnl: number
  avgDailyTrades: number
  avgWinRate: number

  // Period stats
  weekPnl?: number
  monthPnl?: number

  // Streak info
  currentStreak?: number  // positive = wins, negative = losses
  bestStreak?: number
}

export default function PerformanceComparison({
  todayPnl,
  todayTrades,
  todayWinRate,
  avgDailyPnl,
  avgDailyTrades,
  avgWinRate,
  weekPnl,
  monthPnl,
  currentStreak,
  bestStreak
}: PerformanceComparisonProps) {
  // Calculate comparisons
  const pnlVsAvg = avgDailyPnl !== 0 ? ((todayPnl - avgDailyPnl) / Math.abs(avgDailyPnl)) * 100 : 0
  const tradesVsAvg = avgDailyTrades !== 0 ? ((todayTrades - avgDailyTrades) / avgDailyTrades) * 100 : 0
  const winRateVsAvg = todayWinRate - avgWinRate

  const getComparisonIndicator = (value: number, inverted = false) => {
    const isPositive = inverted ? value < 0 : value > 0
    if (Math.abs(value) < 5) return { text: '~', color: 'text-gray-400' }
    return isPositive
      ? { text: `+${Math.abs(value).toFixed(0)}%`, color: 'text-green-400' }
      : { text: `-${Math.abs(value).toFixed(0)}%`, color: 'text-red-400' }
  }

  const pnlComp = getComparisonIndicator(pnlVsAvg)
  const tradesComp = getComparisonIndicator(tradesVsAvg)
  const winRateComp = getComparisonIndicator(winRateVsAvg)

  return (
    <div className="bg-gray-900/50 rounded-lg border border-gray-700 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-700 bg-gray-800/50 flex items-center gap-2">
        <BarChart3 className="w-4 h-4 text-purple-400" />
        <span className="text-sm font-medium text-white">Performance vs Average</span>
      </div>

      <div className="p-4">
        {/* Comparison Grid */}
        <div className="space-y-3">
          {/* P&L Comparison */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {todayPnl >= 0 ? (
                <TrendingUp className="w-4 h-4 text-green-400" />
              ) : (
                <TrendingDown className="w-4 h-4 text-red-400" />
              )}
              <span className="text-sm text-gray-400">P&L</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="text-right">
                <p className={`text-sm font-bold ${todayPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {todayPnl >= 0 ? '+' : ''}${todayPnl.toFixed(0)}
                </p>
                <p className="text-xs text-gray-500">avg: ${avgDailyPnl.toFixed(0)}</p>
              </div>
              <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${pnlComp.color} bg-gray-800`}>
                {pnlComp.text}
              </span>
            </div>
          </div>

          {/* Trades Comparison */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Target className="w-4 h-4 text-blue-400" />
              <span className="text-sm text-gray-400">Trades</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="text-right">
                <p className="text-sm font-bold text-white">{todayTrades}</p>
                <p className="text-xs text-gray-500">avg: {avgDailyTrades.toFixed(1)}</p>
              </div>
              <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${tradesComp.color} bg-gray-800`}>
                {tradesComp.text}
              </span>
            </div>
          </div>

          {/* Win Rate Comparison */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Award className="w-4 h-4 text-yellow-400" />
              <span className="text-sm text-gray-400">Win Rate</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="text-right">
                <p className={`text-sm font-bold ${todayWinRate >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                  {todayTrades > 0 ? `${todayWinRate.toFixed(0)}%` : '-'}
                </p>
                <p className="text-xs text-gray-500">avg: {avgWinRate.toFixed(0)}%</p>
              </div>
              <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${winRateComp.color} bg-gray-800`}>
                {todayTrades > 0 ? winRateComp.text : '-'}
              </span>
            </div>
          </div>
        </div>

        {/* Period Summary */}
        {(weekPnl !== undefined || monthPnl !== undefined) && (
          <div className="mt-4 pt-3 border-t border-gray-700 grid grid-cols-2 gap-3">
            {weekPnl !== undefined && (
              <div className="text-center">
                <p className="text-xs text-gray-500 flex items-center justify-center gap-1">
                  <Calendar className="w-3 h-3" /> This Week
                </p>
                <p className={`text-lg font-bold ${weekPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {weekPnl >= 0 ? '+' : ''}${weekPnl.toFixed(0)}
                </p>
              </div>
            )}
            {monthPnl !== undefined && (
              <div className="text-center">
                <p className="text-xs text-gray-500 flex items-center justify-center gap-1">
                  <Calendar className="w-3 h-3" /> This Month
                </p>
                <p className={`text-lg font-bold ${monthPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {monthPnl >= 0 ? '+' : ''}${monthPnl.toFixed(0)}
                </p>
              </div>
            )}
          </div>
        )}

        {/* Streak */}
        {currentStreak !== undefined && (
          <div className="mt-3 pt-3 border-t border-gray-700 flex items-center justify-between">
            <span className="text-xs text-gray-500">Current Streak</span>
            <div className="flex items-center gap-2">
              <span className={`text-sm font-bold ${currentStreak >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {currentStreak >= 0 ? `${currentStreak}W` : `${Math.abs(currentStreak)}L`}
              </span>
              {bestStreak !== undefined && (
                <span className="text-xs text-gray-500">(best: {bestStreak}W)</span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
