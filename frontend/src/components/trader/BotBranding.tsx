'use client'

import React from 'react'
import { Sword, Target, TrendingUp, TrendingDown, Clock, AlertTriangle, CheckCircle, XCircle, RefreshCw } from 'lucide-react'

// =============================================================================
// BOT BRANDING SYSTEM
// =============================================================================
// Unified branding for ARES and ATHENA to ensure visual consistency

export type BotName = 'ARES' | 'ATHENA'

export interface BotBrand {
  name: BotName
  fullName: string
  description: string
  strategy: string
  primaryColor: string
  primaryBg: string
  primaryBorder: string
  primaryText: string
  icon: React.ComponentType<{ className?: string }>
  gradientFrom: string
  gradientTo: string
}

export const BOT_BRANDS: Record<BotName, BotBrand> = {
  ARES: {
    name: 'ARES',
    fullName: 'ARES Iron Condor',
    description: 'Premium Collection via Iron Condors',
    strategy: '0DTE Iron Condor Strategy',
    primaryColor: 'red',
    primaryBg: 'bg-red-600',
    primaryBorder: 'border-red-500',
    primaryText: 'text-red-400',
    icon: Sword,
    gradientFrom: 'from-red-600',
    gradientTo: 'to-red-900',
  },
  ATHENA: {
    name: 'ATHENA',
    fullName: 'ATHENA Directional',
    description: 'GEX-Based Directional Spreads',
    strategy: 'Directional Spread Trading',
    primaryColor: 'orange',
    primaryBg: 'bg-orange-600',
    primaryBorder: 'border-orange-500',
    primaryText: 'text-orange-400',
    icon: Target,
    gradientFrom: 'from-orange-600',
    gradientTo: 'to-orange-900',
  },
}

// =============================================================================
// UNIFIED TAB STRUCTURE
// =============================================================================
// Both bots should have the same tab structure for consistency

export const UNIFIED_TABS = [
  { id: 'portfolio', label: 'Portfolio', description: 'Live P&L and positions' },
  { id: 'overview', label: 'Overview', description: 'Bot status and metrics' },
  { id: 'activity', label: 'Activity', description: 'Scans and decisions' },
  { id: 'history', label: 'History', description: 'Closed positions' },
  { id: 'config', label: 'Config', description: 'Settings and controls' },
] as const

export type TabId = typeof UNIFIED_TABS[number]['id']

// =============================================================================
// DATA FRESHNESS INDICATOR
// =============================================================================
// Shows how fresh the data is with color coding

interface DataFreshnessProps {
  lastUpdated: string | null | undefined
  refreshInterval?: number // seconds
  onRefresh?: () => void
  isRefreshing?: boolean
  showTimestamp?: boolean
  className?: string
}

export function DataFreshnessIndicator({
  lastUpdated,
  refreshInterval = 30,
  onRefresh,
  isRefreshing = false,
  showTimestamp = true,
  className = '',
}: DataFreshnessProps) {
  const [now, setNow] = React.useState(new Date())

  React.useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  if (!lastUpdated) {
    return (
      <div className={`flex items-center gap-2 text-gray-500 ${className}`}>
        <Clock className="w-3 h-3" />
        <span className="text-xs">No data</span>
      </div>
    )
  }

  const lastUpdateTime = new Date(lastUpdated)
  const ageSeconds = Math.floor((now.getTime() - lastUpdateTime.getTime()) / 1000)

  // Determine freshness level
  let freshnessColor = 'text-green-400'
  let freshnessLabel = 'Live'
  let freshnessIcon = CheckCircle

  if (ageSeconds > refreshInterval * 4) {
    freshnessColor = 'text-red-400'
    freshnessLabel = 'Stale'
    freshnessIcon = AlertTriangle
  } else if (ageSeconds > refreshInterval * 2) {
    freshnessColor = 'text-yellow-400'
    freshnessLabel = 'Delayed'
    freshnessIcon = Clock
  } else if (ageSeconds > refreshInterval) {
    freshnessColor = 'text-blue-400'
    freshnessLabel = 'Updating'
    freshnessIcon = Clock
  }

  const FreshnessIcon = freshnessIcon

  const formatAge = (seconds: number) => {
    if (seconds < 60) return `${seconds}s ago`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
    return `${Math.floor(seconds / 3600)}h ago`
  }

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className={`flex items-center gap-1 ${freshnessColor}`}>
        <FreshnessIcon className="w-3 h-3" />
        <span className="text-xs font-medium">{freshnessLabel}</span>
      </div>
      {showTimestamp && (
        <span className="text-xs text-gray-500">{formatAge(ageSeconds)}</span>
      )}
      {onRefresh && (
        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          className="p-1 hover:bg-gray-700 rounded transition"
        >
          <RefreshCw className={`w-3 h-3 text-gray-400 ${isRefreshing ? 'animate-spin' : ''}`} />
        </button>
      )}
    </div>
  )
}

