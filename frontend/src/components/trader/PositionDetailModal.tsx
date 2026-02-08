'use client'

import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'

interface PositionDetailModalProps {
  isOpen: boolean
  onClose: () => void
  position: {
    // Core position data
    position_id: string
    spread_type: string
    ticker?: string
    long_strike: number
    short_strike: number
    expiration: string
    contracts: number
    contracts_remaining?: number

    // Iron Condor specific
    put_long_strike?: number
    put_short_strike?: number
    call_short_strike?: number
    call_long_strike?: number
    credit_received?: number
    put_distance?: number
    call_distance?: number
    risk_status?: string

    // Pricing
    entry_price: number  // Entry debit/credit per contract
    current_price?: number  // Current spread value
    exit_price?: number

    // P&L
    unrealized_pnl?: number
    realized_pnl?: number
    pnl_pct?: number
    scaled_pnl?: number

    // Market context at entry
    spot_at_entry?: number
    current_underlying?: number
    vix_at_entry?: number
    gex_regime?: string

    // GEX levels at entry
    put_wall_at_entry?: number
    call_wall_at_entry?: number
    flip_point_at_entry?: number
    net_gex_at_entry?: number

    // Greeks at entry
    entry_delta?: number
    entry_gamma?: number
    entry_theta?: number
    entry_vega?: number

    // Oracle/ML data
    oracle_confidence?: number
    oracle_reasoning?: string
    ml_direction?: string
    ml_confidence?: number
    ml_win_probability?: number

    // Signal source & Override tracking
    signal_source?: string
    override_occurred?: boolean
    override_details?: {
      overridden_signal?: string
      overridden_advice?: string
      override_reason?: string
      override_by?: string
      ml_confidence?: number
      oracle_confidence?: number
    }

    // Trade metrics
    max_profit?: number
    max_loss?: number
    breakeven?: number
    rr_ratio?: number

    // Timestamps
    created_at?: string
    entry_time?: string
    exit_time?: string
    status: string
    exit_reason?: string
  }
  underlyingPrice?: number
  botType?: 'SOLOMON' | 'FORTRESS' | 'PEGASUS'
}

