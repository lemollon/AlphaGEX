'use client'

/**
 * Shared Strike Table Component
 *
 * Used by both ARGUS (0DTE) and HYPERION (Weekly) for efficient rendering
 * of strike lists. Uses memoization and CSS containment for performance.
 */

import React, { useMemo, memo } from 'react'
import { Activity, Clock } from 'lucide-react'

// Types
export interface StrikeData {
  strike: number
  net_gamma: number
  probability: number
  gamma_change_pct?: number
  roc_1min: number
  roc_5min: number
  roc_30min?: number
  roc_1hr?: number
  roc_4hr?: number
  roc_trading_day?: number
  is_magnet: boolean
  magnet_rank?: number | null
  is_pin: boolean
  is_danger: boolean
  danger_type?: string | null
  gamma_flipped?: boolean
  flip_direction?: string | null
}

export interface StrikeTrend {
  dominant_status: string
  dominant_duration_mins: number
}

export interface GammaFlip {
  strike: number
  direction: string
  mins_ago: number
}

export type RocTimeframe = '4hr' | 'day'

export interface StrikeTableProps {
  strikes: StrikeData[]
  spotPrice: number
  selectedStrike: StrikeData | null
  onSelectStrike: (strike: StrikeData) => void
  lastUpdated?: Date | null

  // Optional extended columns (for ARGUS)
  showProbabilityColumn?: boolean
  showTrendColumn?: boolean
  strikeTrends?: Record<string, StrikeTrend>
  gammaFlips?: GammaFlip[]

  // ROC timeframe selection
  selectedRocTimeframe?: RocTimeframe
  onRocTimeframeChange?: (timeframe: RocTimeframe) => void
  showRocSelector?: boolean

  // Row configuration
  maxHeight?: number

  // Column visibility
  showGammaFlipColumn?: boolean
}

// Format gamma values
const formatGamma = (gamma: number): string => {
  const absGamma = Math.abs(gamma)
  if (absGamma >= 1e9) return `${(gamma / 1e9).toFixed(2)}B`
  if (absGamma >= 1e6) return `${(gamma / 1e6).toFixed(2)}M`
  if (absGamma >= 1e3) return `${(gamma / 1e3).toFixed(1)}K`
  return gamma.toFixed(0)
}

// Format ROC value
const formatRoc = (value: number | undefined | null): string => {
  const v = value ?? 0
  return `${v > 0 ? '+' : ''}${v.toFixed(1)}%`
}

// Get ROC color class
const getRocColorClass = (value: number | undefined | null): string => {
  const v = value ?? 0
  if (v > 0) return 'text-emerald-400'
  if (v < 0) return 'text-rose-400'
  return 'text-gray-500'
}

// ROC Timeframe options
const rocTimeframeOptions = [
  { value: '4hr' as const, label: '4 Hour', shortLabel: '4hr' },
  { value: 'day' as const, label: 'Trading Day', shortLabel: 'Day' }
]

// Memoized Row Component
interface RowProps {
  strike: StrikeData
  spotPrice: number
  isSelected: boolean
  onSelect: () => void
  showProbabilityColumn: boolean
  showTrendColumn: boolean
  showGammaFlipColumn: boolean
  trend: StrikeTrend | null
  flip: GammaFlip | null
  longRocValue: number | undefined
}