// =============================================================================
// UNIFIED CARD COMPONENT
// =============================================================================
// Consistent card styling across both bots

interface CardProps {
  title: string
  subtitle?: string
  icon?: React.ReactNode
  botName?: BotName
  children: React.ReactNode
  className?: string
  headerRight?: React.ReactNode
  freshness?: {
    lastUpdated: string | null
    onRefresh?: () => void
    isRefreshing?: boolean
  }
}

export function BotCard({
  title,
  subtitle,
  icon,
  botName,
  children,
  className = '',
  headerRight,
  freshness,
}: CardProps) {
  const brand = botName ? BOT_BRANDS[botName] : null

  return (
    <div className={`bg-[#0a0a0a] rounded-xl border border-gray-800 overflow-hidden ${className}`}>
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <div className="flex items-center gap-3">
          {icon && <div className={brand ? brand.primaryText : 'text-gray-400'}>{icon}</div>}
          <div>
            <h3 className="font-semibold text-white">{title}</h3>
            {subtitle && <p className="text-xs text-gray-500">{subtitle}</p>}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {freshness && (
            <DataFreshnessIndicator
              lastUpdated={freshness.lastUpdated}
              onRefresh={freshness.onRefresh}
              isRefreshing={freshness.isRefreshing}
            />
          )}
          {headerRight}
        </div>
      </div>
      {/* Content */}
      <div className="p-4">{children}</div>
    </div>
  )
}

// =============================================================================
// EMPTY STATE COMPONENT
// =============================================================================
// Consistent empty states across both bots

interface EmptyStateProps {
  icon?: React.ReactNode
  title: string
  description: string
  action?: {
    label: string
    onClick: () => void
  }
  className?: string
}

export function EmptyState({ icon, title, description, action, className = '' }: EmptyStateProps) {
  return (
    <div className={`text-center py-8 px-4 ${className}`}>
      {icon && <div className="flex justify-center mb-3 text-gray-600">{icon}</div>}
      <h3 className="text-lg font-medium text-gray-300 mb-1">{title}</h3>
      <p className="text-sm text-gray-500 mb-4">{description}</p>
      {action && (
        <button
          onClick={action.onClick}
          className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded-lg transition"
        >
          {action.label}
        </button>
      )}
    </div>
  )
}

// =============================================================================
// LOADING STATE COMPONENT
// =============================================================================

interface LoadingStateProps {
  message?: string
  className?: string
}

export function LoadingState({ message = 'Loading...', className = '' }: LoadingStateProps) {
  return (
    <div className={`flex items-center justify-center py-8 ${className}`}>
      <div className="flex items-center gap-3 text-gray-400">
        <RefreshCw className="w-5 h-5 animate-spin" />
        <span>{message}</span>
      </div>
    </div>
  )
}

// =============================================================================
// STAT CARD COMPONENT
// =============================================================================
// Consistent stat display across both bots

interface StatCardProps {
  label: string
  value: string | number
  change?: number
  changeLabel?: string
  icon?: React.ReactNode
  color?: 'green' | 'red' | 'yellow' | 'blue' | 'gray'
  className?: string
}

