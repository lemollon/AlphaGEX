'use client'

import { useState } from 'react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import {
  Calculator,
  TrendingUp,
  DollarSign,
  Target,
  AlertCircle,
  CheckCircle,
  Award
} from 'lucide-react'

interface CalculationResult {
  calculations: {
    kelly_percentage: number
    kelly_percentage_capped: number
    reward_to_risk_ratio: number
    expected_value: number
    expected_value_pct: number
    recommendation: string
  }
  positions: {
    full_kelly: {
      dollars: number
      contracts: number
      percentage: number
    }
    half_kelly: {
      dollars: number
      contracts: number
      percentage: number
    }
    fixed_risk: {
      dollars: number
      contracts: number
      percentage: number
    }
  }
  money_making_guide: string
}

export default function PositionSizingPage() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<CalculationResult | null>(null)

  // Input fields
  const [accountSize, setAccountSize] = useState('50000')
  const [winRate, setWinRate] = useState('65')
  const [avgWin, setAvgWin] = useState('300')
  const [avgLoss, setAvgLoss] = useState('150')
  const [currentPrice, setCurrentPrice] = useState('2.50')
  const [riskPerTradePct, setRiskPerTradePct] = useState('2.0')

  const handleCalculate = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)

    try {
      const response = await apiClient.calculatePositionSize({
        account_size: parseFloat(accountSize),
        win_rate: parseFloat(winRate) / 100,
        avg_win: parseFloat(avgWin),
        avg_loss: parseFloat(avgLoss),
        current_price: parseFloat(currentPrice),
        risk_per_trade_pct: parseFloat(riskPerTradePct)
      })

      if (response.data.success) {
        setResult(response.data)
      }
    } catch (error) {
      console.error('Error calculating position size:', error)
      alert('Failed to calculate. Please check your inputs.')
    } finally {
      setLoading(false)
    }
  }

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2
    }).format(value)
  }

  const getRecommendationColor = (rec: string) => {
    if (rec === 'FULL KELLY') return 'text-danger'
    if (rec === 'HALF KELLY') return 'text-success'
    return 'text-warning'
  }

  const getRecommendationBadge = (rec: string) => {
    if (rec === 'FULL KELLY') return 'bg-danger/20 text-danger'
    if (rec === 'HALF KELLY') return 'bg-success/20 text-success'
    return 'bg-warning/20 text-warning'
  }

  return (
    <div className="min-h-screen">
      <Navigation />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-text-primary flex items-center space-x-3">
            <Calculator className="w-8 h-8 text-primary" />
            <span>Position Sizing Calculator</span>
          </h1>
          <p className="text-text-secondary mt-2">
            Calculate optimal position size using Kelly Criterion for maximum edge
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Input Form */}
          <div className="card">
            <h2 className="text-xl font-semibold mb-6 flex items-center space-x-2">
              <DollarSign className="w-5 h-5 text-primary" />
              <span>Your Trading Stats</span>
            </h2>

            <form onSubmit={handleCalculate} className="space-y-4">
              {/* Account Size */}
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Account Size ($)
                </label>
                <input
                  type="number"
                  step="1000"
                  value={accountSize}
                  onChange={(e) => setAccountSize(e.target.value)}
                  className="w-full px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary font-mono"
                  required
                />
                <p className="text-xs text-text-muted mt-1">Your total trading capital</p>
              </div>

              {/* Win Rate */}
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Win Rate (%)
                </label>
                <input
                  type="number"
                  step="1"
                  min="0"
                  max="100"
                  value={winRate}
                  onChange={(e) => setWinRate(e.target.value)}
                  className="w-full px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary font-mono"
                  required
                />
                <p className="text-xs text-text-muted mt-1">Percentage of winning trades (e.g., 65%)</p>
              </div>

              {/* Average Win */}
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Average Win ($)
                </label>
                <input
                  type="number"
                  step="10"
                  value={avgWin}
                  onChange={(e) => setAvgWin(e.target.value)}
                  className="w-full px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary font-mono"
                  required
                />
                <p className="text-xs text-text-muted mt-1">Average profit per winning trade</p>
              </div>

              {/* Average Loss */}
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Average Loss ($)
                </label>
                <input
                  type="number"
                  step="10"
                  value={avgLoss}
                  onChange={(e) => setAvgLoss(e.target.value)}
                  className="w-full px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary font-mono"
                  required
                />
                <p className="text-xs text-text-muted mt-1">Average loss per losing trade</p>
              </div>

              {/* Current Price */}
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Option Price ($)
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={currentPrice}
                  onChange={(e) => setCurrentPrice(e.target.value)}
                  className="w-full px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary font-mono"
                  required
                />
                <p className="text-xs text-text-muted mt-1">Current option premium per contract</p>
              </div>

              {/* Risk per Trade */}
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Max Risk per Trade (%)
                </label>
                <input
                  type="number"
                  step="0.5"
                  value={riskPerTradePct}
                  onChange={(e) => setRiskPerTradePct(e.target.value)}
                  className="w-full px-4 py-2 bg-background-deep border border-gray-700 rounded-lg text-text-primary font-mono"
                  required
                />
                <p className="text-xs text-text-muted mt-1">Maximum % of account to risk (usually 1-2%)</p>
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={loading}
                className="btn-primary w-full py-3 text-lg disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Calculating...' : 'Calculate Position Size'}
              </button>
            </form>

            {/* Quick Presets */}
            <div className="mt-6 pt-6 border-t border-gray-800">
              <p className="text-sm font-medium text-text-secondary mb-3">Quick Presets:</p>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => {
                    setWinRate('65')
                    setAvgWin('300')
                    setAvgLoss('150')
                  }}
                  className="text-xs btn-secondary py-2"
                >
                  Good Strategy (65% / 2:1)
                </button>
                <button
                  onClick={() => {
                    setWinRate('55')
                    setAvgWin('500')
                    setAvgLoss('200')
                  }}
                  className="text-xs btn-secondary py-2"
                >
                  High R:R (55% / 2.5:1)
                </button>
                <button
                  onClick={() => {
                    setWinRate('72')
                    setAvgWin('100')
                    setAvgLoss('300')
                  }}
                  className="text-xs btn-secondary py-2"
                >
                  Iron Condor (72% / 0.3:1)
                </button>
                <button
                  onClick={() => {
                    setWinRate('50')
                    setAvgWin('200')
                    setAvgLoss('200')
                  }}
                  className="text-xs btn-secondary py-2"
                >
                  Breakeven (50% / 1:1)
                </button>
              </div>
            </div>
          </div>

          {/* Results */}
          <div className="space-y-6">
            {result ? (
              <>
                {/* Recommendation */}
                <div className="card bg-primary/10 border-primary/30">
                  <div className="flex items-center space-x-3 mb-4">
                    <Award className="w-6 h-6 text-primary" />
                    <h2 className="text-xl font-semibold">Recommendation</h2>
                  </div>
                  <div className={`text-3xl font-bold mb-2 ${getRecommendationColor(result.calculations.recommendation)}`}>
                    {result.calculations.recommendation}
                  </div>
                  <div className="text-sm text-text-secondary">
                    Based on your win rate and R:R ratio
                  </div>
                </div>

                {/* Key Stats */}
                <div className="card">
                  <h3 className="text-lg font-semibold mb-4">Key Metrics</h3>
                  <div className="space-y-3">
                    <div className="flex justify-between items-center p-3 bg-background-hover rounded-lg">
                      <span className="text-text-secondary">Kelly %</span>
                      <span className="font-semibold text-text-primary">
                        {(result.calculations.kelly_percentage_capped * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="flex justify-between items-center p-3 bg-background-hover rounded-lg">
                      <span className="text-text-secondary">Reward:Risk</span>
                      <span className="font-semibold text-success">
                        {result.calculations.reward_to_risk_ratio.toFixed(2)}:1
                      </span>
                    </div>
                    <div className="flex justify-between items-center p-3 bg-background-hover rounded-lg">
                      <span className="text-text-secondary">Expected Value</span>
                      <span className={`font-semibold ${result.calculations.expected_value > 0 ? 'text-success' : 'text-danger'}`}>
                        {formatCurrency(result.calculations.expected_value)}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Position Sizes */}
                <div className="card">
                  <h3 className="text-lg font-semibold mb-4">Position Sizes</h3>
                  <div className="space-y-4">
                    {/* Full Kelly */}
                    <div className="p-4 bg-danger/10 border border-danger/30 rounded-lg">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-semibold text-danger">Full Kelly (Aggressive)</span>
                        <span className="text-xs px-2 py-1 bg-danger/20 text-danger rounded">
                          {result.positions.full_kelly.percentage.toFixed(1)}%
                        </span>
                      </div>
                      <div className="text-2xl font-bold text-text-primary mb-1">
                        {result.positions.full_kelly.contracts} contracts
                      </div>
                      <div className="text-sm text-text-secondary">
                        {formatCurrency(result.positions.full_kelly.dollars)} risk
                      </div>
                    </div>

                    {/* Half Kelly */}
                    <div className="p-4 bg-success/10 border border-success/30 rounded-lg">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-semibold text-success">Half Kelly (Recommended)</span>
                        <span className="text-xs px-2 py-1 bg-success/20 text-success rounded">
                          {result.positions.half_kelly.percentage.toFixed(1)}%
                        </span>
                      </div>
                      <div className="text-2xl font-bold text-text-primary mb-1">
                        {result.positions.half_kelly.contracts} contracts
                      </div>
                      <div className="text-sm text-text-secondary">
                        {formatCurrency(result.positions.half_kelly.dollars)} risk
                      </div>
                    </div>

                    {/* Fixed Risk */}
                    <div className="p-4 bg-warning/10 border border-warning/30 rounded-lg">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-semibold text-warning">Fixed Risk (Conservative)</span>
                        <span className="text-xs px-2 py-1 bg-warning/20 text-warning rounded">
                          {result.positions.fixed_risk.percentage.toFixed(1)}%
                        </span>
                      </div>
                      <div className="text-2xl font-bold text-text-primary mb-1">
                        {result.positions.fixed_risk.contracts} contracts
                      </div>
                      <div className="text-sm text-text-secondary">
                        {formatCurrency(result.positions.fixed_risk.dollars)} risk
                      </div>
                    </div>
                  </div>
                </div>

                {/* Money Making Guide */}
                <div className="card">
                  <h3 className="text-lg font-semibold mb-4">Complete Money-Making Guide</h3>
                  <div className="bg-background-deep rounded-lg p-6">
                    <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-text-primary overflow-x-auto">
                      {result.money_making_guide}
                    </pre>
                  </div>
                </div>
              </>
            ) : (
              <div className="card text-center py-12">
                <Calculator className="w-16 h-16 mx-auto mb-4 text-text-muted opacity-50" />
                <p className="text-text-muted mb-2">No calculation yet</p>
                <p className="text-sm text-text-secondary">
                  Enter your trading stats and click Calculate
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Info Card */}
        <div className="card mt-8 bg-primary/10 border-primary/30">
          <div className="flex items-start space-x-3">
            <AlertCircle className="w-5 h-5 text-primary mt-1 flex-shrink-0" />
            <div className="text-sm text-text-secondary">
              <p className="font-semibold text-text-primary mb-2">What is Kelly Criterion?</p>
              <p className="mb-2">
                Kelly Criterion is a mathematical formula that tells you the optimal % of your account to risk on each trade
                to maximize long-term growth. It factors in your win rate and average win/loss ratio.
              </p>
              <p className="font-semibold text-text-primary mb-2">How to Use This:</p>
              <ul className="space-y-1 list-disc list-inside">
                <li>Track your last 30+ trades to get accurate win rate and R:R</li>
                <li>Start with Half Kelly until you prove your edge over 100+ trades</li>
                <li>If Expected Value is negative, DO NOT TRADE - fix your strategy first</li>
                <li>Recalculate monthly as your stats improve</li>
                <li>Never risk more than 2-3% of account per trade (even if Kelly says more)</li>
              </ul>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
