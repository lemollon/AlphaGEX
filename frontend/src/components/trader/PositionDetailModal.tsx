'use client'

import { Fragment } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import { XMarkIcon } from '@heroicons/react/24/outline'

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

    // Pricing
    entry_price: number  // Entry debit/credit per contract
    current_price?: number  // Current spread value
    exit_price?: number

    // P&L
    unrealized_pnl?: number
    realized_pnl?: number
    pnl_pct?: number

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

    // Trade metrics
    max_profit?: number
    max_loss?: number
    breakeven?: number
    rr_ratio?: number

    // Timestamps
    created_at?: string
    exit_time?: string
    status: string
    exit_reason?: string
  }
  underlyingPrice?: number
}

export default function PositionDetailModal({
  isOpen,
  onClose,
  position,
  underlyingPrice
}: PositionDetailModalProps) {
  if (!position) return null

  const isOpen_ = position.status === 'open'
  const isBullish = position.spread_type?.includes('BULL')
  const ticker = position.ticker || 'SPY'

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
  const spreadName = `${ticker} $${position.long_strike}/$${position.short_strike} ${isBullish ? 'Bull' : 'Bear'} Spread`

  // Calculate breakeven
  const spreadWidth = Math.abs(position.short_strike - position.long_strike)
  const breakeven = isBullish
    ? position.long_strike + Math.abs(position.entry_price)
    : position.short_strike - Math.abs(position.entry_price)

  const currentUnderlying = underlyingPrice || position.current_underlying || position.spot_at_entry || 0
  const distanceToBreakeven = currentUnderlying - breakeven
  const distancePct = breakeven > 0 ? (distanceToBreakeven / breakeven) * 100 : 0

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/80" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-2xl transform overflow-hidden rounded-2xl bg-gray-900 border border-gray-700 shadow-xl transition-all">
                {/* Header */}
                <div className="flex items-center justify-between p-6 border-b border-gray-700">
                  <div>
                    <Dialog.Title className="text-xl font-bold text-white">
                      {spreadName}
                    </Dialog.Title>
                    <p className="text-sm text-gray-400 mt-1">
                      ${position.current_price?.toFixed(2) || position.entry_price?.toFixed(2)} per contract
                    </p>
                  </div>
                  <button
                    onClick={onClose}
                    className="p-2 rounded-lg hover:bg-gray-800 transition-colors"
                  >
                    <XMarkIcon className="w-6 h-6 text-gray-400" />
                  </button>
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
                  <button
                    onClick={onClose}
                    className="px-6 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-white font-medium transition-colors"
                  >
                    Close
                  </button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  )
}
