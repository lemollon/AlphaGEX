'use client'

/**
 * Shared Danger Zone Card Component
 *
 * Displays gamma danger zones (BUILDING, COLLAPSING, SPIKE) for both
 * WATCHTOWER (0DTE) and GLORY (Weekly) visualizations.
 */

import React, { useMemo } from 'react'
import { Flame, TrendingUp, TrendingDown, Zap, AlertTriangle, Info } from 'lucide-react'

// Types
export interface DangerZone {
  strike: number
  danger_type: string
  roc_1min?: number
  roc_5min?: number
  net_gamma?: number
  probability?: number
}

export interface DangerZoneCardProps {
  dangerZones: DangerZone[]
  spotPrice?: number
  title?: string
  showRoc?: boolean
  showProbability?: boolean
  maxItems?: number
  onStrikeClick?: (strike: number) => void
  emptyMessage?: string
}

// Danger type configurations
const dangerTypeConfig: Record<string, {
  label: string
  icon: React.ElementType
  bgColor: string
  textColor: string
  borderColor: string
  description: string
}> = {
  BUILDING: {
    label: 'BUILDING',
    icon: TrendingUp,
    bgColor: 'bg-emerald-500/10',
    textColor: 'text-emerald-400',
    borderColor: 'border-emerald-500/30',
    description: 'Gamma increasing rapidly'
  },
  COLLAPSING: {
    label: 'COLLAPSING',
    icon: TrendingDown,
    bgColor: 'bg-rose-500/10',
    textColor: 'text-rose-400',
    borderColor: 'border-rose-500/30',
    description: 'Gamma decreasing rapidly'
  },
  SPIKE: {
    label: 'SPIKE',
    icon: Zap,
    bgColor: 'bg-orange-500/10',
    textColor: 'text-orange-400',
    borderColor: 'border-orange-500/30',
    description: 'Sudden gamma spike detected'
  }
}

// Format gamma values
const formatGamma = (gamma: number): string => {
  const absGamma = Math.abs(gamma)
  if (absGamma >= 1e9) return `${(gamma / 1e9).toFixed(2)}B`
  if (absGamma >= 1e6) return `${(gamma / 1e6).toFixed(2)}M`
  if (absGamma >= 1e3) return `${(gamma / 1e3).toFixed(1)}K`
  return gamma.toFixed(0)
}

