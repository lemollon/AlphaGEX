'use client'

/**
 * Capital Configuration Panel
 *
 * Allows users to:
 * 1. View current capital source and value
 * 2. Set/update starting capital
 * 3. Reset bot data (for blown accounts or fresh starts)
 *
 * Created: January 2025
 * Purpose: Provide UI for unified metrics capital configuration
 */

import { useState } from 'react'
import {
  DollarSign,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  RotateCcw,
  Database,
  Wallet,
  Settings,
  Trash2,
} from 'lucide-react'
import { useUnifiedBotSummary, useUnifiedBotCapital } from '@/lib/hooks/useMarketData'

interface CapitalConfigPanelProps {
  botName: 'ARES' | 'ATHENA' | 'ICARUS' | 'TITAN' | 'PEGASUS'
  onReset?: () => Promise<void>
  brandColor?: string  // e.g., 'amber', 'cyan', 'orange', 'violet', 'blue'
}

const BRAND_COLORS: Record<string, { bg: string; border: string; text: string; hover: string }> = {
  amber: { bg: 'bg-amber-500/10', border: 'border-amber-500/30', text: 'text-amber-400', hover: 'hover:bg-amber-500/20' },
  cyan: { bg: 'bg-cyan-500/10', border: 'border-cyan-500/30', text: 'text-cyan-400', hover: 'hover:bg-cyan-500/20' },
  orange: { bg: 'bg-orange-500/10', border: 'border-orange-500/30', text: 'text-orange-400', hover: 'hover:bg-orange-500/20' },
  violet: { bg: 'bg-violet-500/10', border: 'border-violet-500/30', text: 'text-violet-400', hover: 'hover:bg-violet-500/20' },
  blue: { bg: 'bg-blue-500/10', border: 'border-blue-500/30', text: 'text-blue-400', hover: 'hover:bg-blue-500/20' },
}

