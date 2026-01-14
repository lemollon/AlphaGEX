'use client'

import React, { useState, useMemo } from 'react'
import {
  Shield, TrendingUp, TrendingDown, Activity, DollarSign, Target,
  RefreshCw, BarChart3, ChevronDown, ChevronUp, Server, Clock, Zap,
  Brain, Crosshair, Settings, Wallet, History, LayoutDashboard, Eye, Download
} from 'lucide-react'
// Recharts imports removed - using shared EquityCurveChart component
import Navigation from '@/components/Navigation'
import ScanActivityFeed from '@/components/ScanActivityFeed'
import { apiClient } from '@/lib/api'
import { useToast } from '@/components/ui/Toast'
import { RotateCcw, AlertTriangle } from 'lucide-react'
import {
  useTITANStatus,
  useTITANPositions,
  useTITANConfig,
  useTITANLivePnL,
  useScanActivityTitan,
} from '@/lib/hooks/useMarketData'
import {
  BotPageHeader,
  BotCard,
  DataFreshnessIndicator,
  EmptyState,
  LoadingState,
  StatCard,
  StatusBadge,
  PnLDisplay,
  BOT_BRANDS,
  BotName,
  BotStatusBanner,
} from '@/components/trader'
import EquityCurveChart from '@/components/charts/EquityCurveChart'
import DriftStatusCard from '@/components/DriftStatusCard'

// ==============================================================================
// INTERFACES
// ==============================================================================

interface Heartbeat {
  last_scan: string | null
  last_scan_iso: string | null
  status: string
  scan_count_today: number
  details: Record<string, any>
}

interface TITANStatus {
  mode: string
  ticker: string
  capital: number
  capital_source?: string
  total_pnl: number
  trade_count: number
  win_rate: number
  open_positions: number
  closed_positions: number
  traded_today: boolean
  trades_today: number
  in_trading_window: boolean
  trading_window_status?: string
  trading_window_end?: string
  current_time: string
  is_active: boolean
  high_water_mark: number
  tradier_connected?: boolean
  tradier_for_prices?: boolean
  source?: string
  message?: string
  scan_interval_minutes?: number
  heartbeat?: Heartbeat
  config?: {
    risk_per_trade: number
    spread_width: number
    sd_multiplier: number
    ticker: string
    trade_cooldown_minutes: number
  }
}

interface IronCondorPosition {
  position_id: string
  ticker: string
  expiration: string
  dte: number
  is_0dte: boolean
  put_long_strike: number
  put_short_strike: number
  call_short_strike: number
  call_long_strike: number
  put_spread: string
  call_spread: string
  put_credit: number
  call_credit: number
  total_credit: number
  contracts: number
  spread_width: number
  max_loss: number
  max_profit?: number
  premium_collected: number
  underlying_at_entry: number
  vix_at_entry: number
  status: string
  // GEX Context (AUDIT TRAIL)
  gex_regime: string
  call_wall: number
  put_wall: number
  flip_point: number
  net_gex: number
  // Oracle Context (AUDIT TRAIL - WHY this trade)
  oracle_confidence: number
  oracle_win_probability: number
  oracle_advice: string
  oracle_reasoning: string
  oracle_top_factors: string
  // Timing (Central Time)
  open_time: string
  open_time_iso: string
  close_time?: string
  close_time_iso?: string
  close_price?: number
  close_reason?: string
  realized_pnl?: number
  return_pct?: number
}

// ==============================================================================
// TABS CONFIGURATION
// ==============================================================================

const TITAN_TABS = [
  { id: 'portfolio' as const, label: 'Portfolio', icon: Wallet, description: 'Live P&L and positions' },
  { id: 'overview' as const, label: 'Overview', icon: LayoutDashboard, description: 'Bot status and metrics' },
  { id: 'activity' as const, label: 'Activity', icon: Activity, description: 'Scans and decisions' },
  { id: 'history' as const, label: 'History', icon: History, description: 'Closed positions' },
  { id: 'config' as const, label: 'Config', icon: Settings, description: 'Settings and controls' },
]
type TitanTabId = typeof TITAN_TABS[number]['id']

// ==============================================================================
// HELPER FUNCTIONS
// ==============================================================================

