'use client'

import { AlertTriangle, XCircle, TrendingDown, TrendingUp, Zap } from 'lucide-react'

interface AdjustmentStrategiesSectionProps {
  wallStrike: number
}

export default function AdjustmentStrategiesSection({
  wallStrike
}: AdjustmentStrategiesSectionProps) {

  return (
    <div className="bg-gradient-to-br from-orange-900/20 via-red-900/10 to-pink-900/10 border-2 border-orange-500/40 rounded-xl p-8 shadow-2xl">
      <div className="flex items-center gap-3 mb-6">
        <AlertTriangle className="w-10 h-10 text-orange-400" />
        <div>
          <h2 className="text-3xl font-bold text-white">⚠️ WHAT IF YOU'RE WRONG?</h2>
          <p className="text-gray-300 text-sm mt-1">Adjustment plan for when setup fails (accept, adapt, preserve capital)</p>
        </div>
      </div>

      {/* Scenarios Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">

        {/* Scenario 1: Price Breaks Wall */}
        <div className="bg-red-500/10 border-2 border-red-500/30 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-6 h-6 text-red-400" />
            <h3 className="text-xl font-bold text-red-300">Scenario 1: Price Breaks ${wallStrike.toFixed(0)}</h3>
          </div>

          <div className="space-y-3 text-sm">
            <div className="bg-gray-950/50 rounded p-3">
              <p className="text-gray-400 mb-1 font-semibold">Signal:</p>
              <p className="text-white">Close above ${wallStrike + 1} on volume {'>'} 2x average</p>
            </div>

            <div className="bg-gray-950/50 rounded p-3">
              <p className="text-gray-400 mb-1 font-semibold">Action:</p>
              <p className="text-white font-bold">STOP OUT at market immediately</p>
            </div>

            <div className="bg-gray-950/50 rounded p-3">
              <p className="text-gray-400 mb-1 font-semibold">Expected Loss:</p>
              <p className="text-white">~$50-70 per spread (manageable)</p>
            </div>

            <div className="bg-gray-950/50 rounded p-3">
              <p className="text-gray-400 mb-1 font-semibold">Why:</p>
              <p className="text-white">Mechanics failed. Dealers not selling enough. Paradigm shifted.</p>
            </div>

            <div className="mt-4 pt-4 border-t border-red-500/30">
              <div className="flex items-start gap-2">
                <XCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-red-300 font-bold mb-1">DON'T:</p>
                  <ul className="space-y-1 ml-4 text-gray-300">
                    <li>• Hope it comes back</li>
                    <li>• Move your stop lower</li>
                    <li>• Average down</li>
                    <li>• Hold "just one more day"</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Scenario 2: Volume Dies */}
        <div className="bg-yellow-500/10 border-2 border-yellow-500/30 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-4">
            <TrendingDown className="w-6 h-6 text-yellow-400" />
            <h3 className="text-xl font-bold text-yellow-300">Scenario 2: Volume Dies</h3>
          </div>

          <div className="space-y-3 text-sm">
            <div className="bg-gray-950/50 rounded p-3">
              <p className="text-gray-400 mb-1 font-semibold">Signal:</p>
              <p className="text-white">Volume drops {'<'} 1.5x avg for 2+ hours</p>
            </div>

            <div className="bg-gray-950/50 rounded p-3">
              <p className="text-gray-400 mb-1 font-semibold">Action:</p>
              <p className="text-white font-bold">Close position at small loss/gain</p>
            </div>

            <div className="bg-gray-950/50 rounded p-3">
              <p className="text-gray-400 mb-1 font-semibold">Expected Result:</p>
              <p className="text-white">Breakeven to -$20 per spread</p>
            </div>

            <div className="bg-gray-950/50 rounded p-3">
              <p className="text-gray-400 mb-1 font-semibold">Why:</p>
              <p className="text-white">No dealer flow = no edge. Exit before losing more.</p>
            </div>

            <div className="mt-4 pt-4 border-t border-yellow-500/30">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-yellow-300 font-bold mb-1">REMEMBER:</p>
                  <p className="text-gray-300">Your edge is dealer hedging. No volume = no hedging = no edge. Cut it.</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Scenario 3: IV Collapses */}
        <div className="bg-blue-500/10 border-2 border-blue-500/30 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-4">
            <TrendingDown className="w-6 h-6 text-blue-400" />
            <h3 className="text-xl font-bold text-blue-300">Scenario 3: IV Collapses</h3>
          </div>

          <div className="space-y-3 text-sm">
            <div className="bg-gray-950/50 rounded p-3">
              <p className="text-gray-400 mb-1 font-semibold">Signal:</p>
              <p className="text-white">IV rank drops to {'<'} 50% suddenly</p>
            </div>

            <div className="bg-gray-950/50 rounded p-3">
              <p className="text-gray-400 mb-1 font-semibold">Action:</p>
              <p className="text-white font-bold">Take profit early, even if small</p>
            </div>

            <div className="bg-gray-950/50 rounded p-3">
              <p className="text-gray-400 mb-1 font-semibold">Expected Result:</p>
              <p className="text-white">+$20-40 per spread (20-30%)</p>
            </div>

            <div className="bg-gray-950/50 rounded p-3">
              <p className="text-gray-400 mb-1 font-semibold">Why:</p>
              <p className="text-white">Premium too cheap. No theta edge left. Lock in gains.</p>
            </div>

            <div className="mt-4 pt-4 border-t border-blue-500/30">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-blue-300 font-bold mb-1">NOTE:</p>
                  <p className="text-gray-300">Small profit {'>'} risking it for 50%. Environment changed.</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Scenario 4: Major News */}
        <div className="bg-purple-500/10 border-2 border-purple-500/30 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-4">
            <Zap className="w-6 h-6 text-purple-400" />
            <h3 className="text-xl font-bold text-purple-300">Scenario 4: Major News Hits</h3>
          </div>

          <div className="space-y-3 text-sm">
            <div className="bg-gray-950/50 rounded p-3">
              <p className="text-gray-400 mb-1 font-semibold">Signal:</p>
              <p className="text-white">Unscheduled Fed/earnings/geopolitical event</p>
            </div>

            <div className="bg-gray-950/50 rounded p-3">
              <p className="text-gray-400 mb-1 font-semibold">Action:</p>
              <p className="text-white font-bold">Close immediately, reassess</p>
            </div>

            <div className="bg-gray-950/50 rounded p-3">
              <p className="text-gray-400 mb-1 font-semibold">Expected Result:</p>
              <p className="text-white">Variable (-$50 to +$30)</p>
            </div>

            <div className="bg-gray-950/50 rounded p-3">
              <p className="text-gray-400 mb-1 font-semibold">Why:</p>
              <p className="text-white">Paradigm shift. Dealer models irrelevant. Preserve capital.</p>
            </div>

            <div className="mt-4 pt-4 border-t border-purple-500/30">
              <div className="flex items-start gap-2">
                <Zap className="w-5 h-5 text-purple-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-purple-300 font-bold mb-1">CRITICAL:</p>
                  <p className="text-gray-300">Don't fight paradigm shifts. Close and wait for clarity.</p>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div>

      {/* Mindset Section */}
      <div className="bg-gray-950/50 rounded-lg p-6 mb-6">
        <h3 className="text-xl font-bold text-white mb-4">The Professional Trader Mindset:</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <div className="flex items-start gap-2">
            <XCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-red-300 font-bold mb-1">Amateur:</p>
              <p className="text-gray-300">"I'll hold and hope it comes back. I can't take a loss."</p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-green-300 font-bold mb-1">Professional:</p>
              <p className="text-gray-300">"Setup failed. Cut loss quickly. Preserve capital for next trade."</p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <XCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-red-300 font-bold mb-1">Amateur:</p>
              <p className="text-gray-300">"I was right earlier, I'll move my stop and give it more room."</p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-green-300 font-bold mb-1">Professional:</p>
              <p className="text-gray-300">"Market invalidated my thesis. Stops are hard limits. Exit now."</p>
            </div>
          </div>
        </div>
      </div>

      {/* Key Rules */}
      <div className="bg-gradient-to-r from-orange-600/20 to-red-600/20 border border-orange-500/30 rounded-lg p-5">
        <h3 className="text-lg font-bold text-white mb-3">Non-Negotiable Rules:</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
          <div className="flex items-start gap-2">
            <span className="text-orange-400">1.</span>
            <span className="text-gray-200"><strong>Never</strong> move stops to "give it more room"</span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-orange-400">2.</span>
            <span className="text-gray-200"><strong>Never</strong> average down on a losing trade</span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-orange-400">3.</span>
            <span className="text-gray-200"><strong>Never</strong> hold hoping for breakeven</span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-orange-400">4.</span>
            <span className="text-gray-200"><strong>Never</strong> let small loss become big loss</span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-orange-400">5.</span>
            <span className="text-gray-200"><strong>Always</strong> accept when setup fails</span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-orange-400">6.</span>
            <span className="text-gray-200"><strong>Always</strong> preserve capital for next trade</span>
          </div>
        </div>
      </div>

      {/* Bottom Line */}
      <div className="mt-6 bg-gradient-to-r from-red-600/20 to-orange-600/20 border border-red-500/30 rounded-lg p-4">
        <p className="text-center text-lg text-white">
          <span className="font-bold text-orange-400">Being wrong is not the problem. Staying wrong is.</span>
          <br />
          <span className="text-sm text-gray-300">Cut losses fast. Let winners run. This is the edge.</span>
        </p>
      </div>
    </div>
  )
}
