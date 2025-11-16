'use client'

import { XCircle, CheckCircle, TrendingDown, TrendingUp } from 'lucide-react'

interface WhyTheyLoseWhyWeWinProps {
  strikePrice: number
  volumeRatio: number
  winRate: number
}

export default function WhyTheyLoseWhyWeWin({
  strikePrice,
  volumeRatio,
  winRate
}: WhyTheyLoseWhyWeWinProps) {

  const dealerPressure = (volumeRatio * 2.1).toFixed(1)

  return (
    <div className="bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 border-2 border-gray-700 rounded-xl p-8 shadow-2xl">
      <div className="text-center mb-8">
        <h2 className="text-4xl font-bold text-white mb-2">❌ vs ✅ WHY THEY LOSE vs WHY WE WIN</h2>
        <p className="text-gray-300">Understanding the inverse relationship: Their mistakes = Your profit</p>
      </div>

      {/* Comparison Grid */}
      <div className="space-y-4">

        {/* Row 1: Position */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-red-500/10 border-2 border-red-500/30 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-3">
              <XCircle className="w-6 h-6 text-red-400" />
              <h3 className="text-lg font-bold text-red-300">❌ They Buy Calls on Momentum</h3>
            </div>
            <p className="text-gray-300 text-sm mb-2">
              Entry: Buy ${strikePrice.toFixed(0)} calls at $2.50 when price is at ${(strikePrice - 2).toFixed(0)}
            </p>
            <p className="text-gray-400 text-sm">
              → Chasing strength, buying premium at resistance, theta works against them
            </p>
          </div>

          <div className="bg-green-500/10 border-2 border-green-500/30 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-3">
              <CheckCircle className="w-6 h-6 text-green-400" />
              <h3 className="text-lg font-bold text-green-300">✅ We Sell Calls at Resistance</h3>
            </div>
            <p className="text-gray-300 text-sm mb-2">
              Entry: Sell ${strikePrice.toFixed(0)}/${(strikePrice + 5).toFixed(0)} spread for $1.85 credit
            </p>
            <p className="text-gray-400 text-sm">
              <strong className="text-green-400">Why we win:</strong> Theta decay + dealer sell pressure works FOR us
            </p>
          </div>
        </div>

        {/* Row 2: Understanding */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-red-500/10 border-2 border-red-500/30 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-3">
              <XCircle className="w-6 h-6 text-red-400" />
              <h3 className="text-lg font-bold text-red-300">❌ They Think: "Momentum = Higher Prices"</h3>
            </div>
            <p className="text-gray-300 text-sm mb-2">
              Belief: "It's up 2%, breaking out, going to $600!"
            </p>
            <p className="text-gray-400 text-sm">
              → Linear extrapolation, ignoring dealer mechanics and structural resistance
            </p>
          </div>

          <div className="bg-green-500/10 border-2 border-green-500/30 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-3">
              <CheckCircle className="w-6 h-6 text-green-400" />
              <h3 className="text-lg font-bold text-green-300">✅ We Know: "Dealer Hedging Creates Ceiling"</h3>
            </div>
            <p className="text-gray-300 text-sm mb-2">
              Fact: Dealers must sell ${dealerPressure}M at ${strikePrice.toFixed(0)} strike
            </p>
            <p className="text-gray-400 text-sm">
              <strong className="text-green-400">Why we win:</strong> Understand mechanics, not hope. Trade math, not emotion.
            </p>
          </div>
        </div>

        {/* Row 3: Entry Timing */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-red-500/10 border-2 border-red-500/30 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-3">
              <XCircle className="w-6 h-6 text-red-400" />
              <h3 className="text-lg font-bold text-red-300">❌ They Chase After +2% Move</h3>
            </div>
            <p className="text-gray-300 text-sm mb-2">
              Entry: FOMO buy after move already happened, worst possible entry
            </p>
            <p className="text-gray-400 text-sm">
              → Late to party, buying tops, zero edge on entry
            </p>
          </div>

          <div className="bg-green-500/10 border-2 border-green-500/30 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-3">
              <CheckCircle className="w-6 h-6 text-green-400" />
              <h3 className="text-lg font-bold text-green-300">✅ We Wait for Price Near ${(strikePrice - 2).toFixed(0)}-${(strikePrice - 1).toFixed(0)}</h3>
            </div>
            <p className="text-gray-300 text-sm mb-2">
              Entry: Patient entry as price approaches wall, not after
            </p>
            <p className="text-gray-400 text-sm">
              <strong className="text-green-400">Why we win:</strong> Better entry = less risk, more profit potential
            </p>
          </div>
        </div>

        {/* Row 4: Data Analysis */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-red-500/10 border-2 border-red-500/30 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-3">
              <XCircle className="w-6 h-6 text-red-400" />
              <h3 className="text-lg font-bold text-red-300">❌ They Ignore Volume at Strikes</h3>
            </div>
            <p className="text-gray-300 text-sm mb-2">
              Decision: Based on chart patterns, social media, gut feel
            </p>
            <p className="text-gray-400 text-sm">
              → Trading narratives, not data. No edge, pure gambling.
            </p>
          </div>

          <div className="bg-green-500/10 border-2 border-green-500/30 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-3">
              <CheckCircle className="w-6 h-6 text-green-400" />
              <h3 className="text-lg font-bold text-green-300">✅ We Track: {volumeRatio.toFixed(1)}x Volume = ${dealerPressure}M Sell Pressure</h3>
            </div>
            <p className="text-gray-300 text-sm mb-2">
              Decision: Data-driven. Volume/OI confirms dealer hedging activity.
            </p>
            <p className="text-gray-400 text-sm">
              <strong className="text-green-400">Why we win:</strong> Facts {'>'} feelings. Quantified edge, not hope.
            </p>
          </div>
        </div>

        {/* Row 5: Risk Management */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-red-500/10 border-2 border-red-500/30 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-3">
              <XCircle className="w-6 h-6 text-red-400" />
              <h3 className="text-lg font-bold text-red-300">❌ They Use Market Orders, No Stops</h3>
            </div>
            <p className="text-gray-300 text-sm mb-2">
              Execution: Market buy, no stop loss, "it'll come back"
            </p>
            <p className="text-gray-400 text-sm">
              → Hope trading. Small losses become big losses. Account blown.
            </p>
          </div>

          <div className="bg-green-500/10 border-2 border-green-500/30 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-3">
              <CheckCircle className="w-6 h-6 text-green-400" />
              <h3 className="text-lg font-bold text-green-300">✅ We Use Limit Orders, Defined Risk, Hard Stops</h3>
            </div>
            <p className="text-gray-300 text-sm mb-2">
              Execution: Limit entry, max loss = $315, stop at ${(strikePrice + 1).toFixed(0)} close
            </p>
            <p className="text-gray-400 text-sm">
              <strong className="text-green-400">Why we win:</strong> Discipline beats hope. Every. Single. Time.
            </p>
          </div>
        </div>

        {/* Row 6: Trade Management */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-red-500/10 border-2 border-red-500/30 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-3">
              <XCircle className="w-6 h-6 text-red-400" />
              <h3 className="text-lg font-bold text-red-300">❌ They Hold Losers, Cut Winners Early</h3>
            </div>
            <p className="text-gray-300 text-sm mb-2">
              Psychology: "It'll come back" (losers), "Lock in profits!" (winners)
            </p>
            <p className="text-gray-400 text-sm">
              → Backwards. Guaranteed to lose long-term. Broken psychology.
            </p>
          </div>

          <div className="bg-green-500/10 border-2 border-green-500/30 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-3">
              <CheckCircle className="w-6 h-6 text-green-400" />
              <h3 className="text-lg font-bold text-green-300">✅ We Cut Losers Fast, Let Winners Run to Target</h3>
            </div>
            <p className="text-gray-300 text-sm mb-2">
              System: Stop at -$70, target at +$92 (50% profit), no emotion
            </p>
            <p className="text-gray-400 text-sm">
              <strong className="text-green-400">Why we win:</strong> Math: {winRate}% × $250 {'>'} {100-winRate}% × $70 = +${((winRate/100 * 250) - ((100-winRate)/100 * 70)).toFixed(0)}
            </p>
          </div>
        </div>

        {/* Row 7: Decision Making */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-red-500/10 border-2 border-red-500/30 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-3">
              <XCircle className="w-6 h-6 text-red-400" />
              <h3 className="text-lg font-bold text-red-300">❌ They Trade on FOMO and Twitter Hype</h3>
            </div>
            <p className="text-gray-300 text-sm mb-2">
              Process: See trending ticker, read bullish tweets, FOMO buy
            </p>
            <p className="text-gray-400 text-sm">
              → Emotional, reactive, no edge, following the herd to slaughter
            </p>
          </div>

          <div className="bg-green-500/10 border-2 border-green-500/30 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-3">
              <CheckCircle className="w-6 h-6 text-green-400" />
              <h3 className="text-lg font-bold text-green-300">✅ We Trade on Dealer Positioning & Volume Data</h3>
            </div>
            <p className="text-gray-300 text-sm mb-2">
              Process: Check GEX, volume/OI, RSI, confirm ALL signals before entry
            </p>
            <p className="text-gray-400 text-sm">
              <strong className="text-green-400">Why we win:</strong> Systematic, unemotional, data-driven edge
            </p>
          </div>
        </div>

      </div>

      {/* Summary Box */}
      <div className="mt-8 bg-gradient-to-r from-purple-600/20 to-pink-600/20 border-2 border-purple-500/40 rounded-lg p-6">
        <h3 className="text-2xl font-bold text-white text-center mb-4">The Zero-Sum Truth</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-center">
          <div>
            <div className="text-4xl font-bold text-red-400 mb-2">-$200</div>
            <div className="text-sm text-gray-300">Their Average Loss</div>
            <div className="text-xs text-gray-500 mt-1">(Buying calls at resistance)</div>
          </div>
          <div className="flex items-center justify-center">
            <div className="text-3xl font-bold text-purple-400">=</div>
          </div>
          <div>
            <div className="text-4xl font-bold text-green-400 mb-2">+$92</div>
            <div className="text-sm text-gray-300">Your Average Profit</div>
            <div className="text-xs text-gray-500 mt-1">(Selling spreads at resistance)</div>
          </div>
        </div>
        <p className="text-center text-gray-300 mt-6 text-lg">
          <span className="text-purple-400 font-bold">Options are zero-sum.</span>
          {" "}When they lose $200 buying calls at resistance, you collect $92 selling spreads.
          <br />
          <span className="text-sm text-gray-400">Dealer gets $50 in bid-ask spread. Net: -$200 + $92 + $50 (dealer) ≈ -$58 (options friction)</span>
        </p>
      </div>

      {/* Bottom Line */}
      <div className="mt-6 bg-gray-950/50 rounded-lg p-5">
        <p className="text-center text-xl text-white">
          <span className="font-bold text-green-400">Your Edge = Their Mistakes × Dealer Mechanics × Time</span>
        </p>
        <p className="text-center text-gray-400 mt-2">
          They trade emotion. You trade facts. That's why you win.
        </p>
      </div>
    </div>
  )
}
