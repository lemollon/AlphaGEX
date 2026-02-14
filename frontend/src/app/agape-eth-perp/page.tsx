'use client'

import { useState } from 'react'
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Clock,
  Activity,
  Eye,
  CheckCircle,
  Zap,
  RefreshCw,
  Shield,
  Target,
  ArrowUpDown,
  Wallet,
  History,
  LayoutDashboard,
  Settings,
  BarChart3,
  Globe,
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import EquityCurveChart from '@/components/charts/EquityCurveChart'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import {
  BotPageHeader,
  BotCard,
  StatCard,
  LoadingState,
  EmptyState,
  BOT_BRANDS,
} from '@/components/trader'
import {
  useAGAPEEthPerpStatus,
  useAGAPEEthPerpPerformance,
  useAGAPEEthPerpPositions,
  useAGAPEEthPerpScanActivity,
  useAGAPEEthPerpClosedTrades,
  useAGAPEEthPerpSnapshot,
  useAGAPEEthPerpGexMapping,
} from '@/lib/hooks/useMarketData'

// ==============================================================================
// EQUITY CURVE TIMEFRAMES (matching VALOR/FORTRESS pattern)
// ==============================================================================
const EQUITY_TIMEFRAMES = [
  { id: 'intraday', label: 'Today', days: 0 },
  { id: '7d', label: '7D', days: 7 },
  { id: '14d', label: '14D', days: 14 },
  { id: '30d', label: '30D', days: 30 },
  { id: '90d', label: '90D', days: 90 },
]

// ==============================================================================
// TABS CONFIGURATION (matching FORTRESS/SAMSON pattern with icons)
// ==============================================================================
const AGAPE_ETH_PERP_TABS = [
  { id: 'portfolio' as const, label: 'Portfolio', icon: Wallet, description: 'Live P&L and positions' },
  { id: 'overview' as const, label: 'Overview', icon: LayoutDashboard, description: 'Bot status and metrics' },
  { id: 'snapshot' as const, label: 'Market', icon: Globe, description: 'Crypto microstructure' },
  { id: 'activity' as const, label: 'Activity', icon: Activity, description: 'Scans and decisions' },
  { id: 'history' as const, label: 'History', icon: History, description: 'Closed trades' },
  { id: 'config' as const, label: 'Config', icon: Settings, description: 'Settings and GEX mapping' },
]
type AgapeEthPerpTabId = typeof AGAPE_ETH_PERP_TABS[number]['id']

// ==============================================================================
// MAIN COMPONENT
// ==============================================================================

