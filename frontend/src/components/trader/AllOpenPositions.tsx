'use client'

import { useState, useEffect, useRef, useMemo } from 'react'
import {
  TrendingUp, TrendingDown, AlertTriangle, Clock, Timer, Eye, X,
  ChevronRight, Zap, Shield, Target, DollarSign, Activity, Gauge,
  Info, Flame, Hourglass, ChevronDown, ChevronUp, BarChart3, Brain
} from 'lucide-react'
import { LivePosition } from './LivePortfolio'

// Extended position interface with all available data
interface EnhancedPosition extends LivePosition {
  // Greeks at entry (from DB)
  entry_delta?: number
  entry_gamma?: number
  entry_theta?: number
  entry_vega?: number
  // Risk metrics
  max_profit?: number
  max_loss?: number
  probability_of_profit?: number
  // 0DTE flag
  is_0dte?: boolean
  // Context at entry
  ml_direction?: string
  ml_confidence?: number
  oracle_confidence?: number
  gex_regime?: string
  vix_at_entry?: number
  put_wall_at_entry?: number
  call_wall_at_entry?: number
}

interface AllOpenPositionsProps {
  botName: 'SOLOMON' | 'FORTRESS' | 'ANCHOR'
  positions: LivePosition[]
  underlyingPrice?: number
  isLoading?: boolean
  lastUpdated?: string
  onPositionClick?: (position: LivePosition) => void
  onClosePosition?: (position: LivePosition) => void
}

