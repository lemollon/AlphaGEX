import { DollarSign, Target, TrendingUp, TrendingDown, AlertCircle, CheckCircle2, XCircle, Clock, BarChart3, Zap } from 'lucide-react'

interface TradingGuideProps {
  guide: {
    strategy: string
    entry_rules: string[]
    exit_rules: string[]
    strike_selection: string
    position_sizing: string
    win_rate: number
    avg_gain: string
    max_loss: string
    time_horizon: string
    why_it_works: string
    example_trade: {
      setup: string
      entry: string
      cost: string
      target: string
      stop: string
      expected: string
    }
  }
  currentPrice: number
}

export default function TradingGuide({ guide, currentPrice }: TradingGuideProps) {
  return (
    <div className="bg-gradient-to-br from-green-900/20 to-emerald-900/20 border-2 border-green-500/40 rounded-xl p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <DollarSign className="w-6 h-6 text-green-400" />
            <h2 className="text-2xl font-bold text-green-400">HOW TO MAKE MONEY</h2>
          </div>
          <div className="text-3xl font-bold text-white">
            {guide.strategy}
          </div>
        </div>

        <div className="text-right">
          <div className="text-sm text-gray-400">Expected Win Rate</div>
          <div className="text-3xl font-bold text-green-400">{guide.win_rate}%</div>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-900/50 rounded-lg p-4">
          <div className="flex items-center gap-2 text-green-400 mb-1">
            <TrendingUp className="w-4 h-4" />
            <span className="text-sm">Average Gain</span>
          </div>
          <div className="text-2xl font-bold">{guide.avg_gain}</div>
        </div>

        <div className="bg-gray-900/50 rounded-lg p-4">
          <div className="flex items-center gap-2 text-red-400 mb-1">
            <TrendingDown className="w-4 h-4" />
            <span className="text-sm">Max Loss</span>
          </div>
          <div className="text-2xl font-bold">{guide.max_loss}</div>
        </div>

        <div className="bg-gray-900/50 rounded-lg p-4">
          <div className="flex items-center gap-2 text-blue-400 mb-1">
            <Clock className="w-4 h-4" />
            <span className="text-sm">Time Horizon</span>
          </div>
          <div className="text-xl font-bold">{guide.time_horizon}</div>
        </div>
      </div>

      {/* Entry Rules */}
      <div className="bg-gray-900/50 rounded-lg p-5">
        <div className="flex items-center gap-2 mb-3">
          <CheckCircle2 className="w-5 h-5 text-green-400" />
          <h3 className="text-lg font-bold">ENTRY RULES</h3>
        </div>
        <div className="space-y-2">
          {guide.entry_rules.map((rule, idx) => (
            <div key={idx} className="flex items-start gap-2">
              <div className="w-6 h-6 rounded-full bg-green-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                <span className="text-sm font-bold text-green-400">{idx + 1}</span>
              </div>
              <div className="text-gray-200">{rule}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Strike Selection - HIGHLIGHTED */}
      <div className="bg-yellow-500/10 border-2 border-yellow-500/40 rounded-lg p-5">
        <div className="flex items-center gap-2 mb-2">
          <Target className="w-5 h-5 text-yellow-400" />
          <h3 className="text-lg font-bold text-yellow-400">STRIKE SELECTION</h3>
        </div>
        <div className="text-xl font-bold text-white">{guide.strike_selection}</div>
        <div className="text-sm text-gray-400 mt-2">
          <strong>Position Sizing:</strong> {guide.position_sizing}
        </div>
      </div>

      {/* Exit Rules */}
      <div className="bg-gray-900/50 rounded-lg p-5">
        <div className="flex items-center gap-2 mb-3">
          <XCircle className="w-5 h-5 text-orange-400" />
          <h3 className="text-lg font-bold">EXIT RULES</h3>
        </div>
        <div className="space-y-2">
          {guide.exit_rules.map((rule, idx) => (
            <div key={idx} className="flex items-start gap-2">
              <div className="w-6 h-6 rounded-full bg-orange-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                <span className="text-sm font-bold text-orange-400">{idx + 1}</span>
              </div>
              <div className="text-gray-200">{rule}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Why It Works */}
      <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-5">
        <div className="flex items-center gap-2 mb-3">
          <BarChart3 className="w-5 h-5 text-blue-400" />
          <h3 className="text-lg font-bold text-blue-400">WHY THIS WORKS</h3>
        </div>
        <div className="text-gray-200 leading-relaxed whitespace-pre-line">
          {guide.why_it_works}
        </div>
      </div>

      {/* Example Trade - SUPER EXPLICIT */}
      <div className="bg-gradient-to-r from-purple-500/10 to-pink-500/10 border-2 border-purple-500/40 rounded-lg p-6">
        <div className="flex items-center gap-2 mb-4">
          <Zap className="w-6 h-6 text-purple-400" />
          <h3 className="text-xl font-bold text-purple-400">CONCRETE EXAMPLE TRADE</h3>
        </div>

        <div className="space-y-4">
          {/* Setup */}
          <div>
            <div className="text-sm font-semibold text-purple-400 mb-1">THE SETUP</div>
            <div className="text-lg text-white">{guide.example_trade.setup}</div>
          </div>

          {/* Entry */}
          <div className="bg-gray-900/50 rounded-lg p-4">
            <div className="text-sm font-semibold text-green-400 mb-2">✓ YOUR ENTRY</div>
            <div className="text-white font-mono mb-2">{guide.example_trade.entry}</div>
            <div className="text-yellow-400 font-bold">Cost: {guide.example_trade.cost}</div>
          </div>

          {/* Target */}
          <div className="bg-gray-900/50 rounded-lg p-4">
            <div className="text-sm font-semibold text-green-400 mb-2">🎯 TARGET</div>
            <div className="text-white mb-2">{guide.example_trade.target}</div>
          </div>

          {/* Stop */}
          <div className="bg-gray-900/50 rounded-lg p-4">
            <div className="text-sm font-semibold text-red-400 mb-2">🛑 STOP LOSS</div>
            <div className="text-white">{guide.example_trade.stop}</div>
          </div>

          {/* Expected Outcome */}
          <div className="bg-green-500/20 border border-green-500/40 rounded-lg p-4">
            <div className="text-sm font-semibold text-green-400 mb-2">💰 EXPECTED PROFIT</div>
            <div className="text-2xl font-bold text-green-400">{guide.example_trade.expected}</div>
          </div>
        </div>
      </div>

      {/* Action Alert */}
      <div className="bg-yellow-500/20 border-2 border-yellow-500 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-6 h-6 text-yellow-400 flex-shrink-0" />
          <div>
            <div className="font-bold text-yellow-400 mb-1">REMEMBER:</div>
            <div className="text-sm text-gray-200">
              This is not financial advice - these are the mechanics of how market makers operate.
              Always use proper risk management and never risk more than you can afford to lose.
              The win rate of {guide.win_rate}% means you will have losing trades - size positions accordingly.
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
