'use client'

import { useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { TrendingUp, Award, Target, Info } from 'lucide-react'

interface StrategyPreset {
  id: string
  name: string
  description: string
  backtest_sharpe: number
  backtest_win_rate: number
  is_active: boolean
}

interface PresetPerformanceChartProps {
  presets: StrategyPreset[]
  activePreset?: string
  currentVix?: number
}

// Color scheme for presets
const PRESET_COLORS: Record<string, string> = {
  baseline: '#6B7280',      // gray
  conservative: '#3B82F6',  // blue
  moderate: '#10B981',      // green
  aggressive: '#F59E0B',    // amber
  wide_strikes: '#8B5CF6',  // purple
}

// Get recommended preset based on VIX
function getRecommendedPreset(vix: number): string {
  if (vix > 35) return 'conservative'  // Very high volatility - be safe
  if (vix > 25) return 'baseline'      // High volatility - standard
  if (vix > 18) return 'moderate'      // Normal volatility - moderate risk
  if (vix > 12) return 'aggressive'    // Low volatility - can be aggressive
  return 'wide_strikes'                 // Very low volatility - wide strikes
}

export default function PresetPerformanceChart({
  presets,
  activePreset,
  currentVix
}: PresetPerformanceChartProps) {
  // Transform data for chart
  const chartData = useMemo(() => {
    return presets.map(preset => ({
      name: preset.name.replace(' ', '\n'),
      shortName: preset.id,
      winRate: preset.backtest_win_rate,
      sharpe: preset.backtest_sharpe,
      isActive: preset.is_active,
      color: PRESET_COLORS[preset.id] || '#6B7280'
    }))
  }, [presets])

  // Find recommended preset
  const recommendedPreset = currentVix ? getRecommendedPreset(currentVix) : null

  // Find best performers
  const bestWinRate = useMemo(() =>
    presets.reduce((best, p) => p.backtest_win_rate > best.backtest_win_rate ? p : best, presets[0]),
    [presets]
  )
  const bestSharpe = useMemo(() =>
    presets.reduce((best, p) => p.backtest_sharpe > best.backtest_sharpe ? p : best, presets[0]),
    [presets]
  )

  if (!presets || presets.length === 0) {
    return null
  }

  return (
    <div className="bg-gray-900/50 rounded-xl border border-gray-800 p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-purple-400" />
          <h3 className="text-sm font-semibold text-white">Preset Performance (2022-2024 Backtest)</h3>
        </div>
        {recommendedPreset && currentVix && (
          <div className="flex items-center gap-2 px-3 py-1 bg-purple-500/20 rounded-full">
            <Target className="w-3 h-3 text-purple-400" />
            <span className="text-xs text-purple-300">
              VIX {currentVix.toFixed(1)} suggests: <strong className="text-purple-400 capitalize">{recommendedPreset}</strong>
            </span>
          </div>
        )}
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Win Rate Chart */}
        <div className="bg-gray-950 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <Award className="w-4 h-4 text-green-400" />
            <span className="text-xs text-gray-400 uppercase tracking-wide">Win Rate</span>
            <span className="ml-auto text-xs text-green-400 font-medium">
              Best: {bestWinRate.name} ({bestWinRate.backtest_win_rate.toFixed(1)}%)
            </span>
          </div>
          <div className="h-32">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} layout="vertical" margin={{ left: 0, right: 10 }}>
                <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 10, fill: '#9CA3AF' }} />
                <YAxis
                  type="category"
                  dataKey="shortName"
                  tick={{ fontSize: 10, fill: '#9CA3AF' }}
                  width={70}
                />
                <Tooltip
                  formatter={(value: number) => [`${value.toFixed(1)}%`, 'Win Rate']}
                  contentStyle={{
                    backgroundColor: '#1F2937',
                    border: '1px solid #374151',
                    borderRadius: '8px',
                    fontSize: '12px'
                  }}
                />
                <Bar dataKey="winRate" radius={[0, 4, 4, 0]}>
                  {chartData.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={entry.isActive ? '#10B981' : entry.color}
                      opacity={entry.isActive ? 1 : 0.7}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Sharpe Ratio Chart */}
        <div className="bg-gray-950 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-4 h-4 text-blue-400" />
            <span className="text-xs text-gray-400 uppercase tracking-wide">Sharpe Ratio</span>
            <span className="ml-auto text-xs text-blue-400 font-medium">
              Best: {bestSharpe.name} ({bestSharpe.backtest_sharpe.toFixed(2)})
            </span>
          </div>
          <div className="h-32">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} layout="vertical" margin={{ left: 0, right: 10 }}>
                <XAxis type="number" domain={[0, 'auto']} tick={{ fontSize: 10, fill: '#9CA3AF' }} />
                <YAxis
                  type="category"
                  dataKey="shortName"
                  tick={{ fontSize: 10, fill: '#9CA3AF' }}
                  width={70}
                />
                <Tooltip
                  formatter={(value: number) => [value.toFixed(2), 'Sharpe']}
                  contentStyle={{
                    backgroundColor: '#1F2937',
                    border: '1px solid #374151',
                    borderRadius: '8px',
                    fontSize: '12px'
                  }}
                />
                <Bar dataKey="sharpe" radius={[0, 4, 4, 0]}>
                  {chartData.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={entry.isActive ? '#3B82F6' : entry.color}
                      opacity={entry.isActive ? 1 : 0.7}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 mt-4 pt-3 border-t border-gray-800">
        {chartData.map(preset => (
          <div key={preset.shortName} className="flex items-center gap-1.5">
            <div
              className={`w-3 h-3 rounded-sm ${preset.isActive ? 'ring-2 ring-white ring-offset-1 ring-offset-gray-900' : ''}`}
              style={{ backgroundColor: preset.color }}
            />
            <span className={`text-xs ${preset.isActive ? 'text-white font-medium' : 'text-gray-400'}`}>
              {preset.shortName}
              {preset.isActive && ' (active)'}
            </span>
          </div>
        ))}
        <div className="ml-auto flex items-center gap-1 text-xs text-gray-500">
          <Info className="w-3 h-3" />
          <span>Based on historical backtest data</span>
        </div>
      </div>
    </div>
  )
}
