'use client'

import { TrendingUp } from 'lucide-react'
import { useEffect, useState } from 'react'

interface TrendBuildingPlaceholderProps {
  title: string
  dataPoints: number
  requiredPoints?: number
  showMiniChart?: boolean
}

export default function TrendBuildingPlaceholder({
  title,
  dataPoints,
  requiredPoints = 30,
  showMiniChart = true
}: TrendBuildingPlaceholderProps) {
  const [animatedPoints, setAnimatedPoints] = useState<number[]>([])

  useEffect(() => {
    if (showMiniChart) {
      // Generate some random data points for visual effect
      const points = Array.from({ length: dataPoints }, () =>
        Math.random() * 40 + 30
      )
      setAnimatedPoints(points)
    }
  }, [dataPoints, showMiniChart])

  const progress = Math.min((dataPoints / requiredPoints) * 100, 100)

  return (
    <div className="relative bg-gradient-to-br from-gray-900/50 to-gray-800/50 border border-gray-700/50 rounded-xl p-6 backdrop-blur-sm">
      {/* Background pattern */}
      <div className="absolute inset-0 opacity-5 rounded-xl overflow-hidden">
        <div className="absolute inset-0" style={{
          backgroundImage: 'linear-gradient(90deg, rgba(59, 130, 246, 0.1) 1px, transparent 0), linear-gradient(rgba(59, 130, 246, 0.1) 1px, transparent 0)',
          backgroundSize: '20px 20px'
        }}></div>
      </div>

      <div className="relative z-10">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-500/10 rounded-lg">
              <TrendingUp className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <h3 className="font-semibold text-white">{title}</h3>
              <p className="text-xs text-gray-400 mt-0.5">
                {dataPoints} of {requiredPoints} data points
              </p>
            </div>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold text-blue-400">{Math.round(progress)}%</div>
            <div className="text-xs text-gray-500">Complete</div>
          </div>
        </div>

        {/* Mini chart visualization */}
        {showMiniChart && animatedPoints.length > 0 && (
          <div className="mb-4 h-24 flex items-end gap-1">
            {animatedPoints.map((height, index) => (
              <div
                key={index}
                className="flex-1 bg-gradient-to-t from-blue-500/50 to-blue-400/20 rounded-t transition-all duration-500 hover:from-blue-500 hover:to-blue-400"
                style={{
                  height: `${height}%`,
                  animationDelay: `${index * 50}ms`
                }}
              />
            ))}
            {/* Placeholder bars for missing data */}
            {[...Array(Math.max(0, requiredPoints - dataPoints))].map((_, index) => (
              <div
                key={`placeholder-${index}`}
                className="flex-1 bg-gray-800/30 border border-dashed border-gray-700 rounded-t"
                style={{ height: '20%' }}
              />
            ))}
          </div>
        )}

        {/* Progress bar */}
        <div className="space-y-2">
          <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-blue-500 to-purple-500 rounded-full transition-all duration-1000 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>

          {progress < 100 && (
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <div className="flex gap-1">
                <div className="w-1 h-1 bg-blue-500 rounded-full animate-pulse" style={{ animationDelay: '0ms' }}></div>
                <div className="w-1 h-1 bg-blue-500 rounded-full animate-pulse" style={{ animationDelay: '200ms' }}></div>
                <div className="w-1 h-1 bg-blue-500 rounded-full animate-pulse" style={{ animationDelay: '400ms' }}></div>
              </div>
              <span>Trend will stabilize with more data</span>
            </div>
          )}

          {progress >= 100 && (
            <div className="flex items-center gap-2 text-xs text-green-400">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
              <span>Sufficient data for reliable trends</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