export function StatCard({
  label,
  value,
  change,
  changeLabel,
  icon,
  color = 'gray',
  className = '',
}: StatCardProps) {
  const colorClasses = {
    green: 'text-green-400',
    red: 'text-red-400',
    yellow: 'text-yellow-400',
    blue: 'text-blue-400',
    gray: 'text-gray-400',
  }

  return (
    <div className={`bg-[#111] rounded-lg p-4 border border-gray-800 ${className}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-gray-500 uppercase tracking-wide">{label}</span>
        {icon && <span className={colorClasses[color]}>{icon}</span>}
      </div>
      <div className={`text-2xl font-bold ${colorClasses[color]}`}>{value}</div>
      {change !== undefined && (
        <div className="flex items-center gap-1 mt-1">
          {change >= 0 ? (
            <TrendingUp className="w-3 h-3 text-green-400" />
          ) : (
            <TrendingDown className="w-3 h-3 text-red-400" />
          )}
          <span className={`text-xs ${change >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {change >= 0 ? '+' : ''}{change.toFixed(2)}%
          </span>
          {changeLabel && <span className="text-xs text-gray-500">{changeLabel}</span>}
        </div>
      )}
    </div>
  )
}

// =============================================================================
// POSITION STATUS BADGE
// =============================================================================

interface StatusBadgeProps {
  status: 'open' | 'closed' | 'expired' | 'pending' | string
  className?: string
}

