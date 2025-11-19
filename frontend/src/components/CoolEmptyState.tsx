'use client'

import { LucideIcon } from 'lucide-react'
import { useEffect, useState } from 'react'

interface CoolEmptyStateProps {
  icon: LucideIcon
  title: string
  description: string
  ctaText?: string
  ctaAction?: () => void
  showProgress?: boolean
  estimatedDays?: number
  variant?: 'default' | 'gradient' | 'glow'
}

export default function CoolEmptyState({
  icon: Icon,
  title,
  description,
  ctaText,
  ctaAction,
  showProgress = false,
  estimatedDays = 30,
  variant = 'gradient'
}: CoolEmptyStateProps) {
  const [progress, setProgress] = useState(0)
  const [daysElapsed, setDaysElapsed] = useState(0)

  useEffect(() => {
    if (showProgress) {
      // Simulate some progress based on time
      const timer = setInterval(() => {
        setProgress(prev => Math.min(prev + 0.5, 15)) // Max 15% for demo
      }, 100)

      // Simulate days elapsed (for demo, we'll show 1-3 days)
      setDaysElapsed(Math.floor(Math.random() * 3) + 1)

      return () => clearInterval(timer)
    }
  }, [showProgress])

  const progressPercent = Math.min((daysElapsed / estimatedDays) * 100, 100)

  if (variant === 'glow') {
    return (
      <div className="relative overflow-hidden bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 border border-gray-700 rounded-xl p-12 text-center">
        {/* Animated glow effect */}
        <div className="absolute inset-0 opacity-20">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 rounded-full blur-3xl animate-pulse"></div>
        </div>

        <div className="relative z-10">
          <div className="relative inline-block mb-6">
            <div className="absolute inset-0 bg-gradient-to-r from-blue-400 to-purple-400 rounded-full blur-xl opacity-50 animate-pulse"></div>
            <Icon className="relative w-20 h-20 mx-auto text-gray-300" />
          </div>

          <h2 className="text-3xl font-bold mb-4 bg-gradient-to-r from-blue-300 via-purple-300 to-pink-300 bg-clip-text text-transparent">
            {title}
          </h2>
          <p className="text-gray-300 text-lg mb-8 max-w-2xl mx-auto">
            {description}
          </p>

          {showProgress && (
            <div className="mb-8 max-w-md mx-auto">
              <div className="flex justify-between text-sm text-gray-400 mb-2">
                <span>Data Collection Progress</span>
                <span>{daysElapsed} of {estimatedDays} days</span>
              </div>
              <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 transition-all duration-500 ease-out"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <p className="text-xs text-gray-500 mt-2">
                Charts will populate as data accumulates • Check back daily for updates
              </p>
            </div>
          )}

          {ctaText && ctaAction && (
            <button
              onClick={ctaAction}
              className="group relative px-8 py-4 bg-gradient-to-r from-blue-600 via-purple-600 to-pink-600 hover:from-blue-500 hover:via-purple-500 hover:to-pink-500 text-white font-semibold rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 transform hover:scale-105"
            >
              <span className="relative z-10">{ctaText}</span>
              <div className="absolute inset-0 rounded-xl bg-gradient-to-r from-blue-400 to-pink-400 opacity-0 group-hover:opacity-20 blur transition-opacity"></div>
            </button>
          )}
        </div>
      </div>
    )
  }

  if (variant === 'gradient') {
    return (
      <div className="relative bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 border-2 border-dashed border-gray-700 rounded-xl p-12 text-center overflow-hidden">
        {/* Animated background pattern */}
        <div className="absolute inset-0 opacity-5">
          <div className="absolute inset-0" style={{
            backgroundImage: 'radial-gradient(circle at 2px 2px, rgba(255,255,255,0.15) 1px, transparent 0)',
            backgroundSize: '40px 40px'
          }}></div>
        </div>

        <div className="relative z-10">
          <div className="mb-6 inline-block">
            <div className="relative">
              <div className="absolute inset-0 bg-gradient-to-r from-blue-500 to-purple-500 rounded-2xl blur-lg opacity-30 animate-pulse"></div>
              <div className="relative bg-gray-800 p-5 rounded-2xl">
                <Icon className="w-16 h-16 text-gray-400" />
              </div>
            </div>
          </div>

          <h2 className="text-3xl font-bold mb-4 text-white">
            {title}
          </h2>
          <p className="text-gray-400 text-lg mb-8 max-w-2xl mx-auto leading-relaxed">
            {description}
          </p>

          {showProgress && (
            <div className="mb-8 max-w-md mx-auto">
              <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 backdrop-blur-sm">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-sm font-medium text-gray-300">Building History</span>
                  <span className="text-xs text-gray-500">{daysElapsed}/{estimatedDays} days</span>
                </div>
                <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-blue-500 to-purple-500 transition-all duration-1000 ease-out rounded-full"
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
                <div className="mt-3 flex items-center justify-center gap-2">
                  <div className="flex gap-1">
                    {[...Array(3)].map((_, i) => (
                      <div
                        key={i}
                        className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse"
                        style={{ animationDelay: `${i * 0.2}s` }}
                      />
                    ))}
                  </div>
                  <span className="text-xs text-gray-400">Collecting data automatically</span>
                </div>
              </div>
            </div>
          )}

          {ctaText && ctaAction && (
            <button
              onClick={ctaAction}
              className="inline-flex items-center gap-3 px-8 py-4 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white font-semibold rounded-xl shadow-lg hover:shadow-2xl transition-all duration-300 transform hover:scale-105 hover:-translate-y-1"
            >
              {ctaText}
            </button>
          )}
        </div>
      </div>
    )
  }

  // Default variant
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl p-12 text-center">
      <Icon className="w-20 h-20 mx-auto mb-6 text-gray-600" />
      <h2 className="text-3xl font-bold mb-4 text-white">{title}</h2>
      <p className="text-gray-400 text-lg mb-8 max-w-2xl mx-auto">{description}</p>

      {showProgress && (
        <div className="mb-8 max-w-md mx-auto">
          <div className="flex justify-between text-sm text-gray-400 mb-2">
            <span>Progress</span>
            <span>{daysElapsed}/{estimatedDays} days</span>
          </div>
          <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-500"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      )}

      {ctaText && ctaAction && (
        <button
          onClick={ctaAction}
          className="px-8 py-4 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-xl transition-colors"
        >
          {ctaText}
        </button>
      )}
    </div>
  )
}
