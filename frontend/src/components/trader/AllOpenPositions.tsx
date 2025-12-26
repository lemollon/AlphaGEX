'use client'

import { useState, useEffect, useRef } from 'react'
import {
  TrendingUp, TrendingDown, AlertTriangle, Clock, Timer, Eye, X,
  ChevronRight, Zap, Shield, Target, DollarSign
} from 'lucide-react'
import { LivePosition } from './LivePortfolio'

interface AllOpenPositionsProps {
  botName: 'ATHENA' | 'ARES'
  positions: LivePosition[]
  underlyingPrice?: number
  isLoading?: boolean
  lastUpdated?: string
  onPositionClick?: (position: LivePosition) => void
  onClosePosition?: (position: LivePosition) => void  // For manual close
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

// Calculate time since entry with full timestamp
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

// Single Position Card - ATHENA style (spreads)
function AthenaPositionCard({
  position,
  underlyingPrice,
  onClick,
  onClose
}: {
  position: LivePosition
  underlyingPrice?: number
  onClick?: () => void
  onClose?: () => void
}) {
  const isPositive = position.unrealized_pnl >= 0
  const spreadType = position.spread_type?.includes('BULL') ? 'Bull Call Spread' :
    position.spread_type?.includes('BEAR') ? 'Bear Put Spread' : 'Spread'
  const { isFlashing, flashDirection } = usePnLAnimation(position.unrealized_pnl)
  const { age, timestamp } = getPositionAge(position.entry_time || position.created_at)

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
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full animate-pulse ${isPositive ? 'bg-[#00C805]' : 'bg-[#FF5000]'}`} />
          <span className="text-white font-medium">{spreadType}</span>
          <span className="text-xs px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded">
            {position.spread_type?.includes('BULL') ? 'BULLISH' : 'BEARISH'}
          </span>
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
          <span className="text-gray-400">Exp: {position.expiration}</span>
          {position.entry_debit && (
            <span className="text-gray-500">Entry: ${position.entry_debit?.toFixed(2)}</span>
          )}
        </div>
      </div>

      {/* Timestamps - PROMINENT */}
      <div className="bg-gray-900/50 rounded-lg p-2 mb-3 flex items-center justify-between text-xs">
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
      <div className="border-t border-gray-800 pt-3 grid grid-cols-2 gap-3 text-sm">
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

      {/* Actions */}
      <div className="flex gap-2 mt-3 pt-3 border-t border-gray-800">
        <button
          onClick={onClick}
          className="flex-1 flex items-center justify-center gap-1 px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-white transition-colors"
        >
          <Eye className="w-4 h-4" />
          Details
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

// Single Position Card - ARES style (iron condors)
function AresPositionCard({
  position,
  underlyingPrice,
  onClick,
  onClose
}: {
  position: LivePosition
  underlyingPrice?: number
  onClick?: () => void
  onClose?: () => void
}) {
  const isPositive = position.unrealized_pnl >= 0
  const isAtRisk = position.risk_status === 'AT_RISK'
  const { isFlashing, flashDirection } = usePnLAnimation(position.unrealized_pnl)
  const { age, timestamp } = getPositionAge(position.entry_time || position.created_at)

  // Price position visualization
  const putShort = position.put_short_strike || 0
  const callShort = position.call_short_strike || 0
  const price = underlyingPrice || position.current_underlying || 0
  const range = callShort - putShort
  const pricePosition = range > 0 ? ((price - putShort) / range) * 100 : 50

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
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full animate-pulse ${isPositive ? 'bg-[#00C805]' : 'bg-[#FF5000]'}`} />
          <span className="text-white font-medium">Iron Condor</span>
          {isAtRisk && (
            <span className="flex items-center gap-1 text-xs text-[#FF5000] bg-[#FF5000]/10 px-2 py-0.5 rounded">
              <AlertTriangle className="w-3 h-3" />
              AT RISK
            </span>
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

      {/* Timestamps - PROMINENT */}
      <div className="bg-gray-900/50 rounded-lg p-2 mb-3 flex items-center justify-between text-xs">
        <div className="flex items-center gap-1 text-gray-400">
          <Clock className="w-3 h-3" />
          <span>Opened: {timestamp}</span>
        </div>
        <div className="flex items-center gap-1 text-gray-500">
          <Timer className="w-3 h-3" />
          <span>{age} ago</span>
        </div>
      </div>

      {/* Strike Visualization */}
      <div className="bg-[#0a0a0a] rounded-lg p-3 mb-3">
        <div className="flex justify-between text-xs text-gray-500 mb-2">
          <span>PUT SIDE</span>
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
            className="absolute top-0 bottom-0 w-0.5 bg-white"
            style={{ left: `${Math.max(0, Math.min(100, pricePosition))}%` }}
          >
            <div className="absolute -top-1 -left-1.5 w-3 h-3 rounded-full bg-white shadow-lg" />
          </div>
        </div>

        {/* Strike labels */}
        <div className="flex justify-between text-xs">
          <span className="text-gray-500">{position.put_long_strike}/{position.put_short_strike}P</span>
          <span className="text-white font-medium">${price.toFixed(2)}</span>
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

      {/* Position Details */}
      <div className="grid grid-cols-2 gap-3 text-sm mb-3">
        <div>
          <span className="text-gray-500 block text-xs">Expiration</span>
          <span className="text-white font-medium">{position.expiration}</span>
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

      {/* Actions */}
      <div className="flex gap-2 pt-3 border-t border-gray-800">
        <button
          onClick={onClick}
          className="flex-1 flex items-center justify-center gap-1 px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-white transition-colors"
        >
          <Eye className="w-4 h-4" />
          Details
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

  return (
    <div className="bg-[#0a0a0a] rounded-lg p-6 border border-gray-800">
      {/* Header */}
      <div className="flex justify-between items-center mb-4">
        <div className="flex items-center gap-3">
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
            botName === 'ATHENA' ? (
              <AthenaPositionCard
                key={position.position_id}
                position={position}
                underlyingPrice={underlyingPrice}
                onClick={() => onPositionClick?.(position)}
                onClose={onClosePosition ? () => onClosePosition(position) : undefined}
              />
            ) : (
              <AresPositionCard
                key={position.position_id}
                position={position}
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