export default function PositionDetailModal({
  isOpen,
  onClose,
  position,
  underlyingPrice,
  botType = 'SOLOMON'
}: PositionDetailModalProps) {
  if (!position) return null

  const isOpen_ = position.status === 'open'
  const isBullish = position.spread_type?.includes('BULL')
  const isIronCondor = position.spread_type?.includes('IRON_CONDOR') || botType === 'FORTRESS'
  const ticker = position.ticker || (isIronCondor ? 'SPX' : 'SPY')

  // Calculate position age
  const getPositionAge = () => {
    const entryTime = position.entry_time || position.created_at
    if (!entryTime) return ''
    const entry = new Date(entryTime)
    const now = new Date()
    const diffMs = now.getTime() - entry.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMins / 60)
    const diffDays = Math.floor(diffHours / 24)

    if (diffDays > 0) return `${diffDays}d ${diffHours % 24}h`
    if (diffHours > 0) return `${diffHours}h ${diffMins % 60}m`
    return `${diffMins}m`
  }
  const positionAge = getPositionAge()

  // Calculate values
  const contractMultiplier = 100
  const contracts = position.contracts_remaining || position.contracts || 0
  const entryValue = Math.abs(position.entry_price) * contracts * contractMultiplier
  const currentValue = (position.current_price || position.entry_price) * contracts * contractMultiplier
  const marketValue = position.unrealized_pnl
    ? entryValue + position.unrealized_pnl
    : currentValue

  const totalReturn = position.unrealized_pnl || position.realized_pnl || 0
  const returnPct = entryValue > 0 ? (totalReturn / entryValue) * 100 : 0

  // Format spread name
  const spreadName = isIronCondor
    ? `${ticker} Iron Condor ${position.put_short_strike}/${position.call_short_strike}`
    : `${ticker} $${position.long_strike}/$${position.short_strike} ${isBullish ? 'Bull' : 'Bear'} Spread`

  // Signal source styling
  const getSignalSourceStyle = () => {
    const source = position.signal_source || ''
    if (source.includes('Oracle') && position.override_occurred) {
      return { bg: 'bg-amber-500/20', border: 'border-amber-500/50', text: 'text-amber-400' }
    }
    if (source.includes('Oracle')) {
      return { bg: 'bg-purple-500/20', border: 'border-purple-500/50', text: 'text-purple-400' }
    }
    if (source.includes('ML')) {
      return { bg: 'bg-cyan-500/20', border: 'border-cyan-500/50', text: 'text-cyan-400' }
    }
    return { bg: 'bg-gray-500/20', border: 'border-gray-500/50', text: 'text-gray-400' }
  }
  const signalStyle = getSignalSourceStyle()

  // Calculate breakeven
  const spreadWidth = Math.abs(position.short_strike - position.long_strike)
  const breakeven = isBullish
    ? position.long_strike + Math.abs(position.entry_price)
    : position.short_strike - Math.abs(position.entry_price)

  const currentUnderlying = underlyingPrice || position.current_underlying || position.spot_at_entry || 0
  const distanceToBreakeven = currentUnderlying - breakeven
  const distancePct = breakeven > 0 ? (distanceToBreakeven / breakeven) * 100 : 0

  return (
    <Dialog.Root open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/80 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content className="fixed left-[50%] top-[50%] z-50 w-full max-w-2xl translate-x-[-50%] translate-y-[-50%] overflow-hidden rounded-2xl bg-gray-900 border border-gray-700 shadow-xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%] max-h-[90vh] overflow-y-auto">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-gray-700">
            <div>
              <div className="flex items-center gap-3">
                <Dialog.Title className="text-xl font-bold text-white">
                  {spreadName}
                </Dialog.Title>
                {position.signal_source && (
                  <span className={`px-2 py-0.5 rounded text-xs ${signalStyle.bg} ${signalStyle.text} border ${signalStyle.border}`}>
                    {position.signal_source}
                  </span>
                )}
                {position.override_occurred && (
                  <span className="px-2 py-0.5 rounded text-xs bg-amber-500/20 text-amber-400 border border-amber-500/50 animate-pulse">
                    OVERRIDE
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3 mt-1">
                <p className="text-sm text-gray-400">
                  ${position.current_price?.toFixed(2) || position.entry_price?.toFixed(2)} per contract
                </p>
                {positionAge && (
                  <span className="text-xs text-gray-500">• Held for {positionAge}</span>
                )}
                {position.risk_status === 'AT_RISK' && (
                  <span className="text-xs text-red-400 bg-red-500/20 px-2 py-0.5 rounded">AT RISK</span>
                )}
              </div>
            </div>
            <Dialog.Close asChild>
              <button
                className="p-2 rounded-lg hover:bg-gray-800 transition-colors"
                aria-label="Close"
              >
                <X className="w-6 h-6 text-gray-400" />
              </button>
            </Dialog.Close>
          </div>

          {/* Content */}
          <div className="p-6 space-y-6">
            {/* Your Position */}
            <div>
              <h3 className="text-lg font-semibold text-white mb-4">Your Position</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-gray-400">Contracts</p>
                  <p className="text-xl font-bold text-green-400">+{contracts}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-400">Current price</p>
                  <p className="text-xl font-bold text-white">
                    ${(position.current_price || position.entry_price)?.toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-400">Average cost</p>
                  <p className="text-xl font-bold text-white">
                    ${Math.abs(position.entry_price)?.toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-400">Market value</p>
                  <p className="text-xl font-bold text-white">
                    ${marketValue.toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-400">Date opened</p>
                  <p className="text-xl font-bold text-white">
                    {position.created_at ? new Date(position.created_at).toLocaleDateString() : 'N/A'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-400">Expiration date</p>
                  <p className="text-xl font-bold text-white">
                    {position.expiration ? new Date(position.expiration).toLocaleDateString() : 'N/A'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-400">Breakeven price</p>
                  <p className="text-xl font-bold text-white">${breakeven.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-400">Current {ticker} price</p>
                  <p className="text-xl font-bold text-white">${currentUnderlying.toFixed(2)}</p>
                </div>
              </div>

              {/* Returns */}
              <div className="mt-6 pt-4 border-t border-gray-700">
                <div className="flex justify-between items-center">
                  <span className="text-gray-400">Total return</span>
                  <span className={`text-xl font-bold ${totalReturn >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {totalReturn >= 0 ? '+' : ''}{totalReturn.toFixed(2)} ({returnPct >= 0 ? '+' : ''}{returnPct.toFixed(2)}%)
                  </span>
                </div>
              </div>
            </div>

            {/* Trade Context - What we have that Robinhood doesn't! */}
            <div className="bg-gray-800/50 rounded-xl p-4">
              <h3 className="text-lg font-semibold text-white mb-4">Trade Context</h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                {/* GEX Context */}
                <div>
                  <p className="text-gray-500">GEX Regime</p>
                  <p className={`font-semibold ${
                    position.gex_regime === 'POSITIVE' ? 'text-green-400' :
                    position.gex_regime === 'NEGATIVE' ? 'text-red-400' : 'text-yellow-400'
                  }`}>
                    {position.gex_regime || 'N/A'}
                  </p>
                </div>
                <div>
                  <p className="text-gray-500">VIX at Entry</p>
                  <p className="text-white font-semibold">{position.vix_at_entry?.toFixed(2) || 'N/A'}</p>
                </div>
                <div>
                  <p className="text-gray-500">Put Wall</p>
                  <p className="text-orange-400 font-semibold">${position.put_wall_at_entry?.toFixed(0) || 'N/A'}</p>
                </div>
                <div>
                  <p className="text-gray-500">Call Wall</p>
                  <p className="text-cyan-400 font-semibold">${position.call_wall_at_entry?.toFixed(0) || 'N/A'}</p>
                </div>
              </div>
            </div>

            {/* Oracle & ML Signals */}
            <div className="bg-gray-800/50 rounded-xl p-4">
              <h3 className="text-lg font-semibold text-white mb-4">AI Signals</h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-gray-500">Oracle Confidence</p>
                  <p className={`font-semibold ${
                    (position.oracle_confidence || 0) >= 70 ? 'text-green-400' :
                    (position.oracle_confidence || 0) >= 50 ? 'text-yellow-400' : 'text-red-400'
                  }`}>
                    {position.oracle_confidence?.toFixed(0)}%
                  </p>
                </div>
                <div>
                  <p className="text-gray-500">ML Win Probability</p>
                  <p className={`font-semibold ${
                    (position.ml_win_probability || 0) >= 60 ? 'text-green-400' :
                    (position.ml_win_probability || 0) >= 50 ? 'text-yellow-400' : 'text-red-400'
                  }`}>
                    {position.ml_win_probability?.toFixed(0) || 'N/A'}%
                  </p>
                </div>
                <div>
                  <p className="text-gray-500">ML Direction</p>
                  <p className={`font-semibold ${
                    position.ml_direction === 'BULLISH' ? 'text-green-400' :
                    position.ml_direction === 'BEARISH' ? 'text-red-400' : 'text-gray-400'
                  }`}>
                    {position.ml_direction || 'N/A'}
                  </p>
                </div>
                <div>
                  <p className="text-gray-500">R:R Ratio</p>
                  <p className="text-white font-semibold">{position.rr_ratio?.toFixed(2) || 'N/A'}</p>
                </div>
              </div>
              {position.oracle_reasoning && (
                <div className="mt-4 pt-4 border-t border-gray-700">
                  <p className="text-gray-500 text-sm">Oracle Reasoning</p>
                  <p className="text-gray-300 text-sm mt-1">{position.oracle_reasoning}</p>
                </div>
              )}
            </div>

            {/* Override Details - when Oracle overrode ML */}
            {position.override_occurred && position.override_details && (
              <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4">
                <h3 className="text-lg font-semibold text-amber-400 mb-4 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                  Override Details
                </h3>
                <div className="space-y-3 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Original Signal:</span>
                    <span className="text-red-400 font-semibold">
                      {position.override_details.overridden_signal} → {position.override_details.overridden_advice}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Override By:</span>
                    <span className="text-purple-400 font-semibold">{position.override_details.override_by}</span>
                  </div>
                  {position.override_details.ml_confidence !== undefined && (
                    <div className="flex justify-between">
                      <span className="text-gray-400">ML Confidence:</span>
                      <span className="text-cyan-400">{(position.override_details.ml_confidence * 100).toFixed(0)}%</span>
                    </div>
                  )}
                  {position.override_details.oracle_confidence !== undefined && (
                    <div className="flex justify-between">
                      <span className="text-gray-400">Oracle Confidence:</span>
                      <span className="text-purple-400">{(position.override_details.oracle_confidence * 100).toFixed(0)}%</span>
                    </div>
                  )}
                  {position.override_details.override_reason && (
                    <div className="mt-3 pt-3 border-t border-amber-500/30">
                      <p className="text-gray-400 mb-1">Override Reason:</p>
                      <p className="text-amber-300 text-xs">{position.override_details.override_reason}</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Greeks at Entry */}
            {(position.entry_delta || position.entry_theta) && (
              <div className="bg-gray-800/50 rounded-xl p-4">
                <h3 className="text-lg font-semibold text-white mb-4">Greeks at Entry</h3>
                <div className="grid grid-cols-4 gap-4 text-sm">
                  <div>
                    <p className="text-gray-500">Delta</p>
                    <p className="text-white font-semibold">{position.entry_delta?.toFixed(3) || 'N/A'}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">Gamma</p>
                    <p className="text-white font-semibold">{position.entry_gamma?.toFixed(4) || 'N/A'}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">Theta</p>
                    <p className="text-red-400 font-semibold">{position.entry_theta?.toFixed(2) || 'N/A'}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">Vega</p>
                    <p className="text-white font-semibold">{position.entry_vega?.toFixed(3) || 'N/A'}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Risk/Reward */}
            <div className="bg-gray-800/50 rounded-xl p-4">
              <h3 className="text-lg font-semibold text-white mb-4">Risk / Reward</h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-gray-500">Max Profit</p>
                  <p className="text-green-400 font-semibold">${position.max_profit?.toFixed(2) || 'N/A'}</p>
                </div>
                <div>
                  <p className="text-gray-500">Max Loss</p>
                  <p className="text-red-400 font-semibold">${position.max_loss?.toFixed(2) || 'N/A'}</p>
                </div>
                <div>
                  <p className="text-gray-500">Spread Width</p>
                  <p className="text-white font-semibold">${spreadWidth.toFixed(0)}</p>
                </div>
                <div>
                  <p className="text-gray-500">Distance to Breakeven</p>
                  <p className={`font-semibold ${distanceToBreakeven >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    ${Math.abs(distanceToBreakeven).toFixed(2)} ({distancePct >= 0 ? '+' : ''}{distancePct.toFixed(2)}%)
                  </p>
                </div>
              </div>
            </div>

            {/* Status for closed positions */}
            {!isOpen_ && (
              <div className="bg-gray-800/50 rounded-xl p-4">
                <h3 className="text-lg font-semibold text-white mb-4">Close Details</h3>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-gray-500">Status</p>
                    <p className={`font-semibold ${
                      position.status === 'closed' ? 'text-blue-400' : 'text-purple-400'
                    }`}>
                      {position.status?.toUpperCase()}
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-500">Exit Reason</p>
                    <p className="text-white font-semibold">{position.exit_reason || 'N/A'}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">Exit Price</p>
                    <p className="text-white font-semibold">${position.exit_price?.toFixed(2) || 'N/A'}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">Closed At</p>
                    <p className="text-white font-semibold">
                      {position.exit_time ? new Date(position.exit_time).toLocaleString() : 'N/A'}
                    </p>
                  </div>
                  <div className="col-span-2">
                    <p className="text-gray-500">Realized P&L</p>
                    <p className={`text-2xl font-bold ${
                      (position.realized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {(position.realized_pnl || 0) >= 0 ? '+' : ''}${position.realized_pnl?.toFixed(2) || '0.00'}
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="p-6 border-t border-gray-700 flex justify-end">
            <Dialog.Close asChild>
              <button
                className="px-6 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-white font-medium transition-colors"
              >
                Close
              </button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
