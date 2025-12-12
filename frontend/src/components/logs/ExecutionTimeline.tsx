'use client'

import React from 'react'
import { Clock, Send, CheckCircle, XCircle, TrendingUp, TrendingDown, AlertCircle } from 'lucide-react'

interface ExecutionTimelineProps {
  orderSubmittedAt?: string | null
  orderFilledAt?: string | null
  brokerOrderId?: string
  expectedFillPrice?: number
  actualFillPrice?: number
  slippagePct?: number
  brokerStatus?: string
  executionNotes?: string
  exitTimestamp?: string | null
  exitPrice?: number
  exitSlippagePct?: number
  exitTriggeredBy?: string
  actualPnl?: number
  className?: string
}

export default function ExecutionTimeline({
  orderSubmittedAt,
  orderFilledAt,
  brokerOrderId,
  expectedFillPrice,
  actualFillPrice,
  slippagePct,
  brokerStatus,
  executionNotes,
  exitTimestamp,
  exitPrice,
  exitSlippagePct,
  exitTriggeredBy,
  actualPnl,
  className = ''
}: ExecutionTimelineProps) {
  const formatTime = (timestamp: string | null | undefined) => {
    if (!timestamp) return null
    try {
      const date = new Date(timestamp)
      return date.toLocaleString()
    } catch {
      return timestamp
    }
  }

  const getSlippageColor = (slippage: number | undefined) => {
    if (!slippage) return 'text-gray-400'
    if (Math.abs(slippage) < 0.1) return 'text-green-400'
    if (Math.abs(slippage) < 0.5) return 'text-yellow-400'
    return 'text-red-400'
  }

  const getStatusColor = (status: string | undefined) => {
    if (!status) return 'bg-gray-700 text-gray-300'
    const s = status.toLowerCase()
    if (s === 'filled' || s === 'complete') return 'bg-green-800/50 text-green-300'
    if (s === 'pending' || s === 'open') return 'bg-yellow-800/50 text-yellow-300'
    if (s === 'rejected' || s === 'cancelled' || s === 'error') return 'bg-red-800/50 text-red-300'
    return 'bg-gray-700 text-gray-300'
  }

  const hasEntryData = orderSubmittedAt || orderFilledAt || brokerOrderId
  const hasExitData = exitTimestamp || exitPrice || exitTriggeredBy

  if (!hasEntryData && !hasExitData) {
    return (
      <div className={`bg-gray-800/50 rounded-lg p-4 border border-gray-700 ${className}`}>
        <div className="flex items-center gap-2 text-gray-500">
          <Clock className="w-5 h-5" />
          <span>No execution data recorded for this decision</span>
        </div>
      </div>
    )
  }

  return (
    <div className={`bg-gray-800 rounded-lg border border-gray-700 p-4 ${className}`}>
      <div className="flex items-center gap-2 mb-4">
        <Clock className="w-5 h-5 text-blue-400" />
        <h3 className="font-medium text-blue-300">Execution Timeline</h3>
        {brokerStatus && (
          <span className={`text-xs px-2 py-0.5 rounded ${getStatusColor(brokerStatus)}`}>
            {brokerStatus}
          </span>
        )}
      </div>

      <div className="relative">
        {/* Timeline line */}
        <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-gray-700" />

        {/* Timeline events */}
        <div className="space-y-4 ml-10">
          {/* Order Submitted */}
          {orderSubmittedAt && (
            <div className="relative">
              <div className="absolute -left-8 w-4 h-4 rounded-full bg-blue-500 border-2 border-gray-800" />
              <div className="bg-gray-900/50 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <Send className="w-4 h-4 text-blue-400" />
                  <span className="font-medium text-blue-300">Order Submitted</span>
                </div>
                <div className="text-sm text-gray-400">{formatTime(orderSubmittedAt)}</div>
                {expectedFillPrice && expectedFillPrice > 0 && (
                  <div className="text-sm text-gray-400 mt-1">
                    Expected price: ${expectedFillPrice.toFixed(2)}
                  </div>
                )}
                {brokerOrderId && (
                  <div className="text-xs text-gray-500 mt-1">
                    Order ID: {brokerOrderId}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Order Filled */}
          {orderFilledAt && (
            <div className="relative">
              <div className="absolute -left-8 w-4 h-4 rounded-full bg-green-500 border-2 border-gray-800" />
              <div className="bg-gray-900/50 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <CheckCircle className="w-4 h-4 text-green-400" />
                  <span className="font-medium text-green-300">Order Filled</span>
                </div>
                <div className="text-sm text-gray-400">{formatTime(orderFilledAt)}</div>
                {actualFillPrice && actualFillPrice > 0 && (
                  <div className="flex items-center gap-4 mt-1">
                    <span className="text-sm text-gray-400">
                      Fill price: ${actualFillPrice.toFixed(2)}
                    </span>
                    {slippagePct !== undefined && slippagePct !== null && (
                      <span className={`text-sm ${getSlippageColor(slippagePct)}`}>
                        Slippage: {slippagePct >= 0 ? '+' : ''}{slippagePct.toFixed(2)}%
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Position Open (if no fill yet but submitted) */}
          {orderSubmittedAt && !orderFilledAt && (
            <div className="relative">
              <div className="absolute -left-8 w-4 h-4 rounded-full bg-yellow-500 border-2 border-gray-800 animate-pulse" />
              <div className="bg-yellow-900/20 rounded-lg p-3 border border-yellow-700/50">
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-yellow-400" />
                  <span className="font-medium text-yellow-300">Pending Fill</span>
                </div>
                <div className="text-sm text-yellow-400/70 mt-1">
                  Order submitted, waiting for fill...
                </div>
              </div>
            </div>
          )}

          {/* Exit */}
          {exitTimestamp && (
            <div className="relative">
              <div className={`absolute -left-8 w-4 h-4 rounded-full border-2 border-gray-800 ${
                actualPnl && actualPnl > 0 ? 'bg-green-500' : actualPnl && actualPnl < 0 ? 'bg-red-500' : 'bg-gray-500'
              }`} />
              <div className={`rounded-lg p-3 ${
                actualPnl && actualPnl > 0 ? 'bg-green-900/20 border border-green-700/50' :
                actualPnl && actualPnl < 0 ? 'bg-red-900/20 border border-red-700/50' :
                'bg-gray-900/50'
              }`}>
                <div className="flex items-center gap-2 mb-1">
                  {actualPnl && actualPnl > 0 ? (
                    <TrendingUp className="w-4 h-4 text-green-400" />
                  ) : actualPnl && actualPnl < 0 ? (
                    <TrendingDown className="w-4 h-4 text-red-400" />
                  ) : (
                    <XCircle className="w-4 h-4 text-gray-400" />
                  )}
                  <span className={`font-medium ${
                    actualPnl && actualPnl > 0 ? 'text-green-300' :
                    actualPnl && actualPnl < 0 ? 'text-red-300' : 'text-gray-300'
                  }`}>
                    Position Closed
                  </span>
                  {exitTriggeredBy && (
                    <span className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded">
                      {exitTriggeredBy.replace(/_/g, ' ')}
                    </span>
                  )}
                </div>
                <div className="text-sm text-gray-400">{formatTime(exitTimestamp)}</div>
                <div className="flex items-center gap-4 mt-1">
                  {exitPrice && exitPrice > 0 && (
                    <span className="text-sm text-gray-400">
                      Exit price: ${exitPrice.toFixed(2)}
                    </span>
                  )}
                  {exitSlippagePct !== undefined && exitSlippagePct !== null && (
                    <span className={`text-sm ${getSlippageColor(exitSlippagePct)}`}>
                      Exit slippage: {exitSlippagePct >= 0 ? '+' : ''}{exitSlippagePct.toFixed(2)}%
                    </span>
                  )}
                </div>
                {actualPnl !== undefined && actualPnl !== null && (
                  <div className={`text-lg font-bold mt-2 ${
                    actualPnl > 0 ? 'text-green-400' : actualPnl < 0 ? 'text-red-400' : 'text-gray-400'
                  }`}>
                    P&L: {actualPnl >= 0 ? '+' : ''}${actualPnl.toFixed(2)}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Execution Notes */}
      {executionNotes && (
        <div className="mt-4 pt-4 border-t border-gray-700">
          <div className="text-sm text-gray-400">
            <span className="font-medium">Notes: </span>
            {executionNotes}
          </div>
        </div>
      )}
    </div>
  )
}
