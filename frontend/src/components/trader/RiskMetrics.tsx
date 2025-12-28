'use client'

import { AlertTriangle, Shield, TrendingDown, DollarSign, Activity, Target } from 'lucide-react'

interface RiskMetricsProps {
  // Current exposure
  capitalTotal: number
  capitalAtRisk: number
  openPositions: number
  maxPositionsAllowed: number

  // Drawdown
  currentDrawdown: number
  maxDrawdownToday: number
  maxDrawdownAllTime?: number

  // Greeks (optional - for options)
  totalDelta?: number
  totalGamma?: number
  totalTheta?: number

  // Risk limits
  dailyLossLimit?: number
  dailyLossUsed?: number

  // VIX context
  currentVix?: number
  vixRange?: { min: number; max: number }
}

export default function RiskMetrics({
  capitalTotal,
  capitalAtRisk,
  openPositions,
  maxPositionsAllowed,
  currentDrawdown,
  maxDrawdownToday,
  maxDrawdownAllTime,
  totalDelta,
  totalGamma,
  totalTheta,
  dailyLossLimit,
  dailyLossUsed,
  currentVix,
  vixRange
}: RiskMetricsProps) {
  const riskPct = capitalTotal > 0 ? (capitalAtRisk / capitalTotal) * 100 : 0
  const positionPct = maxPositionsAllowed > 0 ? (openPositions / maxPositionsAllowed) * 100 : 0
  const lossLimitPct = dailyLossLimit && dailyLossUsed ? (Math.abs(dailyLossUsed) / dailyLossLimit) * 100 : 0

  // Risk level assessment
  const getRiskLevel = () => {
    if (riskPct > 20 || lossLimitPct > 80) return { level: 'HIGH', color: 'text-red-400', bg: 'bg-red-500' }
    if (riskPct > 10 || lossLimitPct > 50) return { level: 'MEDIUM', color: 'text-yellow-400', bg: 'bg-yellow-500' }
    return { level: 'LOW', color: 'text-green-400', bg: 'bg-green-500' }
  }

  const risk = getRiskLevel()

  // VIX assessment
  const getVixStatus = () => {
    if (!currentVix || !vixRange) return null
    if (currentVix < vixRange.min) return { status: 'LOW', color: 'text-yellow-400' }
    if (currentVix > vixRange.max) return { status: 'HIGH', color: 'text-red-400' }
    return { status: 'NORMAL', color: 'text-green-400' }
  }

  const vixStatus = getVixStatus()

  return (
    <div className="bg-gray-900/50 rounded-lg border border-gray-700 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-700 bg-gray-800/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-medium text-white">Risk Metrics</span>
        </div>
        <span className={`px-2 py-0.5 rounded text-xs font-bold ${risk.bg}/20 ${risk.color}`}>
          {risk.level} RISK
        </span>
      </div>

      <div className="p-4 space-y-4">
        {/* Capital at Risk */}
        <div>
          <div className="flex justify-between text-xs mb-1">
            <span className="text-gray-400 flex items-center gap-1">
              <DollarSign className="w-3 h-3" />
              Capital at Risk
            </span>
            <span className={riskPct > 15 ? 'text-yellow-400' : 'text-gray-300'}>
              ${capitalAtRisk.toLocaleString()} ({riskPct.toFixed(1)}%)
            </span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2">
            <div
              className={`h-2 rounded-full transition-all ${
                riskPct > 20 ? 'bg-red-500' : riskPct > 10 ? 'bg-yellow-500' : 'bg-blue-500'
              }`}
              style={{ width: `${Math.min(riskPct * 5, 100)}%` }}
            ></div>
          </div>
        </div>

        {/* Position Slots */}
        <div>
          <div className="flex justify-between text-xs mb-1">
            <span className="text-gray-400 flex items-center gap-1">
              <Activity className="w-3 h-3" />
              Position Slots
            </span>
            <span className="text-gray-300">
              {openPositions} / {maxPositionsAllowed}
            </span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2">
            <div
              className={`h-2 rounded-full transition-all ${
                positionPct >= 100 ? 'bg-red-500' : positionPct > 75 ? 'bg-yellow-500' : 'bg-purple-500'
              }`}
              style={{ width: `${Math.min(positionPct, 100)}%` }}
            ></div>
          </div>
        </div>

        {/* Daily Loss Limit */}
        {dailyLossLimit && dailyLossUsed !== undefined && (
          <div>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-gray-400 flex items-center gap-1">
                <TrendingDown className="w-3 h-3" />
                Daily Loss Limit
              </span>
              <span className={lossLimitPct > 75 ? 'text-red-400' : 'text-gray-300'}>
                ${Math.abs(dailyLossUsed).toFixed(0)} / ${dailyLossLimit}
              </span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all ${
                  lossLimitPct >= 100 ? 'bg-red-500' : lossLimitPct > 75 ? 'bg-orange-500' : 'bg-gray-500'
                }`}
                style={{ width: `${Math.min(lossLimitPct, 100)}%` }}
              ></div>
            </div>
          </div>
        )}

        {/* Drawdown with Visual Bar */}
        <div className="pt-2 border-t border-gray-700">
          <div className="flex justify-between text-xs mb-1">
            <span className="text-gray-400 flex items-center gap-1">
              <TrendingDown className="w-3 h-3" />
              Current Drawdown
            </span>
            <span className={currentDrawdown > 5 ? 'text-red-400' : currentDrawdown > 2 ? 'text-yellow-400' : 'text-green-400'}>
              {currentDrawdown > 0 ? `-${currentDrawdown.toFixed(2)}%` : 'At HWM'}
            </span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2 mb-2">
            <div
              className={`h-2 rounded-full transition-all ${
                currentDrawdown > 10 ? 'bg-red-500' :
                currentDrawdown > 5 ? 'bg-orange-500' :
                currentDrawdown > 2 ? 'bg-yellow-500' :
                'bg-green-500'
              }`}
              style={{ width: `${Math.min(currentDrawdown * 5, 100)}%` }}
            ></div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div className="text-center bg-gray-800/50 rounded p-2">
              <p className="text-xs text-gray-500">Current DD</p>
              <p className={`text-sm font-bold ${currentDrawdown > 5 ? 'text-red-400' : 'text-gray-300'}`}>
                -{currentDrawdown.toFixed(1)}%
              </p>
            </div>
            <div className="text-center bg-gray-800/50 rounded p-2">
              <p className="text-xs text-gray-500">Max DD Today</p>
              <p className={`text-sm font-bold ${maxDrawdownToday > 5 ? 'text-red-400' : 'text-gray-300'}`}>
                -{maxDrawdownToday.toFixed(1)}%
              </p>
            </div>
            {maxDrawdownAllTime !== undefined && (
              <div className="text-center bg-gray-800/50 rounded p-2">
                <p className="text-xs text-gray-500">All-Time Max</p>
                <p className={`text-sm font-bold ${maxDrawdownAllTime > 10 ? 'text-red-400' : 'text-gray-300'}`}>
                  -{maxDrawdownAllTime.toFixed(1)}%
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Greeks (if available) */}
        {(totalDelta !== undefined || totalGamma !== undefined || totalTheta !== undefined) && (
          <div className="pt-2 border-t border-gray-700">
            <p className="text-xs text-gray-500 mb-2">Portfolio Greeks</p>
            <div className="grid grid-cols-3 gap-2 text-xs">
              {totalDelta !== undefined && (
                <div className="text-center">
                  <p className="text-gray-500">Delta</p>
                  <p className={`font-bold ${Math.abs(totalDelta) > 0.5 ? 'text-yellow-400' : 'text-white'}`}>
                    {totalDelta > 0 ? '+' : ''}{totalDelta.toFixed(2)}
                  </p>
                </div>
              )}
              {totalGamma !== undefined && (
                <div className="text-center">
                  <p className="text-gray-500">Gamma</p>
                  <p className="font-bold text-white">{totalGamma.toFixed(3)}</p>
                </div>
              )}
              {totalTheta !== undefined && (
                <div className="text-center">
                  <p className="text-gray-500">Theta</p>
                  <p className={`font-bold ${totalTheta > 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {totalTheta > 0 ? '+' : ''}${totalTheta.toFixed(0)}
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* VIX Context */}
        {currentVix && vixStatus && (
          <div className="pt-2 border-t border-gray-700 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-3 h-3 text-gray-500" />
              <span className="text-xs text-gray-500">VIX</span>
            </div>
            <div className="flex items-center gap-2">
              <span className={`text-sm font-bold ${vixStatus.color}`}>
                {currentVix.toFixed(1)}
              </span>
              {vixRange && (
                <span className="text-xs text-gray-500">
                  (range: {vixRange.min}-{vixRange.max})
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