const BOT_BRAND_COLORS: Record<string, string> = {
  ARES: 'amber',
  ATHENA: 'cyan',
  ICARUS: 'orange',
  TITAN: 'violet',
  PEGASUS: 'blue',
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

export default function CapitalConfigPanel({
  botName,
  onReset,
  brandColor,
}: CapitalConfigPanelProps) {
  const [newCapital, setNewCapital] = useState('')
  const [isUpdating, setIsUpdating] = useState(false)
  const [isResetting, setIsResetting] = useState(false)
  const [showResetConfirm, setShowResetConfirm] = useState(false)
  const [updateMessage, setUpdateMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const { data: summaryData, mutate: refreshSummary } = useUnifiedBotSummary(botName)
  const { data: capitalData, mutate: refreshCapital } = useUnifiedBotCapital(botName)

  const summary = summaryData?.data
  const capitalConfig = capitalData?.data

  const color = brandColor || BOT_BRAND_COLORS[botName] || 'blue'
  const colors = BRAND_COLORS[color]

  const handleUpdateCapital = async () => {
    const capitalValue = parseFloat(newCapital.replace(/[^0-9.]/g, ''))

    if (isNaN(capitalValue) || capitalValue <= 0) {
      setUpdateMessage({ type: 'error', text: 'Please enter a valid capital amount' })
      return
    }

    setIsUpdating(true)
    setUpdateMessage(null)

    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || ''
      const response = await fetch(`${baseUrl}/api/metrics/${botName}/capital`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bot: botName, capital: capitalValue }),
      })

      const data = await response.json()

      if (data.success) {
        setUpdateMessage({ type: 'success', text: `Capital updated to ${formatCurrency(capitalValue)}` })
        setNewCapital('')
        // Refresh both summary and capital data
        await Promise.all([refreshSummary(), refreshCapital()])
      } else {
        setUpdateMessage({ type: 'error', text: data.detail || 'Failed to update capital' })
      }
    } catch (error) {
      setUpdateMessage({ type: 'error', text: 'Network error - please try again' })
    } finally {
      setIsUpdating(false)
    }
  }

  const handleReset = async () => {
    if (!onReset) return

    setIsResetting(true)
    try {
      await onReset()
      setShowResetConfirm(false)
      // Refresh data after reset
      await Promise.all([refreshSummary(), refreshCapital()])
    } catch (error) {
      // Error handling should be done in the onReset callback
    } finally {
      setIsResetting(false)
    }
  }

  const sourceIcon = {
    database: <Database className="w-4 h-4 text-green-400" />,
    tradier: <Wallet className="w-4 h-4 text-blue-400" />,
    default: <AlertTriangle className="w-4 h-4 text-yellow-400" />,
  }

  const sourceLabel = {
    database: 'Database Config',
    tradier: 'Tradier Balance',
    default: 'Default (Not Configured)',
  }

  return (
    <div className="space-y-6">
      {/* Current Capital Status */}
      <div className={`rounded-lg border ${colors.border} ${colors.bg} p-4`}>
        <div className="flex items-center gap-2 mb-4">
          <Settings className={`w-5 h-5 ${colors.text}`} />
          <h3 className={`font-semibold ${colors.text}`}>Capital Configuration</h3>
        </div>

        <div className="grid grid-cols-2 gap-4">
          {/* Starting Capital */}
          <div className="bg-gray-800/50 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1">
              <DollarSign className="w-4 h-4 text-gray-400" />
              <span className="text-gray-400 text-sm">Starting Capital</span>
            </div>
            <div className="text-xl font-bold text-white">
              {formatCurrency(capitalConfig?.starting_capital || summary?.starting_capital || 0)}
            </div>
          </div>

          {/* Current Equity */}
          <div className="bg-gray-800/50 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1">
              <DollarSign className="w-4 h-4 text-gray-400" />
              <span className="text-gray-400 text-sm">Current Equity</span>
            </div>
            <div className={`text-xl font-bold ${(summary?.current_equity || 0) >= (summary?.starting_capital || 0) ? 'text-green-400' : 'text-red-400'}`}>
              {formatCurrency(summary?.current_equity || 0)}
            </div>
          </div>

          {/* Capital Source */}
          <div className="bg-gray-800/50 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1">
              {sourceIcon[capitalConfig?.capital_source as keyof typeof sourceIcon] || sourceIcon.default}
              <span className="text-gray-400 text-sm">Capital Source</span>
            </div>
            <div className="text-white font-medium">
              {sourceLabel[capitalConfig?.capital_source as keyof typeof sourceLabel] || 'Unknown'}
            </div>
          </div>

          {/* Tradier Status */}
          <div className="bg-gray-800/50 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1">
              <Wallet className="w-4 h-4 text-gray-400" />
              <span className="text-gray-400 text-sm">Tradier</span>
            </div>
            <div className={`font-medium ${capitalConfig?.tradier_connected ? 'text-green-400' : 'text-gray-500'}`}>
              {capitalConfig?.tradier_connected ? 'Connected' : 'Not Connected'}
              {capitalConfig?.tradier_balance && (
                <span className="text-gray-400 text-sm ml-2">
                  ({formatCurrency(capitalConfig.tradier_balance)})
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Update Capital Form */}
      <div className="bg-gray-800/30 rounded-lg border border-gray-700 p-4">
        <h4 className="text-white font-medium mb-3 flex items-center gap-2">
          <DollarSign className="w-4 h-4 text-gray-400" />
          Set Starting Capital
        </h4>
        <p className="text-gray-400 text-sm mb-4">
          Configure your actual starting capital for accurate P&L and return calculations.
          This value will be used for both historical and intraday equity charts.
        </p>

        <div className="flex gap-3">
          <div className="flex-1 relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">$</span>
            <input
              type="text"
              value={newCapital}
              onChange={(e) => setNewCapital(e.target.value)}
              placeholder="100,000"
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-8 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-gray-500"
            />
          </div>
          <button
            onClick={handleUpdateCapital}
            disabled={isUpdating || !newCapital}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${colors.bg} ${colors.text} ${colors.border} border ${colors.hover} disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2`}
          >
            {isUpdating ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <CheckCircle className="w-4 h-4" />
                Save
              </>
            )}
          </button>
        </div>

        {updateMessage && (
          <div className={`mt-3 p-2 rounded text-sm flex items-center gap-2 ${
            updateMessage.type === 'success'
              ? 'bg-green-500/10 text-green-400 border border-green-500/30'
              : 'bg-red-500/10 text-red-400 border border-red-500/30'
          }`}>
            {updateMessage.type === 'success' ? (
              <CheckCircle className="w-4 h-4" />
            ) : (
              <AlertTriangle className="w-4 h-4" />
            )}
            {updateMessage.text}
          </div>
        )}
      </div>

      {/* Danger Zone - Reset */}
      {onReset && (
        <div className="bg-red-900/10 rounded-lg border border-red-500/30 p-4">
          <h4 className="text-red-400 font-semibold mb-2 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" />
            Danger Zone
          </h4>
          <p className="text-gray-400 text-sm mb-4">
            Reset all {botName} data including positions, trades, and scan history.
            Use this when starting fresh or after an account blow-up.
          </p>

          {!showResetConfirm ? (
            <button
              onClick={() => setShowResetConfirm(true)}
              className="flex items-center gap-2 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 border border-red-500/30 rounded-lg transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              Reset {botName} Data
            </button>
          ) : (
            <div className="p-4 bg-red-900/20 border border-red-500/50 rounded-lg">
              <div className="flex items-start gap-3 mb-4">
                <AlertTriangle className="w-5 h-5 text-red-400 mt-0.5" />
                <div>
                  <p className="text-red-400 font-medium">Are you absolutely sure?</p>
                  <p className="text-gray-400 text-sm mt-1">
                    This will permanently delete all {botName} positions, trades, equity snapshots, and scan history.
                    <strong className="text-red-400"> This action cannot be undone.</strong>
                  </p>
                </div>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={handleReset}
                  disabled={isResetting}
                  className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors disabled:opacity-50"
                >
                  {isResetting ? (
                    <>
                      <RotateCcw className="w-4 h-4 animate-spin" />
                      Resetting...
                    </>
                  ) : (
                    <>
                      <Trash2 className="w-4 h-4" />
                      Yes, Reset All Data
                    </>
                  )}
                </button>
                <button
                  onClick={() => setShowResetConfirm(false)}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Info Note */}
      <div className="text-xs text-gray-500 flex items-start gap-2">
        <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
        <span>
          Capital configuration is stored in the database and persists across deploys.
          Changes take effect immediately for all metrics calculations.
        </span>
      </div>
    </div>
  )
}
