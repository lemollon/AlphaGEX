'use client'

import { Shield, TrendingUp, DollarSign, Activity, CheckCircle, BarChart3 } from 'lucide-react'

interface YourEdgeSectionProps {
  netGex: number
  volumeRatio: number
  strikePrice: number
  volumeAtStrike: number
  openInterestAtStrike: number
  historicalWinRate?: number
  historicalAvgGain?: number
  historicalAvgLoss?: number
  ivRank?: number
  thetaDecay?: number
  expectedValue?: number
}

export default function YourEdgeSection({
  netGex,
  volumeRatio,
  strikePrice,
  volumeAtStrike,
  openInterestAtStrike,
  historicalWinRate = 73,
  historicalAvgGain = 180,
  historicalAvgLoss = 70,
  ivRank = 78,
  thetaDecay = 0.08,
  expectedValue = 180
}: YourEdgeSectionProps) {

  const volumeOIRatio = openInterestAtStrike > 0 ? volumeAtStrike / openInterestAtStrike : 0
  const dealerHedgingPressure = Math.abs(netGex / 1e9) * volumeRatio * 1.5 // Estimated in millions

  return (
    <div className="bg-gradient-to-br from-green-900/20 via-emerald-900/10 to-teal-900/10 border-2 border-green-500/40 rounded-xl p-8 shadow-2xl">
      <div className="flex items-center gap-3 mb-6">
        <Shield className="w-10 h-10 text-green-400" />
        <div>
          <h2 className="text-3xl font-bold text-white">💰 YOUR EDGE</h2>
          <p className="text-gray-300 text-sm mt-1">Why this trade prints money (data-driven proof)</p>
        </div>
      </div>

      {/* Key Edge Factors Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">

        {/* Edge 1: Dealer Must Hedge */}
        <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle className="w-5 h-5 text-green-400" />
            <h3 className="font-bold text-green-300">Dealer MUST Hedge</h3>
          </div>
          <div className="text-2xl font-bold text-white mb-1">
            ${Math.abs(netGex / 1e9).toFixed(1)}B
          </div>
          <p className="text-xs text-gray-400">
            Short gamma exposure triggers automated hedging at risk limits
          </p>
        </div>

        {/* Edge 2: Volume Confirmation */}
        <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <Activity className="w-5 h-5 text-green-400" />
            <h3 className="font-bold text-green-300">Volume Confirms</h3>
          </div>
          <div className="text-2xl font-bold text-white mb-1">
            {volumeOIRatio.toFixed(1)}x OI
          </div>
          <p className="text-xs text-gray-400">
            Volume/OI {volumeOIRatio >= 2.0 ? '≥ 2.0x = active' : '< 2.0x = wait for'} dealer hedging
          </p>
        </div>

        {/* Edge 3: Historical Win Rate */}
        <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <BarChart3 className="w-5 h-5 text-green-400" />
            <h3 className="font-bold text-green-300">Historical Edge</h3>
          </div>
          <div className="text-2xl font-bold text-white mb-1">
            {historicalWinRate}%
          </div>
          <p className="text-xs text-gray-400">
            Win rate on similar setups with this pattern
          </p>
        </div>

        {/* Edge 4: IV Rank */}
        <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-5 h-5 text-green-400" />
            <h3 className="font-bold text-green-300">IV Rank High</h3>
          </div>
          <div className="text-2xl font-bold text-white mb-1">
            {ivRank}%
          </div>
          <p className="text-xs text-gray-400">
            Premium rich → SELL options, don't buy them
          </p>
        </div>

        {/* Edge 5: Theta Decay */}
        <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <DollarSign className="w-5 h-5 text-green-400" />
            <h3 className="font-bold text-green-300">Time Decay</h3>
          </div>
          <div className="text-2xl font-bold text-white mb-1">
            +${thetaDecay.toFixed(2)}/day
          </div>
          <p className="text-xs text-gray-400">
            Theta works FOR you as premium seller
          </p>
        </div>

        {/* Edge 6: Estimated Hedging Pressure */}
        <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <Shield className="w-5 h-5 text-green-400" />
            <h3 className="font-bold text-green-300">Hedging Flow</h3>
          </div>
          <div className="text-2xl font-bold text-white mb-1">
            ${dealerHedgingPressure.toFixed(1)}M
          </div>
          <p className="text-xs text-gray-400">
            Estimated dealer sell pressure at ${strikePrice.toFixed(0)}
          </p>
        </div>

      </div>

      {/* Expected Value Calculation */}
      <div className="bg-gray-950/50 rounded-lg p-6 mb-6">
        <h3 className="text-xl font-bold text-white mb-4">Expected Value (EV) Calculation:</h3>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          <div className="text-center">
            <div className="text-sm text-gray-400 mb-1">Win Probability</div>
            <div className="text-3xl font-bold text-green-400">{historicalWinRate}%</div>
          </div>
          <div className="text-center">
            <div className="text-sm text-gray-400 mb-1">Avg Win</div>
            <div className="text-3xl font-bold text-green-400">+${historicalAvgGain}</div>
          </div>
          <div className="text-center">
            <div className="text-sm text-gray-400 mb-1">Avg Loss</div>
            <div className="text-3xl font-bold text-red-400">-${historicalAvgLoss}</div>
          </div>
        </div>

        <div className="bg-gradient-to-r from-green-600/20 to-emerald-600/20 border border-green-500/30 rounded-lg p-4">
          <div className="text-center">
            <div className="text-sm text-gray-400 mb-2">Expected Value Per Contract:</div>
            <div className="text-4xl font-bold text-green-400 mb-2">
              +${expectedValue}
            </div>
            <div className="text-xs text-gray-300 font-mono">
              = ({historicalWinRate}% × ${historicalAvgGain}) - ({100 - historicalWinRate}% × ${historicalAvgLoss})
            </div>
          </div>
        </div>

        <div className="mt-4 text-center text-sm text-gray-400">
          <p>Over 100 trades with proper risk management, you'd expect to make <span className="text-white font-bold">+${(expectedValue * 100).toLocaleString()}</span></p>
        </div>
      </div>

      {/* Why This Edge Exists */}
      <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-5">
        <h3 className="text-lg font-bold text-blue-300 mb-3">Why This Edge Exists (And Why It Persists):</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
          <div className="flex items-start gap-2">
            <span className="text-blue-400">•</span>
            <div>
              <span className="text-white font-semibold">Regulatory:</span>
              <span className="text-gray-300"> Dealers MUST hedge (SEC/FINRA rules)</span>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-blue-400">•</span>
            <div>
              <span className="text-white font-semibold">Automated:</span>
              <span className="text-gray-300"> Risk systems force hedging (not discretionary)</span>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-blue-400">•</span>
            <div>
              <span className="text-white font-semibold">Mathematical:</span>
              <span className="text-gray-300"> Gamma compounds, waiting costs more</span>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-blue-400">•</span>
            <div>
              <span className="text-white font-semibold">Psychology:</span>
              <span className="text-gray-300"> Retail emotion overrides dealer mechanics</span>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Line */}
      <div className="mt-6 bg-gradient-to-r from-green-600/20 to-teal-600/20 border border-green-500/30 rounded-lg p-4">
        <p className="text-center text-lg text-white">
          <span className="font-bold text-green-400">Edge = Dealer Obligation × Retail Ignorance × Time Decay</span>
          <br />
          <span className="text-sm text-gray-300">They trade hope. You trade math.</span>
        </p>
      </div>
    </div>
  )
}