// Format currency
const formatCurrency = (value: number) => {
  const prefix = value >= 0 ? '+' : ''
  return `${prefix}$${Math.abs(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

// Format percentage
const formatPct = (value: number) => {
  const prefix = value >= 0 ? '+' : ''
  return `${prefix}${value.toFixed(2)}%`
}

// Calculate time to expiration
function getExpirationInfo(expiration?: string): {
  timeLeft: string
  is0DTE: boolean
  urgency: 'low' | 'medium' | 'high' | 'critical'
  hoursLeft: number
} {
  if (!expiration) return { timeLeft: '', is0DTE: false, urgency: 'low', hoursLeft: 999 }

  const now = new Date()
  const exp = new Date(expiration + 'T16:00:00') // Market close
  const diffMs = exp.getTime() - now.getTime()
  const hoursLeft = diffMs / (1000 * 60 * 60)
  const daysLeft = Math.floor(hoursLeft / 24)

  let timeLeft: string
  let urgency: 'low' | 'medium' | 'high' | 'critical'

  if (hoursLeft <= 0) {
    timeLeft = 'EXPIRED'
    urgency = 'critical'
  } else if (hoursLeft <= 1) {
    const minsLeft = Math.floor((hoursLeft * 60))
    timeLeft = `${minsLeft}m left`
    urgency = 'critical'
  } else if (hoursLeft <= 4) {
    timeLeft = `${hoursLeft.toFixed(1)}h left`
    urgency = 'high'
  } else if (daysLeft === 0) {
    timeLeft = `${Math.floor(hoursLeft)}h left`
    urgency = 'medium'
  } else if (daysLeft === 1) {
    timeLeft = '1 day left'
    urgency = 'low'
  } else {
    timeLeft = `${daysLeft} days left`
    urgency = 'low'
  }

  const is0DTE = daysLeft === 0 && hoursLeft > 0

  return { timeLeft, is0DTE, urgency, hoursLeft }
}

// Format expiration date for display (e.g., "Jan 17" or "Jan 17, 2025")
function formatExpiration(expiration?: string): string {
  if (!expiration) return '--'

  try {
    const date = new Date(expiration + 'T12:00:00') // Noon to avoid timezone issues
    const now = new Date()
    const sameYear = date.getFullYear() === now.getFullYear()

    // Format: "Jan 17" for current year, "Jan 17, 2025" for different year
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      ...(sameYear ? {} : { year: 'numeric' })
    })
  } catch {
    return expiration // Fallback to raw string if parsing fails
  }
}

// Calculate time since entry
function getPositionAge(entryTime?: string): { age: string; timestamp: string } {
  if (!entryTime) return { age: '', timestamp: '' }

  const entry = new Date(entryTime)
  const now = new Date()
  const diffMs = now.getTime() - entry.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  let age: string
  if (diffDays > 0) {
    age = `${diffDays}d ${diffHours % 24}h`
  } else if (diffHours > 0) {
    age = `${diffHours}h ${diffMins % 60}m`
  } else {
    age = `${diffMins}m`
  }

  const timestamp = entry.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })

  return { age, timestamp }
}

// Estimate current delta based on price movement
function estimateCurrentDelta(
  entryDelta: number,
  spotAtEntry: number,
  spotNow: number,
  longStrike: number,
  shortStrike: number,
  isBullish: boolean
): number {
  if (!entryDelta || !spotAtEntry || !spotNow) return entryDelta || 0

  // Simplified delta drift estimation
  const pricePctMove = (spotNow - spotAtEntry) / spotAtEntry
  const deltaShift = pricePctMove * 0.5 // Approximate gamma effect

  let newDelta = entryDelta + (isBullish ? deltaShift : -deltaShift)
  return Math.max(-1, Math.min(1, newDelta))
}

// Hook to track P&L changes and trigger animations
function usePnLAnimation(pnl: number) {
  const [isFlashing, setIsFlashing] = useState(false)
  const [flashDirection, setFlashDirection] = useState<'up' | 'down' | null>(null)
  const prevPnL = useRef(pnl)

  useEffect(() => {
    if (prevPnL.current !== pnl) {
      const direction = pnl > prevPnL.current ? 'up' : 'down'
      setFlashDirection(direction)
      setIsFlashing(true)
      prevPnL.current = pnl

      const timer = setTimeout(() => {
        setIsFlashing(false)
        setFlashDirection(null)
      }, 1000)

      return () => clearTimeout(timer)
    }
  }, [pnl])

  return { isFlashing, flashDirection }
}

// Calculate probability of profit based on current price and strikes
function calculateProbabilityOfProfit(
  currentPrice: number,
  putShort: number,
  callShort: number,
  daysToExpiry: number,
  isIC: boolean = true
): { probability: number; trend: 'improving' | 'worsening' | 'stable' } {
  if (!currentPrice || !putShort || !callShort) {
    return { probability: 0, trend: 'stable' }
  }

  // Distance to short strikes as percentage
  const putBuffer = ((currentPrice - putShort) / currentPrice) * 100
  const callBuffer = ((callShort - currentPrice) / currentPrice) * 100
  const minBuffer = Math.min(putBuffer, callBuffer)

  // Base probability from buffer (simplified model)
  // More buffer = higher probability of profit
  let baseProbability: number
  if (minBuffer > 3) baseProbability = 85
  else if (minBuffer > 2) baseProbability = 75
  else if (minBuffer > 1) baseProbability = 60
  else if (minBuffer > 0.5) baseProbability = 45
  else if (minBuffer > 0) baseProbability = 30
  else baseProbability = 15

  // Adjust for time decay benefit (theta positive for credit spreads)
  const timeBonus = Math.min(10, (7 - daysToExpiry) * 2)
  const probability = Math.min(95, Math.max(5, baseProbability + timeBonus))

  // Trend based on buffer symmetry
  const trend = putBuffer > callBuffer * 1.5 ? 'worsening' :
                callBuffer > putBuffer * 1.5 ? 'worsening' : 'stable'

  return { probability: Math.round(probability), trend }
}

// Generate natural language trade explanation
function generateTradeExplanation(position: EnhancedPosition): string {
  const parts: string[] = []

  // ML Signal
  if (position.ml_direction && position.ml_confidence) {
    const confidence = position.ml_confidence > 80 ? 'strong' :
                       position.ml_confidence > 60 ? 'moderate' : 'slight'
    parts.push(`ML predicted ${confidence} ${position.ml_direction.toLowerCase()} move`)
  }

  // GEX Regime
  if (position.gex_regime) {
    const regime = position.gex_regime.toLowerCase()
    if (regime.includes('positive')) {
      parts.push('positive gamma environment (mean reversion expected)')
    } else if (regime.includes('negative')) {
      parts.push('negative gamma environment (trend following)')
    }
  }

  // VIX Context
  if (position.vix_at_entry) {
    if (position.vix_at_entry < 15) {
      parts.push('low volatility favored premium selling')
    } else if (position.vix_at_entry > 25) {
      parts.push('elevated VIX offered rich premiums')
    }
  }

  // Prophet Signal
  if (position.oracle_confidence && position.oracle_confidence > 70) {
    parts.push('Prophet confirmed directional bias')
  }

  // Gamma Walls
  if (position.put_wall_at_entry && position.call_wall_at_entry) {
    parts.push(`price between put wall ($${position.put_wall_at_entry}) and call wall ($${position.call_wall_at_entry})`)
  }

  if (parts.length === 0) {
    return 'Trade entered based on standard strategy criteria'
  }

  return parts.slice(0, 3).join(', ') + '.'
}

// Probability of Profit Badge Component
function ProbabilityBadge({ probability, trend, compact = false }: {
  probability: number
  trend: 'improving' | 'worsening' | 'stable'
  compact?: boolean
}) {
  const color = probability >= 70 ? 'text-green-400 bg-green-400/10' :
                probability >= 50 ? 'text-yellow-400 bg-yellow-400/10' :
                'text-red-400 bg-red-400/10'

  const trendIcon = trend === 'improving' ? '↑' :
                    trend === 'worsening' ? '↓' : ''

  if (compact) {
    return (
      <span className={`text-xs px-1.5 py-0.5 rounded ${color}`}>
        {probability}% {trendIcon}
      </span>
    )
  }

  return (
    <div className={`flex items-center gap-1.5 px-2 py-1 rounded-lg ${color}`}>
      <Target className="w-3 h-3" />
      <span className="text-xs font-medium">{probability}% PoP</span>
      {trendIcon && <span className="text-xs">{trendIcon}</span>}
    </div>
  )
}

// Why This Trade Component
function WhyThisTrade({ position, isExpanded, onToggle }: {
  position: EnhancedPosition
  isExpanded: boolean
  onToggle: () => void
}) {
  const explanation = generateTradeExplanation(position)
  const hasContext = position.ml_direction || position.gex_regime || position.vix_at_entry

  if (!hasContext) return null

  return (
    <div className="mt-3 border-t border-gray-800 pt-3">
      <button
        onClick={onToggle}
        className="flex items-center gap-2 text-xs text-gray-400 hover:text-gray-300 transition-colors w-full"
      >
        <Brain className="w-3 h-3" />
        <span>Why this trade?</span>
        {isExpanded ? <ChevronUp className="w-3 h-3 ml-auto" /> : <ChevronDown className="w-3 h-3 ml-auto" />}
      </button>

      {isExpanded && (
        <div className="mt-2 p-2 bg-gray-900/50 rounded-lg">
          <p className="text-xs text-gray-300 leading-relaxed">{explanation}</p>

          {/* Quick stats row */}
          <div className="flex flex-wrap gap-2 mt-2">
            {position.ml_confidence && (
              <span className="text-[10px] px-1.5 py-0.5 bg-blue-500/20 text-blue-400 rounded">
                ML: {position.ml_confidence}%
              </span>
            )}
            {position.vix_at_entry && (
              <span className="text-[10px] px-1.5 py-0.5 bg-purple-500/20 text-purple-400 rounded">
                VIX: {position.vix_at_entry.toFixed(1)}
              </span>
            )}
            {position.oracle_confidence && (
              <span className="text-[10px] px-1.5 py-0.5 bg-amber-500/20 text-amber-400 rounded">
                Prophet: {position.oracle_confidence}%
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// Greeks Display Component
function GreeksDisplay({
  entryDelta,
  entryGamma,
  entryTheta,
  currentDelta,
  compact = false
}: {
  entryDelta?: number
  entryGamma?: number
  entryTheta?: number
  currentDelta?: number
  compact?: boolean
}) {
  const hasDrift = entryDelta && currentDelta && Math.abs(currentDelta - entryDelta) > 0.05

  if (compact) {
    return (
      <div className="flex items-center gap-2 text-xs">
        <span className="text-gray-500">Δ</span>
        <span className={`font-mono ${hasDrift ? 'text-yellow-400' : 'text-gray-400'}`}>
          {currentDelta?.toFixed(2) || entryDelta?.toFixed(2) || '--'}
        </span>
        {hasDrift && (
          <span className="text-yellow-500 text-[10px]">
            (was {entryDelta?.toFixed(2)})
          </span>
        )}
      </div>
    )
  }

  return (
    <div className="bg-gray-900/50 rounded-lg p-2">
      <div className="flex items-center gap-1 text-xs text-gray-500 mb-2">
        <Activity className="w-3 h-3" />
        <span>Greeks</span>
        {hasDrift && (
          <span className="ml-auto px-1.5 py-0.5 bg-yellow-500/20 text-yellow-400 rounded text-[10px] flex items-center gap-1">
            <AlertTriangle className="w-2.5 h-2.5" />
            DRIFT
          </span>
        )}
      </div>
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div>
          <span className="text-gray-500 block">Delta</span>
          <div className="flex flex-col">
            <span className={`font-mono ${hasDrift ? 'text-yellow-400' : 'text-white'}`}>
              {currentDelta?.toFixed(3) || entryDelta?.toFixed(3) || '--'}
            </span>
            {hasDrift && (
              <span className="text-gray-600 text-[10px]">entry: {entryDelta?.toFixed(3)}</span>
            )}
          </div>
        </div>
        <div>
          <span className="text-gray-500 block">Gamma</span>
          <span className="text-white font-mono">{entryGamma?.toFixed(3) || '--'}</span>
        </div>
        <div>
          <span className="text-gray-500 block">Theta</span>
          <span className="text-red-400 font-mono">{entryTheta?.toFixed(2) || '--'}</span>
        </div>
      </div>
    </div>
  )
}

// Max Profit Progress Bar
function ProfitProgress({
  currentPnl,
  maxProfit,
  maxLoss
}: {
  currentPnl: number
  maxProfit?: number
  maxLoss?: number
}) {
  if (!maxProfit) return null

  const progressPct = Math.min(100, Math.max(0, (currentPnl / maxProfit) * 100))
  const isProfit = currentPnl >= 0

  // Calculate how close to max loss if losing
  const lossProgress = maxLoss && currentPnl < 0
    ? Math.min(100, (Math.abs(currentPnl) / Math.abs(maxLoss)) * 100)
    : 0

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-gray-500">Profit Progress</span>
        <span className={`font-medium ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
          {progressPct.toFixed(0)}% of max
        </span>
      </div>
      <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
        {isProfit ? (
          <div
            className="h-full bg-gradient-to-r from-green-600 to-green-400 transition-all duration-500"
            style={{ width: `${progressPct}%` }}
          />
        ) : (
          <div
            className="h-full bg-gradient-to-r from-red-600 to-red-400 transition-all duration-500"
            style={{ width: `${lossProgress}%` }}
          />
        )}
      </div>
      <div className="flex justify-between text-[10px] text-gray-600">
        <span>Max Loss: ${maxLoss?.toFixed(0)}</span>
        <span>Max Profit: ${maxProfit?.toFixed(0)}</span>
      </div>
    </div>
  )
}

