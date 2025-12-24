'use client'

import { TrendingUp, TrendingDown, Target, Activity, Clock, Award, AlertTriangle, CheckCircle } from 'lucide-react'

interface TodayReportCardProps {
  botName: 'ATHENA' | 'ARES'
  scansToday: number
  tradesToday: number
  winsToday: number
  lossesToday: number
  totalPnl: number
  unrealizedPnl: number
  realizedPnl: number
  bestTrade?: number
  worstTrade?: number
  avgHoldTime?: string  // e.g., "45 min"
  openPositions: number
  capitalAtRisk?: number
  capitalTotal?: number
}

export default function TodayReportCard({
  botName,
  scansToday,
  tradesToday,
  winsToday,
  lossesToday,
  totalPnl,
  unrealizedPnl,
  realizedPnl,
  bestTrade,
  worstTrade,
  avgHoldTime,
  openPositions,
  capitalAtRisk = 0,
  capitalTotal = 100000
}: TodayReportCardProps) {
  const winRate = tradesToday > 0 ? (winsToday / tradesToday) * 100 : 0
  const pnlPositive = totalPnl >= 0
  const riskPct = capitalTotal > 0 ? (capitalAtRisk / capitalTotal) * 100 : 0

  // Determine grade based on performance
  const getGrade = () => {
    if (tradesToday === 0) return { grade: '-', color: 'text-gray-400', bg: 'bg-gray-700' }
    if (winRate >= 80 && totalPnl > 0) return { grade: 'A+', color: 'text-green-400', bg: 'bg-green-900/30' }
    if (winRate >= 70 && totalPnl > 0) return { grade: 'A', color: 'text-green-400', bg: 'bg-green-900/30' }
    if (winRate >= 60 && totalPnl > 0) return { grade: 'B', color: 'text-blue-400', bg: 'bg-blue-900/30' }
    if (winRate >= 50) return { grade: 'C', color: 'text-yellow-400', bg: 'bg-yellow-900/30' }
    return { grade: 'D', color: 'text-red-400', bg: 'bg-red-900/30' }
  }

  const grade = getGrade()

  return (
    <div className="bg-gray-900/50 rounded-lg border border-gray-700 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-700 bg-gray-800/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Award className="w-4 h-4 text-yellow-400" />
          <span className="text-sm font-medium text-white">Today's Report</span>
        </div>
        <div className={`px-2 py-1 rounded ${grade.bg} ${grade.color} font-bold text-lg`}>
          {grade.grade}
        </div>
      </div>

      {/* Stats Grid */}
      <div className="p-4">
        <div className="grid grid-cols-2 gap-4">
          {/* Scans */}
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-gray-400" />
            <div>
              <p className="text-xs text-gray-400">Scans</p>
              <p className="text-lg font-bold text-white">{scansToday}</p>
            </div>
          </div>

          {/* Trades */}
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-blue-400" />
            <div>
              <p className="text-xs text-gray-400">Trades</p>
              <p className="text-lg font-bold text-white">{tradesToday}</p>
            </div>
          </div>

          {/* Win Rate */}
          <div className="flex items-center gap-2">
            <Target className="w-4 h-4 text-purple-400" />
            <div>
              <p className="text-xs text-gray-400">Win Rate</p>
              <p className={`text-lg font-bold ${winRate >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                {tradesToday > 0 ? `${winRate.toFixed(0)}%` : '-'}
              </p>
            </div>
          </div>

          {/* Record */}
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1">
              <CheckCircle className="w-4 h-4 text-green-400" />
              <span className="text-green-400 font-bold">{winsToday}</span>
              <span className="text-gray-500">/</span>
              <AlertTriangle className="w-4 h-4 text-red-400" />
              <span className="text-red-400 font-bold">{lossesToday}</span>
            </div>
          </div>
        </div>

        {/* P&L Section */}
        <div className="mt-4 pt-4 border-t border-gray-700">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-400">Total P&L</span>
            <div className="flex items-center gap-1">
              {pnlPositive ? (
                <TrendingUp className="w-4 h-4 text-green-400" />
              ) : (
                <TrendingDown className="w-4 h-4 text-red-400" />
              )}
              <span className={`text-xl font-bold ${pnlPositive ? 'text-green-400' : 'text-red-400'}`}>
                {pnlPositive ? '+' : ''}${Math.abs(totalPnl).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </div>
          </div>

          {/* Realized vs Unrealized */}
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="flex justify-between">
              <span className="text-gray-500">Realized:</span>
              <span className={realizedPnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                {realizedPnl >= 0 ? '+' : ''}${realizedPnl.toFixed(2)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Unrealized:</span>
              <span className={unrealizedPnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                {unrealizedPnl >= 0 ? '+' : ''}${unrealizedPnl.toFixed(2)}
              </span>
            </div>
          </div>
        </div>

        {/* Best/Worst Trade */}
        {(bestTrade !== undefined || worstTrade !== undefined) && (
          <div className="mt-3 pt-3 border-t border-gray-700 grid grid-cols-2 gap-2 text-xs">
            {bestTrade !== undefined && (
              <div className="flex justify-between">
                <span className="text-gray-500">Best:</span>
                <span className="text-green-400">+${bestTrade.toFixed(2)}</span>
              </div>
            )}
            {worstTrade !== undefined && (
              <div className="flex justify-between">
                <span className="text-gray-500">Worst:</span>
                <span className="text-red-400">${worstTrade.toFixed(2)}</span>
              </div>
            )}
          </div>
        )}

        {/* Risk Exposure */}
        {openPositions > 0 && capitalAtRisk > 0 && (
          <div className="mt-3 pt-3 border-t border-gray-700">
            <div className="flex justify-between text-xs mb-1">
              <span className="text-gray-500">Capital at Risk:</span>
              <span className={riskPct > 10 ? 'text-yellow-400' : 'text-gray-300'}>
                ${capitalAtRisk.toLocaleString()} ({riskPct.toFixed(1)}%)
              </span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-1.5">
              <div
                className={`h-1.5 rounded-full ${riskPct > 10 ? 'bg-yellow-400' : 'bg-blue-400'}`}
                style={{ width: `${Math.min(riskPct, 100)}%` }}
              ></div>
            </div>
          </div>
        )}

        {/* Average Hold Time */}
        {avgHoldTime && (
          <div className="mt-3 pt-3 border-t border-gray-700 flex justify-between text-xs">
            <span className="text-gray-500">Avg Hold Time:</span>
            <span className="text-gray-300">{avgHoldTime}</span>
          </div>
        )}
      </div>
    </div>
  )
}