export function StatusBadge({ status, className = '' }: StatusBadgeProps) {
  const statusStyles = {
    open: 'bg-green-900/50 text-green-400 border-green-700',
    closed: 'bg-gray-800 text-gray-400 border-gray-700',
    expired: 'bg-purple-900/50 text-purple-400 border-purple-700',
    pending: 'bg-yellow-900/50 text-yellow-400 border-yellow-700',
  }

  const style = statusStyles[status as keyof typeof statusStyles] || statusStyles.pending

  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium border ${style} ${className}`}>
      {status.toUpperCase()}
    </span>
  )
}

// =============================================================================
// DIRECTION INDICATOR
// =============================================================================

interface DirectionIndicatorProps {
  direction: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | string
  showLabel?: boolean
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

export function DirectionIndicator({
  direction,
  showLabel = true,
  size = 'md',
  className = '',
}: DirectionIndicatorProps) {
  const sizes = {
    sm: 'w-3 h-3',
    md: 'w-4 h-4',
    lg: 'w-5 h-5',
  }

  const textSizes = {
    sm: 'text-xs',
    md: 'text-sm',
    lg: 'text-base',
  }

  if (direction === 'BULLISH') {
    return (
      <div className={`flex items-center gap-1 text-green-400 ${className}`}>
        <TrendingUp className={sizes[size]} />
        {showLabel && <span className={textSizes[size]}>Bullish</span>}
      </div>
    )
  }

  if (direction === 'BEARISH') {
    return (
      <div className={`flex items-center gap-1 text-red-400 ${className}`}>
        <TrendingDown className={sizes[size]} />
        {showLabel && <span className={textSizes[size]}>Bearish</span>}
      </div>
    )
  }

  return (
    <div className={`flex items-center gap-1 text-gray-400 ${className}`}>
      <span className="text-lg">—</span>
      {showLabel && <span className={textSizes[size]}>Neutral</span>}
    </div>
  )
}

// =============================================================================
// P&L DISPLAY
// =============================================================================

interface PnLDisplayProps {
  value: number
  showSign?: boolean
  showColor?: boolean
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

export function PnLDisplay({
  value,
  showSign = true,
  showColor = true,
  size = 'md',
  className = '',
}: PnLDisplayProps) {
  const isPositive = value >= 0
  const color = showColor ? (isPositive ? 'text-green-400' : 'text-red-400') : 'text-white'

  const sizes = {
    sm: 'text-sm',
    md: 'text-base',
    lg: 'text-xl font-bold',
  }

  const formatted = `${showSign && isPositive ? '+' : ''}$${Math.abs(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`

  return <span className={`${color} ${sizes[size]} ${className}`}>{formatted}</span>
}

// =============================================================================
// UNIFIED PAGE HEADER
// =============================================================================

interface PageHeaderProps {
  botName: BotName
  isActive?: boolean
  lastHeartbeat?: string
  onRefresh?: () => void
  isRefreshing?: boolean
}

export function BotPageHeader({
  botName,
  isActive = false,
  lastHeartbeat,
  onRefresh,
  isRefreshing,
}: PageHeaderProps) {
  const brand = BOT_BRANDS[botName]
  const Icon = brand.icon

  return (
    <div className={`bg-gradient-to-r ${brand.gradientFrom} ${brand.gradientTo} rounded-xl p-6 mb-6`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-black/30 rounded-xl">
            <Icon className="w-8 h-8 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">{brand.fullName}</h1>
            <p className="text-white/70">{brand.strategy}</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {/* Status indicator */}
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${isActive ? 'bg-green-400 animate-pulse' : 'bg-gray-500'}`} />
            <span className="text-white/80 text-sm">{isActive ? 'Active' : 'Inactive'}</span>
          </div>
          {/* Freshness */}
          {lastHeartbeat && (
            <DataFreshnessIndicator
              lastUpdated={lastHeartbeat}
              onRefresh={onRefresh}
              isRefreshing={isRefreshing}
              className="text-white/70"
            />
          )}
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// TIME DISPLAY UTILITIES
// =============================================================================
// For showing "Time in Position" (open) and "Duration Held" (closed)

/**
 * Formats a duration between two dates into a human-readable string
 * @param startTime - ISO date string of start time
 * @param endTime - ISO date string of end time (optional, defaults to now)
 * @returns formatted string like "2h 15m" or "3d 4h"
 */
export function formatDuration(startTime: string | null | undefined, endTime?: string | null): string {
  if (!startTime) return '--'

  const start = new Date(startTime)
  const end = endTime ? new Date(endTime) : new Date()

  const diffMs = end.getTime() - start.getTime()
  if (diffMs < 0) return '--'

  const seconds = Math.floor(diffMs / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)

  if (days > 0) {
    const remainingHours = hours % 24
    return remainingHours > 0 ? `${days}d ${remainingHours}h` : `${days}d`
  }
  if (hours > 0) {
    const remainingMinutes = minutes % 60
    return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`
  }
  if (minutes > 0) {
    return `${minutes}m`
  }
  return `${seconds}s`
}

interface TimeInPositionProps {
  entryTime: string | null | undefined
  exitTime?: string | null
  showLabel?: boolean
  className?: string
}

/**
 * Displays time in position with a live updating timer for open positions
 */
export function TimeInPosition({
  entryTime,
  exitTime,
  showLabel = true,
  className = ''
}: TimeInPositionProps) {
  const [now, setNow] = React.useState(new Date())

  // Only update if position is still open (no exitTime)
  React.useEffect(() => {
    if (!exitTime && entryTime) {
      const timer = setInterval(() => setNow(new Date()), 60000) // Update every minute
      return () => clearInterval(timer)
    }
  }, [exitTime, entryTime])

  const duration = formatDuration(entryTime, exitTime || now.toISOString())

  return (
    <div className={`flex items-center gap-1.5 text-gray-400 ${className}`}>
      <Clock className="w-3 h-3" />
      {showLabel && <span className="text-xs text-gray-500">{exitTime ? 'Held:' : 'Open:'}</span>}
      <span className="text-xs font-medium text-gray-300">{duration}</span>
    </div>
  )
}

interface DateRangeDisplayProps {
  entryTime: string | null | undefined
  exitTime?: string | null
  showDuration?: boolean
  className?: string
}

/**
 * Shows entry date → exit date with optional duration
 */
export function DateRangeDisplay({
  entryTime,
  exitTime,
  showDuration = true,
  className = ''
}: DateRangeDisplayProps) {
  if (!entryTime) return <span className="text-gray-500">--</span>

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric'
    })
  }

  const formatTime = (dateStr: string) => {
    return new Date(dateStr).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    })
  }

  return (
    <div className={`flex flex-col gap-0.5 ${className}`}>
      <div className="flex items-center gap-1 text-xs">
        <span className="text-gray-500">Entry:</span>
        <span className="text-gray-300">{formatDate(entryTime)}</span>
        <span className="text-gray-500">{formatTime(entryTime)}</span>
      </div>
      {exitTime && (
        <div className="flex items-center gap-1 text-xs">
          <span className="text-gray-500">Exit:</span>
          <span className="text-gray-300">{formatDate(exitTime)}</span>
          <span className="text-gray-500">{formatTime(exitTime)}</span>
        </div>
      )}
      {showDuration && (
        <div className="flex items-center gap-1 text-xs mt-0.5">
          <Clock className="w-3 h-3 text-gray-500" />
          <span className="text-gray-400">{formatDuration(entryTime, exitTime)}</span>
        </div>
      )}
    </div>
  )
}

// =============================================================================
// BREAKEVEN DISTANCE DISPLAY
// =============================================================================

interface BreakevenDistanceProps {
  currentPrice: number
  breakeven: number | null | undefined
  direction?: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | string
  className?: string
}

/**
 * Shows distance to breakeven with color coding
 */
export function BreakevenDistance({
  currentPrice,
  breakeven,
  direction,
  className = ''
}: BreakevenDistanceProps) {
  if (!breakeven || !currentPrice) return <span className="text-gray-500">--</span>

  const distance = breakeven - currentPrice
  const distancePct = (distance / currentPrice) * 100
  const isAbove = distance > 0

  // Determine if we're on the "good" side of breakeven
  let isGoodSide = false
  if (direction === 'BULLISH') {
    isGoodSide = currentPrice > breakeven // Want price above breakeven for bull spreads
  } else if (direction === 'BEARISH') {
    isGoodSide = currentPrice < breakeven // Want price below breakeven for bear spreads
  }

  const color = isGoodSide ? 'text-green-400' : 'text-yellow-400'

  return (
    <div className={`flex flex-col ${className}`}>
      <div className={`text-sm font-medium ${color}`}>
        ${Math.abs(distance).toFixed(2)} {isAbove ? 'below' : 'above'}
      </div>
      <div className="text-xs text-gray-500">
        ({Math.abs(distancePct).toFixed(2)}% to BE)
      </div>
    </div>
  )
}

// =============================================================================
// ENTRY CONTEXT DISPLAY
// =============================================================================

interface EntryContextProps {
  vixAtEntry?: number
  spotAtEntry?: number
  callWall?: number
  putWall?: number
  gexRegime?: string
  className?: string
}

/**
 * Shows market context at entry time (VIX, walls, regime)
 */
export function EntryContext({
  vixAtEntry,
  spotAtEntry,
  callWall,
  putWall,
  gexRegime,
  className = ''
}: EntryContextProps) {
  return (
    <div className={`flex flex-wrap gap-2 ${className}`}>
      {vixAtEntry !== undefined && (
        <div className="flex items-center gap-1 px-2 py-1 bg-yellow-900/30 rounded text-xs">
          <span className="text-yellow-500">VIX:</span>
          <span className="text-yellow-400 font-medium">{vixAtEntry.toFixed(1)}</span>
        </div>
      )}
      {spotAtEntry !== undefined && (
        <div className="flex items-center gap-1 px-2 py-1 bg-blue-900/30 rounded text-xs">
          <span className="text-blue-500">Spot:</span>
          <span className="text-blue-400 font-medium">${spotAtEntry.toLocaleString()}</span>
        </div>
      )}
      {gexRegime && (
        <div className={`flex items-center gap-1 px-2 py-1 rounded text-xs ${
          gexRegime.includes('POSITIVE') ? 'bg-green-900/30 text-green-400' :
          gexRegime.includes('NEGATIVE') ? 'bg-red-900/30 text-red-400' :
          'bg-gray-800 text-gray-400'
        }`}>
          {gexRegime.replace('_', ' ')}
        </div>
      )}
      {(callWall || putWall) && (
        <div className="flex items-center gap-1 px-2 py-1 bg-purple-900/30 rounded text-xs">
          <span className="text-purple-500">Walls:</span>
          <span className="text-red-400">{callWall?.toLocaleString() || '--'}</span>
          <span className="text-gray-500">/</span>
          <span className="text-green-400">{putWall?.toLocaleString() || '--'}</span>
        </div>
      )}
    </div>
  )
}

// =============================================================================
// UNLOCK CONDITIONS DISPLAY
// =============================================================================

interface UnlockCondition {
  condition: string
  currentValue: string | number
  requiredValue: string | number
  met: boolean
}

interface UnlockConditionsProps {
  conditions: UnlockCondition[]
  className?: string
}

/**
 * Shows what conditions need to be met for trading to unlock
 */
export function UnlockConditions({ conditions, className = '' }: UnlockConditionsProps) {
  if (!conditions || conditions.length === 0) return null

  const metCount = conditions.filter(c => c.met).length

  return (
    <div className={`bg-gray-900/50 rounded-lg p-3 ${className}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-gray-400 uppercase">Unlock Conditions</span>
        <span className={`text-xs ${metCount === conditions.length ? 'text-green-400' : 'text-yellow-400'}`}>
          {metCount}/{conditions.length} met
        </span>
      </div>
      <div className="space-y-1.5">
        {conditions.map((cond, idx) => (
          <div key={idx} className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              {cond.met ? (
                <CheckCircle className="w-3 h-3 text-green-400" />
              ) : (
                <XCircle className="w-3 h-3 text-red-400" />
              )}
              <span className={cond.met ? 'text-gray-300' : 'text-gray-500'}>{cond.condition}</span>
            </div>
            <div className="text-gray-500">
              <span className={cond.met ? 'text-green-400' : 'text-yellow-400'}>{cond.currentValue}</span>
              <span className="mx-1">/</span>
              <span>{cond.requiredValue}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// =============================================================================
// DRAWDOWN DISPLAY
// =============================================================================

interface DrawdownDisplayProps {
  currentEquity: number
  highWaterMark: number
  maxDrawdownPct?: number
  className?: string
}

/**
 * Shows current drawdown from high water mark
 */
export function DrawdownDisplay({
  currentEquity,
  highWaterMark,
  maxDrawdownPct,
  className = ''
}: DrawdownDisplayProps) {
  const currentDrawdown = highWaterMark > 0
    ? ((highWaterMark - currentEquity) / highWaterMark) * 100
    : 0
  const isInDrawdown = currentDrawdown > 0

  return (
    <div className={`${className}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-gray-500">Current Drawdown</span>
        <span className={`text-sm font-medium ${isInDrawdown ? 'text-red-400' : 'text-green-400'}`}>
          {isInDrawdown ? `-${currentDrawdown.toFixed(2)}%` : 'At HWM'}
        </span>
      </div>
      {maxDrawdownPct !== undefined && (
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">Max Drawdown</span>
          <span className="text-sm text-red-400">-{maxDrawdownPct.toFixed(2)}%</span>
        </div>
      )}
      {/* Visual bar */}
      <div className="mt-2 h-2 bg-gray-800 rounded-full overflow-hidden">
        <div
          className={`h-full transition-all duration-300 ${
            currentDrawdown > 10 ? 'bg-red-500' :
            currentDrawdown > 5 ? 'bg-yellow-500' :
            'bg-green-500'
          }`}
          style={{ width: `${Math.min(currentDrawdown * 5, 100)}%` }}
        />
      </div>
    </div>
  )
}

// Export all components
export default {
  BOT_BRANDS,
  UNIFIED_TABS,
  DataFreshnessIndicator,
  BotCard,
  EmptyState,
  LoadingState,
  StatCard,
  StatusBadge,
  DirectionIndicator,
  PnLDisplay,
  BotPageHeader,
  formatDuration,
  TimeInPosition,
  DateRangeDisplay,
  BreakevenDistance,
  EntryContext,
  UnlockConditions,
  DrawdownDisplay,
}