// 0DTE Badge Component
function ZeroDTEBadge({
  timeLeft,
  urgency
}: {
  timeLeft: string
  urgency: 'low' | 'medium' | 'high' | 'critical'
}) {
  const colors = {
    low: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    high: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    critical: 'bg-red-500/20 text-red-400 border-red-500/30 animate-pulse'
  }

  return (
    <div className={`flex items-center gap-1 px-2 py-1 rounded border text-xs font-medium ${colors[urgency]}`}>
      <Flame className="w-3 h-3" />
      <span>0DTE</span>
      <span className="opacity-75">• {timeLeft}</span>
    </div>
  )
}

// Entry Context Summary
function EntryContext({
  mlDirection,
  mlConfidence,
  prophetConfidence,
  gexRegime,
  vixAtEntry
}: {
  mlDirection?: string
  mlConfidence?: number
  prophetConfidence?: number
  gexRegime?: string
  vixAtEntry?: number
}) {
  const [expanded, setExpanded] = useState(false)

  if (!mlDirection && !gexRegime && !vixAtEntry) return null

  return (
    <div className="border-t border-gray-800 pt-2 mt-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-400 w-full"
      >
        <Brain className="w-3 h-3" />
        <span>Entry Context</span>
        {expanded ? <ChevronUp className="w-3 h-3 ml-auto" /> : <ChevronDown className="w-3 h-3 ml-auto" />}
      </button>

      {expanded && (
        <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
          {mlDirection && (
            <div>
              <span className="text-gray-600 block">ML Signal</span>
              <span className={`font-medium ${mlDirection === 'BULLISH' ? 'text-green-400' : 'text-red-400'}`}>
                {mlDirection} {mlConfidence ? `(${(mlConfidence * 100).toFixed(0)}%)` : ''}
              </span>
            </div>
          )}
          {prophetConfidence && (
            <div>
              <span className="text-gray-600 block">Prophet</span>
              <span className="text-purple-400 font-medium">
                {(prophetConfidence * 100).toFixed(0)}% conf
              </span>
            </div>
          )}
          {gexRegime && (
            <div>
              <span className="text-gray-600 block">GEX Regime</span>
              <span className={`font-medium ${gexRegime === 'POSITIVE' ? 'text-green-400' : 'text-red-400'}`}>
                {gexRegime}
              </span>
            </div>
          )}
          {vixAtEntry && (
            <div>
              <span className="text-gray-600 block">VIX at Entry</span>
              <span className="text-yellow-400 font-medium">{vixAtEntry.toFixed(1)}</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Single Position Card - SOLOMON style (spreads)
function SolomonPositionCard({
  position,
  underlyingPrice,
  onClick,
  onClose
}: {
  position: EnhancedPosition
  underlyingPrice?: number
  onClick?: () => void
  onClose?: () => void
}) {
  const [whyExpanded, setWhyExpanded] = useState(false)
  const isPositive = position.unrealized_pnl >= 0
  const isBullish = position.spread_type?.includes('BULL')
  const spreadType = isBullish ? 'Bull Call Spread' : 'Bear Put Spread'
  const { isFlashing, flashDirection } = usePnLAnimation(position.unrealized_pnl)
  const { age, timestamp } = getPositionAge(position.entry_time || position.created_at)
  const expInfo = getExpirationInfo(position.expiration)

  // Calculate probability for SOLOMON spreads (simplified - debit spreads)
  const price = underlyingPrice || position.current_underlying || 0
  const shortStrike = position.short_strike || 0
  const longStrike = position.long_strike || 0
  const pop = calculateProbabilityOfProfit(
    price,
    isBullish ? longStrike : shortStrike,  // Use appropriate strikes based on direction
    isBullish ? shortStrike : longStrike,
    expInfo.hoursLeft / 24
  )

  // Estimate current delta
  const currentDelta = useMemo(() => {
    if (!position.entry_delta || !position.underlying_at_entry || !underlyingPrice) {
      return position.entry_delta
    }
    return estimateCurrentDelta(
      position.entry_delta,
      position.underlying_at_entry,
      underlyingPrice,
      position.long_strike || 0,
      position.short_strike || 0,
      !!isBullish
    )
  }, [position, underlyingPrice, isBullish])

  // Calculate max profit (spread width - entry debit for debit spreads)
  const spreadWidth = Math.abs((position.long_strike || 0) - (position.short_strike || 0))
  const maxProfit = position.max_profit || (spreadWidth * 100 * (position.contracts || 1) - (position.entry_debit || 0) * 100 * (position.contracts || 1))
  const maxLoss = position.max_loss || ((position.entry_debit || 0) * 100 * (position.contracts || 1))

  return (
    <div
      className={`bg-[#111] border rounded-lg p-4 transition-all ${
        isFlashing
          ? flashDirection === 'up'
            ? 'ring-2 ring-[#00C805]/50 border-[#00C805]/30'
            : 'ring-2 ring-[#FF5000]/50 border-[#FF5000]/30'
          : 'border-gray-800 hover:border-gray-700'
      }`}
    >
      {/* Header Row */}
      <div className="flex justify-between items-start mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <div className={`w-2 h-2 rounded-full animate-pulse ${isPositive ? 'bg-[#00C805]' : 'bg-[#FF5000]'}`} />
          <span className="text-white font-medium">{spreadType}</span>
          <span className={`text-xs px-2 py-0.5 rounded ${isBullish ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
            {isBullish ? 'BULLISH' : 'BEARISH'}
          </span>
          {expInfo.is0DTE && (
            <ZeroDTEBadge timeLeft={expInfo.timeLeft} urgency={expInfo.urgency} />
          )}
          {pop.probability > 0 && (
            <ProbabilityBadge probability={pop.probability} trend={pop.trend} compact />
          )}
        </div>
        <div className="text-right">
          <div className={`text-xl font-bold transition-colors duration-200 ${
            isFlashing
              ? flashDirection === 'up' ? 'text-[#00FF00]' : 'text-[#FF0000]'
              : isPositive ? 'text-[#00C805]' : 'text-[#FF5000]'
          }`}>
            {formatCurrency(position.unrealized_pnl)}
          </div>
          <div className={`text-sm ${isPositive ? 'text-[#00C805]' : 'text-[#FF5000]'}`}>
            {formatPct(position.pnl_pct)}
          </div>
        </div>
      </div>

      {/* Position Details */}
      <div className="space-y-2 mb-3">
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-400">
            SPY ${position.long_strike}/${position.short_strike}
          </span>
          <span className="text-gray-500">
            {position.contracts_remaining || position.contracts} contracts
          </span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-2">
            <span className="text-gray-400">Exp: {formatExpiration(position.expiration)}</span>
            {!expInfo.is0DTE && (
              <span className={`text-xs ${
                expInfo.urgency === 'critical' ? 'text-red-400' :
                expInfo.urgency === 'high' ? 'text-orange-400' :
                expInfo.urgency === 'medium' ? 'text-yellow-400' : 'text-gray-500'
              }`}>
                ({expInfo.timeLeft})
              </span>
            )}
          </div>
          {position.entry_debit && (
            <span className="text-gray-500">Entry: ${position.entry_debit?.toFixed(2)}</span>
          )}
        </div>
      </div>

      {/* Greeks Display */}
      {(position.entry_delta || position.entry_gamma) && (
        <GreeksDisplay
          entryDelta={position.entry_delta}
          entryGamma={position.entry_gamma}
          entryTheta={position.entry_theta}
          currentDelta={currentDelta}
        />
      )}

      {/* Max Profit Progress */}
      <div className="mt-3">
        <ProfitProgress
          currentPnl={position.unrealized_pnl}
          maxProfit={maxProfit}
          maxLoss={maxLoss}
        />
      </div>

      {/* Timestamps */}
      <div className="bg-gray-900/50 rounded-lg p-2 my-3 flex items-center justify-between text-xs">
        <div className="flex items-center gap-1 text-gray-400">
          <Clock className="w-3 h-3" />
          <span>Opened: {timestamp}</span>
        </div>
        <div className="flex items-center gap-1 text-gray-500">
          <Timer className="w-3 h-3" />
          <span>{age} ago</span>
        </div>
      </div>

      {/* Current Values */}
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <span className="text-gray-500 block text-xs">Entry</span>
          <span className="text-white font-medium">${position.entry_debit?.toFixed(2)}</span>
        </div>
        <div>
          <span className="text-gray-500 block text-xs">Current</span>
          <span className="text-white font-medium">${position.current_spread_value?.toFixed(2) || '--'}</span>
        </div>
        {underlyingPrice && position.underlying_at_entry && (
          <>
            <div>
              <span className="text-gray-500 block text-xs">SPY at Entry</span>
              <span className="text-white font-medium">${position.underlying_at_entry?.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-gray-500 block text-xs">SPY Now</span>
              <span className={`font-medium ${underlyingPrice >= position.underlying_at_entry ? 'text-green-400' : 'text-red-400'}`}>
                ${underlyingPrice.toFixed(2)}
                <span className="text-xs ml-1">
                  ({underlyingPrice >= position.underlying_at_entry ? '+' : ''}{((underlyingPrice - position.underlying_at_entry) / position.underlying_at_entry * 100).toFixed(2)}%)
                </span>
              </span>
            </div>
          </>
        )}
      </div>

      {/* Entry Context (collapsed by default) */}
      <EntryContext
        mlDirection={position.ml_direction}
        mlConfidence={position.ml_confidence}
        prophetConfidence={position.oracle_confidence}
        gexRegime={position.gex_regime}
        vixAtEntry={position.vix_at_entry}
      />

      {/* Why This Trade - Natural Language Explanation */}
      <WhyThisTrade
        position={position}
        isExpanded={whyExpanded}
        onToggle={() => setWhyExpanded(!whyExpanded)}
      />

      {/* Actions - Mobile responsive */}
      <div className="flex flex-col sm:flex-row gap-2 mt-3 pt-3 border-t border-gray-800">
        <button
          onClick={onClick}
          className="flex-1 flex items-center justify-center gap-1 px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-white transition-colors"
        >
          <Eye className="w-4 h-4" />
          Full Details
        </button>
        {onClose && (
          <button
            onClick={onClose}
            className="flex items-center justify-center gap-1 px-3 py-2 bg-red-500/20 hover:bg-red-500/30 rounded-lg text-sm text-red-400 transition-colors"
          >
            <X className="w-4 h-4" />
            Close
          </button>
        )}
      </div>
    </div>
  )
}

// Single Position Card - FORTRESS style (iron condors)
function AresPositionCard({
  position,
  underlyingPrice,
  onClick,
  onClose
}: {
  position: EnhancedPosition
  underlyingPrice?: number
  onClick?: () => void
  onClose?: () => void
}) {
  const [whyExpanded, setWhyExpanded] = useState(false)
  const isPositive = position.unrealized_pnl >= 0
  const isAtRisk = position.risk_status === 'AT_RISK'
  const { isFlashing, flashDirection } = usePnLAnimation(position.unrealized_pnl)
  const { age, timestamp } = getPositionAge(position.entry_time || position.created_at)
  const expInfo = getExpirationInfo(position.expiration)

  // Price position visualization
  const putShort = position.put_short_strike || 0
  const callShort = position.call_short_strike || 0
  const price = underlyingPrice || position.current_underlying || 0
  const range = callShort - putShort
  const pricePosition = range > 0 ? ((price - putShort) / range) * 100 : 50

  // Calculate probability of profit
  const pop = calculateProbabilityOfProfit(price, putShort, callShort, expInfo.hoursLeft / 24)

  // Max profit/loss for IC
  const maxProfit = position.max_profit || (position.credit_received || 0) * 100 * (position.contracts || 1)
  const spreadWidth = (position.call_long_strike || 0) - (position.call_short_strike || 0)
  const maxLoss = position.max_loss || (spreadWidth - (position.credit_received || 0)) * 100 * (position.contracts || 1)

  return (
    <div
      className={`bg-[#111] border rounded-lg p-4 transition-all ${
        isAtRisk
          ? 'border-[#FF5000] bg-[#FF5000]/5'
          : isFlashing
            ? flashDirection === 'up'
              ? 'ring-2 ring-[#00C805]/50 border-[#00C805]/30'
              : 'ring-2 ring-[#FF5000]/50 border-[#FF5000]/30'
            : 'border-gray-800 hover:border-gray-700'
      }`}
    >
      {/* Header Row */}
      <div className="flex justify-between items-start mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <div className={`w-2 h-2 rounded-full animate-pulse ${isPositive ? 'bg-[#00C805]' : 'bg-[#FF5000]'}`} />
          <span className="text-white font-medium">Iron Condor</span>
          {isAtRisk && (
            <span className="flex items-center gap-1 text-xs text-[#FF5000] bg-[#FF5000]/10 px-2 py-0.5 rounded animate-pulse">
              <AlertTriangle className="w-3 h-3" />
              AT RISK
            </span>
          )}
          {expInfo.is0DTE && (
            <ZeroDTEBadge timeLeft={expInfo.timeLeft} urgency={expInfo.urgency} />
          )}
          {pop.probability > 0 && (
            <ProbabilityBadge probability={pop.probability} trend={pop.trend} compact />
          )}
        </div>
        <div className="text-right">
          <div className={`text-xl font-bold transition-colors duration-200 ${
            isFlashing
              ? flashDirection === 'up' ? 'text-[#00FF00]' : 'text-[#FF0000]'
              : isPositive ? 'text-[#00C805]' : 'text-[#FF5000]'
          }`}>
            {formatCurrency(position.unrealized_pnl)}
          </div>
          <div className={`text-sm ${isPositive ? 'text-[#00C805]' : 'text-[#FF5000]'}`}>
            {formatPct(position.pnl_pct)}
          </div>
        </div>
      </div>

      {/* Timestamps */}
      <div className="bg-gray-900/50 rounded-lg p-2 mb-3 flex items-center justify-between text-xs">
        <div className="flex items-center gap-1 text-gray-400">
          <Clock className="w-3 h-3" />
          <span>Opened: {timestamp}</span>
        </div>
        <div className="flex items-center gap-1">
          <Timer className="w-3 h-3 text-gray-500" />
          <span className="text-gray-500">{age} ago</span>
          {!expInfo.is0DTE && (
            <span className={`ml-2 ${
              expInfo.urgency === 'critical' ? 'text-red-400' :
              expInfo.urgency === 'high' ? 'text-orange-400' :
              expInfo.urgency === 'medium' ? 'text-yellow-400' : 'text-gray-500'
            }`}>
              • {expInfo.timeLeft}
            </span>
          )}
        </div>
      </div>

      {/* Strike Visualization */}
      <div className="bg-[#0a0a0a] rounded-lg p-3 mb-3">
        <div className="flex justify-between text-xs text-gray-500 mb-2">
          <span>PUT SIDE</span>
          <span className="text-white font-medium">${price.toFixed(2)}</span>
          <span>CALL SIDE</span>
        </div>

        {/* Strike bar */}
        <div className="relative h-6 mb-2">
          {/* Background bar */}
          <div className="absolute inset-0 flex">
            <div className="flex-1 bg-[#FF5000]/20 rounded-l" />
            <div className="flex-1 bg-[#00C805]/30" />
            <div className="flex-1 bg-[#FF5000]/20 rounded-r" />
          </div>

          {/* Price indicator */}
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-white z-10"
            style={{ left: `${Math.max(0, Math.min(100, pricePosition))}%` }}
          >
            <div className="absolute -top-1 -left-1.5 w-3 h-3 rounded-full bg-white shadow-lg" />
          </div>
        </div>

        {/* Strike labels */}
        <div className="flex justify-between text-xs">
          <span className="text-gray-500">{position.put_long_strike}/{position.put_short_strike}P</span>
          <span className="text-gray-500">{position.call_short_strike}/{position.call_long_strike}C</span>
        </div>

        {/* Distance indicators */}
        <div className="flex justify-between text-xs mt-2">
          <span className={`${(position.put_distance || 0) > 0 ? 'text-[#00C805]' : 'text-[#FF5000]'}`}>
            ${Math.abs(position.put_distance || 0).toFixed(1)} buffer
          </span>
          <span className={`${(position.call_distance || 0) > 0 ? 'text-[#00C805]' : 'text-[#FF5000]'}`}>
            ${Math.abs(position.call_distance || 0).toFixed(1)} buffer
          </span>
        </div>
      </div>

      {/* Max Profit Progress */}
      <ProfitProgress
        currentPnl={position.unrealized_pnl}
        maxProfit={maxProfit}
        maxLoss={maxLoss}
      />

      {/* Position Details */}
      <div className="grid grid-cols-2 gap-3 text-sm mt-3">
        <div>
          <span className="text-gray-500 block text-xs">Expiration</span>
          <span className="text-white font-medium">{formatExpiration(position.expiration)}</span>
        </div>
        <div>
          <span className="text-gray-500 block text-xs">Contracts</span>
          <span className="text-white font-medium">{position.contracts}</span>
        </div>
        <div>
          <span className="text-gray-500 block text-xs">Credit Received</span>
          <span className="text-green-400 font-medium">${(position.credit_received || 0).toFixed(2)}</span>
        </div>
        <div>
          <span className="text-gray-500 block text-xs">Current Value</span>
          <span className="text-white font-medium">${position.current_value?.toFixed(2) || '--'}</span>
        </div>
      </div>

      {/* Entry Context (collapsed by default) */}
      <EntryContext
        mlDirection={position.ml_direction}
        mlConfidence={position.ml_confidence}
        prophetConfidence={position.oracle_confidence}
        gexRegime={position.gex_regime}
        vixAtEntry={position.vix_at_entry}
      />

      {/* Why This Trade - Natural Language Explanation */}
      <WhyThisTrade
        position={position}
        isExpanded={whyExpanded}
        onToggle={() => setWhyExpanded(!whyExpanded)}
      />

      {/* Actions - Mobile responsive */}
      <div className="flex flex-col sm:flex-row gap-2 mt-3 pt-3 border-t border-gray-800">
        <button
          onClick={onClick}
          className="flex-1 flex items-center justify-center gap-1 px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-white transition-colors"
        >
          <Eye className="w-4 h-4" />
          Full Details
        </button>
        {onClose && (
          <button
            onClick={onClose}
            className="flex items-center justify-center gap-1 px-3 py-2 bg-red-500/20 hover:bg-red-500/30 rounded-lg text-sm text-red-400 transition-colors"
          >
            <X className="w-4 h-4" />
            Close
          </button>
        )}
      </div>
    </div>
  )
}

// Main Component
export default function AllOpenPositions({
  botName,
  positions,
  underlyingPrice,
  isLoading,
  lastUpdated,
  onPositionClick,
  onClosePosition
}: AllOpenPositionsProps) {
  if (isLoading) {
    return (
      <div className="bg-[#0a0a0a] rounded-lg p-6 border border-gray-800">
        <div className="animate-pulse">
          <div className="h-6 bg-gray-800 rounded w-48 mb-4" />
          <div className="h-32 bg-gray-800 rounded" />
        </div>
      </div>
    )
  }

  const hasPositions = positions && positions.length > 0
  const totalUnrealized = positions?.reduce((sum, p) => sum + (p.unrealized_pnl || 0), 0) || 0
  const isPositiveTotal = totalUnrealized >= 0

  // Count 0DTE positions
  const zeroDteCount = positions?.filter(p => {
    const expInfo = getExpirationInfo(p.expiration)
    return expInfo.is0DTE
  }).length || 0

  return (
    <div className="bg-[#0a0a0a] rounded-lg p-6 border border-gray-800">
      {/* Header */}
      <div className="flex justify-between items-center mb-4">
        <div className="flex items-center gap-3 flex-wrap">
          <h3 className="text-lg font-semibold text-white">
            Open Positions
          </h3>
          {hasPositions && (
            <span className="px-2 py-0.5 bg-purple-500/20 text-purple-400 rounded-full text-sm font-medium">
              {positions.length}
            </span>
          )}
          {hasPositions && (
            <div className="flex items-center gap-1 text-xs text-green-400">
              <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              LIVE
            </div>
          )}
          {zeroDteCount > 0 && (
            <div className="flex items-center gap-1 px-2 py-0.5 bg-orange-500/20 text-orange-400 rounded text-xs">
              <Flame className="w-3 h-3" />
              {zeroDteCount} 0DTE
            </div>
          )}
        </div>

        {hasPositions && (
          <div className="text-right">
            <div className={`font-bold ${isPositiveTotal ? 'text-[#00C805]' : 'text-[#FF5000]'}`}>
              {formatCurrency(totalUnrealized)}
            </div>
            <div className="text-xs text-gray-500">Total Unrealized</div>
          </div>
        )}
      </div>

      {/* Last Updated */}
      {lastUpdated && hasPositions && (
        <div className="flex items-center gap-2 text-xs text-gray-500 mb-4">
          <Clock className="w-3 h-3" />
          Last updated: {new Date(lastUpdated).toLocaleTimeString()}
        </div>
      )}

      {/* Positions Grid */}
      {hasPositions ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {positions.map((position) =>
            botName === 'SOLOMON' ? (
              <SolomonPositionCard
                key={position.position_id}
                position={position as EnhancedPosition}
                underlyingPrice={underlyingPrice}
                onClick={() => onPositionClick?.(position)}
                onClose={onClosePosition ? () => onClosePosition(position) : undefined}
              />
            ) : (
              <AresPositionCard
                key={position.position_id}
                position={position as EnhancedPosition}
                underlyingPrice={underlyingPrice}
                onClick={() => onPositionClick?.(position)}
                onClose={onClosePosition ? () => onClosePosition(position) : undefined}
              />
            )
          )}
        </div>
      ) : (
        <div className="text-center py-12">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-800 flex items-center justify-center">
            <Target className="w-8 h-8 text-gray-600" />
          </div>
          <p className="text-gray-400 font-medium">No open positions</p>
          <p className="text-sm text-gray-600 mt-1">
            Positions will appear here when {botName} executes trades
          </p>
        </div>
      )}
    </div>
  )
}
