'use client'

import { useState, useEffect, useRef } from 'react'
import { TrendingUp, TrendingDown, AlertTriangle, Clock, ChevronRight, Timer } from 'lucide-react'
import { LivePosition } from './LivePortfolio'

interface OpenPositionsLiveProps {
  botName: 'SOLOMON' | 'FORTRESS' | 'PEGASUS'
  positions: LivePosition[]
  underlyingPrice?: number
  isLoading?: boolean
  onPositionClick?: (position: LivePosition) => void
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

// Calculate time since entry
function getPositionAge(entryTime?: string): string {
  if (!entryTime) return ''
  const entry = new Date(entryTime)
  const now = new Date()
  const diffMs = now.getTime() - entry.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)

  if (diffHours > 0) {
    return `${diffHours}h ${diffMins % 60}m`
  }
  return `${diffMins}m`
}

// Format currency
const formatCurrency = (value: number) => {
  const prefix = value >= 0 ? '+' : ''
  return `${prefix}$${Math.abs(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

// Format expiration date for display (e.g., "Jan 17" or "Jan 17, 2025")
function formatExpiration(expiration?: string): string {
  if (!expiration) return '--'
  try {
    const date = new Date(expiration + 'T12:00:00')
    const now = new Date()
    const sameYear = date.getFullYear() === now.getFullYear()
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      ...(sameYear ? {} : { year: 'numeric' })
    })
  } catch {
    return expiration
  }
}

// Format percentage
const formatPct = (value: number) => {
  const prefix = value >= 0 ? '+' : ''
  return `${prefix}${value.toFixed(2)}%`
}

// Calculate breakeven for a spread
function getBreakevenInfo(position: LivePosition, currentPrice?: number): { distance: number; distancePct: number; isGoodSide: boolean } | null {
  const breakeven = position.breakeven
  if (!breakeven || !currentPrice) return null

  const distance = currentPrice - breakeven
  const distancePct = (distance / currentPrice) * 100
  const isBullish = position.spread_type?.includes('BULL')

  // For bull spreads, we want price above breakeven
  // For bear spreads, we want price below breakeven
  const isGoodSide = isBullish ? distance > 0 : distance < 0

  return { distance, distancePct, isGoodSide }
}

// Solomon Spread Position Card
function SolomonPositionCard({ position, underlyingPrice, onClick }: { position: LivePosition; underlyingPrice?: number; onClick?: () => void }) {
  const isPositive = position.unrealized_pnl >= 0
  const spreadType = position.spread_type?.includes('BULL') ? 'Bull Call Spread' : 'Bear Call Spread'
  const isBullish = position.spread_type?.includes('BULL')
  const { isFlashing, flashDirection } = usePnLAnimation(position.unrealized_pnl)
  const positionAge = getPositionAge(position.entry_time || position.created_at)
  const beInfo = getBreakevenInfo(position, underlyingPrice)

  return (
    <div
      className={`bg-[#111] border border-gray-800 rounded-lg p-4 hover:border-gray-700 transition-all cursor-pointer ${
        isFlashing ? (flashDirection === 'up' ? 'ring-2 ring-[#00C805]/50' : 'ring-2 ring-[#FF5000]/50') : ''
      }`}
      onClick={onClick}
    >
      <div className="flex justify-between items-start mb-3">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${isPositive ? 'bg-[#00C805]' : 'bg-[#FF5000]'}`} />
          <span className="text-white font-medium">{spreadType}</span>
        </div>
        <div className="text-right">
          <div className={`text-lg font-bold ${isPositive ? 'text-[#00C805]' : 'text-[#FF5000]'}`}>
            {formatCurrency(position.unrealized_pnl)}
          </div>
          <div className={`text-sm ${isPositive ? 'text-[#00C805]' : 'text-[#FF5000]'}`}>
            {formatPct(position.pnl_pct)}
          </div>
        </div>
      </div>

      <div className="text-gray-400 text-sm mb-3">
        SPY ${position.long_strike}/${position.short_strike} Call
        <span className="mx-2">·</span>
        {formatExpiration(position.expiration)}
        <span className="mx-2">·</span>
        {position.contracts_remaining || position.contracts} contracts
        {positionAge && (
          <>
            <span className="mx-2">·</span>
            <span className="flex items-center gap-1 inline-flex">
              <Timer className="w-3 h-3" />
              {positionAge}
            </span>
          </>
        )}
      </div>

      {/* Entry Context - VIX, GEX Regime */}
      {(position.vix_at_entry || position.gex_regime) && (
        <div className="flex flex-wrap gap-2 mb-3">
          {position.vix_at_entry && (
            <span className="px-2 py-1 bg-yellow-900/30 text-yellow-400 text-xs rounded">
              VIX: {position.vix_at_entry.toFixed(1)}
            </span>
          )}
          {position.gex_regime && (
            <span className={`px-2 py-1 text-xs rounded ${
              position.gex_regime.includes('POSITIVE') ? 'bg-green-900/30 text-green-400' :
              position.gex_regime.includes('NEGATIVE') ? 'bg-red-900/30 text-red-400' :
              'bg-gray-800 text-gray-400'
            }`}>
              {position.gex_regime.replace('_', ' ')}
            </span>
          )}
          {position.oracle_confidence && (
            <span className="px-2 py-1 bg-purple-900/30 text-purple-400 text-xs rounded">
              Oracle: {(position.oracle_confidence * 100).toFixed(0)}%
            </span>
          )}
        </div>
      )}

      {/* Breakeven Distance */}
      {beInfo && (
        <div className={`mb-3 p-2 rounded ${beInfo.isGoodSide ? 'bg-green-900/20 border border-green-700/30' : 'bg-yellow-900/20 border border-yellow-700/30'}`}>
          <div className="flex justify-between items-center text-sm">
            <span className="text-gray-400">Distance to BE:</span>
            <span className={beInfo.isGoodSide ? 'text-green-400 font-medium' : 'text-yellow-400 font-medium'}>
              ${Math.abs(beInfo.distance).toFixed(2)} {beInfo.distance > 0 ? 'above' : 'below'}
              <span className="text-xs ml-1">({Math.abs(beInfo.distancePct).toFixed(2)}%)</span>
            </span>
          </div>
        </div>
      )}

      <div className="border-t border-gray-800 pt-3">
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Entry:</span>
          <span className="text-white">${position.entry_debit?.toFixed(2)}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Current:</span>
          <span className="text-white">${position.current_spread_value?.toFixed(2) || '--'}</span>
        </div>
        {position.breakeven && (
          <div className="flex justify-between text-sm">
            <span className="text-gray-500">Breakeven:</span>
            <span className="text-white">${position.breakeven.toFixed(2)}</span>
          </div>
        )}
        {underlyingPrice && (
          <div className="flex justify-between text-sm mt-2">
            <span className="text-gray-500">SPY:</span>
            <span className="text-white">
              ${underlyingPrice.toFixed(2)}
              {position.underlying_at_entry && (
                <span className={`ml-2 text-xs ${underlyingPrice >= position.underlying_at_entry ? 'text-[#00C805]' : 'text-[#FF5000]'}`}>
                  ({underlyingPrice >= position.underlying_at_entry ? '+' : ''}{((underlyingPrice - position.underlying_at_entry) / position.underlying_at_entry * 100).toFixed(2)}%)
                </span>
              )}
            </span>
          </div>
        )}
      </div>

      {/* Scaled P&L indicator if any */}
      {position.scaled_pnl !== undefined && position.scaled_pnl !== 0 && (
        <div className="mt-2 pt-2 border-t border-gray-800">
          <div className="flex justify-between text-xs">
            <span className="text-gray-500">Scaled P&L:</span>
            <span className={position.scaled_pnl >= 0 ? 'text-[#00C805]' : 'text-[#FF5000]'}>
              {formatCurrency(position.scaled_pnl)}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

// FORTRESS Iron Condor Position Card
function AresPositionCard({ position, underlyingPrice, onClick }: { position: LivePosition; underlyingPrice?: number; onClick?: () => void }) {
  const isPositive = position.unrealized_pnl >= 0
  const isAtRisk = position.risk_status === 'AT_RISK'
  const { isFlashing, flashDirection } = usePnLAnimation(position.unrealized_pnl)
  const positionAge = getPositionAge(position.entry_time || position.created_at)

  // Visual representation of where price is relative to strikes
  const putShort = position.put_short_strike || 0
  const callShort = position.call_short_strike || 0
  const price = underlyingPrice || position.current_underlying || 0
  const range = callShort - putShort
  const pricePosition = range > 0 ? ((price - putShort) / range) * 100 : 50

  return (
    <div
      className={`bg-[#111] border rounded-lg p-4 transition-all cursor-pointer ${
        isAtRisk ? 'border-[#FF5000]' : 'border-gray-800 hover:border-gray-700'
      } ${isFlashing ? (flashDirection === 'up' ? 'ring-2 ring-[#00C805]/50' : 'ring-2 ring-[#FF5000]/50') : ''}`}
      onClick={onClick}
    >
      <div className="flex justify-between items-start mb-3">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${isPositive ? 'bg-[#00C805]' : 'bg-[#FF5000]'}`} />
          <span className="text-white font-medium">Iron Condor</span>
          {isAtRisk && (
            <span className="flex items-center gap-1 text-xs text-[#FF5000] bg-[#FF5000]/10 px-2 py-0.5 rounded">
              <AlertTriangle className="w-3 h-3" />
              AT RISK
            </span>
          )}
        </div>
        <div className="text-right">
          <div className={`text-lg font-bold ${isPositive ? 'text-[#00C805]' : 'text-[#FF5000]'}`}>
            {formatCurrency(position.unrealized_pnl)}
          </div>
          <div className={`text-sm ${isPositive ? 'text-[#00C805]' : 'text-[#FF5000]'}`}>
            {formatPct(position.pnl_pct)}
          </div>
        </div>
      </div>

      <div className="text-gray-400 text-sm mb-3 flex items-center gap-2 flex-wrap">
        <Clock className="w-3 h-3" />
        {formatExpiration(position.expiration)}
        <span className="mx-1">·</span>
        {position.contracts} contracts
        <span className="mx-1">·</span>
        Credit: ${position.credit_received?.toFixed(2)}
        {positionAge && (
          <>
            <span className="mx-1">·</span>
            <span className="flex items-center gap-1">
              <Timer className="w-3 h-3" />
              {positionAge}
            </span>
          </>
        )}
      </div>

      {/* Entry Context - VIX at entry */}
      {(position.vix_at_entry || position.underlying_at_entry) && (
        <div className="flex flex-wrap gap-2 mb-3">
          {position.vix_at_entry && (
            <span className="px-2 py-1 bg-yellow-900/30 text-yellow-400 text-xs rounded">
              VIX @ Entry: {position.vix_at_entry.toFixed(1)}
            </span>
          )}
          {position.underlying_at_entry && (
            <span className="px-2 py-1 bg-blue-900/30 text-blue-400 text-xs rounded">
              SPX @ Entry: ${position.underlying_at_entry.toLocaleString()}
            </span>
          )}
        </div>
      )}

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
            <div className="absolute -top-1 -left-1.5 w-3 h-3 rounded-full bg-white" />
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
            ${Math.abs(position.put_distance || 0).toFixed(2)} away
          </span>
          <span className={`${(position.call_distance || 0) > 0 ? 'text-[#00C805]' : 'text-[#FF5000]'}`}>
            ${Math.abs(position.call_distance || 0).toFixed(2)} away
          </span>
        </div>
      </div>

      {/* P&L Details */}
      <div className="border-t border-gray-800 pt-3">
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Credit Received:</span>
          <span className="text-white">${(position.credit_received || 0 * 100 * (position.contracts || 1)).toFixed(2)}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Current Value:</span>
          <span className="text-white">${position.current_value?.toFixed(2) || '--'}</span>
        </div>
      </div>
    </div>
  )
}

export default function OpenPositionsLive({ botName, positions, underlyingPrice, isLoading, onPositionClick }: OpenPositionsLiveProps) {
  if (isLoading) {
    return (
      <div className="bg-[#0a0a0a] rounded-lg p-6">
        <div className="animate-pulse">
          <div className="h-6 bg-gray-800 rounded w-48 mb-4" />
          <div className="h-32 bg-gray-800 rounded" />
        </div>
      </div>
    )
  }

  if (!positions || positions.length === 0) {
    return (
      <div className="bg-[#0a0a0a] rounded-lg p-6">
        <h3 className="text-lg font-semibold text-white mb-4">Open Positions</h3>
        <div className="text-center text-gray-500 py-8">
          <p>No open positions</p>
          <p className="text-sm text-gray-600 mt-1">Positions will appear here when trades are executed</p>
        </div>
      </div>
    )
  }

  // Calculate totals
  const totalUnrealized = positions.reduce((sum, p) => sum + (p.unrealized_pnl || 0), 0)
  const isPositiveTotal = totalUnrealized >= 0

  return (
    <div className="bg-[#0a0a0a] rounded-lg p-6">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold text-white">
          Open Positions ({positions.length})
        </h3>
        <div className={`font-semibold ${isPositiveTotal ? 'text-[#00C805]' : 'text-[#FF5000]'}`}>
          Unrealized: {formatCurrency(totalUnrealized)}
        </div>
      </div>

      <div className="space-y-3">
        {positions.map((position) => (
          botName === 'SOLOMON' ? (
            <SolomonPositionCard
              key={position.position_id}
              position={position}
              underlyingPrice={underlyingPrice}
              onClick={() => onPositionClick?.(position)}
            />
          ) : (
            // FORTRESS and PEGASUS both trade Iron Condors
            <AresPositionCard
              key={position.position_id}
              position={position}
              underlyingPrice={underlyingPrice}
              onClick={() => onPositionClick?.(position)}
            />
          )
        ))}
      </div>
    </div>
  )
}
