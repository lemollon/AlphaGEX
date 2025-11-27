'use client'

import { Activity, TrendingUp, TrendingDown, AlertCircle, CheckCircle, XCircle } from 'lucide-react'

interface LiveMonitoringSectionProps {
  currentPrice: number
  wallStrike: number
  volumeRatio: number
  premiumValue: number // Current value of the spread
  entryPremium: number // Entry value
  ivRank: number
  daysInTrade: number
}

export default function LiveMonitoringSection({
  currentPrice,
  wallStrike,
  volumeRatio,
  premiumValue,
  entryPremium,
  ivRank,
  daysInTrade
}: LiveMonitoringSectionProps) {

  // Calculate metrics (with zero-division guards)
  const distanceToWall = currentPrice > 0 ? ((wallStrike - currentPrice) / currentPrice * 100) : 0
  const isPriceAboveWall = currentPrice > wallStrike
  const priceBouncedOffWall = Math.abs(distanceToWall) < 0.5 && currentPrice < wallStrike
  const priceBrokeWall = currentPrice > wallStrike

  const premiumChange = entryPremium - premiumValue
  const premiumChangePct = entryPremium > 0 ? (premiumChange / entryPremium) * 100 : 0
  const isWinning = premiumChange > 0

  const volumeConfirmed = volumeRatio >= 2.0
  const volumeWeakening = volumeRatio < 1.7 && volumeRatio >= 1.5
  const volumeDied = volumeRatio < 1.5

  const expectedDailyDecay = 0.08 * daysInTrade
  const actualDecay = premiumChange
  const isOnTrack = actualDecay >= (expectedDailyDecay * 0.8) // Within 20% of expected

  const ivDropped = ivRank < 65
  const ivSpiked = ivRank > 85

  // Overall status
  const getOverallStatus = () => {
    if (priceBrokeWall) return { status: 'STOP_OUT', color: 'red' }
    if (volumeDied) return { status: 'EXIT', color: 'yellow' }
    if (premiumChangePct >= 50) return { status: 'TAKE_PROFIT', color: 'green' }
    if (priceBouncedOffWall && volumeConfirmed && isOnTrack) return { status: 'WORKING', color: 'green' }
    if (volumeWeakening || !isOnTrack) return { status: 'MONITOR', color: 'yellow' }
    return { status: 'ACTIVE', color: 'blue' }
  }

  const overall = getOverallStatus()

  return (
    <div className="bg-gradient-to-br from-blue-900/20 via-indigo-900/10 to-purple-900/10 border-2 border-blue-500/40 rounded-xl p-8 shadow-2xl">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Activity className="w-10 h-10 text-blue-400" />
          <div>
            <h2 className="text-3xl font-bold text-white">📊 IS IT WORKING?</h2>
            <p className="text-gray-300 text-sm mt-1">Real-time trade monitoring (Day {daysInTrade})</p>
          </div>
        </div>

        {/* Overall Status Badge */}
        <div className={`px-6 py-3 rounded-lg border-2 ${
          overall.color === 'green' ? 'bg-green-500/20 border-green-500 text-green-400' :
          overall.color === 'yellow' ? 'bg-yellow-500/20 border-yellow-500 text-yellow-400' :
          overall.color === 'red' ? 'bg-red-500/20 border-red-500 text-red-400' :
          'bg-blue-500/20 border-blue-500 text-blue-400'
        }`}>
          <div className="text-2xl font-bold">{overall.status}</div>
        </div>
      </div>

      {/* Monitoring Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">

        {/* Price Action */}
        <div className="bg-gray-950/50 rounded-lg p-5 border-l-4 border-purple-500">
          <h3 className="text-lg font-bold text-purple-300 mb-4 flex items-center gap-2">
            <TrendingUp className="w-5 h-5" />
            Price Action
          </h3>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Current Price:</span>
              <span className="text-lg font-bold text-white">${currentPrice.toFixed(2)}</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Wall at:</span>
              <span className="text-lg font-bold text-white">${wallStrike.toFixed(2)}</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Distance:</span>
              <span className={`text-lg font-bold ${distanceToWall > 0 ? 'text-green-400' : 'text-red-400'}`}>
                {distanceToWall > 0 ? '↓' : '↑'} {Math.abs(distanceToWall).toFixed(2)}%
              </span>
            </div>

            <div className="mt-4 pt-4 border-t border-gray-800">
              {priceBouncedOffWall && (
                <div className="flex items-start gap-2 text-sm">
                  <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
                  <span className="text-green-300">✅ Bounced off ${wallStrike.toFixed(0)} wall → Trade working</span>
                </div>
              )}
              {priceBrokeWall && (
                <div className="flex items-start gap-2 text-sm">
                  <XCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                  <span className="text-red-300">❌ Broke ${wallStrike.toFixed(0)} wall → STOP OUT</span>
                </div>
              )}
              {!priceBouncedOffWall && !priceBrokeWall && currentPrice < wallStrike && (
                <div className="flex items-start gap-2 text-sm">
                  <AlertCircle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
                  <span className="text-yellow-300">⚠️ Approaching wall → Monitor closely</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Volume Confirmation */}
        <div className="bg-gray-950/50 rounded-lg p-5 border-l-4 border-cyan-500">
          <h3 className="text-lg font-bold text-cyan-300 mb-4 flex items-center gap-2">
            <Activity className="w-5 h-5" />
            Volume Confirmation
          </h3>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Current Volume:</span>
              <span className="text-lg font-bold text-white">{volumeRatio.toFixed(1)}x avg</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Required:</span>
              <span className="text-lg font-bold text-white">≥ 2.0x</span>
            </div>

            <div className="mt-4 pt-4 border-t border-gray-800">
              {volumeConfirmed && (
                <div className="flex items-start gap-2 text-sm">
                  <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
                  <span className="text-green-300">✅ Volume {volumeRatio.toFixed(1)}x → Dealers still hedging</span>
                </div>
              )}
              {volumeWeakening && (
                <div className="flex items-start gap-2 text-sm">
                  <AlertCircle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
                  <span className="text-yellow-300">⚠️ Volume weakening → Prepare to exit</span>
                </div>
              )}
              {volumeDied && (
                <div className="flex items-start gap-2 text-sm">
                  <XCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                  <span className="text-red-300">❌ Volume died → No edge, exit now</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Premium Decay */}
        <div className="bg-gray-950/50 rounded-lg p-5 border-l-4 border-green-500">
          <h3 className="text-lg font-bold text-green-300 mb-4 flex items-center gap-2">
            <TrendingDown className="w-5 h-5" />
            Premium Decay
          </h3>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Entry:</span>
              <span className="text-lg font-bold text-white">${entryPremium.toFixed(2)}</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Current:</span>
              <span className="text-lg font-bold text-white">${premiumValue.toFixed(2)}</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Profit:</span>
              <span className={`text-lg font-bold ${isWinning ? 'text-green-400' : 'text-red-400'}`}>
                {isWinning ? '+' : ''}{premiumChange.toFixed(2)} ({premiumChangePct.toFixed(0)}%)
              </span>
            </div>

            <div className="mt-4 pt-4 border-t border-gray-800">
              {premiumChangePct >= 50 && (
                <div className="flex items-start gap-2 text-sm">
                  <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
                  <span className="text-green-300">✅ Hit 50% profit target → TAKE IT</span>
                </div>
              )}
              {isOnTrack && premiumChangePct < 50 && (
                <div className="flex items-start gap-2 text-sm">
                  <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
                  <span className="text-green-300">✅ On track (Day {daysInTrade})</span>
                </div>
              )}
              {!isOnTrack && premiumChange > 0 && (
                <div className="flex items-start gap-2 text-sm">
                  <AlertCircle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
                  <span className="text-yellow-300">⚠️ Slower than expected → Monitor</span>
                </div>
              )}
              {!isWinning && (
                <div className="flex items-start gap-2 text-sm">
                  <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                  <span className="text-red-300">⚠️ Premium UP → Losing, check stops</span>
                </div>
              )}
            </div>
          </div>
        </div>

      </div>

      {/* IV Movement */}
      <div className="bg-gray-950/50 rounded-lg p-5 mb-6">
        <h3 className="text-lg font-bold text-white mb-3">IV Movement:</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-400">Current IV Rank:</span>
            <span className="text-xl font-bold text-white">{ivRank}%</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-400">Status:</span>
            {ivDropped && (
              <span className="text-green-400 flex items-center gap-1">
                <CheckCircle className="w-4 h-4" /> Good for sellers
              </span>
            )}
            {ivSpiked && (
              <span className="text-red-400 flex items-center gap-1">
                <AlertCircle className="w-4 h-4" /> Risk increased
              </span>
            )}
            {!ivDropped && !ivSpiked && (
              <span className="text-gray-400">Stable</span>
            )}
          </div>
          <div className="text-sm text-gray-400">
            {ivDropped && "✅ IV drop helps premium sellers"}
            {ivSpiked && "⚠️ IV spike + price breakout = close immediately"}
            {!ivDropped && !ivSpiked && "Normal range"}
          </div>
        </div>
      </div>

      {/* Action Summary */}
      <div className={`rounded-lg p-5 border-2 ${
        overall.status === 'STOP_OUT' ? 'bg-red-500/10 border-red-500' :
        overall.status === 'TAKE_PROFIT' ? 'bg-green-500/10 border-green-500' :
        overall.status === 'EXIT' ? 'bg-yellow-500/10 border-yellow-500' :
        overall.status === 'WORKING' ? 'bg-green-500/10 border-green-500' :
        overall.status === 'MONITOR' ? 'bg-yellow-500/10 border-yellow-500' :
        'bg-blue-500/10 border-blue-500'
      }`}>
        <div className="flex items-start gap-3">
          <AlertCircle className={`w-6 h-6 flex-shrink-0 mt-1 ${
            overall.color === 'green' ? 'text-green-400' :
            overall.color === 'yellow' ? 'text-yellow-400' :
            overall.color === 'red' ? 'text-red-400' :
            'text-blue-400'
          }`} />
          <div>
            <h3 className={`text-xl font-bold mb-2 ${
              overall.color === 'green' ? 'text-green-300' :
              overall.color === 'yellow' ? 'text-yellow-300' :
              overall.color === 'red' ? 'text-red-300' :
              'text-blue-300'
            }`}>
              {overall.status === 'STOP_OUT' && 'ACTION REQUIRED: Stop Out Immediately'}
              {overall.status === 'TAKE_PROFIT' && 'ACTION: Take 50% Profit Now'}
              {overall.status === 'EXIT' && 'CONSIDER: Exit Position (No Edge)'}
              {overall.status === 'WORKING' && 'STATUS: Trade Working As Expected'}
              {overall.status === 'MONITOR' && 'STATUS: Monitor Closely'}
              {overall.status === 'ACTIVE' && 'STATUS: Trade Active'}
            </h3>
            <p className="text-gray-300">
              {overall.status === 'STOP_OUT' && 'Price broke above wall. Mechanics failed. Close at market to prevent further loss.'}
              {overall.status === 'TAKE_PROFIT' && 'You\'re up 50%+ on the spread. Take the profit. Don\'t be greedy. Live to trade another day.'}
              {overall.status === 'EXIT' && 'Volume dropped below 1.5x average. No dealer flow = no edge. Exit at small loss/gain.'}
              {overall.status === 'WORKING' && 'Price respecting wall, volume confirmed, premium decaying as expected. Let theta work.'}
              {overall.status === 'MONITOR' && 'Some signals weakening. Watch price action and volume closely. Prepare exit plan.'}
              {overall.status === 'ACTIVE' && 'Position entered. Monitoring key metrics. Stay disciplined.'}
            </p>
          </div>
        </div>
      </div>

    </div>
  )
}