// Individual Danger Zone Item
const DangerZoneItem: React.FC<{
  zone: DangerZone
  spotPrice?: number
  showRoc: boolean
  showProbability: boolean
  onClick?: () => void
}> = ({ zone, spotPrice, showRoc, showProbability, onClick }) => {
  const config = dangerTypeConfig[zone.danger_type] || dangerTypeConfig.SPIKE
  const Icon = config.icon

  const distPct = spotPrice ? ((zone.strike - spotPrice) / spotPrice * 100) : null

  return (
    <div
      className={`p-3 rounded-lg border ${config.bgColor} ${config.borderColor} ${
        onClick ? 'cursor-pointer hover:brightness-110 transition-all' : ''
      }`}
      onClick={onClick}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className={`w-4 h-4 ${config.textColor}`} />
          <span className={`font-mono font-bold ${config.textColor}`}>
            ${zone.strike}
          </span>
          {distPct !== null && (
            <span className={`text-xs ${distPct > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              ({distPct > 0 ? '+' : ''}{distPct.toFixed(2)}%)
            </span>
          )}
        </div>
        <span className={`text-xs px-2 py-0.5 rounded ${config.bgColor} ${config.textColor}`}>
          {config.label}
        </span>
      </div>

      {(showRoc || showProbability || zone.net_gamma !== undefined) && (
        <div className="mt-2 flex items-center gap-3 text-xs">
          {showRoc && zone.roc_1min !== undefined && (
            <span className={zone.roc_1min > 0 ? 'text-emerald-400' : 'text-rose-400'}>
              1m: {zone.roc_1min > 0 ? '+' : ''}{zone.roc_1min.toFixed(1)}%
            </span>
          )}
          {showRoc && zone.roc_5min !== undefined && (
            <span className={zone.roc_5min > 0 ? 'text-emerald-400' : 'text-rose-400'}>
              5m: {zone.roc_5min > 0 ? '+' : ''}{zone.roc_5min.toFixed(1)}%
            </span>
          )}
          {zone.net_gamma !== undefined && (
            <span className={zone.net_gamma > 0 ? 'text-emerald-400' : 'text-rose-400'}>
              {formatGamma(zone.net_gamma)}
            </span>
          )}
          {showProbability && zone.probability !== undefined && (
            <span className="text-gray-400">
              {zone.probability.toFixed(1)}% prob
            </span>
          )}
        </div>
      )}
    </div>
  )
}

// Grouped View Component
const GroupedDangerZones: React.FC<{
  zones: DangerZone[]
  spotPrice?: number
  showRoc: boolean
  showProbability: boolean
  maxItems: number
  onStrikeClick?: (strike: number) => void
}> = ({ zones, spotPrice, showRoc, showProbability, maxItems, onStrikeClick }) => {
  // Group by danger type
  const grouped = useMemo(() => {
    const groups: Record<string, DangerZone[]> = {
      BUILDING: [],
      COLLAPSING: [],
      SPIKE: []
    }

    zones.forEach(zone => {
      const type = zone.danger_type || 'SPIKE'
      if (groups[type]) {
        groups[type].push(zone)
      } else {
        groups.SPIKE.push(zone)
      }
    })

    return groups
  }, [zones])

  const hasAny = grouped.BUILDING.length > 0 || grouped.COLLAPSING.length > 0 || grouped.SPIKE.length > 0

  if (!hasAny) {
    return (
      <div className="text-center text-gray-500 py-4 text-sm">
        No danger zones detected
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* BUILDING Section */}
      {grouped.BUILDING.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-4 h-4 text-emerald-400" />
            <span className="text-xs text-emerald-400 font-medium">
              BUILDING ({grouped.BUILDING.length})
            </span>
          </div>
          <div className="space-y-2">
            {grouped.BUILDING.slice(0, maxItems).map((zone, idx) => (
              <DangerZoneItem
                key={`building-${zone.strike}-${idx}`}
                zone={zone}
                spotPrice={spotPrice}
                showRoc={showRoc}
                showProbability={showProbability}
                onClick={onStrikeClick ? () => onStrikeClick(zone.strike) : undefined}
              />
            ))}
            {grouped.BUILDING.length > maxItems && (
              <div className="text-xs text-gray-500 text-center">
                +{grouped.BUILDING.length - maxItems} more
              </div>
            )}
          </div>
        </div>
      )}

      {/* COLLAPSING Section */}
      {grouped.COLLAPSING.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <TrendingDown className="w-4 h-4 text-rose-400" />
            <span className="text-xs text-rose-400 font-medium">
              COLLAPSING ({grouped.COLLAPSING.length})
            </span>
          </div>
          <div className="space-y-2">
            {grouped.COLLAPSING.slice(0, maxItems).map((zone, idx) => (
              <DangerZoneItem
                key={`collapsing-${zone.strike}-${idx}`}
                zone={zone}
                spotPrice={spotPrice}
                showRoc={showRoc}
                showProbability={showProbability}
                onClick={onStrikeClick ? () => onStrikeClick(zone.strike) : undefined}
              />
            ))}
            {grouped.COLLAPSING.length > maxItems && (
              <div className="text-xs text-gray-500 text-center">
                +{grouped.COLLAPSING.length - maxItems} more
              </div>
            )}
          </div>
        </div>
      )}

      {/* SPIKE Section */}
      {grouped.SPIKE.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-orange-400" />
            <span className="text-xs text-orange-400 font-medium">
              SPIKE ({grouped.SPIKE.length})
            </span>
          </div>
          <div className="space-y-2">
            {grouped.SPIKE.slice(0, maxItems).map((zone, idx) => (
              <DangerZoneItem
                key={`spike-${zone.strike}-${idx}`}
                zone={zone}
                spotPrice={spotPrice}
                showRoc={showRoc}
                showProbability={showProbability}
                onClick={onStrikeClick ? () => onStrikeClick(zone.strike) : undefined}
              />
            ))}
            {grouped.SPIKE.length > maxItems && (
              <div className="text-xs text-gray-500 text-center">
                +{grouped.SPIKE.length - maxItems} more
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// Main Component
export const DangerZoneCard: React.FC<DangerZoneCardProps> = ({
  dangerZones,
  spotPrice,
  title = 'Danger Zones',
  showRoc = true,
  showProbability = false,
  maxItems = 3,
  onStrikeClick,
  emptyMessage = 'No danger zones detected'
}) => {
  const hasZones = dangerZones.length > 0

  return (
    <div className={`bg-gray-800/50 rounded-xl p-5 ${hasZones ? 'border border-red-500/30' : ''}`}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-bold text-white flex items-center gap-2">
          <Flame className={`w-5 h-5 ${hasZones ? 'text-red-400' : 'text-gray-500'}`} />
          {title}
          {hasZones && (
            <span className="text-xs text-gray-500 font-normal ml-2">
              {dangerZones.length} active
            </span>
          )}
        </h3>
        {hasZones && (
          <div className="group relative">
            <Info className="w-4 h-4 text-gray-500 cursor-help" />
            <div className="absolute right-0 top-6 z-20 hidden group-hover:block w-64 p-3 bg-gray-900 border border-gray-700 rounded-lg text-xs">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <TrendingUp className="w-3 h-3 text-emerald-400" />
                  <span className="text-emerald-400">BUILDING:</span>
                  <span className="text-gray-400">Gamma increasing rapidly</span>
                </div>
                <div className="flex items-center gap-2">
                  <TrendingDown className="w-3 h-3 text-rose-400" />
                  <span className="text-rose-400">COLLAPSING:</span>
                  <span className="text-gray-400">Gamma decreasing rapidly</span>
                </div>
                <div className="flex items-center gap-2">
                  <Zap className="w-3 h-3 text-orange-400" />
                  <span className="text-orange-400">SPIKE:</span>
                  <span className="text-gray-400">Sudden gamma spike</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {hasZones ? (
        <GroupedDangerZones
          zones={dangerZones}
          spotPrice={spotPrice}
          showRoc={showRoc}
          showProbability={showProbability}
          maxItems={maxItems}
          onStrikeClick={onStrikeClick}
        />
      ) : (
        <div className="flex items-center justify-center gap-2 py-6 text-gray-500">
          <AlertTriangle className="w-4 h-4" />
          <span className="text-sm">{emptyMessage}</span>
        </div>
      )}
    </div>
  )
}

export default DangerZoneCard
