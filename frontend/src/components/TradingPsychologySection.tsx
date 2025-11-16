'use client'

import { Brain, AlertCircle, CheckCircle, XCircle, Clock } from 'lucide-react'

interface TradingPsychologySectionProps {
  winRate: number
  strikePrice: number
}

export default function TradingPsychologySection({
  winRate,
  strikePrice
}: TradingPsychologySectionProps) {

  return (
    <div className="bg-gradient-to-br from-purple-900/20 via-pink-900/10 to-indigo-900/10 border-2 border-purple-500/40 rounded-xl p-8 shadow-2xl">
      <div className="flex items-center gap-3 mb-6">
        <Brain className="w-10 h-10 text-purple-400" />
        <div>
          <h2 className="text-3xl font-bold text-white">🧠 TRADING PSYCHOLOGY</h2>
          <p className="text-gray-300 text-sm mt-1">How to NOT sabotage yourself (the real edge)</p>
        </div>
      </div>

      <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-5 mb-6">
        <p className="text-yellow-300 text-center text-lg font-semibold">
          ⚠️ 90% of traders lose not because they don't understand mechanics,
          <br />
          but because they <span className="text-white font-bold">override their edge with emotion</span>
        </p>
      </div>

      {/* Day-by-Day Emotional Checkpoints */}
      <div className="space-y-6 mb-6">

        {/* Entry Day */}
        <div className="bg-gray-950/50 rounded-lg p-6 border-l-4 border-purple-500">
          <div className="flex items-center gap-2 mb-4">
            <Clock className="w-6 h-6 text-purple-400" />
            <h3 className="text-xl font-bold text-purple-300">Entry Day: Price Approaching ${strikePrice.toFixed(0)}</h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-red-500/10 border border-red-500/30 rounded p-4">
              <div className="flex items-center gap-2 mb-2">
                <XCircle className="w-5 h-5 text-red-400" />
                <h4 className="font-bold text-red-300">❌ What You'll FEEL</h4>
              </div>
              <p className="text-gray-300 text-sm italic mb-2">
                "Price is ripping +2%, I'm going to miss the breakout! Everyone on Twitter is bullish. Should I buy calls instead?"
              </p>
              <p className="text-xs text-gray-400">
                Emotion: FOMO, fear of being left out, doubt in contrarian position
              </p>
            </div>

            <div className="bg-green-500/10 border border-green-500/30 rounded p-4">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle className="w-5 h-5 text-green-400" />
                <h4 className="font-bold text-green-300">✅ What You Should THINK</h4>
              </div>
              <p className="text-gray-300 text-sm mb-2">
                "Dealers MUST sell $4.2M at ${strikePrice.toFixed(0)}. {winRate}% historical win rate. Trust the mechanics. Be patient."
              </p>
              <p className="text-xs text-gray-400">
                Reality: Your edge is contrarian positioning + dealer mechanics
              </p>
            </div>
          </div>
        </div>

        {/* Day 1 */}
        <div className="bg-gray-950/50 rounded-lg p-6 border-l-4 border-blue-500">
          <div className="flex items-center gap-2 mb-4">
            <Clock className="w-6 h-6 text-blue-400" />
            <h3 className="text-xl font-bold text-blue-300">Day 1: Price Tests Wall</h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-red-500/10 border border-red-500/30 rounded p-4">
              <div className="flex items-center gap-2 mb-2">
                <XCircle className="w-5 h-5 text-red-400" />
                <h4 className="font-bold text-red-300">❌ What You'll FEEL</h4>
              </div>
              <p className="text-gray-300 text-sm italic mb-2">
                "It touched ${(strikePrice + 0.5).toFixed(0)} and is still going! I'm wrong. Should I close now before it gets worse?"
              </p>
              <p className="text-xs text-gray-400">
                Emotion: Panic, self-doubt, urge to close at small loss
              </p>
            </div>

            <div className="bg-green-500/10 border border-green-500/30 rounded p-4">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle className="w-5 h-5 text-green-400" />
                <h4 className="font-bold text-green-300">✅ What You Should THINK</h4>
              </div>
              <p className="text-gray-300 text-sm mb-2">
                "Day 1 volatility is normal. Check volume: still 2x? Check stop: ${(strikePrice + 1).toFixed(0)} not hit. Position still valid. Let it work."
              </p>
              <p className="text-xs text-gray-400">
                Reality: {winRate}% win rate. 1 day doesn't invalidate the setup.
              </p>
            </div>
          </div>
        </div>

        {/* Day 2 */}
        <div className="bg-gray-950/50 rounded-lg p-6 border-l-4 border-green-500">
          <div className="flex items-center gap-2 mb-4">
            <Clock className="w-6 h-6 text-green-400" />
            <h3 className="text-xl font-bold text-green-300">Day 2: Small Profit Appearing</h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-red-500/10 border border-red-500/30 rounded p-4">
              <div className="flex items-center gap-2 mb-2">
                <XCircle className="w-5 h-5 text-red-400" />
                <h4 className="font-bold text-red-300">❌ What You'll FEEL</h4>
              </div>
              <p className="text-gray-300 text-sm italic mb-2">
                "I'm only up $40. What if it reverses tomorrow? Should I just take this small profit and close?"
              </p>
              <p className="text-xs text-gray-400">
                Emotion: Fear of giving back profits, impatience
              </p>
            </div>

            <div className="bg-green-500/10 border border-green-500/30 rounded p-4">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle className="w-5 h-5 text-green-400" />
                <h4 className="font-bold text-green-300">✅ What You Should THINK</h4>
              </div>
              <p className="text-gray-300 text-sm mb-2">
                "Target is 50% ($92). Up $40 = 21% in 2 days = on track. Theta decay working. Let it run to target. Don't cut winners early."
              </p>
              <p className="text-xs text-gray-400">
                Reality: Patience = profit. Typical win takes 2-3 days.
              </p>
            </div>
          </div>
        </div>

        {/* Day 3 */}
        <div className="bg-gray-950/50 rounded-lg p-6 border-l-4 border-yellow-500">
          <div className="flex items-center gap-2 mb-4">
            <Clock className="w-6 h-6 text-yellow-400" />
            <h3 className="text-xl font-bold text-yellow-300">Day 3: Near Profit Target</h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-red-500/10 border border-red-500/30 rounded p-4">
              <div className="flex items-center gap-2 mb-2">
                <XCircle className="w-5 h-5 text-red-400" />
                <h4 className="font-bold text-red-300">❌ What You'll FEEL</h4>
              </div>
              <p className="text-gray-300 text-sm italic mb-2">
                "I'm at +48% ($89). So close to worthless! Can squeeze last $30 by holding to expiration for max profit!"
              </p>
              <p className="text-xs text-gray-400">
                Emotion: Greed, wanting 100% instead of 50%
              </p>
            </div>

            <div className="bg-green-500/10 border border-green-500/30 rounded p-4">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle className="w-5 h-5 text-green-400" />
                <h4 className="font-bold text-green-300">✅ What You Should THINK</h4>
              </div>
              <p className="text-gray-300 text-sm mb-2">
                "Hit target. Close at $0.90 for 51% profit ($94). Gamma risk explodes near expiration. Take the win. Live to trade tomorrow."
              </p>
              <p className="text-xs text-gray-400">
                Reality: Greed kills accounts. Professionals take 50%, amateurs hold for 100% and lose.
              </p>
            </div>
          </div>
        </div>

      </div>

      {/* Common Mistakes That Kill The Edge */}
      <div className="bg-gray-950/50 rounded-lg p-6 mb-6">
        <h3 className="text-xl font-bold text-white mb-4">6 Common Mistakes That Kill The Edge:</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <div className="flex items-start gap-2">
            <XCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-red-300 font-bold mb-1">1. Chasing (Late Entry)</p>
              <p className="text-gray-300">Entering after +2% move. You're late. Wait for pullback to ${(strikePrice - 2).toFixed(0)}</p>
            </div>
          </div>

          <div className="flex items-start gap-2">
            <XCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-red-300 font-bold mb-1">2. Oversizing (Too Much Risk)</p>
              <p className="text-gray-300">Risking 5% instead of 1-2%. One bad trade hurts too much. Stick to position sizing rules.</p>
            </div>
          </div>

          <div className="flex items-start gap-2">
            <XCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-red-300 font-bold mb-1">3. No Stops (Hope Trading)</p>
              <p className="text-gray-300">"I'll wait it out" mentality. Stops are hard limits. No exceptions. Cut at ${(strikePrice + 1).toFixed(0)} close.</p>
            </div>
          </div>

          <div className="flex items-start gap-2">
            <XCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-red-300 font-bold mb-1">4. Moving Stops (Discipline = 0)</p>
              <p className="text-gray-300">"Just a bit more room" destroys edge. Stops are set for a reason. Never move them.</p>
            </div>
          </div>

          <div className="flex items-start gap-2">
            <XCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-red-300 font-bold mb-1">5. Early Exit (Impatience)</p>
              <p className="text-gray-300">Closing at +$10 instead of +$90. Fear of giving back. Let theta work. Wait for 50% target.</p>
            </div>
          </div>

          <div className="flex items-start gap-2">
            <XCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-red-300 font-bold mb-1">6. Greed (Holding Past Target)</p>
              <p className="text-gray-300">Wanting 100% instead of 50%. Gamma risk near expiration. Close at target, always.</p>
            </div>
          </div>
        </div>
      </div>

      {/* The Mental Game */}
      <div className="bg-gradient-to-r from-purple-600/20 to-pink-600/20 border border-purple-500/30 rounded-lg p-6">
        <h3 className="text-xl font-bold text-white mb-4">The Mental Game (Professional vs Amateur):</h3>

        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="bg-red-500/10 border border-red-500/30 rounded p-3">
              <p className="text-red-300 font-bold mb-1">❌ Amateur Mindset:</p>
              <p className="text-gray-300">"I need to be right on every trade. Losses mean I'm a bad trader."</p>
            </div>
            <div className="bg-green-500/10 border border-green-500/30 rounded p-3">
              <p className="text-green-300 font-bold mb-1">✅ Professional Mindset:</p>
              <p className="text-gray-300">"{winRate}% win rate = {100-winRate}% losses are normal. Edge is over 100 trades, not 1."</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="bg-red-500/10 border border-red-500/30 rounded p-3">
              <p className="text-red-300 font-bold mb-1">❌ Amateur Mindset:</p>
              <p className="text-gray-300">"Market is against me. I have bad luck. Nothing works."</p>
            </div>
            <div className="bg-green-500/10 border border-green-500/30 rounded p-3">
              <p className="text-green-300 font-bold mb-1">✅ Professional Mindset:</p>
              <p className="text-gray-300">"Market is neutral. Variance is expected. Trust the process."</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="bg-red-500/10 border border-red-500/30 rounded p-3">
              <p className="text-red-300 font-bold mb-1">❌ Amateur Mindset:</p>
              <p className="text-gray-300">"I'll trade more to make back losses faster."</p>
            </div>
            <div className="bg-green-500/10 border border-green-500/30 rounded p-3">
              <p className="text-green-300 font-bold mb-1">✅ Professional Mindset:</p>
              <p className="text-gray-300">"Revenge trading destroys accounts. Step back. Wait for A+ setup."</p>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Line */}
      <div className="mt-6 bg-gradient-to-r from-purple-600/20 to-indigo-600/20 border border-purple-500/30 rounded-lg p-5">
        <p className="text-center text-xl text-white">
          <span className="font-bold text-purple-400">Your edge is NOT prediction. It's discipline.</span>
        </p>
        <p className="text-center text-gray-300 mt-2 text-sm">
          Mechanics give you the setup. Psychology determines if you profit from it.
        </p>
      </div>
    </div>
  )
}
