'use client'

import { Brain, TrendingUp, AlertTriangle, Users, Target } from 'lucide-react'

interface PsychologyTrapSectionProps {
  regimeType: string
  psychologyTrap?: string
  currentPrice: number
  callWallStrike?: number
  putWallStrike?: number
  sentiment?: string // e.g., "85% bullish"
}

export default function PsychologyTrapSection({
  regimeType,
  psychologyTrap,
  currentPrice,
  callWallStrike,
  putWallStrike,
  sentiment = "Unknown"
}: PsychologyTrapSectionProps) {

  // Determine what retail thinks based on regime
  const getRetailThinking = () => {
    if (regimeType.includes('LIBERATION')) {
      return "Breakout coming! Momentum is strong! Buy calls NOW!"
    } else if (regimeType.includes('FALSE_FLOOR')) {
      return "Found support! Time to buy the dip! Calls here!"
    } else if (regimeType.includes('GAMMA_SQUEEZE')) {
      return "Short squeeze! Going to the moon! FOMO buy!"
    } else if (callWallStrike && currentPrice < callWallStrike) {
      return "Breaking out to new highs! Buy calls before it runs!"
    }
    return "Follow the momentum! Buy what's moving!"
  }

  const getReality = () => {
    if (regimeType.includes('LIBERATION')) {
      return `Dealers short gamma at $${callWallStrike?.toFixed(0) || 'resistance'}, MUST sell into strength. Creates temporary ceiling.`
    } else if (regimeType.includes('FALSE_FLOOR')) {
      return `Support expires soon. Dealers will STOP defending $${putWallStrike?.toFixed(0) || 'support'} level. Trap breaks down.`
    } else if (callWallStrike) {
      return `Dealers are short $${((callWallStrike - currentPrice) / currentPrice * 100).toFixed(1)}B gamma. MUST sell at $${callWallStrike.toFixed(0)} resistance.`
    }
    return "Dealer positioning creates mechanical ceiling/floor that retail ignores."
  }

  return (
    <div className="bg-gradient-to-br from-red-900/30 via-orange-900/20 to-yellow-900/10 border-2 border-red-500/40 rounded-xl p-8 shadow-2xl">
      <div className="flex items-center gap-3 mb-6">
        <Brain className="w-10 h-10 text-red-400" />
        <div>
          <h2 className="text-3xl font-bold text-white">🧠 THE PSYCHOLOGY TRAP</h2>
          <p className="text-gray-300 text-sm mt-1">Why 95% of traders lose this exact setup</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* What They Think */}
        <div className="bg-red-500/10 border-2 border-red-500/30 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-3">
            <Users className="w-6 h-6 text-red-400" />
            <h3 className="text-xl font-bold text-red-300">What 95% Think</h3>
          </div>
          <div className="bg-gray-950/50 rounded-lg p-4 mb-3">
            <p className="text-lg text-white italic">"{getRetailThinking()}"</p>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex items-start gap-2">
              <span className="text-red-400 mt-1">❌</span>
              <span>Chasing momentum after the move already happened</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-red-400 mt-1">❌</span>
              <span>Ignoring dealer positioning and gamma walls</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-red-400 mt-1">❌</span>
              <span>Trading on emotion and social media hype</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-red-400 mt-1">❌</span>
              <span>Buying premium at resistance / selling at support</span>
            </div>
          </div>
          {sentiment && sentiment !== "Unknown" && (
            <div className="mt-4 pt-4 border-t border-red-500/30">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">Crowd Sentiment:</span>
                <span className="text-lg font-bold text-red-400">{sentiment}</span>
              </div>
            </div>
          )}
        </div>

        {/* Reality */}
        <div className="bg-green-500/10 border-2 border-green-500/30 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-3">
            <Target className="w-6 h-6 text-green-400" />
            <h3 className="text-xl font-bold text-green-300">The Reality</h3>
          </div>
          <div className="bg-gray-950/50 rounded-lg p-4 mb-3">
            <p className="text-lg text-white">{getReality()}</p>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex items-start gap-2">
              <span className="text-green-400 mt-1">✅</span>
              <span>Dealers MUST hedge (regulatory + margin + automated systems)</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-green-400 mt-1">✅</span>
              <span>Volume confirms active hedging at this strike</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-green-400 mt-1">✅</span>
              <span>We position opposite the crowd (contrarian edge)</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-green-400 mt-1">✅</span>
              <span>Time decay + dealer pressure = our profit</span>
            </div>
          </div>
        </div>
      </div>

      {/* Psychology Trap Explanation */}
      {psychologyTrap && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-5">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-6 h-6 text-yellow-400 flex-shrink-0 mt-1" />
            <div>
              <h3 className="text-lg font-bold text-yellow-300 mb-2">The Trap Explained:</h3>
              <p className="text-gray-200">{psychologyTrap}</p>
            </div>
          </div>
        </div>
      )}

      {/* Why They Lose - Cognitive Errors */}
      <div className="mt-6 bg-gray-950/50 rounded-lg p-5">
        <h3 className="text-lg font-bold text-white mb-4">6 Cognitive Errors That Kill Their Edge:</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
          <div className="flex items-start gap-2">
            <span className="text-red-400 font-bold">1.</span>
            <div>
              <span className="text-red-400 font-bold">Recency Bias:</span>
              <span className="text-gray-300"> "It's up 2%, it'll keep going!"</span>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-red-400 font-bold">2.</span>
            <div>
              <span className="text-red-400 font-bold">Confirmation Bias:</span>
              <span className="text-gray-300"> "Everyone on Twitter agrees!"</span>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-red-400 font-bold">3.</span>
            <div>
              <span className="text-red-400 font-bold">FOMO:</span>
              <span className="text-gray-300"> "I'll miss the breakout if I don't buy NOW!"</span>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-red-400 font-bold">4.</span>
            <div>
              <span className="text-red-400 font-bold">Hope Trading:</span>
              <span className="text-gray-300"> "No stop loss, it'll come back"</span>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-red-400 font-bold">5.</span>
            <div>
              <span className="text-red-400 font-bold">Sunk Cost Fallacy:</span>
              <span className="text-gray-300"> "I'm down, I'll hold to breakeven"</span>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-red-400 font-bold">6.</span>
            <div>
              <span className="text-red-400 font-bold">Overconfidence:</span>
              <span className="text-gray-300"> "This time is different!"</span>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Line */}
      <div className="mt-6 bg-gradient-to-r from-purple-600/20 to-pink-600/20 border border-purple-500/30 rounded-lg p-4">
        <p className="text-center text-lg text-white">
          <span className="font-bold text-purple-400">Their Loss = Your Gain.</span>
          {" "}Options are zero-sum. When they buy calls at resistance and lose, you sell spreads and profit.
        </p>
      </div>
    </div>
  )
}