const StrikeRow = memo<RowProps>(({
  strike,
  spotPrice,
  isSelected,
  onSelect,
  showProbabilityColumn,
  showTrendColumn,
  showGammaFlipColumn,
  trend,
  flip,
  longRocValue
}) => {
  const distPct = spotPrice ? ((strike.strike - spotPrice) / spotPrice * 100) : 0

  return (
    <tr
      className={`border-b border-gray-700/50 hover:bg-gray-700/30 cursor-pointer transition-colors ${
        isSelected ? 'bg-purple-500/10' : ''
      }`}
      onClick={onSelect}
      style={{ contain: 'layout style paint' }}
    >
      {/* Strike */}
      <td className="py-2 px-2">
        <span className={`font-mono font-bold ${
          strike.is_pin ? 'text-purple-400' :
          strike.is_magnet ? 'text-yellow-400' : 'text-white'
        }`}>
          ${strike.strike}
        </span>
      </td>

      {/* Distance */}
      <td className={`py-2 px-2 text-right font-mono text-xs ${
        distPct > 0 ? 'text-emerald-400' : distPct < 0 ? 'text-rose-400' : 'text-gray-500'
      }`}>
        {distPct > 0 ? '+' : ''}{distPct.toFixed(2)}%
      </td>

      {/* Net Gamma */}
      <td className={`py-2 px-2 text-right font-mono ${
        strike.net_gamma > 0 ? 'text-emerald-400' : 'text-rose-400'
      }`}>
        {formatGamma(strike.net_gamma)}
      </td>

      {/* Probability (optional) */}
      {showProbabilityColumn && (
        <td className="py-2 px-2 text-right text-gray-300">
          {strike.probability.toFixed(1)}%
        </td>
      )}

      {/* ROC 1m */}
      <td className={`py-2 px-2 text-right font-mono text-xs ${getRocColorClass(strike.roc_1min)}`}>
        {formatRoc(strike.roc_1min)}
      </td>

      {/* ROC 5m */}
      <td className={`py-2 px-2 text-right font-mono text-xs ${getRocColorClass(strike.roc_5min)}`}>
        {formatRoc(strike.roc_5min)}
      </td>

      {/* ROC 30m */}
      <td className={`py-2 px-2 text-right font-mono text-xs ${getRocColorClass(strike.roc_30min)}`}>
        {formatRoc(strike.roc_30min)}
      </td>

      {/* ROC 1hr */}
      <td className={`py-2 px-2 text-right font-mono text-xs ${getRocColorClass(strike.roc_1hr)}`}>
        {formatRoc(strike.roc_1hr)}
      </td>

      {/* Long ROC (4hr or Day) */}
      <td className={`py-2 px-2 text-right font-mono text-xs ${getRocColorClass(longRocValue)}`}>
        {formatRoc(longRocValue)}
      </td>

      {/* 30m Trend (optional) */}
      {showTrendColumn && (
        <td className="py-2 px-2 text-center">
          {(!trend || trend.dominant_status === 'NEUTRAL') ? (
            <span className="text-gray-600 text-[10px]">—</span>
          ) : (
            <span className={`px-1.5 py-0.5 rounded text-[10px] ${
              trend.dominant_status === 'BUILDING' ? 'text-emerald-400 bg-emerald-500/20' :
              trend.dominant_status === 'COLLAPSING' ? 'text-rose-400 bg-rose-500/20' :
              trend.dominant_status === 'SPIKE' ? 'text-orange-400 bg-orange-500/20' :
              'text-gray-400'
            }`}>
              {trend.dominant_status === 'BUILDING' ? '↑' :
               trend.dominant_status === 'COLLAPSING' ? '↓' : '⚡'} {trend.dominant_duration_mins.toFixed(0)}m
            </span>
          )}
        </td>
      )}

      {/* Status */}
      <td className="py-2 px-2 text-center">
        <div className="flex items-center justify-center gap-1 flex-wrap">
          {strike.is_pin && (
            <span className="px-1.5 py-0.5 bg-purple-500/20 text-purple-400 rounded text-[10px]">PIN</span>
          )}
          {strike.is_magnet && (
            <span className="px-1.5 py-0.5 bg-yellow-500/20 text-yellow-400 rounded text-[10px]">MAG</span>
          )}
          {strike.is_danger && (
            <span className="px-1.5 py-0.5 bg-orange-500/20 text-orange-400 rounded text-[10px]">
              {strike.danger_type}
            </span>
          )}
          {showGammaFlipColumn && flip && (
            <span className={`px-1.5 py-0.5 rounded text-[10px] ${
              flip.direction === 'POS_TO_NEG'
                ? 'bg-rose-500/20 text-rose-400'
                : 'bg-emerald-500/20 text-emerald-400'
            }`}>
              FLIP {flip.mins_ago.toFixed(0)}m
            </span>
          )}
        </div>
      </td>
    </tr>
  )
})

StrikeRow.displayName = 'StrikeRow'

