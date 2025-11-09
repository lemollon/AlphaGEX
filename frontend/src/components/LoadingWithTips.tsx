'use client'

import { useState, useEffect } from 'react'
import { Lightbulb, TrendingUp, Target, Zap, AlertTriangle, Brain } from 'lucide-react'

const TRADING_TIPS = [
  {
    icon: TrendingUp,
    text: "GEX flips happen when dealer gamma crosses zero - watch for explosive moves!",
    color: "text-primary"
  },
  {
    icon: Target,
    text: "Call walls act as resistance. Price tends to pin near max pain on expiration.",
    color: "text-success"
  },
  {
    icon: Zap,
    text: "Negative GEX means dealers are short gamma - expect higher volatility.",
    color: "text-warning"
  },
  {
    icon: AlertTriangle,
    text: "VIX below 15 = complacency. Above 30 = panic. Both create opportunities.",
    color: "text-danger"
  },
  {
    icon: Brain,
    text: "Psychology traps catch 90% of traders. Liberation setups break through gamma walls.",
    color: "text-primary"
  },
  {
    icon: Lightbulb,
    text: "0DTE gamma creates intraday magnets. Watch Friday PM for max gamma effects.",
    color: "text-success"
  },
  {
    icon: Target,
    text: "Dealer hedging amplifies moves. Negative GEX = dealers chase price in same direction.",
    color: "text-warning"
  },
  {
    icon: TrendingUp,
    text: "Best trades align multiple timeframes: GEX + RSI + psychology all confirming.",
    color: "text-primary"
  },
  {
    icon: Zap,
    text: "Market makers defend their deltas. Watch for resistance at call walls!",
    color: "text-danger"
  },
  {
    icon: Brain,
    text: "FOMO and Fear are quantifiable. Use psychology metrics to fade the crowd.",
    color: "text-success"
  }
]

interface LoadingWithTipsProps {
  message?: string
  showProgress?: boolean
  progress?: number
  total?: number
}

export default function LoadingWithTips({
  message = "Loading data...",
  showProgress = false,
  progress = 0,
  total = 100
}: LoadingWithTipsProps) {
  const [currentTip, setCurrentTip] = useState(0)

  useEffect(() => {
    // Rotate tips every 3 seconds
    const interval = setInterval(() => {
      setCurrentTip((prev) => (prev + 1) % TRADING_TIPS.length)
    }, 3000)

    return () => clearInterval(interval)
  }, [])

  const tip = TRADING_TIPS[currentTip]
  const Icon = tip.icon
  const progressPercent = total > 0 ? (progress / total) * 100 : 0

  return (
    <div className="card border-2 border-primary/30 bg-gradient-to-br from-background-card to-background-deep">
      <div className="flex items-start space-x-4">
        {/* Animated Spinner */}
        <div className="relative flex-shrink-0">
          <div className="w-12 h-12 border-4 border-primary/20 rounded-full"></div>
          <div className="absolute top-0 left-0 w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
        </div>

        {/* Content */}
        <div className="flex-1">
          <h3 className="text-lg font-semibold text-text-primary mb-2">{message}</h3>

          {/* Progress Bar */}
          {showProgress && (
            <div className="mb-4">
              <div className="w-full bg-background-deep rounded-full h-2 overflow-hidden">
                <div
                  className="bg-primary h-full transition-all duration-300 ease-out"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <p className="text-xs text-text-muted mt-1">
                {progress} of {total} loaded ({Math.round(progressPercent)}%)
              </p>
            </div>
          )}

          {/* Rotating Tips */}
          <div className="bg-background-deep rounded-lg p-4 border border-gray-700">
            <div className="flex items-start space-x-3">
              <Icon className={`w-5 h-5 ${tip.color} flex-shrink-0 mt-0.5`} />
              <div className="flex-1">
                <p className="text-sm text-text-secondary">
                  <span className="font-semibold text-text-primary">Pro Tip:</span> {tip.text}
                </p>
              </div>
            </div>
          </div>

          {/* Indicator Dots */}
          <div className="flex items-center justify-center space-x-2 mt-3">
            {TRADING_TIPS.map((_, idx) => (
              <div
                key={idx}
                className={`h-1.5 rounded-full transition-all duration-300 ${
                  idx === currentTip
                    ? 'w-6 bg-primary'
                    : 'w-1.5 bg-gray-600'
                }`}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