function formatTime(timestamp: string): string {
  // Already formatted as "YYYY-MM-DD HH:MM:SS CT" from backend
  if (timestamp.includes(' CT')) {
    const parts = timestamp.split(' ')
    return `${parts[1]} CT`
  }
  const date = new Date(timestamp)
  return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'America/Chicago' }) + ' CT'
}

function formatDateTime(timestamp: string): string {
  if (timestamp.includes(' CT')) {
    return timestamp
  }
  const date = new Date(timestamp)
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'America/Chicago' }) +
    ' ' + date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'America/Chicago' }) + ' CT'
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

function parseOracleTopFactors(topFactors: string): Array<{ factor: string; impact: number }> {
  if (!topFactors) return []
  try {
    const parsed = JSON.parse(topFactors)
    if (Array.isArray(parsed)) {
      return parsed.map(f => ({
        factor: f.factor || f[0] || 'Unknown',
        impact: f.impact || f[1] || 0
      }))
    }
    return []
  } catch {
    return []
  }
}

// Export trades to CSV
function exportTradesToCSV(positions: IronCondorPosition[], filename: string) {
  const headers = [
    'Position ID',
    'Expiration',
    'Put Spread',
    'Call Spread',
    'Contracts',
    'Total Credit',
    'Max Profit',
    'Max Loss',
    'Realized P&L',
    'Return %',
    'Close Reason',
    'Open Time',
    'Close Time',
    'SPX at Entry',
    'VIX at Entry',
    'GEX Regime',
    'Flip Point',
    'Net GEX',
    'Oracle Confidence',
    'Oracle Win Prob',
    'Oracle Advice',
    'Oracle Reasoning',
  ]

  const rows = positions.map(p => [
    p.position_id,
    p.expiration,
    p.put_spread,
    p.call_spread,
    p.contracts,
    p.total_credit?.toFixed(2),
    p.premium_collected?.toFixed(2),
    p.max_loss?.toFixed(2),
    p.realized_pnl?.toFixed(2) || '0',
    p.return_pct?.toFixed(1) || '0',
    p.close_reason || '',
    p.open_time || '',
    p.close_time || '',
    p.underlying_at_entry?.toFixed(2),
    p.vix_at_entry?.toFixed(2),
    p.gex_regime,
    p.flip_point?.toFixed(0),
    p.net_gex?.toFixed(0),
    ((p.oracle_confidence || 0) * 100).toFixed(0) + '%',
    ((p.oracle_win_probability || 0) * 100).toFixed(0) + '%',
    p.oracle_advice,
    `"${(p.oracle_reasoning || '').replace(/"/g, '""')}"`,
  ])

  const csvContent = [
    headers.join(','),
    ...rows.map(row => row.join(','))
  ].join('\n')

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename
  link.click()
  URL.revokeObjectURL(link.href)
}

// ==============================================================================
// POSITION CARD COMPONENT - Shows full audit trail
// ==============================================================================

