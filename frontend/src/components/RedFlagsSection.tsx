'use client'

import { AlertTriangle, XCircle, TrendingUp } from 'lucide-react'

interface RedFlagsSectionProps {
  netGex: number
  volumeRatio: number
  ivRank: number
  currentPrice: number
  strikePrice: number
  daysToExpiration: number
}

export default function RedFlagsSection({
  netGex,
  volumeRatio,
  ivRank,
  currentPrice,
  strikePrice,
  daysToExpiration
}: RedFlagsSectionProps) {

  // Calculate red flags
  const redFlags: Array<{ flag: string; reason: string }> = []

  if (volumeRatio < 1.5) {
    redFlags.push({ flag: 'Volume < 1.5x average', reason: 'No dealer activity confirmed' })
  }
  if (netGex > 0) {
    redFlags.push({ flag: 'Net GEX > 0', reason: 'Dealers LONG gamma (dampen, not amplify)' })
  }
  if (ivRank < 30) {
    redFlags.push({ flag: 'IV Rank < 30%', reason: 'Premium too cheap to sell' })
  }
  if (daysToExpiration < 2) {
    redFlags.push({ flag: 'Time to exp < 2 days', reason: 'Gamma risk too high' })
  }
  if (currentPrice > strikePrice) {
    redFlags.push({ flag: `Price already > $${strikePrice.toFixed(0)}`, reason: 'Missed entry, wait for next' })
  }

  const hasRedFlags = redFlags.length > 0

  return (
    <div className="bg-gradient-to-br from-red-900/30 via-orange-900/20 to-yellow-900/10 border-2 border-red-500/50 rounded-xl p-8 shadow-2xl">
      <div className="flex items-center gap-3 mb-6">
        <AlertTriangle className="w-10 h-10 text-red-400" />
        <div>
          <h2 className="text-3xl font-bold text-white">🚩 RED FLAGS</h2>
          <p className="text-gray-300 text-sm mt-1">When NOT to take this trade (pre-entry invalidation)</p>
        </div>
      </div>

      {/* Current Red Flags Alert */}
      {hasRedFlags && (
        <div className="bg-red-500/20 border-2 border-red-500 rounded-lg p-5 mb-6">
          <div className="flex items-start gap-3">
            <XCircle className="w-6 h-6 text-red-400 flex-shrink-0 mt-1" />
            <div>
              <h3 className="text-xl font-bold text-red-300 mb-3">⚠️ ACTIVE RED FLAGS DETECTED</h3>
              <p className="text-white mb-3">Do NOT take this trade. The following invalidation criteria are present:</p>
              <div className="space-y-2">
                {redFlags.map((item, idx) => (
                  <div key={idx} className="bg-red-900/30 rounded p-3">
                    <div className="font-bold text-red-300">{item.flag}</div>
                    <div className="text-sm text-gray-300">→ {item.reason}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {!hasRedFlags && (
        <div className="bg-green-500/20 border-2 border-green-500 rounded-lg p-5 mb-6">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-6 h-6 text-green-400 flex-shrink-0 mt-1" />
            <div>
              <h3 className="text-xl font-bold text-green-300 mb-2">✅ NO RED FLAGS DETECTED</h3>
              <p className="text-white">All pre-entry conditions are satisfied. Trade is valid based on setup criteria.</p>
            </div>
          </div>
        </div>
      )}

      {/* Pre-Entry Invalidation Checklist */}
      <div className="bg-gray-950/50 rounded-lg p-6 mb-6">
        <h3 className="text-xl font-bold text-white mb-4">Pre-Entry Invalidation Checklist:</h3>
        <p className="text-gray-300 text-sm mb-4">Do NOT take trade if ANY of the following are true:</p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className={`rounded-lg p-4 border-2 ${volumeRatio < 1.5 ? 'bg-red-500/10 border-red-500' : 'bg-gray-900/50 border-gray-700'}`}>
            <div className="flex items-center gap-2 mb-2">
              {volumeRatio < 1.5 ? (
                <XCircle className="w-5 h-5 text-red-400" />
              ) : (
                <span className="text-green-400 text-xl">✓</span>
              )}
              <h4 className="font-bold text-white">Volume < 1.5x Average</h4>
            </div>
            <p className="text-sm text-gray-300">Current: {volumeRatio.toFixed(1)}x</p>
            <p className="text-xs text-gray-400 mt-1">Why: No dealer activity = no edge</p>
          </div>

          <div className={`rounded-lg p-4 border-2 ${netGex > 0 ? 'bg-red-500/10 border-red-500' : 'bg-gray-900/50 border-gray-700'}`}>
            <div className="flex items-center gap-2 mb-2">
              {netGex > 0 ? (
                <XCircle className="w-5 h-5 text-red-400" />
              ) : (
                <span className="text-green-400 text-xl">✓</span>
              )}
              <h4 className="font-bold text-white">Net GEX > 0</h4>
            </div>
            <p className="text-sm text-gray-300">Current: ${(netGex / 1e9).toFixed(1)}B</p>
            <p className="text-xs text-gray-400 mt-1">Why: Dealers LONG gamma (dampen moves)</p>
          </div>

          <div className="rounded-lg p-4 border-2 bg-gray-900/50 border-gray-700">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-5 h-5 text-yellow-400" />
              <h4 className="font-bold text-white">Major News Pending</h4>
            </div>
            <p className="text-sm text-gray-300">Fed, CPI, Earnings, FOMC</p>
            <p className="text-xs text-gray-400 mt-1">Why: Unpredictable volatility spike</p>
          </div>

          <div className={`rounded-lg p-4 border-2 ${ivRank < 30 ? 'bg-red-500/10 border-red-500' : 'bg-gray-900/50 border-gray-700'}`}>
            <div className="flex items-center gap-2 mb-2">
              {ivRank < 30 ? (
                <XCircle className="w-5 h-5 text-red-400" />
              ) : (
                <span className="text-green-400 text-xl">✓</span>
              )}
              <h4 className="font-bold text-white">IV Rank < 30%</h4>
            </div>
            <p className="text-sm text-gray-300">Current: {ivRank}%</p>
            <p className="text-xs text-gray-400 mt-1">Why: Premium too cheap to sell</p>
          </div>

          <div className={`rounded-lg p-4 border-2 ${daysToExpiration < 2 ? 'bg-red-500/10 border-red-500' : 'bg-gray-900/50 border-gray-700'}`}>
            <div className="flex items-center gap-2 mb-2">
              {daysToExpiration < 2 ? (
                <XCircle className="w-5 h-5 text-red-400" />
              ) : (
                <span className="text-green-400 text-xl">✓</span>
              )}
              <h4 className="font-bold text-white">Time to Exp < 2 Days</h4>
            </div>
            <p className="text-sm text-gray-300">Current: {daysToExpiration} days</p>
            <p className="text-xs text-gray-400 mt-1">Why: Gamma risk explodes near expiration</p>
          </div>

          <div className={`rounded-lg p-4 border-2 ${currentPrice > strikePrice ? 'bg-red-500/10 border-red-500' : 'bg-gray-900/50 border-gray-700'}`}>
            <div className="flex items-center gap-2 mb-2">
              {currentPrice > strikePrice ? (
                <XCircle className="w-5 h-5 text-red-400" />
              ) : (
                <span className="text-green-400 text-xl">✓</span>
              )}
              <h4 className="font-bold text-white">Price Already > ${strikePrice.toFixed(0)}</h4>
            </div>
            <p className="text-sm text-gray-300">Current: ${currentPrice.toFixed(2)}</p>
            <p className="text-xs text-gray-400 mt-1">Why: Missed entry, wait for pullback</p>
          </div>

          <div className="rounded-lg p-4 border-2 bg-gray-900/50 border-gray-700">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-5 h-5 text-yellow-400" />
              <h4 className="font-bold text-white">Weekend Approaching</h4>
            </div>
            <p className="text-sm text-gray-300">Friday PM entries</p>
            <p className="text-xs text-gray-400 mt-1">Why: 2-day gap risk, can't manage</p>
          </div>

          <div className="rounded-lg p-4 border-2 bg-gray-900/50 border-gray-700">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-5 h-5 text-yellow-400" />
              <h4 className="font-bold text-white">Market Closed</h4>
            </div>
            <p className="text-sm text-gray-300">After hours / Pre-market</p>
            <p className="text-xs text-gray-400 mt-1">Why: Low liquidity, wide spreads</p>
          </div>
        </div>
      </div>

      {/* Bull Case - When You Might Be Wrong */}
      <div className="bg-gradient-to-r from-green-600/10 to-emerald-600/10 border border-green-500/30 rounded-lg p-6 mb-6">
        <div className="flex items-start gap-3 mb-4">
          <TrendingUp className="w-6 h-6 text-green-400 flex-shrink-0 mt-1" />
          <div>
            <h3 className="text-xl font-bold text-green-300 mb-2">Bull Case (Why You Might Be Wrong):</h3>
            <p className="text-gray-300 text-sm mb-3">These scenarios invalidate the bearish setup. If they occur, close position immediately:</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-gray-950/50 rounded p-4">
            <div className="font-bold text-green-300 mb-2">🐂 Fed Pivot Announced</div>
            <p className="text-sm text-gray-300 mb-2">Paradigm shift → All assets rally</p>
            <p className="text-xs text-gray-400">Recognition: Immediate {'>'} 1% gap up + sustained buying</p>
          </div>

          <div className="bg-gray-950/50 rounded p-4">
            <div className="font-bold text-green-300 mb-2">🐂 Massive Buyback Program</div>
            <p className="text-sm text-gray-300 mb-2">Real demand, not just dealer hedging</p>
            <p className="text-xs text-gray-400">Recognition: Volume {'>'} 5x + corporate announcement</p>
          </div>

          <div className="bg-gray-950/50 rounded p-4">
            <div className="font-bold text-green-300 mb-2">🐂 Short Squeeze Initiated</div>
            <p className="text-sm text-gray-300 mb-2">Dealers flip to LONG gamma</p>
            <p className="text-xs text-gray-400">Recognition: GEX flips positive + volume explosion</p>
          </div>

          <div className="bg-gray-950/50 rounded p-4">
            <div className="font-bold text-green-300 mb-2">🐂 Momentum > Mechanics</div>
            <p className="text-sm text-gray-300 mb-2">Price breaks wall and HOLDS above</p>
            <p className="text-xs text-gray-400">Recognition: Close above ${(strikePrice + 1).toFixed(0)} for 2+ hours</p>
          </div>
        </div>

        <div className="mt-4 bg-yellow-500/10 border border-yellow-500/30 rounded p-3">
          <p className="text-yellow-300 text-sm">
            <strong>What to do:</strong> If ANY bull case scenario occurs, CLOSE position immediately. Don't fight paradigm shifts.
            Your edge is dealer mechanics in normal conditions, not predicting Fed pivots or corporate announcements.
          </p>
        </div>
      </div>

      {/* Bottom Line */}
      <div className="bg-gradient-to-r from-red-600/20 to-orange-600/20 border border-red-500/30 rounded-lg p-5">
        <h3 className="text-lg font-bold text-white mb-3">The Professional's Rule:</h3>
        <p className="text-gray-200 text-center text-lg">
          <span className="text-red-400 font-bold">"When in doubt, stay out."</span>
          <br />
          <span className="text-sm text-gray-300">
            Missing a trade costs $0. Taking a bad trade costs real money. Wait for A+ setups only.
          </span>
        </p>
      </div>
    </div>
  )
}