// Main Component
export const StrikeTable: React.FC<StrikeTableProps> = ({
  strikes,
  spotPrice,
  selectedStrike,
  onSelectStrike,
  lastUpdated,
  showProbabilityColumn = false,
  showTrendColumn = false,
  strikeTrends = {},
  gammaFlips = [],
  selectedRocTimeframe = '4hr',
  onRocTimeframeChange,
  showRocSelector = false,
  maxHeight = 400,
  showGammaFlipColumn = false
}) => {
  // Memoize row data lookup functions
  const getTrend = useMemo(() => {
    return (strike: number): StrikeTrend | null => {
      return strikeTrends[String(strike)] ||
        strikeTrends[String(strike) + '.0'] ||
        strikeTrends[String(parseFloat(String(strike)).toFixed(1))] ||
        null
    }
  }, [strikeTrends])

  const getFlip = useMemo(() => {
    return (strike: number): GammaFlip | null => {
      return gammaFlips.find(f => Math.abs(f.strike - strike) < 0.01) || null
    }
  }, [gammaFlips])

  return (
    <div className="bg-gray-800/50 rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-bold text-white flex items-center gap-2">
          <Activity className="w-5 h-5 text-blue-400" />
          Strike Analysis
          <span className="text-xs text-gray-500 font-normal ml-2">{strikes.length} strikes</span>
        </h3>
        {lastUpdated && (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <Clock className="w-3 h-3" />
            <span>Last updated: {lastUpdated.toLocaleTimeString('en-US', {
              timeZone: 'America/Chicago',
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
              hour12: true
            })} CT</span>
          </div>
        )}
      </div>

      <div
        className="overflow-x-auto overflow-y-auto rounded-lg border border-gray-700"
        style={{ maxHeight: `${maxHeight}px`, contain: 'strict' }}
      >
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-gray-800/95 z-10">
            <tr className="border-b border-gray-700">
              <th className="text-left py-2 px-2 text-gray-500 font-medium">Strike</th>
              <th className="text-right py-2 px-2 text-gray-500 font-medium">Dist</th>
              <th className="text-right py-2 px-2 text-gray-500 font-medium">Net Gamma</th>
              {showProbabilityColumn && (
                <th className="text-right py-2 px-2 text-gray-500 font-medium">Prob %</th>
              )}
              <th className="text-right py-2 px-2 text-gray-500 font-medium">1m</th>
              <th className="text-right py-2 px-2 text-gray-500 font-medium">5m</th>
              <th className="text-right py-2 px-2 text-gray-500 font-medium">30m</th>
              <th className="text-right py-2 px-2 text-gray-500 font-medium">1hr</th>
              <th className="text-right py-2 px-2 text-gray-500 font-medium">
                {showRocSelector && onRocTimeframeChange ? (
                  <select
                    value={selectedRocTimeframe}
                    onChange={(e) => onRocTimeframeChange(e.target.value as RocTimeframe)}
                    className="bg-gray-800 border border-gray-600 rounded px-1 py-0.5 text-xs text-gray-300 cursor-pointer hover:border-purple-500 focus:outline-none focus:border-purple-500"
                  >
                    {rocTimeframeOptions.map(opt => (
                      <option key={opt.value} value={opt.value}>{opt.shortLabel}</option>
                    ))}
                  </select>
                ) : (
                  rocTimeframeOptions.find(o => o.value === selectedRocTimeframe)?.shortLabel || '4hr'
                )}
              </th>
              {showTrendColumn && (
                <th className="text-center py-2 px-2 text-gray-500 font-medium">30m Trend</th>
              )}
              <th className="text-center py-2 px-2 text-gray-500 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {strikes.length > 0 ? (
              strikes.map((strike) => (
                <StrikeRow
                  key={strike.strike}
                  strike={strike}
                  spotPrice={spotPrice}
                  isSelected={selectedStrike?.strike === strike.strike}
                  onSelect={() => onSelectStrike(strike)}
                  showProbabilityColumn={showProbabilityColumn}
                  showTrendColumn={showTrendColumn}
                  showGammaFlipColumn={showGammaFlipColumn}
                  trend={getTrend(strike.strike)}
                  flip={getFlip(strike.strike)}
                  longRocValue={selectedRocTimeframe === '4hr' ? strike.roc_4hr : strike.roc_trading_day}
                />
              ))
            ) : (
              <tr>
                <td colSpan={showProbabilityColumn ? 11 : 10} className="py-8 text-center text-gray-500">
                  No strike data available
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// Also export as VirtualizedStrikeTable for backwards compatibility
export const VirtualizedStrikeTable = StrikeTable

export default StrikeTable