function PositionCard({ position, isOpen }: { position: IronCondorPosition; isOpen: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const topFactors = parseOracleTopFactors(position.oracle_top_factors)

  const pnl = isOpen ? 0 : (position.realized_pnl || 0)
  const isPositive = pnl >= 0

  return (
    <div className={`bg-[#0a0a0a] rounded-lg border ${isOpen ? 'border-violet-500/30' : isPositive ? 'border-green-500/30' : 'border-red-500/30'} overflow-hidden`}>
      {/* Header - Always visible */}
      <div className="p-4 cursor-pointer hover:bg-gray-800/30 transition-colors" onClick={() => setExpanded(!expanded)}>
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-white font-bold">SPX Iron Condor</span>
              {isOpen && (
                <span className="text-xs px-2 py-0.5 rounded bg-violet-500/20 text-violet-400 border border-violet-500/30 flex items-center gap-1">
                  <div className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
                  OPEN
                </span>
              )}
              {position.oracle_advice && (
                <span className={`text-xs px-2 py-0.5 rounded ${
                  position.oracle_advice === 'ENTER' ? 'bg-green-500/20 text-green-400 border border-green-500/30' :
                  position.oracle_advice === 'EXIT' ? 'bg-red-500/20 text-red-400 border border-red-500/30' :
                  'bg-gray-500/20 text-gray-400 border border-gray-500/30'
                }`}>
                  Oracle: {position.oracle_advice}
                </span>
              )}
            </div>

            {/* Iron Condor structure */}
            <div className="mt-2 flex items-center gap-4 text-sm">
              <span className="text-orange-400">{position.put_spread}</span>
              <span className="text-gray-500">|</span>
              <span className="text-cyan-400">{position.call_spread}</span>
              <span className="text-gray-500">x{position.contracts}</span>
            </div>

            {/* Timing */}
            <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {position.open_time || 'Unknown'}
              </span>
              <span>Exp: {position.expiration}</span>
              {position.dte !== undefined && (
                <span className={position.is_0dte ? 'text-red-400' : 'text-gray-400'}>
                  {position.is_0dte ? '0DTE' : `${position.dte} DTE`}
                </span>
              )}
            </div>
          </div>

          {/* Right side - P&L and expand */}
          <div className="flex items-center gap-3">
            <div className="text-right">
              {isOpen ? (
                <div>
                  <div className="text-sm text-gray-400">Premium</div>
                  <div className="text-green-400 font-bold">${position.premium_collected.toFixed(0)}</div>
                </div>
              ) : (
                <div className={`text-xl font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                  {isPositive ? '+' : ''}${pnl.toFixed(2)}
                </div>
              )}
            </div>
            <div className="text-gray-500">
              {expanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
            </div>
          </div>
        </div>
      </div>

      {/* Expanded Content - Full Audit Trail */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-800 space-y-4">
          {/* Oracle Context - WHY this trade */}
          <div className="mt-4 bg-purple-500/10 border border-purple-500/30 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-2">
              <Zap className="w-4 h-4 text-purple-400" />
              <span className="text-purple-400 font-medium text-sm">Oracle Decision</span>
            </div>
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div>
                <span className="text-gray-500 block">Confidence</span>
                <span className={`font-bold ${(position.oracle_confidence || 0) >= 0.7 ? 'text-green-400' : 'text-yellow-400'}`}>
                  {((position.oracle_confidence || 0) * 100).toFixed(0)}%
                </span>
              </div>
              <div>
                <span className="text-gray-500 block">Win Probability</span>
                <span className={`font-bold ${(position.oracle_win_probability || 0) >= 0.40 ? 'text-green-400' : 'text-red-400'}`}>
                  {((position.oracle_win_probability || 0) * 100).toFixed(0)}%
                </span>
              </div>
              <div>
                <span className="text-gray-500 block">Advice</span>
                <span className={`font-bold ${position.oracle_advice === 'ENTER' ? 'text-green-400' : 'text-yellow-400'}`}>
                  {position.oracle_advice || 'N/A'}
                </span>
              </div>
            </div>
            {position.oracle_reasoning && (
              <div className="mt-3 pt-3 border-t border-purple-500/20">
                <span className="text-gray-500 text-xs">Reasoning:</span>
                <p className="text-gray-300 text-sm mt-1">{position.oracle_reasoning}</p>
              </div>
            )}
            {topFactors.length > 0 && (
              <div className="mt-3 pt-3 border-t border-purple-500/20">
                <span className="text-gray-500 text-xs">Top Factors:</span>
                <div className="mt-1 space-y-1">
                  {topFactors.slice(0, 3).map((f, i) => (
                    <div key={i} className="flex justify-between text-xs">
                      <span className="text-gray-400">{f.factor}</span>
                      <span className="text-purple-300">{f.impact.toFixed(3)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* GEX Context - Market conditions */}
          <div className="bg-gray-800/50 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-2">
              <Shield className="w-4 h-4 text-violet-400" />
              <span className="text-gray-400 font-medium text-sm">Market Context at Entry</span>
            </div>
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div>
                <span className="text-gray-500 block">GEX Regime</span>
                <span className={`font-bold ${
                  position.gex_regime === 'POSITIVE' ? 'text-green-400' :
                  position.gex_regime === 'NEGATIVE' ? 'text-red-400' : 'text-yellow-400'
                }`}>
                  {position.gex_regime || 'NEUTRAL'}
                </span>
              </div>
              <div>
                <span className="text-gray-500 block">Flip Point</span>
                <span className="text-white font-bold">${position.flip_point?.toFixed(0) || 'N/A'}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Net GEX</span>
                <span className={`font-bold ${(position.net_gex || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {((position.net_gex || 0) / 1e9).toFixed(2)}B
                </span>
              </div>
              <div>
                <span className="text-gray-500 block">Put Wall</span>
                <span className="text-orange-400 font-bold">${position.put_wall?.toFixed(0) || 'N/A'}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Call Wall</span>
                <span className="text-cyan-400 font-bold">${position.call_wall?.toFixed(0) || 'N/A'}</span>
              </div>
              <div>
                <span className="text-gray-500 block">VIX</span>
                <span className={`font-bold ${(position.vix_at_entry || 0) > 40 ? 'text-red-400' : 'text-green-400'}`}>
                  {position.vix_at_entry?.toFixed(1) || 'N/A'}
                </span>
              </div>
            </div>
          </div>

          {/* Position Details */}
          <div className="bg-gray-800/50 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-2">
              <Target className="w-4 h-4 text-green-400" />
              <span className="text-gray-400 font-medium text-sm">Position Details</span>
            </div>
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div>
                <span className="text-gray-500 block">Total Credit</span>
                <span className="text-green-400 font-bold">${position.total_credit?.toFixed(2)}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Max Profit</span>
                <span className="text-green-400 font-bold">${position.premium_collected?.toFixed(0)}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Max Loss</span>
                <span className="text-red-400 font-bold">${position.max_loss?.toFixed(0)}</span>
              </div>
              <div>
                <span className="text-gray-500 block">SPX at Entry</span>
                <span className="text-white font-bold">${position.underlying_at_entry?.toFixed(0)}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Spread Width</span>
                <span className="text-white font-bold">${position.spread_width}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Contracts</span>
                <span className="text-white font-bold">{position.contracts}</span>
              </div>
            </div>
          </div>

          {/* Close details (for closed positions) */}
          {!isOpen && position.close_reason && (
            <div className="bg-gray-800/50 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-2">
                <History className="w-4 h-4 text-gray-400" />
                <span className="text-gray-400 font-medium text-sm">Close Details</span>
              </div>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <span className="text-gray-500 block">Close Reason</span>
                  <span className="text-white">{position.close_reason}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">Closed At</span>
                  <span className="text-white">{position.close_time || 'N/A'}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">Close Price</span>
                  <span className="text-white">${position.close_price?.toFixed(2) || 'N/A'}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">Return</span>
                  <span className={`font-bold ${(position.return_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {position.return_pct?.toFixed(1)}%
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ==============================================================================
// MAIN PAGE COMPONENT
// ==============================================================================

export default function TitanPage() {
  const [activeTab, setActiveTab] = useState<TitanTabId>('portfolio')
  const [showResetConfirm, setShowResetConfirm] = useState(false)
  const [isResetting, setIsResetting] = useState(false)
  const { addToast } = useToast()

  // Data hooks
  const { data: statusData, error: statusError, isLoading: statusLoading, mutate: refreshStatus } = useTITANStatus()
  const { data: positionsData, error: positionsError, isLoading: positionsLoading } = useTITANPositions()
  // Equity curve data is now fetched by the shared EquityCurveChart component
  const { data: configData } = useTITANConfig()
  const { data: livePnLData } = useTITANLivePnL()
  const { data: scanData, isLoading: scansLoading } = useScanActivityTitan(50)

  // Extract data
  const status: TITANStatus | null = statusData?.data || null
  const openPositions: IronCondorPosition[] = positionsData?.data?.open_positions || []
  const closedPositions: IronCondorPosition[] = positionsData?.data?.closed_positions || []
  const scans = scanData?.data?.scans || []
  const config = configData?.data || null

  // Calculate stats
  const totalPnL = status?.total_pnl || 0
  const winRate = status?.win_rate || 0
  const tradeCount = status?.trade_count || 0
  const capital = status?.capital || 200000

  // Brand info
  const brand = BOT_BRANDS.TITAN

  const handleRefresh = async () => {
    await refreshStatus()
    addToast({ type: 'success', title: 'Refreshed', message: 'TITAN data refreshed' })
  }

  const handleReset = async () => {
    setIsResetting(true)
    try {
      const response = await apiClient.resetTITANData(true)
      if (response.data?.success) {
        addToast({ type: 'success', title: 'Reset Complete', message: 'TITAN data has been reset successfully' })
        setShowResetConfirm(false)
        // Refresh all data
        refreshStatus()
      } else {
        addToast({ type: 'error', title: 'Reset Failed', message: response.data?.message || 'Failed to reset TITAN data' })
      }
    } catch (error) {
      addToast({ type: 'error', title: 'Reset Error', message: 'An error occurred while resetting data' })
    } finally {
      setIsResetting(false)
    }
  }

  if (statusLoading) {
    return (
      <>
        <Navigation />
        <div className="flex items-center justify-center h-screen">
          <LoadingState message="Loading TITAN..." />
        </div>
      </>
    )
  }

  return (
    <>
      <Navigation />
      <main className="min-h-screen bg-black text-white px-4 pb-4 md:px-6 md:pb-6 pt-28">
        <div className="max-w-7xl mx-auto space-y-6">

          {/* Header - Branded */}
          <BotPageHeader
            botName="TITAN"
            isActive={status?.is_active || false}
            lastHeartbeat={status?.heartbeat?.last_scan_iso || undefined}
            onRefresh={handleRefresh}
            isRefreshing={statusLoading}
            scanIntervalMinutes={status?.scan_interval_minutes || 5}
          />

          {/* Paper Trading Info Banner */}
          {status && status.source === 'paper' && (
            <div className="bg-violet-900/30 border border-violet-500/50 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <Wallet className="w-5 h-5 text-violet-400 mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <h3 className="text-violet-400 font-semibold">Paper Trading Mode - Aggressive Daily Trading</h3>
                  <p className="text-gray-300 text-sm mt-1">
                    {status.message || 'TITAN is paper trading with $200k simulated capital. Multiple trades per day with 30-min cooldown.'}
                  </p>
                  {!status.tradier_connected && (
                    <p className="text-gray-400 text-xs mt-2">
                      Tradier connection optional for live SPX prices. Paper trading works without it.
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Aggressive Parameters Banner */}
          <div className="bg-violet-900/20 border border-violet-500/30 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <Zap className="w-5 h-5 text-violet-400 mt-0.5 flex-shrink-0" />
              <div className="flex-1">
                <h3 className="text-violet-400 font-semibold">TITAN vs PEGASUS: Aggressive Parameters</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-3 text-sm">
                  <div>
                    <span className="text-gray-500">Risk/Trade:</span>
                    <span className="text-violet-400 ml-2">15%</span>
                    <span className="text-gray-600 ml-1">(vs 10%)</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Min Win Prob:</span>
                    <span className="text-violet-400 ml-2">40%</span>
                    <span className="text-gray-600 ml-1">(vs 50%)</span>
                  </div>
                  <div>
                    <span className="text-gray-500">VIX Skip:</span>
                    <span className="text-violet-400 ml-2">40</span>
                    <span className="text-gray-600 ml-1">(vs 32)</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Spread Width:</span>
                    <span className="text-violet-400 ml-2">$12</span>
                    <span className="text-gray-600 ml-1">(vs $10)</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Quick Stats */}
          <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
            <StatCard
              label="Capital"
              value={formatCurrency(capital)}
              icon={<DollarSign className="h-4 w-4" />}
              color="blue"
            />
            <StatCard
              label="Total P&L"
              value={`${totalPnL >= 0 ? '+' : ''}${formatCurrency(totalPnL)}`}
              icon={<TrendingUp className="h-4 w-4" />}
              color={totalPnL >= 0 ? 'green' : 'red'}
            />
            <StatCard
              label="Win Rate"
              value={`${winRate.toFixed(1)}%`}
              icon={<Target className="h-4 w-4" />}
              color={winRate >= 50 ? 'green' : winRate >= 40 ? 'yellow' : 'red'}
            />
            <StatCard
              label="Total Trades"
              value={tradeCount.toString()}
              icon={<Activity className="h-4 w-4" />}
              color="blue"
            />
            <StatCard
              label="Today's Trades"
              value={(status?.trades_today || 0).toString()}
              icon={<Zap className="h-4 w-4" />}
              color="blue"
            />
            <StatCard
              label="Open Positions"
              value={openPositions.length.toString()}
              icon={<Crosshair className="h-4 w-4" />}
              color="blue"
            />
          </div>

          {/* Tabs - Branded */}
          <div className="flex gap-2 border-b border-gray-800 pb-2">
            {TITAN_TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
                  activeTab === tab.id
                    ? `${brand.lightBg} ${brand.primaryText} border ${brand.primaryBorder}`
                    : 'text-gray-400 hover:text-white hover:bg-gray-800'
                }`}
              >
                <tab.icon className="w-4 h-4" />
                <span className="text-sm font-medium">{tab.label}</span>
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <div className="space-y-6">
            {/* Portfolio Tab */}
            {activeTab === 'portfolio' && (
              <>
                {/* Bot Status Banner - Shows active/paused/error status with countdown */}
                <BotStatusBanner
                  botName="TITAN"
                  isActive={status?.is_active || false}
                  lastScan={status?.heartbeat?.last_scan_iso}
                  scanInterval={status?.scan_interval_minutes || 5}
                  openPositions={openPositions.length}
                  todayPnl={closedPositions.filter(p => {
                    const closeTime = p.close_time_iso || p.close_time
                    if (!closeTime) return false
                    const today = new Date().toISOString().split('T')[0]
                    return closeTime.startsWith(today)
                  }).reduce((sum, p) => sum + (p.realized_pnl || 0), 0)}
                  todayTrades={status?.trades_today || closedPositions.filter(p => {
                    const closeTime = p.close_time_iso || p.close_time
                    if (!closeTime) return false
                    const today = new Date().toISOString().split('T')[0]
                    return closeTime.startsWith(today)
                  }).length}
                />

                {/* Performance Drift - Backtest vs Live */}
                <DriftStatusCard botName="TITAN" />

                {/* Open Positions */}
                <BotCard title="Open Positions" icon={<Crosshair className="h-5 w-5" />}>
                  {openPositions.length === 0 ? (
                    <EmptyState title="No open positions" description="Positions will appear here when trades are opened" icon={<Crosshair className="h-8 w-8" />} />
                  ) : (
                    <div className="space-y-4">
                      {openPositions.map((position) => (
                        <PositionCard key={position.position_id} position={position} isOpen={true} />
                      ))}
                    </div>
                  )}
                </BotCard>

                {/* Equity Curve - Using Shared Component */}
                <EquityCurveChart
                  title="TITAN Equity Curve"
                  botFilter="TITAN"
                  showIntradayOption={true}
                />
              </>
            )}

            {/* Overview Tab */}
            {activeTab === 'overview' && (
              <BotCard title="Bot Status" icon={<Server className="h-5 w-5" />}>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Mode</span>
                    <span className="text-xl font-bold text-white">{status?.mode?.toUpperCase() || 'PAPER'}</span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Ticker</span>
                    <span className="text-xl font-bold text-violet-400">{status?.ticker || 'SPX'}</span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Trading Window</span>
                    <span className={`text-xl font-bold ${status?.in_trading_window ? 'text-green-400' : 'text-gray-400'}`}>
                      {status?.in_trading_window ? 'ACTIVE' : 'CLOSED'}
                    </span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Last Scan</span>
                    <span className="text-lg font-bold text-white">
                      {status?.heartbeat?.last_scan || 'Never'}
                    </span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Current Time</span>
                    <span className="text-lg font-bold text-white">
                      {status?.current_time || 'Unknown'}
                    </span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Scans Today</span>
                    <span className="text-xl font-bold text-white">
                      {status?.heartbeat?.scan_count_today || 0}
                    </span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Trades Today</span>
                    <span className={`text-xl font-bold ${(status?.trades_today || 0) > 0 ? 'text-green-400' : 'text-gray-400'}`}>
                      {status?.trades_today || 0}
                    </span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">High Water Mark</span>
                    <span className="text-xl font-bold text-white">
                      {formatCurrency(status?.high_water_mark || 200000)}
                    </span>
                  </div>
                </div>
              </BotCard>
            )}

            {/* Activity Tab */}
            {activeTab === 'activity' && (
              <BotCard title="Scan Activity" icon={<Activity className="h-5 w-5" />}>
                <ScanActivityFeed
                  scans={scans}
                  botName="TITAN"
                  isLoading={scansLoading}
                />
              </BotCard>
            )}

            {/* History Tab */}
            {activeTab === 'history' && (
              <BotCard title="Closed Positions" icon={<History className="h-5 w-5" />}>
                {/* Export Button */}
                {closedPositions.length > 0 && (
                  <div className="flex justify-end mb-4">
                    <button
                      onClick={() => {
                        const today = new Date().toISOString().split('T')[0]
                        exportTradesToCSV(closedPositions, `titan-trades-${today}.csv`)
                        addToast({ type: 'success', title: 'Export Complete', message: `Exported ${closedPositions.length} trades to CSV` })
                      }}
                      className="flex items-center gap-2 px-4 py-2 bg-violet-500/20 hover:bg-violet-500/30 text-violet-400 border border-violet-500/30 rounded-lg transition-colors"
                    >
                      <Download className="w-4 h-4" />
                      <span className="text-sm">Export CSV</span>
                    </button>
                  </div>
                )}
                {closedPositions.length === 0 ? (
                  <EmptyState title="No closed positions yet" description="Closed trades will appear here" icon={<History className="h-8 w-8" />} />
                ) : (
                  <div className="space-y-4">
                    {closedPositions.map((position) => (
                      <PositionCard key={position.position_id} position={position} isOpen={false} />
                    ))}
                  </div>
                )}
              </BotCard>
            )}

            {/* Config Tab */}
            {activeTab === 'config' && (
              <BotCard title="Configuration" icon={<Settings className="h-5 w-5" />}>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Spread Width</span>
                    <span className="text-xl font-bold text-white">${config?.spread_width || 12}</span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Risk Per Trade</span>
                    <span className="text-xl font-bold text-white">{config?.risk_per_trade_pct || 15}%</span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">SD Multiplier</span>
                    <span className="text-xl font-bold text-white">{config?.sd_multiplier || 0.8}x</span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Trade Cooldown</span>
                    <span className="text-xl font-bold text-white">{config?.trade_cooldown_minutes || 30} min</span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Profit Target</span>
                    <span className="text-xl font-bold text-green-400">{config?.profit_target_pct || 30}%</span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Min Win Probability</span>
                    <span className="text-xl font-bold text-white">{((config?.min_win_probability || 0.40) * 100).toFixed(0)}%</span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4 col-span-2">
                    <span className="text-gray-500 text-sm block">Trading Window</span>
                    <span className="text-xl font-bold text-white">{config?.entry_window || '08:45 - 14:30 CT'}</span>
                  </div>
                </div>

                {config?.description && (
                  <div className="mt-4 p-4 bg-violet-500/10 border border-violet-500/30 rounded-lg">
                    <p className="text-gray-300 text-sm">{config.description}</p>
                  </div>
                )}

                {/* Reset Section */}
                <div className="mt-6 pt-6 border-t border-gray-800">
                  <h4 className="text-lg font-semibold text-white mb-4">Danger Zone</h4>
                  {!showResetConfirm ? (
                    <button
                      onClick={() => setShowResetConfirm(true)}
                      className="flex items-center gap-2 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 border border-red-500/30 rounded-lg transition-colors"
                    >
                      <RotateCcw className="w-4 h-4" />
                      <span>Reset TITAN Data</span>
                    </button>
                  ) : (
                    <div className="p-4 bg-red-900/20 border border-red-500/50 rounded-lg">
                      <div className="flex items-start gap-3 mb-4">
                        <AlertTriangle className="w-5 h-5 text-red-400 mt-0.5" />
                        <div>
                          <p className="text-red-400 font-medium">Are you sure you want to reset?</p>
                          <p className="text-gray-400 text-sm mt-1">
                            This will permanently delete all TITAN positions, trades, and scan history.
                            This action cannot be undone.
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
                              <span>Resetting...</span>
                            </>
                          ) : (
                            <>
                              <RotateCcw className="w-4 h-4" />
                              <span>Yes, Reset All Data</span>
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
              </BotCard>
            )}
          </div>
        </div>
      </main>
    </>
  )
}