export default function AgapeEthPerpPage() {
  const [activeTab, setActiveTab] = useState<AgapeEthPerpTabId>('portfolio')
  const [equityTimeframe, setEquityTimeframe] = useState('intraday')
  const sidebarPadding = useSidebarPadding()

  // Brand from centralized system
  const brand = BOT_BRANDS.AGAPE_ETH_PERP

  // Data hooks (matching FORTRESS/SAMSON pattern)
  const { data: statusData, isLoading: statusLoading, mutate: refreshStatus } = useAGAPEEthPerpStatus()
  const { data: perfData } = useAGAPEEthPerpPerformance()
  const { data: positionsData, isLoading: posLoading } = useAGAPEEthPerpPositions()
  const { data: snapshotData, isLoading: snapLoading } = useAGAPEEthPerpSnapshot()
  const { data: scansData } = useAGAPEEthPerpScanActivity(30)
  const { data: closedData } = useAGAPEEthPerpClosedTrades(50)
  const { data: mappingData } = useAGAPEEthPerpGexMapping()

  const status = statusData?.data
  const perf = perfData?.data
  const paperAccount = status?.paper_account || null
  const startingCapital = paperAccount?.starting_capital ?? status?.starting_capital ?? 12500

  const handleRefresh = async () => {
    await refreshStatus()
  }

  if (statusLoading && !statusData) {
    return (
      <>
        <Navigation />
        <div className="flex items-center justify-center h-screen">
          <LoadingState message="Loading AGAPE-ETH-PERP..." />
        </div>
      </>
    )
  }

  return (
    <>
      <Navigation />
      <main className={`min-h-screen bg-black text-white px-4 pb-4 md:px-6 md:pb-6 pt-24 transition-all duration-300 ${sidebarPadding}`}>
        <div className="max-w-7xl mx-auto space-y-6">

          {/* Header - Branded (matches FORTRESS/SAMSON pattern) */}
          <BotPageHeader
            botName="AGAPE_ETH_PERP"
            isActive={status?.status === 'ACTIVE'}
            lastHeartbeat={status?.heartbeat?.last_scan_iso || status?.last_scan_iso || undefined}
            onRefresh={handleRefresh}
            isRefreshing={statusLoading}
            scanIntervalMinutes={5}
          />

          {/* 24/7 Perpetual Trading Banner */}
          <div className="rounded-lg p-3 border bg-green-900/20 border-green-500/30">
            <div className="flex items-center gap-3 text-sm">
              <div className="w-2.5 h-2.5 rounded-full bg-green-500 animate-pulse" />
              <span className="text-green-300">
                Perpetual: 24/7 Trading
              </span>
              <span className="text-gray-500 ml-auto text-xs">Always Open</span>
            </div>
          </div>

          {/* Aggressive Mode Banner - Uses brand colors */}
          <div className={`${brand.lightBg} border ${brand.lightBorder} rounded-lg p-4`}>
            <div className="flex items-start gap-3">
              <Zap className={`w-5 h-5 ${brand.primaryText} mt-0.5 flex-shrink-0`} />
              <div className="flex-1">
                <h3 className={`${brand.primaryText} font-semibold`}>Aggressive Mode - Perpetual Contract Trading</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-3 text-sm">
                  <div>
                    <span className="text-gray-500">SAR:</span>
                    <span className={`ml-2 ${status?.aggressive_features?.use_sar ? 'text-green-400' : 'text-gray-500'}`}>
                      {status?.aggressive_features?.use_sar ? 'Active' : 'Off'}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500">No-Loss Trail:</span>
                    <span className={`ml-2 ${status?.aggressive_features?.use_no_loss_trailing ? 'text-green-400' : 'text-gray-500'}`}>
                      {status?.aggressive_features?.use_no_loss_trailing ? 'Active' : 'Off'}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500">Cooldown:</span>
                    <span className={`${brand.primaryText} ml-2`}>None</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Max Positions:</span>
                    <span className={`${brand.primaryText} ml-2`}>Unlimited</span>
                  </div>
                </div>
              </div>
              {status?.mode && (
                <span className={`px-2 py-0.5 text-xs rounded font-mono ${
                  status.mode === 'live' ? 'bg-green-900/50 text-green-300' : 'bg-yellow-900/50 text-yellow-300'
                }`}>{status.mode.toUpperCase()}</span>
              )}
            </div>
          </div>

          {/* Loss Streak Warning Banner (matches VALOR pattern) */}
          {status?.aggressive_features?.consecutive_losses > 0 && !status?.aggressive_features?.loss_streak_paused && (
            <div className="bg-orange-900/30 border border-orange-500/50 rounded-lg p-3">
              <div className="flex items-center gap-3">
                <div className="w-3 h-3 rounded-full bg-orange-500" />
                <p className="text-orange-300 text-sm">
                  <span className="font-semibold">Loss Streak: {status.aggressive_features.consecutive_losses}</span>
                  <span className="text-gray-400 ml-2">
                    (pauses after 3 consecutive losses)
                  </span>
                </p>
              </div>
            </div>
          )}

          {/* Loss Streak Pause Banner */}
          {status?.aggressive_features?.loss_streak_paused && (
            <div className="bg-red-900/40 border border-red-500/50 rounded-lg p-4 animate-pulse">
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 rounded-full bg-red-500 animate-ping" />
                <div className="flex-1">
                  <h3 className="text-red-400 font-semibold">PAUSED - Loss Streak Protection Active</h3>
                  <p className="text-gray-400 text-sm mt-1">
                    AGAPE-ETH-PERP paused after {status.aggressive_features.consecutive_losses} consecutive losses. Will resume automatically.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Top Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <StatCard
              label="ETH Price"
              value={status?.current_eth_price ? `$${status.current_eth_price.toFixed(2)}` : '---'}
              icon={<DollarSign className="w-4 h-4" />}
              color="blue"
            />
            <StatCard
              label="Open Positions"
              value={`${status?.open_positions || 0}`}
              icon={<Activity className="w-4 h-4" />}
              color="blue"
            />
            <StatCard
              label="Unrealized P&L"
              value={status?.total_unrealized_pnl != null ? `$${status.total_unrealized_pnl.toFixed(2)}` : '$0.00'}
              icon={status?.total_unrealized_pnl >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
              color={(status?.total_unrealized_pnl || 0) >= 0 ? 'green' : 'red'}
            />
            <StatCard
              label="Total P&L"
              value={`$${(perf?.total_pnl ?? paperAccount?.cumulative_pnl ?? 0).toFixed(2)}`}
              icon={<DollarSign className="w-4 h-4" />}
              color={(perf?.total_pnl ?? paperAccount?.cumulative_pnl ?? 0) >= 0 ? 'green' : 'red'}
            />
            <StatCard
              label="Win Rate"
              value={(perf?.win_rate ?? paperAccount?.win_rate) != null ? `${perf?.win_rate ?? paperAccount?.win_rate}%` : '---'}
              icon={<CheckCircle className="w-4 h-4" />}
              color={(perf?.win_rate ?? paperAccount?.win_rate ?? 0) >= 60 ? 'green' : (perf?.win_rate ?? paperAccount?.win_rate ?? 0) >= 50 ? 'yellow' : 'gray'}
            />
            <StatCard
              label="Trades"
              value={`${perf?.total_trades ?? paperAccount?.total_trades ?? 0}`}
              icon={<BarChart3 className="w-4 h-4" />}
              color="blue"
            />
          </div>

          {/* Tabs - Branded (matching FORTRESS/SAMSON icon tab pattern) */}
          <div className="flex gap-2 border-b border-gray-800 pb-2">
            {AGAPE_ETH_PERP_TABS.map((tab) => (
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
            {activeTab === 'portfolio' && (
              <PortfolioTab
                status={status}
                perf={perf}
                positions={positionsData?.data}
                posLoading={posLoading}
                equityTimeframe={equityTimeframe}
                setEquityTimeframe={setEquityTimeframe}
                brand={brand}
                paperAccount={paperAccount}
                startingCapital={startingCapital}
              />
            )}
            {activeTab === 'overview' && (
              <OverviewTab status={status} perf={perf} brand={brand} />
            )}
            {activeTab === 'snapshot' && (
              <SnapshotTab data={snapshotData?.data} loading={snapLoading} brand={brand} />
            )}
            {activeTab === 'activity' && <ActivityTab data={scansData?.data} brand={brand} />}
            {activeTab === 'history' && <HistoryTab data={closedData?.data} brand={brand} />}
            {activeTab === 'config' && <ConfigTab status={status} mappingData={mappingData?.data} brand={brand} />}
          </div>
        </div>
      </main>
    </>
  )
}

// ==============================================================================
// PORTFOLIO TAB (Primary tab - matches FORTRESS/SAMSON pattern)
// ==============================================================================

function PortfolioTab({
  status,
  perf,
  positions,
  posLoading,
  equityTimeframe,
  setEquityTimeframe,
  brand,
  paperAccount,
  startingCapital,
}: {
  status: any
  perf: any
  positions: any[]
  posLoading: boolean
  equityTimeframe: string
  setEquityTimeframe: (tf: string) => void
  brand: typeof BOT_BRANDS.AGAPE_ETH_PERP
  paperAccount: any
  startingCapital: number
}) {
  const openPositions = positions || []

  return (
    <>
      {/* Paper Account Summary (matches VALOR pattern) */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-4">
          <div className="text-sm text-gray-400">Starting Capital</div>
          <div className="text-2xl font-bold text-white mt-1">
            ${startingCapital.toLocaleString()}
          </div>
        </div>
        <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-4">
          <div className="text-sm text-gray-400">Current Balance</div>
          <div className={`text-2xl font-bold mt-1 ${
            (paperAccount?.current_balance || startingCapital) >= startingCapital
              ? 'text-green-400' : 'text-red-400'
          }`}>
            ${(paperAccount?.current_balance || startingCapital).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>
        <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-4">
          <div className="text-sm text-gray-400">Cumulative P&L</div>
          <div className={`text-2xl font-bold mt-1 ${
            (paperAccount?.cumulative_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
          }`}>
            {(paperAccount?.cumulative_pnl || 0) >= 0 ? '+' : ''}${(paperAccount?.cumulative_pnl || 0).toFixed(2)}
          </div>
        </div>
        <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-4">
          <div className="text-sm text-gray-400">Return</div>
          <div className={`text-2xl font-bold mt-1 ${
            (paperAccount?.return_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'
          }`}>
            {(paperAccount?.return_pct || 0) >= 0 ? '+' : ''}{(paperAccount?.return_pct || 0).toFixed(2)}%
          </div>
        </div>
      </div>

      {/* Equity Curve */}
      <BotCard title="Equity Curve" botName="AGAPE_ETH_PERP" icon={<TrendingUp className="w-5 h-5" />}
        headerRight={
          <div className="flex gap-1">
            {EQUITY_TIMEFRAMES.map((tf) => (
              <button
                key={tf.id}
                onClick={() => setEquityTimeframe(tf.id)}
                className={`px-3 py-1 text-xs rounded transition-colors ${
                  equityTimeframe === tf.id
                    ? `${brand.primaryBg} text-white font-semibold`
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {tf.label}
              </button>
            ))}
          </div>
        }
      >
        <EquityCurveChart
          title=""
          botFilter="AGAPE_ETH_PERP"
          showIntradayOption={equityTimeframe === 'intraday'}
        />
      </BotCard>

      {/* Open Positions */}
      <BotCard title={`Open Positions (${openPositions.length})`} botName="AGAPE_ETH_PERP" icon={<Wallet className="w-5 h-5" />}>
        {posLoading ? (
          <LoadingState />
        ) : openPositions.length === 0 ? (
          <EmptyState
            icon={<Eye className="w-12 h-12" />}
            title="No open positions"
            description="AGAPE-ETH-PERP is scanning for opportunities"
          />
        ) : (
          <div className="space-y-3">
            {openPositions.map((pos: any) => (
              <div key={pos.position_id} className={`rounded-lg p-4 border ${brand.positionBorder} ${brand.positionBg}`}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <span className={`px-2 py-1 rounded text-xs font-bold ${
                      pos.side === 'long' ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'
                    }`}>
                      {pos.side?.toUpperCase()}
                    </span>
                    <span className="text-white font-mono font-semibold">
                      {pos.quantity}x ETH-PERP @ ${pos.entry_price?.toFixed(2)}
                    </span>
                    {pos.trailing_active && (
                      <span className={`px-2 py-0.5 ${brand.badgeBg} ${brand.badgeText} text-xs rounded font-mono`}>
                        TRAILING @ ${pos.current_stop?.toFixed(2)}
                      </span>
                    )}
                  </div>
                  <span className={`text-lg font-mono font-bold ${
                    (pos.unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {(pos.unrealized_pnl || 0) >= 0 ? '+' : ''}${pos.unrealized_pnl?.toFixed(2) || '0.00'}
                  </span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 text-xs">
                  <div>
                    <span className="text-gray-500">Stop Loss</span>
                    <p className="text-red-400 font-mono">{pos.stop_loss ? `$${pos.stop_loss.toFixed(2)}` : 'Trailing'}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">Take Profit</span>
                    <p className="text-green-400 font-mono">{pos.take_profit ? `$${pos.take_profit.toFixed(2)}` : 'No-Loss Trail'}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">Funding Regime</span>
                    <p className="text-gray-300">{pos.funding_regime_at_entry}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">Prophet</span>
                    <p className="text-gray-300">
                      {pos.oracle_advice || 'Advisory'}
                      {pos.oracle_win_probability ? ` (${(pos.oracle_win_probability * 100).toFixed(0)}%)` : ''}
                    </p>
                  </div>
                  <div>
                    <span className="text-gray-500">Opened</span>
                    <p className="text-white">{pos.open_time ? new Date(pos.open_time).toLocaleTimeString() : '---'}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">ID</span>
                    <p className="text-white font-mono">{pos.position_id?.slice(0, 8) || '---'}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </BotCard>

      {/* Performance Stats */}
      {(perf?.total_trades > 0 || (paperAccount?.total_trades ?? 0) > 0) && (
        <BotCard title="Performance" botName="AGAPE_ETH_PERP" icon={<BarChart3 className="w-5 h-5" />}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-gray-500">Profit Factor</span>
              <p className="text-white font-mono text-lg">{perf?.profit_factor ?? '---'}</p>
            </div>
            <div>
              <span className="text-gray-500">Avg Win</span>
              <p className="text-green-400 font-mono">${perf?.avg_win ?? '---'}</p>
            </div>
            <div>
              <span className="text-gray-500">Avg Loss</span>
              <p className="text-red-400 font-mono">-${perf?.avg_loss ?? '---'}</p>
            </div>
            <div>
              <span className="text-gray-500">Return</span>
              <p className={`font-mono ${(perf?.return_pct ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {perf?.return_pct ?? paperAccount?.return_pct ?? 0}%
              </p>
            </div>
            <div>
              <span className="text-gray-500">Realized P&L</span>
              <p className={`font-mono ${(perf?.realized_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ${(perf?.realized_pnl ?? paperAccount?.realized_pnl ?? 0).toFixed(2)}
              </p>
            </div>
            <div>
              <span className="text-gray-500">Unrealized P&L</span>
              <p className={`font-mono ${(perf?.unrealized_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ${(perf?.unrealized_pnl ?? paperAccount?.unrealized_pnl ?? 0).toFixed(2)}
              </p>
            </div>
            <div>
              <span className="text-gray-500">Best Trade</span>
              <p className="text-green-400 font-mono">${perf?.best_trade?.toFixed(2) ?? '---'}</p>
            </div>
            <div>
              <span className="text-gray-500">Worst Trade</span>
              <p className="text-red-400 font-mono">${perf?.worst_trade?.toFixed(2) ?? '---'}</p>
            </div>
          </div>
        </BotCard>
      )}
    </>
  )
}

// ==============================================================================
// OVERVIEW TAB (Bot status, aggressive features, direction tracker)
// ==============================================================================

function OverviewTab({
  status,
  perf,
  brand,
}: {
  status: any
  perf: any
  brand: typeof BOT_BRANDS.AGAPE_ETH_PERP
}) {
  const aggressive = status?.aggressive_features || {}
  const dirTracker = aggressive.direction_tracker || {}

  return (
    <>
      {/* Aggressive Features Panel */}
      <BotCard title="Aggressive Features" botName="AGAPE_ETH_PERP" icon={<Zap className="w-5 h-5" />}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div className="flex items-start gap-2">
            <Shield className={`w-4 h-4 ${brand.primaryText} mt-0.5 flex-shrink-0`} />
            <div>
              <span className="text-gray-500">No-Loss Trailing</span>
              <p className={`font-mono font-semibold ${aggressive.use_no_loss_trailing ? 'text-green-400' : 'text-gray-500'}`}>
                {aggressive.use_no_loss_trailing ? 'ACTIVE' : 'OFF'}
              </p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <RefreshCw className={`w-4 h-4 ${brand.primaryText} mt-0.5 flex-shrink-0`} />
            <div>
              <span className="text-gray-500">Stop-and-Reverse</span>
              <p className={`font-mono font-semibold ${aggressive.use_sar ? 'text-green-400' : 'text-gray-500'}`}>
                {aggressive.use_sar ? 'ACTIVE' : 'OFF'}
              </p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <Target className={`w-4 h-4 ${brand.primaryText} mt-0.5 flex-shrink-0`} />
            <div>
              <span className="text-gray-500">Consecutive Losses</span>
              <p className={`font-mono font-semibold ${(aggressive.consecutive_losses || 0) >= 3 ? 'text-red-400' : 'text-white'}`}>
                {aggressive.consecutive_losses || 0}
              </p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <ArrowUpDown className={`w-4 h-4 ${brand.primaryText} mt-0.5 flex-shrink-0`} />
            <div>
              <span className="text-gray-500">Direction Tracker</span>
              <p className="text-white font-mono text-xs">
                L: {dirTracker.long_win_rate != null ? `${(dirTracker.long_win_rate * 100).toFixed(0)}%` : '--'}
                {' '}S: {dirTracker.short_win_rate != null ? `${(dirTracker.short_win_rate * 100).toFixed(0)}%` : '--'}
              </p>
            </div>
          </div>
        </div>
      </BotCard>

      {/* Configuration */}
      <BotCard title="Bot Configuration" botName="AGAPE_ETH_PERP" icon={<Settings className="w-5 h-5" />}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Instrument</span>
            <p className="text-white font-mono">{status?.instrument || 'ETH-PERP'}</p>
          </div>
          <div>
            <span className="text-gray-500">Starting Capital</span>
            <p className="text-white font-mono">${status?.starting_capital?.toLocaleString() || '12,500'}</p>
          </div>
          <div>
            <span className="text-gray-500">Risk Per Trade</span>
            <p className="text-white font-mono">{status?.risk_per_trade_pct || 5}%</p>
          </div>
          <div>
            <span className="text-gray-500">Max Quantity</span>
            <p className="text-white font-mono">{status?.max_contracts || 10}</p>
          </div>
          <div>
            <span className="text-gray-500">Cooldown</span>
            <p className="text-white font-mono">{status?.cooldown_minutes || 5} min</p>
          </div>
          <div>
            <span className="text-gray-500">Prophet</span>
            <p className="text-white font-mono">{status?.require_oracle ? 'Required' : 'Advisory'}</p>
          </div>
          <div>
            <span className="text-gray-500">Cycles Run</span>
            <p className="text-white font-mono">{status?.cycle_count || 0}</p>
          </div>
          <div>
            <span className="text-gray-500">Mode</span>
            <p className={`font-mono font-semibold ${status?.mode === 'live' ? 'text-green-400' : 'text-yellow-400'}`}>
              {(status?.mode || 'paper').toUpperCase()}
            </p>
          </div>
        </div>
      </BotCard>
    </>
  )
}

// ==============================================================================
// MARKET SNAPSHOT TAB (Crypto microstructure signals)
// ==============================================================================

function SnapshotTab({ data, loading, brand }: { data: any; loading: boolean; brand: typeof BOT_BRANDS.AGAPE_ETH_PERP }) {
  if (loading) return <LoadingState />
  if (!data) return (
    <EmptyState
      icon={<Globe className="w-12 h-12" />}
      title="No snapshot available"
      description="Waiting for crypto market data"
    />
  )

  const signalColor = (signal: string) => {
    if (['LONG', 'BULLISH'].some(s => signal?.includes(s))) return 'text-green-400'
    if (['SHORT', 'BEARISH'].some(s => signal?.includes(s))) return 'text-red-400'
    if (signal === 'RANGE_BOUND') return 'text-yellow-400'
    return 'text-gray-400'
  }

  const riskColor = (risk: string) => {
    if (risk === 'HIGH') return 'text-red-400 bg-red-900/20'
    if (risk === 'ELEVATED') return 'text-orange-400 bg-orange-900/20'
    return 'text-green-400 bg-green-900/20'
  }

  return (
    <>
      {/* Price & Combined Signal */}
      <BotCard
        title={`${data.symbol} $${data.spot_price?.toFixed(2) || '---'}`}
        botName="AGAPE_ETH_PERP"
        icon={<DollarSign className="w-5 h-5" />}
        headerRight={
          <span className={`px-3 py-1 rounded-full font-semibold text-sm ${signalColor(data.signals?.combined_signal)}`}>
            {data.signals?.combined_signal} ({data.signals?.combined_confidence})
          </span>
        }
      >
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Leverage Regime</span>
            <p className="text-white">{data.signals?.leverage_regime}</p>
          </div>
          <div>
            <span className="text-gray-500">Direction Bias</span>
            <p className={signalColor(data.signals?.directional_bias)}>{data.signals?.directional_bias}</p>
          </div>
          <div>
            <span className="text-gray-500">Squeeze Risk</span>
            <p className={riskColor(data.signals?.squeeze_risk).split(' ')[0]}>{data.signals?.squeeze_risk}</p>
          </div>
          <div>
            <span className="text-gray-500">Volatility</span>
            <p className="text-white">{data.signals?.volatility_regime}</p>
          </div>
        </div>
      </BotCard>

      {/* Crypto Microstructure Signals */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Funding Rate */}
        <BotCard title="Funding Rate" subtitle="Replaces: Gamma Regime (POSITIVE/NEGATIVE)" botName="AGAPE_ETH_PERP">
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Current Rate</span>
              <span className="text-white font-mono">{data.funding?.rate != null ? `${(data.funding.rate * 100).toFixed(4)}%` : '---'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Predicted</span>
              <span className="text-white font-mono">{data.funding?.predicted != null ? `${(data.funding.predicted * 100).toFixed(4)}%` : '---'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Regime</span>
              <span className={`font-semibold ${signalColor(data.funding?.regime)}`}>{data.funding?.regime}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Annualized</span>
              <span className="text-white font-mono">{data.funding?.annualized != null ? `${(data.funding.annualized * 100).toFixed(1)}%` : '---'}</span>
            </div>
          </div>
        </BotCard>

        {/* Long/Short Ratio */}
        <BotCard title="Long/Short Ratio" subtitle="Replaces: GEX Directional Bias" botName="AGAPE_ETH_PERP">
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Ratio</span>
              <span className="text-white font-mono">{data.long_short?.ratio?.toFixed(2) || '---'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Long %</span>
              <span className="text-green-400 font-mono">{data.long_short?.long_pct?.toFixed(1) || '---'}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Short %</span>
              <span className="text-red-400 font-mono">{data.long_short?.short_pct?.toFixed(1) || '---'}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Bias</span>
              <span className={`font-semibold ${signalColor(data.long_short?.bias)}`}>{data.long_short?.bias}</span>
            </div>
          </div>
        </BotCard>

        {/* Liquidations */}
        <BotCard title="Liquidation Clusters" subtitle="Replaces: Gamma Walls / Price Magnets" botName="AGAPE_ETH_PERP">
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Nearest Long Liq</span>
              <span className="text-red-400 font-mono">{data.liquidations?.nearest_long_liq ? `$${data.liquidations.nearest_long_liq.toFixed(2)}` : '---'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Nearest Short Liq</span>
              <span className="text-green-400 font-mono">{data.liquidations?.nearest_short_liq ? `$${data.liquidations.nearest_short_liq.toFixed(2)}` : '---'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Cluster Count</span>
              <span className="text-white font-mono">{data.liquidations?.cluster_count || 0}</span>
            </div>
          </div>
          {data.liquidations?.top_clusters?.length > 0 && (
            <div className="mt-3 border-t border-gray-700 pt-3">
              <p className="text-xs text-gray-500 mb-2">Top Clusters</p>
              <div className="space-y-1">
                {data.liquidations.top_clusters.slice(0, 5).map((c: any, i: number) => (
                  <div key={i} className="flex justify-between text-xs">
                    <span className="text-gray-400 font-mono">${c.price?.toFixed(2)}</span>
                    <span className={`${riskColor(c.intensity).split(' ')[0]} font-mono`}>
                      {c.intensity} ({c.distance_pct}%)
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </BotCard>

        {/* Crypto GEX */}
        <BotCard title="Crypto GEX (Deribit)" subtitle="Direct equivalent of Net GEX" botName="AGAPE_ETH_PERP">
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Net GEX</span>
              <span className="text-white font-mono">{data.crypto_gex?.net_gex?.toFixed(2) || '---'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Regime</span>
              <span className={`font-semibold ${signalColor(data.crypto_gex?.regime)}`}>{data.crypto_gex?.regime}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Call GEX</span>
              <span className="text-green-400 font-mono">{data.crypto_gex?.call_gex?.toFixed(2) || '---'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Put GEX</span>
              <span className="text-red-400 font-mono">{data.crypto_gex?.put_gex?.toFixed(2) || '---'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Max Pain / Flip</span>
              <span className="text-white font-mono">{data.crypto_gex?.flip_point ? `$${data.crypto_gex.flip_point.toFixed(2)}` : '---'}</span>
            </div>
          </div>
        </BotCard>
      </div>
    </>
  )
}

// ==============================================================================
// ACTIVITY TAB
// ==============================================================================

function ActivityTab({ data, brand }: { data: any[]; brand: typeof BOT_BRANDS.AGAPE_ETH_PERP }) {
  const scans = data || []

  if (scans.length === 0) {
    return (
      <EmptyState
        icon={<Activity className="w-12 h-12" />}
        title="No scan activity yet"
        description="AGAPE-ETH-PERP scans will appear here as they run"
      />
    )
  }

  return (
    <BotCard title={`Scan Activity (${scans.length})`} botName="AGAPE_ETH_PERP" icon={<Activity className="w-5 h-5" />}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="text-left px-4 py-3 text-gray-500 font-medium">Time</th>
              <th className="text-left px-4 py-3 text-gray-500 font-medium">ETH</th>
              <th className="text-left px-4 py-3 text-gray-500 font-medium">Funding</th>
              <th className="text-left px-4 py-3 text-gray-500 font-medium">Signal</th>
              <th className="text-left px-4 py-3 text-gray-500 font-medium">Prophet</th>
              <th className="text-left px-4 py-3 text-gray-500 font-medium">Outcome</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {scans.map((scan: any, i: number) => (
              <tr key={i} className="hover:bg-gray-800/30">
                <td className="px-4 py-2 text-gray-400 font-mono text-xs">
                  {scan.timestamp ? new Date(scan.timestamp).toLocaleTimeString() : '---'}
                </td>
                <td className="px-4 py-2 text-white font-mono">
                  ${scan.eth_price?.toFixed(2) || '---'}
                </td>
                <td className="px-4 py-2">
                  <span className="text-xs text-gray-400">{scan.funding_regime}</span>
                </td>
                <td className="px-4 py-2">
                  <span className={`text-xs font-semibold ${
                    scan.combined_signal === 'LONG' ? 'text-green-400' :
                    scan.combined_signal === 'SHORT' ? 'text-red-400' :
                    scan.combined_signal === 'RANGE_BOUND' ? 'text-yellow-400' :
                    'text-gray-500'
                  }`}>
                    {scan.combined_signal} {scan.combined_confidence && `(${scan.combined_confidence})`}
                  </span>
                </td>
                <td className="px-4 py-2 text-xs text-gray-400">{scan.oracle_advice || 'Advisory'}</td>
                <td className="px-4 py-2">
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    scan.outcome?.includes('TRADED') ? `${brand.badgeBg} ${brand.badgeText}` :
                    scan.outcome?.includes('SAR') ? 'bg-violet-900/50 text-violet-300' :
                    scan.outcome?.includes('ERROR') ? 'bg-red-900/50 text-red-300' :
                    scan.outcome?.includes('LOSS_STREAK') ? 'bg-orange-900/50 text-orange-300' :
                    'bg-gray-800 text-gray-500'
                  }`}>
                    {scan.outcome}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </BotCard>
  )
}

// ==============================================================================
// HISTORY TAB
// ==============================================================================

function HistoryTab({ data, brand }: { data: any[]; brand: typeof BOT_BRANDS.AGAPE_ETH_PERP }) {
  const trades = data || []

  if (trades.length === 0) {
    return (
      <EmptyState
        icon={<History className="w-12 h-12" />}
        title="No closed trades yet"
        description="Completed trades will appear here"
      />
    )
  }

  return (
    <BotCard title={`Trade History (${trades.length})`} botName="AGAPE_ETH_PERP" icon={<History className="w-5 h-5" />}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="text-left px-4 py-3 text-gray-500 font-medium">Closed</th>
              <th className="text-left px-4 py-3 text-gray-500 font-medium">Side</th>
              <th className="text-left px-4 py-3 text-gray-500 font-medium">Entry</th>
              <th className="text-left px-4 py-3 text-gray-500 font-medium">Exit</th>
              <th className="text-left px-4 py-3 text-gray-500 font-medium">P&L</th>
              <th className="text-left px-4 py-3 text-gray-500 font-medium">Reason</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {trades.map((trade: any, i: number) => (
              <tr key={i} className="hover:bg-gray-800/30">
                <td className="px-4 py-2 text-gray-400 font-mono text-xs">
                  {trade.close_time ? new Date(trade.close_time).toLocaleString() : '---'}
                </td>
                <td className="px-4 py-2">
                  <span className={`text-xs font-bold ${
                    trade.side === 'long' ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {trade.side?.toUpperCase()}
                  </span>
                </td>
                <td className="px-4 py-2 text-white font-mono">${trade.entry_price?.toFixed(2)}</td>
                <td className="px-4 py-2 text-white font-mono">${trade.close_price?.toFixed(2) || '---'}</td>
                <td className="px-4 py-2">
                  <span className={`font-mono font-semibold ${
                    (trade.realized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {(trade.realized_pnl || 0) >= 0 ? '+' : ''}${trade.realized_pnl?.toFixed(2) || '0.00'}
                  </span>
                </td>
                <td className="px-4 py-2">
                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                    trade.close_reason?.includes('SAR') ? 'bg-violet-900/30 text-violet-300' :
                    trade.close_reason?.includes('TRAIL') ? `${brand.badgeBg} ${brand.badgeText}` :
                    trade.close_reason?.includes('PROFIT') ? 'bg-green-900/30 text-green-300' :
                    trade.close_reason?.includes('EMERGENCY') ? 'bg-red-900/30 text-red-300' :
                    'text-gray-400'
                  }`}>
                    {trade.close_reason}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </BotCard>
  )
}

// ==============================================================================
// CONFIG TAB (Settings + GEX Mapping)
// ==============================================================================

function ConfigTab({ status, mappingData, brand }: { status: any; mappingData: any; brand: typeof BOT_BRANDS.AGAPE_ETH_PERP }) {
  return (
    <>
      {/* Configuration */}
      <BotCard title="Bot Configuration" botName="AGAPE_ETH_PERP" icon={<Settings className="w-5 h-5" />}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Instrument</span>
            <p className="text-white font-mono">{status?.instrument || 'ETH-PERP'}</p>
          </div>
          <div>
            <span className="text-gray-500">Starting Capital</span>
            <p className="text-white font-mono">${status?.starting_capital?.toLocaleString() || '12,500'}</p>
          </div>
          <div>
            <span className="text-gray-500">Risk Per Trade</span>
            <p className="text-white font-mono">{status?.risk_per_trade_pct || 5}%</p>
          </div>
          <div>
            <span className="text-gray-500">Max Quantity</span>
            <p className="text-white font-mono">{status?.max_contracts || 10}</p>
          </div>
          <div>
            <span className="text-gray-500">Cooldown</span>
            <p className="text-white font-mono">{status?.cooldown_minutes || 5} min</p>
          </div>
          <div>
            <span className="text-gray-500">Prophet</span>
            <p className="text-white font-mono">{status?.require_oracle ? 'Required' : 'Advisory'}</p>
          </div>
          <div>
            <span className="text-gray-500">Cycles Run</span>
            <p className="text-white font-mono">{status?.cycle_count || 0}</p>
          </div>
          <div>
            <span className="text-gray-500">Mode</span>
            <p className={`font-mono font-semibold ${status?.mode === 'live' ? 'text-green-400' : 'text-yellow-400'}`}>
              {(status?.mode || 'paper').toUpperCase()}
            </p>
          </div>
        </div>
      </BotCard>

      {/* GEX Mapping */}
      {mappingData && (
        <BotCard title={mappingData.title || 'GEX Mapping'} subtitle={mappingData.description} botName="AGAPE_ETH_PERP" icon={<Globe className="w-5 h-5" />}>
          <div className="space-y-4">
            {mappingData.mappings?.map((m: any, i: number) => (
              <div key={i} className="border border-gray-700 rounded-lg p-4">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <span className="text-xs text-gray-500">Equity GEX:</span>
                    <p className="text-gray-400 font-mono text-sm">{m.gex_concept}</p>
                  </div>
                  <div className="text-right">
                    <span className={`text-xs ${brand.primaryText}`}>Crypto Equivalent:</span>
                    <p className={`${brand.lightText} font-semibold text-sm`}>{m.crypto_equivalent}</p>
                  </div>
                </div>
                <p className="text-gray-400 text-xs mt-2">{m.explanation}</p>
                {m.data_source && (
                  <p className="text-gray-500 text-xs mt-1">Source: {m.data_source}</p>
                )}
              </div>
            ))}
          </div>
        </BotCard>
      )}

      {/* Trade Instrument */}
      {mappingData?.trade_instrument && (
        <BotCard title="Trade Instrument" botName="AGAPE_ETH_PERP" icon={<Target className="w-5 h-5" />}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            {Object.entries(mappingData.trade_instrument).map(([key, val]: [string, any]) => (
              <div key={key}>
                <span className="text-gray-500 text-xs">{key.replace(/_/g, ' ')}</span>
                <p className="text-white font-mono">{val}</p>
              </div>
            ))}
          </div>
        </BotCard>
      )}
    </>
  )
}
