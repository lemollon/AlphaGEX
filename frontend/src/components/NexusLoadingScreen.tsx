'use client'

import { useState, useEffect } from 'react'
import NexusCanvas, { BotStatus } from './NexusCanvas'

// =============================================================================
// TYPES
// =============================================================================

interface NexusLoadingScreenProps {
  /** Main loading message */
  message?: string
  /** Sub-message or status */
  subMessage?: string
  /** Show progress bar */
  showProgress?: boolean
  /** Progress value (0-100) */
  progress?: number
  /** Real-time bot status */
  botStatus?: BotStatus
  /** Callback when loading completes */
  onComplete?: () => void
  /** Callback when a node is clicked */
  onNodeClick?: (nodeId: string) => void
  /** Optional loading tips to cycle through */
  tips?: string[]
  /** Duration to show each tip (ms) */
  tipDuration?: number
  /** Show the tips section */
  showTips?: boolean
}

// =============================================================================
// DEFAULT TIPS
// =============================================================================

const DEFAULT_TIPS = [
  "GEX flips signal dealer gamma crossing zero - watch for explosive moves",
  "Negative GEX means dealers chase price - expect higher volatility",
  "Call walls act as resistance, put walls as support",
  "FORTRESS hunts Iron Condor opportunities when volatility spikes",
  "SOLOMON captures directional momentum with GEX-aligned spreads",
  "LAZARUS targets 0DTE gamma scalps during high-activity periods",
  "CORNERSTONE wheels premium through systematic SPX strategies",
  "ORACLE's ML models predict direction with 65%+ accuracy",
  "Psychology traps catch 90% of traders - we exploit their fear",
  "VIX below 15 = complacency. Above 30 = panic. Both create edge",
]

// =============================================================================
// COMPONENT
// =============================================================================

export default function NexusLoadingScreen({
  message = 'Initializing NEXUS',
  subMessage = 'Connecting to GEX Core...',
  showProgress = false,
  progress = 0,
  botStatus,
  onComplete,
  onNodeClick,
  tips = DEFAULT_TIPS,
  tipDuration = 4000,
  showTips = true,
}: NexusLoadingScreenProps) {
  const [currentTipIndex, setCurrentTipIndex] = useState(0)
  const [tipOpacity, setTipOpacity] = useState(1)
  const [loadingDots, setLoadingDots] = useState('')

  // Cycle through tips with fade effect
  useEffect(() => {
    if (!showTips || tips.length === 0) return

    const interval = setInterval(() => {
      setTipOpacity(0)
      setTimeout(() => {
        setCurrentTipIndex(prev => (prev + 1) % tips.length)
        setTipOpacity(1)
      }, 300)
    }, tipDuration)

    return () => clearInterval(interval)
  }, [tips, tipDuration, showTips])

  // Animate loading dots
  useEffect(() => {
    const interval = setInterval(() => {
      setLoadingDots(prev => {
        if (prev.length >= 3) return ''
        return prev + '.'
      })
    }, 500)

    return () => clearInterval(interval)
  }, [])

  // Handle completion
  useEffect(() => {
    if (showProgress && progress >= 100 && onComplete) {
      const timeout = setTimeout(onComplete, 500)
      return () => clearTimeout(timeout)
    }
  }, [progress, showProgress, onComplete])

  return (
    <div className="fixed inset-0 z-50 bg-background-deep flex flex-col">
      {/* NEXUS Canvas - Full Screen Background */}
      <div className="absolute inset-0">
        <NexusCanvas
          botStatus={botStatus}
          onNodeClick={onNodeClick}
          showLabels={true}
        />
      </div>

      {/* Gradient Overlays for better text readability */}
      <div className="absolute inset-0 pointer-events-none">
        {/* Top fade */}
        <div className="absolute top-0 left-0 right-0 h-32 bg-gradient-to-b from-background-deep/80 to-transparent" />
        {/* Bottom fade */}
        <div className="absolute bottom-0 left-0 right-0 h-48 bg-gradient-to-t from-background-deep/90 to-transparent" />
      </div>

      {/* Content Overlay */}
      <div className="relative z-10 flex flex-col h-full">
        {/* Top Header */}
        <div className="pt-8 px-8 text-center">
          <div className="inline-flex items-center space-x-3">
            <div className="relative">
              <div className="w-3 h-3 rounded-full bg-primary animate-pulse" />
              <div className="absolute inset-0 w-3 h-3 rounded-full bg-primary animate-ping" />
            </div>
            <span className="text-text-secondary text-sm font-medium tracking-wider uppercase">
              AlphaGEX NEXUS Interface
            </span>
          </div>
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Bottom Loading Info */}
        <div className="pb-12 px-8">
          <div className="max-w-2xl mx-auto text-center">
            {/* Loading Message */}
            <h1 className="text-2xl md:text-3xl font-bold text-text-primary mb-2">
              {message}
              <span className="text-primary">{loadingDots}</span>
            </h1>

            <p className="text-text-secondary text-sm md:text-base mb-6">
              {subMessage}
            </p>

            {/* Progress Bar */}
            {showProgress && (
              <div className="mb-6">
                <div className="w-full max-w-md mx-auto">
                  <div className="flex justify-between text-xs text-text-muted mb-1">
                    <span>Initializing</span>
                    <span>{Math.round(progress)}%</span>
                  </div>
                  <div className="w-full h-2 bg-background-card rounded-full overflow-hidden border border-gray-700">
                    <div
                      className="h-full bg-gradient-to-r from-primary to-cyan-400 transition-all duration-300 ease-out"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Tip Section */}
            {showTips && tips.length > 0 && (
              <div className="mt-6">
                <div className="inline-block bg-background-card/80 backdrop-blur-sm rounded-lg px-6 py-4 border border-gray-700/50">
                  <div className="flex items-start space-x-3">
                    <span className="text-primary text-xs font-semibold tracking-wider uppercase flex-shrink-0 mt-0.5">
                      PRO TIP
                    </span>
                    <p
                      className="text-text-secondary text-sm text-left transition-opacity duration-300"
                      style={{ opacity: tipOpacity }}
                    >
                      {tips[currentTipIndex]}
                    </p>
                  </div>
                </div>

                {/* Tip Indicators */}
                <div className="flex justify-center space-x-1.5 mt-4">
                  {tips.map((_, idx) => (
                    <div
                      key={idx}
                      className={`h-1 rounded-full transition-all duration-300 ${
                        idx === currentTipIndex
                          ? 'w-6 bg-primary'
                          : 'w-1.5 bg-gray-600'
                      }`}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Bot Status Quick View */}
            {botStatus && (
              <div className="mt-6 flex justify-center space-x-4">
                {Object.entries(botStatus).map(([bot, status]) => (
                  <div
                    key={bot}
                    className="flex items-center space-x-2 text-xs"
                  >
                    <div
                      className={`w-2 h-2 rounded-full ${
                        status === 'active'
                          ? 'bg-success'
                          : status === 'trading'
                          ? 'bg-warning animate-pulse'
                          : status === 'error'
                          ? 'bg-danger'
                          : 'bg-gray-500'
                      }`}
                    />
                    <span className="text-text-muted uppercase tracking-wider">
                      {bot}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
