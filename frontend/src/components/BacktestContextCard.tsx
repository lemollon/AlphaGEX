'use client'

import { Calendar, TrendingUp, AlertTriangle, CheckCircle, Clock, BarChart3 } from 'lucide-react'

interface BacktestContextCardProps {
  strategyName: string
  startDate: string
  endDate: string
  timestamp: string
  totalTrades: number
  winRate: number
  expectancyPct: number
  liveWinRate?: number
  liveExpectancy?: number
  liveTrades?: number
}

export default function BacktestContextCard({
  strategyName,
  startDate,
  endDate,
  timestamp,
  totalTrades,
  winRate,
  expectancyPct,
  liveWinRate,
  liveExpectancy,
  liveTrades
}: BacktestContextCardProps) {

  // Calculate days since backtest
  const daysSinceBacktest = Math.floor(
    (new Date().getTime() - new Date(timestamp).getTime()) / (1000 * 60 * 60 * 24)
  )

  // Freshness assessment
  const getFreshnessStatus = () => {
    if (daysSinceBacktest <= 7) return { label: 'FRESH', color: 'text-green-400', icon: CheckCircle }
    if (daysSinceBacktest <= 30) return { label: 'RECENT', color: 'text-yellow-400', icon: Clock }
    return { label: 'STALE', color: 'text-red-400', icon: AlertTriangle }
  }

  // Sample size confidence
  const getSampleSizeConfidence = () => {
    if (totalTrades >= 100) return { label: 'High Confidence', color: 'text-green-400', percent: 95 }
    if (totalTrades >= 50) return { label: 'Medium Confidence', color: 'text-yellow-400', percent: 75 }
    if (totalTrades >= 20) return { label: 'Low Confidence', color: 'text-orange-400', percent: 50 }
    return { label: 'Very Low Confidence', color: 'text-red-400', percent: 25 }
  }

  // Forward testing comparison
  const getForwardTestStatus = () => {
    if (!liveWinRate || !liveTrades) return null

    const winRateDiff = liveWinRate - winRate
    const expectancyDiff = (liveExpectancy || 0) - expectancyPct

    if (Math.abs(winRateDiff) <= 5 && Math.abs(expectancyDiff) <= 0.5) {
      return { status: 'VALID', color: 'text-green-400', message: 'Within tolerance' }
    }
    if (winRateDiff < -10 || expectancyDiff < -1.0) {
      return { status: 'DEGRADING', color: 'text-red-400', message: 'Performance declining' }
    }
    if (winRateDiff > 10 || expectancyDiff > 1.0) {
      return { status: 'IMPROVING', color: 'text-blue-400', message: 'Outperforming backtest' }
    }
    return { status: 'MONITOR', color: 'text-yellow-400', message: 'Some variation' }
  }

  const freshness = getFreshnessStatus()
  const confidence = getSampleSizeConfidence()
  const forwardTest = getForwardTestStatus()
  const FreshnessIcon = freshness.icon

  return (
    <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-4 space-y-3">

      {/* Header */}
      <div className="flex items-center justify-between">
        <h4 className="font-bold text-white">{strategyName.replace(/_/g, ' ')}</h4>
        <div className={`flex items-center gap-1 text-xs font-bold ${freshness.color}`}>
          <FreshnessIcon className="w-3 h-3" />
          {freshness.label}
        </div>
      </div>

      {/* Test Period */}
      <div className="grid grid-cols-2 gap-3 text-xs">
        <div className="flex items-start gap-2">
          <Calendar className="w-3 h-3 text-gray-400 flex-shrink-0 mt-0.5" />
          <div>
            <div className="text-gray-500">Test Period</div>
            <div className="font-mono text-gray-300">{startDate}</div>
            <div className="font-mono text-gray-300">to {endDate}</div>
          </div>
        </div>
        <div className="flex items-start gap-2">
          <Clock className="w-3 h-3 text-gray-400 flex-shrink-0 mt-0.5" />
          <div>
            <div className="text-gray-500">Last Run</div>
            <div className="text-gray-300">{daysSinceBacktest} days ago</div>
            {daysSinceBacktest > 30 && (
              <div className="text-red-400 text-xs">Re-run recommended</div>
            )}
          </div>
        </div>
      </div>

      {/* Sample Size Confidence */}
      <div className="bg-gray-950/50 rounded p-3">
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs text-gray-400">Statistical Confidence</div>
          <div className={`text-xs font-bold ${confidence.color}`}>{confidence.label}</div>
        </div>
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-gray-400" />
          <div className="flex-1">
            <div className="text-xs text-gray-300 mb-1">{totalTrades} trades</div>
            <div className="w-full bg-gray-800 rounded-full h-2">
              <div
                className={`h-2 rounded-full ${confidence.percent >= 75 ? 'bg-green-500' : confidence.percent >= 50 ? 'bg-yellow-500' : 'bg-orange-500'}`}
                style={{ width: `${confidence.percent}%` }}
              />
            </div>
          </div>
          <div className="text-xs font-bold text-gray-400">{confidence.percent}%</div>
        </div>
        {totalTrades < 30 && (
          <div className="mt-2 text-xs text-orange-400">
            ⚠️ Small sample - results may not be representative
          </div>
        )}
      </div>

      {/* Forward Testing Comparison */}
      {forwardTest && (
        <div className={`bg-gray-950/50 rounded p-3 border ${
          forwardTest.status === 'VALID' ? 'border-green-500/30' :
          forwardTest.status === 'IMPROVING' ? 'border-blue-500/30' :
          forwardTest.status === 'DEGRADING' ? 'border-red-500/30' :
          'border-yellow-500/30'
        }`}>
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs font-bold text-gray-300">Forward Testing (Last 30 days)</div>
            <div className={`text-xs font-bold ${forwardTest.color}`}>
              {forwardTest.status}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <div className="text-gray-500">Backtest</div>
              <div className="font-bold">{winRate.toFixed(1)}% WR | {expectancyPct.toFixed(2)}% Exp</div>
            </div>
            <div>
              <div className="text-gray-500">Live ({liveTrades} trades)</div>
              <div className={`font-bold ${forwardTest.color}`}>
                {liveWinRate?.toFixed(1)}% WR | {liveExpectancy?.toFixed(2)}% Exp
              </div>
            </div>
          </div>
          <div className={`mt-2 text-xs ${forwardTest.color}`}>
            {forwardTest.status === 'VALID' && '✓ Still valid - trade with confidence'}
            {forwardTest.status === 'IMPROVING' && '🚀 Outperforming - edge may be strengthening'}
            {forwardTest.status === 'DEGRADING' && '⚠️ Performance declining - investigate before trading'}
            {forwardTest.status === 'MONITOR' && '👀 Monitor closely - some variation from backtest'}
          </div>
        </div>
      )}

      {/* No Live Data Notice */}
      {!forwardTest && (
        <div className="bg-gray-950/50 rounded p-3 border border-gray-700">
          <div className="text-xs text-gray-400">
            No live trading data yet. Start trading this strategy to track real performance vs backtest.
          </div>
        </div>
      )}

    </div>
  )
}
