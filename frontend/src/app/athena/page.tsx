'use client'

import React, { useState } from 'react'
import {
  Target, TrendingUp, TrendingDown, Activity, DollarSign,
  BarChart3, ChevronDown, ChevronUp, Server, Clock, Zap,
  Shield, Crosshair, Settings, Wallet, History, LayoutDashboard, Download
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import ScanActivityFeed from '@/components/ScanActivityFeed'
import { useToast } from '@/components/ui/Toast'
import { apiClient } from '@/lib/api'
import { RotateCcw, AlertTriangle } from 'lucide-react'
import {
  useATHENAStatus,
  useATHENAPositions,
  useATHENAPerformance,
  useATHENAConfig,
  useATHENALivePnL,
  useScanActivityAthena,
  useUnifiedBotSummary,
} from '@/lib/hooks/useMarketData'
import {
  BotPageHeader,
  BotCard,
  EmptyState,
  LoadingState,
  StatCard,
  BOT_BRANDS,
  BotStatusBanner,
  UnrealizedPnLCard,
  HedgeSignalCard,
  CapitalConfigPanel,
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

interface ATHENAStatus {
  mode: string
  ticker: string
  capital: number
  starting_capital?: number
  current_equity?: number
  unrealized_pnl?: number | null
  total_pnl: number
  trade_count: number
  win_rate: number
  open_positions: number
  closed_positions: number
  traded_today: boolean
  daily_trades: number
  daily_pnl: number
  in_trading_window: boolean
  current_time: string
  is_active: boolean
  scan_interval_minutes?: number
  heartbeat?: Heartbeat
  oracle_available?: boolean
  gex_ml_available?: boolean
  config?: {
    risk_per_trade: number
    spread_width: number
    ticker: string
    max_daily_trades: number
  }
}

interface SpreadPosition {
  position_id: string
  ticker: string
  spread_type: string
  long_strike: number
  short_strike: number
  expiration: string
  is_0dte: boolean
  entry_price: number
  contracts: number
  max_profit: number
  max_loss: number
  spot_at_entry: number
  vix_at_entry?: number
  gex_regime: string
  // Oracle audit trail
  oracle_confidence: number
  oracle_win_probability?: number
  oracle_advice?: string
  oracle_reasoning?: string
  oracle_top_factors?: string
  // GEX context
  flip_point?: number
  net_gex?: number
  put_wall?: number
  call_wall?: number
  status: string
  exit_price?: number
  exit_reason?: string
  realized_pnl?: number
  created_at: string
  exit_time?: string
}

// Helper to parse Oracle top factors
function parseOracleTopFactors(factorsJson: string | undefined): Array<{factor: string, impact: number}> {
  if (!factorsJson) return []
  try {
    const parsed = JSON.parse(factorsJson)
    if (Array.isArray(parsed)) return parsed
    return []
  } catch {
    return []
  }
}

// ==============================================================================
// TABS
// ==============================================================================

const ATHENA_TABS = [
  { id: 'portfolio' as const, label: 'Portfolio', icon: Wallet },
  { id: 'overview' as const, label: 'Overview', icon: LayoutDashboard },
  { id: 'activity' as const, label: 'Activity', icon: Activity },
  { id: 'history' as const, label: 'History', icon: History },
  { id: 'config' as const, label: 'Config', icon: Settings },
]
type AthenaTabId = typeof ATHENA_TABS[number]['id']

// ==============================================================================
// HELPERS
// ==============================================================================

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

function exportTradesToCSV(positions: SpreadPosition[], filename: string) {
  const headers = ['Position ID', 'Ticker', 'Type', 'Long Strike', 'Short Strike', 'Entry', 'Exit', 'P&L', 'Exit Reason', 'Exit Time']
  const rows = positions.map(p => [
    p.position_id,
    p.ticker,
    p.spread_type,
    p.long_strike,
    p.short_strike,
    p.entry_price,
    p.exit_price || '',
    p.realized_pnl || '',
    p.exit_reason || '',
    p.exit_time || ''
  ])
  const csv = [headers, ...rows].map(row => row.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
}

// ==============================================================================
// POSITION CARD
// ==============================================================================

function PositionCard({ position, isOpen }: { position: SpreadPosition; isOpen: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const isBullish = position.spread_type?.includes('BULL')
  const pnl = isOpen ? 0 : (position.realized_pnl || 0)
  const pnlColor = pnl >= 0 ? 'text-green-400' : 'text-red-400'
  const topFactors = parseOracleTopFactors(position.oracle_top_factors)

  return (
    <div className={`bg-gray-800/50 rounded-lg border ${isOpen ? 'border-cyan-500/30' : 'border-gray-700'} overflow-hidden`}>
      <div
        className="p-4 cursor-pointer hover:bg-gray-700/30 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className={`w-2 h-2 rounded-full ${isOpen ? 'bg-cyan-400 animate-pulse' : 'bg-gray-500'}`} />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-white font-bold">{position.ticker}</span>
                <span className={`text-xs px-2 py-0.5 rounded ${isBullish ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                  {isBullish ? 'BULL CALL' : 'BEAR PUT'}
                </span>
              </div>
              <span className="text-gray-400 text-sm">
                {position.long_strike}/{position.short_strike} • Exp: {position.expiration}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            {!isOpen && (
              <span className={`font-bold ${pnlColor}`}>
                {pnl >= 0 ? '+' : ''}{formatCurrency(pnl)}
              </span>
            )}
            {isOpen && (
              <span className="text-cyan-400 text-sm">
                {position.contracts} contract{position.contracts !== 1 ? 's' : ''}
              </span>
            )}
            {expanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
          </div>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-gray-700 p-4 space-y-4">
          {/* Oracle Decision - WHY this trade */}
          <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-2">
              <Zap className="w-4 h-4 text-purple-400" />
              <span className="text-purple-400 font-medium text-sm">Oracle Decision</span>
            </div>
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div>
                <span className="text-gray-500 block">Confidence</span>
                <span className={`font-bold ${(position.oracle_confidence || 0) >= 70 ? 'text-green-400' : 'text-yellow-400'}`}>
                  {position.oracle_confidence?.toFixed(0) || 0}%
                </span>
              </div>
              <div>
                <span className="text-gray-500 block">Win Probability</span>
                <span className={`font-bold ${(position.oracle_win_probability || 0) >= 0.50 ? 'text-green-400' : 'text-red-400'}`}>
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
              <Shield className="w-4 h-4 text-red-400" />
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
                  {position.net_gex ? ((position.net_gex) / 1e9).toFixed(2) + 'B' : 'N/A'}
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
                <span className={`font-bold ${(position.vix_at_entry || 0) > 22 ? 'text-red-400' : 'text-green-400'}`}>
                  {position.vix_at_entry?.toFixed(1) || 'N/A'}
                </span>
              </div>
            </div>
          </div>

          {/* Position Details */}
          <div className="bg-gray-800/50 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-2">
              <Target className="w-4 h-4 text-cyan-400" />
              <span className="text-gray-400 font-medium text-sm">Position Details</span>
            </div>
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div>
                <span className="text-gray-500 block">Entry Price</span>
                <span className="text-white font-bold">${position.entry_price?.toFixed(2)}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Max Profit</span>
                <span className="text-green-400 font-bold">${position.max_profit?.toFixed(0)}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Max Loss</span>
                <span className="text-red-400 font-bold">${position.max_loss?.toFixed(0)}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Spot at Entry</span>
                <span className="text-white font-bold">${position.spot_at_entry?.toFixed(2)}</span>
              </div>
              <div>
                <span className="text-gray-500 block">Contracts</span>
                <span className="text-white font-bold">{position.contracts}</span>
              </div>
              <div>
                <span className="text-gray-500 block">0DTE</span>
                <span className="text-white font-bold">{position.is_0dte ? 'Yes' : 'No'}</span>
              </div>
            </div>
          </div>

          {/* Close Details */}
          {!isOpen && position.exit_reason && (
            <div className="bg-gray-800/50 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-2">
                <History className="w-4 h-4 text-gray-400" />
                <span className="text-gray-400 font-medium text-sm">Close Details</span>
              </div>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <span className="text-gray-500 block">Exit Reason</span>
                  <span className="text-white">{position.exit_reason}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">Exit Time</span>
                  <span className="text-white">{position.exit_time || 'N/A'}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">Exit Price</span>
                  <span className="text-white">${position.exit_price?.toFixed(2) || 'N/A'}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">P&L</span>
                  <span className={`font-bold ${pnlColor}`}>
                    {pnl >= 0 ? '+' : ''}{formatCurrency(pnl)}
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

export default function AthenaPage() {
  const [activeTab, setActiveTab] = useState<AthenaTabId>('portfolio')
  const { addToast } = useToast()

  // Data hooks
  const { data: statusData, error: statusError, isLoading: statusLoading, mutate: refreshStatus } = useATHENAStatus()
  const { data: positionsData, error: positionsError, isLoading: positionsLoading } = useATHENAPositions()
  const { data: performanceData } = useATHENAPerformance(30)
  const { data: configData } = useATHENAConfig()
  const { data: livePnLData, isLoading: livePnLLoading, isValidating: livePnLValidating } = useATHENALivePnL()
  const { data: scanData, isLoading: scansLoading } = useScanActivityAthena(50)

  // UNIFIED METRICS: Single source of truth for all stats
  const { data: unifiedData, mutate: refreshUnified } = useUnifiedBotSummary('ATHENA')
  const unifiedMetrics = unifiedData?.data

  // Extract data
  const status: ATHENAStatus | null = statusData?.data || statusData || null
  const allPositions: SpreadPosition[] = positionsData?.data || positionsData || []
  const scans = scanData?.data?.scans || scanData?.scans || []
  const config = configData?.data || configData || status?.config || null
  const performance = performanceData?.data || performanceData || null

  // Separate open and closed positions
  const openPositions = allPositions.filter(p => p.status === 'open')
  const closedPositions = allPositions.filter(p => p.status === 'closed' || p.status === 'expired')

  // UNIFIED: Use server-calculated stats (never calculate in frontend)
  // Priority: unified metrics → status fallback → frontend calculation as last resort
  const totalPnL = unifiedMetrics?.total_realized_pnl ?? closedPositions.reduce((sum, p) => sum + (p.realized_pnl || 0), 0)
  const winRate = unifiedMetrics?.win_rate ?? (closedPositions.length > 0
    ? (closedPositions.filter(p => (p.realized_pnl || 0) > 0).length / closedPositions.length) * 100
    : 0)  // Already 0-100 percentage from server
  const tradeCount = unifiedMetrics?.total_trades ?? closedPositions.length
  const currentEquity = unifiedMetrics?.current_equity ?? (status?.current_equity || status?.capital || 100000)
  const capitalSource = unifiedMetrics?.capital_source ?? 'default'
  // Check if unrealized P&L is available (live pricing from worker)
  const hasLivePricing = status?.unrealized_pnl !== null && status?.unrealized_pnl !== undefined

  // Brand info
  const brand = BOT_BRANDS.ATHENA

  const handleRefresh = async () => {
    await Promise.all([refreshStatus(), refreshUnified()])
    addToast({ type: 'success', title: 'Refreshed', message: 'ATHENA data refreshed' })
  }

  const handleReset = async () => {
    const response = await apiClient.resetATHENAData(true)
    if (response.data?.success) {
      addToast({ type: 'success', title: 'Reset Complete', message: 'ATHENA data has been reset successfully' })
      refreshStatus()
    } else {
      addToast({ type: 'error', title: 'Reset Failed', message: response.data?.message || 'Failed to reset ATHENA data' })
      throw new Error(response.data?.message || 'Failed to reset')
    }
  }

  if (statusLoading) {
    return (
      <>
        <Navigation />
        <div className="flex items-center justify-center h-screen">
          <LoadingState message="Loading ATHENA..." />
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
            botName="ATHENA"
            isActive={status?.is_active || false}
            lastHeartbeat={status?.heartbeat?.last_scan_iso || undefined}
            onRefresh={handleRefresh}
            isRefreshing={statusLoading}
            scanIntervalMinutes={status?.scan_interval_minutes || 5}
          />

          {/* Capital Source Warning - Shows when using default capital */}
          {capitalSource === 'default' && (
            <div className="bg-yellow-900/30 border border-yellow-500/50 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-yellow-400 mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <h3 className="text-yellow-400 font-semibold">Using Default Capital</h3>
                  <p className="text-gray-300 text-sm mt-1">
                    ATHENA is using the default starting capital ($100,000). For accurate P&L and return calculations,
                    configure your actual starting capital via the API.
                  </p>
                  <p className="text-gray-500 text-xs mt-2">
                    POST /api/metrics/ATHENA/capital with your actual starting capital
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* ATHENA vs ICARUS Comparison Banner */}
          <div className="bg-cyan-900/20 border border-cyan-500/30 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <Shield className="w-5 h-5 text-cyan-400 mt-0.5 flex-shrink-0" />
              <div className="flex-1">
                <h3 className="text-cyan-400 font-semibold">ATHENA vs ICARUS: Conservative Parameters</h3>
                <p className="text-gray-400 text-sm mt-1">ATHENA uses more conservative settings for steady, consistent returns.</p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-3 text-sm">
                  <div>
                    <span className="text-gray-500">Risk/Trade:</span>
                    <span className="text-cyan-400 ml-2">2%</span>
                    <span className="text-gray-600 ml-1">(vs 3%)</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Spread Width:</span>
                    <span className="text-cyan-400 ml-2">$2</span>
                    <span className="text-gray-600 ml-1">(vs $3)</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Min Win Prob:</span>
                    <span className="text-cyan-400 ml-2">50%</span>
                    <span className="text-gray-600 ml-1">(vs 48%)</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Wall Filter:</span>
                    <span className="text-cyan-400 ml-2">1.0%</span>
                    <span className="text-gray-600 ml-1">(vs 2.0%)</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Quick Stats */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <StatCard
              label={hasLivePricing ? "Current Equity" : "Realized Equity"}
              value={formatCurrency(currentEquity)}
              icon={<DollarSign className="h-4 w-4" />}
              color="blue"
            />
            <StatCard
              label="Realized P&L"
              value={`${totalPnL >= 0 ? '+' : ''}${formatCurrency(totalPnL)}`}
              icon={<TrendingUp className="h-4 w-4" />}
              color={totalPnL >= 0 ? 'green' : 'red'}
            />
            <StatCard
              label="Win Rate"
              value={`${winRate.toFixed(1)}%`}
              icon={<Target className="h-4 w-4" />}
              color={winRate >= 60 ? 'green' : winRate >= 50 ? 'yellow' : 'red'}
            />
            <StatCard
              label="Trades"
              value={tradeCount.toString()}
              icon={<Activity className="h-4 w-4" />}
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
            {ATHENA_TABS.map((tab) => (
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
                {/* Bot Status Banner */}
                <BotStatusBanner
                  botName="ATHENA"
                  isActive={status?.is_active || false}
                  lastScan={status?.heartbeat?.last_scan_iso}
                  scanInterval={status?.scan_interval_minutes || 5}
                  openPositions={openPositions.length}
                  todayPnl={status?.daily_pnl || 0}
                  todayTrades={status?.daily_trades || 0}
                />

                {/* Live Unrealized P&L Card */}
                <UnrealizedPnLCard
                  botName="ATHENA"
                  data={livePnLData?.data || livePnLData}
                  isLoading={livePnLLoading}
                  isValidating={livePnLValidating}
                />

                {/* VIX Hedge Signal */}
                <HedgeSignalCard />

                {/* Performance Drift - Backtest vs Live */}
                <DriftStatusCard botName="ATHENA" />

                {/* Equity Curve */}
                <EquityCurveChart
                  title="ATHENA Equity Curve"
                  botFilter="ATHENA"
                  showIntradayOption={true}
                />

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
                    <span className="text-xl font-bold text-cyan-400">{config?.ticker || 'SPY'}</span>
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
                    <span className="text-gray-500 text-sm block">Traded Today</span>
                    <span className={`text-xl font-bold ${status?.traded_today || (status?.daily_trades || 0) > 0 ? 'text-green-400' : 'text-gray-400'}`}>
                      {status?.traded_today || (status?.daily_trades || 0) > 0 ? 'YES' : 'NO'}
                    </span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Oracle</span>
                    <span className={`text-xl font-bold ${status?.oracle_available ? 'text-green-400' : 'text-gray-400'}`}>
                      {status?.oracle_available ? 'ONLINE' : 'OFFLINE'}
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
                  botName="ATHENA"
                  isLoading={scansLoading}
                />
              </BotCard>
            )}

            {/* History Tab */}
            {activeTab === 'history' && (
              <BotCard title="Closed Positions" icon={<History className="h-5 w-5" />}>
                {closedPositions.length > 0 && (
                  <div className="flex justify-end mb-4">
                    <button
                      onClick={() => {
                        const today = new Date().toISOString().split('T')[0]
                        exportTradesToCSV(closedPositions, `athena-trades-${today}.csv`)
                        addToast({ type: 'success', title: 'Export Complete', message: `Exported ${closedPositions.length} trades to CSV` })
                      }}
                      className="flex items-center gap-2 px-4 py-2 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 border border-cyan-500/30 rounded-lg transition-colors"
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
              <>
              <BotCard title="Configuration" icon={<Settings className="h-5 w-5" />}>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Spread Width</span>
                    <span className="text-xl font-bold text-white">${config?.spread_width || 2}</span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Risk Per Trade</span>
                    <span className="text-xl font-bold text-white">{config?.risk_per_trade || 2}%</span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Max Daily Trades</span>
                    <span className="text-xl font-bold text-white">{config?.max_daily_trades || 5}</span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Ticker</span>
                    <span className="text-xl font-bold text-cyan-400">{config?.ticker || 'SPY'}</span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">Oracle</span>
                    <span className={`text-xl font-bold ${status?.oracle_available ? 'text-green-400' : 'text-gray-400'}`}>
                      {status?.oracle_available ? 'ENABLED' : 'DISABLED'}
                    </span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4">
                    <span className="text-gray-500 text-sm block">GEX ML</span>
                    <span className={`text-xl font-bold ${status?.gex_ml_available ? 'text-green-400' : 'text-gray-400'}`}>
                      {status?.gex_ml_available ? 'ENABLED' : 'DISABLED'}
                    </span>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-4 col-span-2">
                    <span className="text-gray-500 text-sm block">Trading Window</span>
                    <span className="text-xl font-bold text-white">08:35 - 14:30 CT</span>
                  </div>
                </div>
              </BotCard>

              {/* Capital Configuration & Reset */}
              <CapitalConfigPanel
                botName="ATHENA"
                onReset={handleReset}
                brandColor="cyan"
              />
              </>
            )}
          </div>
        </div>
      </main>
    </>
  )
}
