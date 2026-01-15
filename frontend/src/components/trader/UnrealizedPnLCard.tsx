'use client'

import React from 'react'
import { TrendingUp, TrendingDown, DollarSign, Activity, RefreshCw, AlertCircle } from 'lucide-react'
import { BOT_BRANDS, BotName } from './index'

interface PositionPnL {
  position_id: string
  unrealized_pnl: number | null
  credit_received?: number
  max_profit?: number
  profit_progress_pct?: number | null
  put_short_strike?: number
  call_short_strike?: number
  distance_to_put?: number
  distance_to_call?: number
  risk_status?: string
}

interface LivePnLData {
  total_unrealized_pnl: number | null
  total_realized_pnl: number
  net_pnl: number
  positions: PositionPnL[]
  position_count: number
  underlying_price?: number
  source?: string
  note?: string
}

interface UnrealizedPnLCardProps {
  botName: BotName
  data: LivePnLData | null
  isLoading?: boolean
  isValidating?: boolean
  error?: any
  onRefresh?: () => void
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

function formatCurrencyDecimal(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

export default function UnrealizedPnLCard({
  botName,
  data,
  isLoading = false,
  isValidating = false,
  error,
  onRefresh
}: UnrealizedPnLCardProps) {
  const brand = BOT_BRANDS[botName]

  // No open positions - hide the card entirely
  if (!isLoading && data && data.position_count === 0) {
    return null
  }

  // Only show loading skeleton on initial load (no data yet)
  if (isLoading && !data) {
    return (
      <div className={`bg-[#0a0a0a] border rounded-lg p-4 ${brand.primaryBorder}`}>
        <div className="animate-pulse">
          <div className={`h-4 w-24 rounded ${brand.lightBg}`} />
          <div className="h-8 bg-gray-800 rounded mt-2 w-32" />
        </div>
      </div>
    )
  }

  // Error state
  if (error) {
    return (
      <div className="bg-[#0a0a0a] border border-red-500/30 rounded-lg p-4">
        <div className="flex items-center gap-2 text-red-400">
          <AlertCircle className="w-4 h-4" />
          <span className="text-sm">Failed to load live P&L</span>
        </div>
      </div>
    )
  }

  if (!data) return null

  const hasUnrealized = data.total_unrealized_pnl !== null
  const unrealizedPnL = data.total_unrealized_pnl || 0
  const realizedPnL = data.total_realized_pnl || 0
  const netPnL = data.net_pnl || 0
  const isPositive = netPnL >= 0
  const unrealizedIsPositive = unrealizedPnL >= 0

  return (
    <div className={`bg-[#0a0a0a] border rounded-lg overflow-hidden ${brand.primaryBorder}`}>
      {/* Header */}
      <div className={`px-4 py-3 border-b border-gray-800 flex items-center justify-between ${brand.lightBg}`}>
        <div className="flex items-center gap-2">
          <DollarSign className={`w-4 h-4 ${brand.primaryText}`} />
          <span className={`font-semibold text-sm ${brand.primaryText}`}>Live P&L</span>
          {data.position_count > 0 && (
            <span className="text-xs text-gray-400 bg-gray-800/50 px-2 py-0.5 rounded">
              {data.position_count} open position{data.position_count > 1 ? 's' : ''}
            </span>
          )}
          {/* Subtle refresh indicator during background revalidation */}
          {isValidating && !isLoading && (
            <RefreshCw className="w-3 h-3 text-gray-500 animate-spin" />
          )}
        </div>
        {onRefresh && (
          <button
            onClick={onRefresh}
            className="text-gray-400 hover:text-white transition-colors p-1 rounded hover:bg-gray-800"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading || isValidating ? 'animate-spin' : ''}`} />
          </button>
        )}
      </div>

      {/* Main P&L Display */}
      <div className="p-4">
        <div className="grid grid-cols-3 gap-4">
          {/* Unrealized P&L */}
          <div className="text-center">
            <div className="text-xs text-gray-500 mb-1">Unrealized</div>
            {hasUnrealized ? (
              <div className={`text-xl font-bold flex items-center justify-center gap-1 ${unrealizedIsPositive ? 'text-green-400' : 'text-red-400'}`}>
                {unrealizedIsPositive ? (
                  <TrendingUp className="w-4 h-4" />
                ) : (
                  <TrendingDown className="w-4 h-4" />
                )}
                {unrealizedIsPositive ? '+' : ''}{formatCurrency(unrealizedPnL)}
              </div>
            ) : (
              <div className="text-lg text-gray-500">--</div>
            )}
          </div>

          {/* Today's Realized P&L */}
          <div className="text-center border-x border-gray-800">
            <div className="text-xs text-gray-500 mb-1">Today Realized</div>
            <div className={`text-xl font-bold ${realizedPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {realizedPnL >= 0 ? '+' : ''}{formatCurrency(realizedPnL)}
            </div>
          </div>

          {/* Net P&L */}
          <div className="text-center">
            <div className="text-xs text-gray-500 mb-1">Net P&L</div>
            <div className={`text-xl font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
              {isPositive ? '+' : ''}{formatCurrency(netPnL)}
            </div>
          </div>
        </div>

        {/* Current Price */}
        {data.underlying_price && (
          <div className="mt-3 pt-3 border-t border-gray-800 flex items-center justify-center gap-2 text-sm text-gray-400">
            <Activity className="w-3 h-3" />
            <span>
              {botName === 'TITAN' || botName === 'PEGASUS' ? 'SPX' : 'SPY'}: <span className="text-white font-medium">${data.underlying_price.toFixed(2)}</span>
            </span>
          </div>
        )}

        {/* Position Details - Collapsed summary */}
        {data.positions && data.positions.length > 0 && hasUnrealized && (
          <div className="mt-3 pt-3 border-t border-gray-800">
            <div className="space-y-2">
              {data.positions.slice(0, 3).map((pos) => (
                <div key={pos.position_id} className="flex items-center justify-between text-xs">
                  <span className="text-gray-400 truncate max-w-[120px]">
                    {pos.put_short_strike && pos.call_short_strike
                      ? `${pos.put_short_strike}/${pos.call_short_strike}`
                      : pos.position_id.substring(0, 8)}
                  </span>
                  <div className="flex items-center gap-2">
                    {pos.profit_progress_pct !== null && pos.profit_progress_pct !== undefined && (
                      <span className={`${pos.profit_progress_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {pos.profit_progress_pct.toFixed(0)}%
                      </span>
                    )}
                    <span className={`font-medium ${(pos.unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {pos.unrealized_pnl !== null
                        ? `${(pos.unrealized_pnl >= 0 ? '+' : '')}${formatCurrencyDecimal(pos.unrealized_pnl)}`
                        : '--'}
                    </span>
                  </div>
                </div>
              ))}
              {data.positions.length > 3 && (
                <div className="text-xs text-gray-500 text-center">
                  +{data.positions.length - 3} more position{data.positions.length - 3 > 1 ? 's' : ''}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Source Note */}
        {data.source === 'database' && data.note && (
          <div className="mt-3 pt-3 border-t border-gray-800 text-xs text-gray-500 text-center">
            {data.note}
          </div>
        )}
      </div>
    </div>
  )
}
