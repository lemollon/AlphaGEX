'use client'

import { useState, useMemo } from 'react'
import useSWR from 'swr'
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
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import EquityCurveChart from '@/components/charts/EquityCurveChart'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import {
  BotPageHeader,
  StatCard,
  LoadingState,
} from '@/components/trader'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const fetcher = (url: string) => fetch(`${API_BASE}${url}`).then(r => r.json())

// ============================================================================
// AGAPE BRAND COLORS - Fuchsia/Violet theme
// ============================================================================
const BRAND = {
  primary: 'fuchsia',
  accent: 'violet',
  activeBg: 'bg-fuchsia-500',
  activeText: 'text-black',
  activeBorder: 'border-fuchsia-500',
  glowBorder: 'border-fuchsia-600/50',
  headerGradient: 'from-fuchsia-600 to-violet-600',
  tagBg: 'bg-fuchsia-900/50',
  tagText: 'text-fuchsia-300',
}

// ============================================================================
// EQUITY CURVE TIMEFRAMES (matching HERACLES pattern)
// ============================================================================
const EQUITY_TIMEFRAMES = [
  { id: 'intraday', label: 'Today', days: 0 },
  { id: '7d', label: '7D', days: 7 },
  { id: '14d', label: '14D', days: 14 },
  { id: '30d', label: '30D', days: 30 },
  { id: '90d', label: '90D', days: 90 },
]

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'snapshot', label: 'Market Snapshot' },
  { id: 'positions', label: 'Positions' },
  { id: 'activity', label: 'Activity' },
  { id: 'history', label: 'History' },
  { id: 'gex-mapping', label: 'GEX Mapping' },
] as const

type TabId = typeof TABS[number]['id']

export default function AgapePage() {
  const [activeTab, setActiveTab] = useState<TabId>('overview')
  const [equityTimeframe, setEquityTimeframe] = useState('intraday')
  const sidebarPadding = useSidebarPadding()

  const selectedTimeframe = EQUITY_TIMEFRAMES.find(tf => tf.id === equityTimeframe) || EQUITY_TIMEFRAMES[0]
  const equityDays = selectedTimeframe.days || 30

  const { data: statusData, isLoading: statusLoading } = useSWR('/api/agape/status', fetcher, { refreshInterval: 30000 })
  const { data: perfData } = useSWR('/api/agape/performance', fetcher, { refreshInterval: 60000 })
  const { data: equityData } = useSWR(
    equityTimeframe === 'intraday'
      ? '/api/agape/equity-curve/intraday'
      : `/api/agape/equity-curve?days=${equityDays}`,
    fetcher,
    { refreshInterval: 30000 }
  )
  const { data: positionsData, isLoading: posLoading } = useSWR(
    activeTab === 'positions' ? '/api/agape/positions' : null, fetcher, { refreshInterval: 15000 }
  )
  const { data: snapshotData, isLoading: snapLoading } = useSWR(
    activeTab === 'snapshot' ? '/api/agape/snapshot' : null, fetcher, { refreshInterval: 30000 }
  )
  const { data: scansData } = useSWR(
    activeTab === 'activity' ? '/api/agape/scan-activity?limit=30' : null, fetcher, { refreshInterval: 15000 }
  )
  const { data: closedData } = useSWR(
    activeTab === 'history' ? '/api/agape/closed-trades?limit=50' : null, fetcher
  )
  const { data: mappingData } = useSWR(
    activeTab === 'gex-mapping' ? '/api/agape/gex-mapping' : null, fetcher
  )

  const status = statusData?.data
  const perf = perfData?.data

  if (statusLoading) {
    return (
      <>
        <Navigation />
        <main className={`pt-24 ${sidebarPadding} pr-4 pb-8`}>
          <LoadingState />
        </main>
      </>
    )
  }

  return (
    <>
      <Navigation />
      <main className={`pt-24 ${sidebarPadding} pr-4 pb-8`}>
        {/* Header */}
        <BotPageHeader
          botName="AGAPE"
          isActive={status?.status === 'ACTIVE'}
        />

        {/* Aggressive Mode Banner */}
        <div className="mb-4 bg-gradient-to-r from-fuchsia-900/40 to-violet-900/40 border border-fuchsia-600/30 rounded-xl px-4 py-3 flex items-center gap-3">
          <Zap className="w-5 h-5 text-fuchsia-400 flex-shrink-0" />
          <div>
            <span className="text-fuchsia-300 font-semibold text-sm">AGGRESSIVE MODE</span>
            <span className="text-text-secondary text-xs ml-2">
              SAR + No-Loss Trailing + Direction Tracker | {status?.cooldown_minutes || 5}m cooldown | {status?.max_positions || 20} max positions
            </span>
          </div>
          {status?.aggressive_features?.loss_streak_paused && (
            <span className="ml-auto px-2 py-0.5 bg-red-900/50 text-red-300 text-xs rounded font-mono">LOSS STREAK PAUSE</span>
          )}
        </div>

        {/* Top Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-6">
          <StatCard
            label="ETH Price"
            value={status?.current_eth_price ? `$${status.current_eth_price.toFixed(2)}` : '---'}
            icon={<DollarSign className="w-4 h-4" />}
            color="blue"
          />
          <StatCard
            label="Open Positions"
            value={`${status?.open_positions || 0} / ${status?.max_positions || 20}`}
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
            value={perf?.total_pnl != null ? `$${perf.total_pnl.toFixed(2)}` : '$0.00'}
            icon={<DollarSign className="w-4 h-4" />}
            color={(perf?.total_pnl || 0) >= 0 ? 'green' : 'red'}
          />
          <StatCard
            label="Win Rate"
            value={perf?.win_rate != null ? `${perf.win_rate}%` : '---'}
            icon={<CheckCircle className="w-4 h-4" />}
            color={(perf?.win_rate || 0) >= 60 ? 'green' : (perf?.win_rate || 0) >= 50 ? 'yellow' : 'gray'}
          />
          <StatCard
            label="Trades"
            value={`${perf?.total_trades || 0}`}
            icon={<Clock className="w-4 h-4" />}
            color="blue"
          />
        </div>

        {/* Tabs */}
        <div className="flex space-x-1 bg-background-card rounded-lg p-1 mb-6 overflow-x-auto">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'bg-fuchsia-600 text-white'
                  : 'text-text-secondary hover:text-text-primary hover:bg-background-hover'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        {activeTab === 'overview' && (
          <OverviewTab
            status={status}
            perf={perf}
            equityData={equityData}
            equityTimeframe={equityTimeframe}
            setEquityTimeframe={setEquityTimeframe}
          />
        )}
        {activeTab === 'snapshot' && <SnapshotTab data={snapshotData?.data} loading={snapLoading} />}
        {activeTab === 'positions' && <PositionsTab data={positionsData?.data} loading={posLoading} />}
        {activeTab === 'activity' && <ActivityTab data={scansData?.data} />}
        {activeTab === 'history' && <HistoryTab data={closedData?.data} />}
        {activeTab === 'gex-mapping' && <GexMappingTab data={mappingData?.data} />}
      </main>
    </>
  )
}

// ==============================================================================
// OVERVIEW TAB (with time frame filters + aggressive features)
// ==============================================================================

function OverviewTab({
  status,
  perf,
  equityData,
  equityTimeframe,
  setEquityTimeframe,
}: {
  status: any
  perf: any
  equityData: any
  equityTimeframe: string
  setEquityTimeframe: (tf: string) => void
}) {
  // Build equity curve data from API response
  const chartData = useMemo(() => {
    if (!equityData?.success) return []

    if (equityTimeframe === 'intraday') {
      // Intraday snapshots
      const snapshots = equityData.data || []
      return snapshots.map((s: any) => ({
        date: s.timestamp ? new Date(s.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '',
        equity: s.equity || 0,
        unrealized_pnl: s.unrealized_pnl || 0,
        eth_price: s.eth_price || 0,
      }))
    } else {
      // Historical equity curve
      const curve = equityData.data?.equity_curve || []
      return curve.map((p: any) => ({
        date: p.date || '',
        equity: p.equity || 0,
        daily_pnl: p.daily_pnl || 0,
        cumulative_pnl: p.cumulative_pnl || 0,
        trades: p.trades || 0,
      }))
    }
  }, [equityData, equityTimeframe])

  const aggressive = status?.aggressive_features || {}
  const dirTracker = aggressive.direction_tracker || {}

  return (
    <div className="space-y-6">
      {/* Equity Curve with Time Frame Selector */}
      <div className="bg-background-card rounded-xl p-6 border border-gray-800">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-text-primary">AGAPE Equity Curve</h3>
          {/* Time Frame Buttons - AGAPE branded */}
          <div className="flex gap-1">
            {EQUITY_TIMEFRAMES.map((tf) => (
              <button
                key={tf.id}
                onClick={() => setEquityTimeframe(tf.id)}
                className={`px-3 py-1 text-xs rounded transition-colors ${
                  equityTimeframe === tf.id
                    ? 'bg-fuchsia-500 text-black font-semibold'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {tf.label}
              </button>
            ))}
          </div>
        </div>

        {/* Summary stats for the selected period */}
        {equityTimeframe !== 'intraday' && equityData?.data && (
          <div className="grid grid-cols-4 gap-4 mb-4 text-sm">
            <div>
              <span className="text-text-muted">Starting Capital</span>
              <p className="text-text-primary font-mono">${equityData.data.starting_capital?.toLocaleString()}</p>
            </div>
            <div>
              <span className="text-text-muted">Current Equity</span>
              <p className="text-text-primary font-mono">${equityData.data.current_equity?.toLocaleString()}</p>
            </div>
            <div>
              <span className="text-text-muted">Total P&L</span>
              <p className={`font-mono font-semibold ${(equityData.data.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ${equityData.data.total_pnl?.toFixed(2)}
              </p>
            </div>
            <div>
              <span className="text-text-muted">Return</span>
              <p className={`font-mono font-semibold ${(equityData.data.total_return_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {equityData.data.total_return_pct?.toFixed(2)}%
              </p>
            </div>
          </div>
        )}

        {/* Chart */}
        {chartData.length > 0 ? (
          <EquityCurveChart
            title=""
            botFilter="AGAPE"
            showIntradayOption={equityTimeframe === 'intraday'}
          />
        ) : (
          <div className="h-48 flex items-center justify-center text-text-muted">
            No equity data for this period
          </div>
        )}
      </div>

      {/* Aggressive Features Panel */}
      <div className="bg-background-card rounded-xl p-6 border border-fuchsia-600/20">
        <h3 className="text-lg font-semibold text-fuchsia-400 mb-4 flex items-center gap-2">
          <Zap className="w-5 h-5" />
          Aggressive Features
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div className="flex items-start gap-2">
            <Shield className="w-4 h-4 text-fuchsia-400 mt-0.5 flex-shrink-0" />
            <div>
              <span className="text-text-muted">No-Loss Trailing</span>
              <p className={`font-mono font-semibold ${aggressive.use_no_loss_trailing ? 'text-green-400' : 'text-gray-500'}`}>
                {aggressive.use_no_loss_trailing ? 'ACTIVE' : 'OFF'}
              </p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <RefreshCw className="w-4 h-4 text-fuchsia-400 mt-0.5 flex-shrink-0" />
            <div>
              <span className="text-text-muted">Stop-and-Reverse</span>
              <p className={`font-mono font-semibold ${aggressive.use_sar ? 'text-green-400' : 'text-gray-500'}`}>
                {aggressive.use_sar ? 'ACTIVE' : 'OFF'}
              </p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <Target className="w-4 h-4 text-fuchsia-400 mt-0.5 flex-shrink-0" />
            <div>
              <span className="text-text-muted">Consecutive Losses</span>
              <p className={`font-mono font-semibold ${(aggressive.consecutive_losses || 0) >= 3 ? 'text-red-400' : 'text-text-primary'}`}>
                {aggressive.consecutive_losses || 0}
              </p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <ArrowUpDown className="w-4 h-4 text-fuchsia-400 mt-0.5 flex-shrink-0" />
            <div>
              <span className="text-text-muted">Direction Tracker</span>
              <p className="text-text-primary font-mono text-xs">
                L: {dirTracker.long_win_rate != null ? `${(dirTracker.long_win_rate * 100).toFixed(0)}%` : '--'}
                {' '}S: {dirTracker.short_win_rate != null ? `${(dirTracker.short_win_rate * 100).toFixed(0)}%` : '--'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Config */}
      <div className="bg-background-card rounded-xl p-6 border border-gray-800">
        <h3 className="text-lg font-semibold text-text-primary mb-4">Configuration</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-text-muted">Instrument</span>
            <p className="text-text-primary font-mono">{status?.instrument || '/MET'}</p>
          </div>
          <div>
            <span className="text-text-muted">Starting Capital</span>
            <p className="text-text-primary font-mono">${status?.starting_capital?.toLocaleString() || '5,000'}</p>
          </div>
          <div>
            <span className="text-text-muted">Risk Per Trade</span>
            <p className="text-text-primary font-mono">{status?.risk_per_trade_pct || 5}%</p>
          </div>
          <div>
            <span className="text-text-muted">Max Contracts</span>
            <p className="text-text-primary font-mono">{status?.max_contracts || 10}</p>
          </div>
          <div>
            <span className="text-text-muted">Cooldown</span>
            <p className="text-text-primary font-mono">{status?.cooldown_minutes || 5} min</p>
          </div>
          <div>
            <span className="text-text-muted">Oracle</span>
            <p className="text-text-primary font-mono">{status?.require_oracle ? 'Required' : 'Advisory'}</p>
          </div>
          <div>
            <span className="text-text-muted">Cycles Run</span>
            <p className="text-text-primary font-mono">{status?.cycle_count || 0}</p>
          </div>
          <div>
            <span className="text-text-muted">Mode</span>
            <p className={`font-mono font-semibold ${status?.mode === 'live' ? 'text-green-400' : 'text-yellow-400'}`}>
              {(status?.mode || 'paper').toUpperCase()}
            </p>
          </div>
        </div>
      </div>

      {/* Performance Stats */}
      {perf && perf.total_trades > 0 && (
        <div className="bg-background-card rounded-xl p-6 border border-gray-800">
          <h3 className="text-lg font-semibold text-text-primary mb-4">Performance</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-text-muted">Profit Factor</span>
              <p className="text-text-primary font-mono text-lg">{perf.profit_factor}</p>
            </div>
            <div>
              <span className="text-text-muted">Avg Win</span>
              <p className="text-green-400 font-mono">${perf.avg_win}</p>
            </div>
            <div>
              <span className="text-text-muted">Avg Loss</span>
              <p className="text-red-400 font-mono">-${perf.avg_loss}</p>
            </div>
            <div>
              <span className="text-text-muted">Return</span>
              <p className={`font-mono ${perf.return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {perf.return_pct}%
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ==============================================================================
// MARKET SNAPSHOT TAB
// ==============================================================================

function SnapshotTab({ data, loading }: { data: any; loading: boolean }) {
  if (loading) return <LoadingState />
  if (!data) return <div className="text-text-muted text-center py-12">No snapshot available</div>

  const signalColor = (signal: string) => {
    if (['LONG', 'BULLISH'].some(s => signal?.includes(s))) return 'text-green-400'
    if (['SHORT', 'BEARISH'].some(s => signal?.includes(s))) return 'text-red-400'
    if (signal === 'RANGE_BOUND') return 'text-yellow-400'
    return 'text-text-secondary'
  }

  const riskColor = (risk: string) => {
    if (risk === 'HIGH') return 'text-red-400 bg-red-900/20'
    if (risk === 'ELEVATED') return 'text-orange-400 bg-orange-900/20'
    return 'text-green-400 bg-green-900/20'
  }

  return (
    <div className="space-y-6">
      {/* Price & Combined Signal */}
      <div className="bg-background-card rounded-xl p-6 border border-gray-800">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-text-primary">
            {data.symbol} ${data.spot_price?.toFixed(2)}
          </h3>
          <div className={`px-3 py-1 rounded-full font-semibold text-sm ${signalColor(data.signals?.combined_signal)}`}>
            {data.signals?.combined_signal} ({data.signals?.combined_confidence})
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-text-muted">Leverage Regime</span>
            <p className="text-text-primary">{data.signals?.leverage_regime}</p>
          </div>
          <div>
            <span className="text-text-muted">Direction Bias</span>
            <p className={signalColor(data.signals?.directional_bias)}>{data.signals?.directional_bias}</p>
          </div>
          <div>
            <span className="text-text-muted">Squeeze Risk</span>
            <p className={riskColor(data.signals?.squeeze_risk).split(' ')[0]}>{data.signals?.squeeze_risk}</p>
          </div>
          <div>
            <span className="text-text-muted">Volatility</span>
            <p className="text-text-primary">{data.signals?.volatility_regime}</p>
          </div>
        </div>
      </div>

      {/* Crypto Microstructure Signals */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Funding Rate */}
        <div className="bg-background-card rounded-xl p-6 border border-gray-800">
          <h4 className="text-sm font-semibold text-fuchsia-400 mb-1">Funding Rate</h4>
          <p className="text-xs text-text-muted mb-3">Replaces: Gamma Regime (POSITIVE/NEGATIVE)</p>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-text-muted">Current Rate</span>
              <span className="text-text-primary font-mono">{data.funding?.rate != null ? `${(data.funding.rate * 100).toFixed(4)}%` : '---'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Predicted</span>
              <span className="text-text-primary font-mono">{data.funding?.predicted != null ? `${(data.funding.predicted * 100).toFixed(4)}%` : '---'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Regime</span>
              <span className={`font-semibold ${signalColor(data.funding?.regime)}`}>{data.funding?.regime}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Annualized</span>
              <span className="text-text-primary font-mono">{data.funding?.annualized != null ? `${(data.funding.annualized * 100).toFixed(1)}%` : '---'}</span>
            </div>
          </div>
        </div>

        {/* Long/Short Ratio */}
        <div className="bg-background-card rounded-xl p-6 border border-gray-800">
          <h4 className="text-sm font-semibold text-fuchsia-400 mb-1">Long/Short Ratio</h4>
          <p className="text-xs text-text-muted mb-3">Replaces: GEX Directional Bias</p>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-text-muted">Ratio</span>
              <span className="text-text-primary font-mono">{data.long_short?.ratio?.toFixed(2) || '---'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Long %</span>
              <span className="text-green-400 font-mono">{data.long_short?.long_pct?.toFixed(1) || '---'}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Short %</span>
              <span className="text-red-400 font-mono">{data.long_short?.short_pct?.toFixed(1) || '---'}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Bias</span>
              <span className={`font-semibold ${signalColor(data.long_short?.bias)}`}>{data.long_short?.bias}</span>
            </div>
          </div>
        </div>

        {/* Liquidations */}
        <div className="bg-background-card rounded-xl p-6 border border-gray-800">
          <h4 className="text-sm font-semibold text-fuchsia-400 mb-1">Liquidation Clusters</h4>
          <p className="text-xs text-text-muted mb-3">Replaces: Gamma Walls / Price Magnets</p>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-text-muted">Nearest Long Liq</span>
              <span className="text-red-400 font-mono">{data.liquidations?.nearest_long_liq ? `$${data.liquidations.nearest_long_liq.toFixed(0)}` : '---'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Nearest Short Liq</span>
              <span className="text-green-400 font-mono">{data.liquidations?.nearest_short_liq ? `$${data.liquidations.nearest_short_liq.toFixed(0)}` : '---'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Cluster Count</span>
              <span className="text-text-primary font-mono">{data.liquidations?.cluster_count || 0}</span>
            </div>
          </div>
          {data.liquidations?.top_clusters?.length > 0 && (
            <div className="mt-3 border-t border-gray-700 pt-3">
              <p className="text-xs text-text-muted mb-2">Top Clusters</p>
              <div className="space-y-1">
                {data.liquidations.top_clusters.slice(0, 5).map((c: any, i: number) => (
                  <div key={i} className="flex justify-between text-xs">
                    <span className="text-text-secondary font-mono">${c.price?.toFixed(0)}</span>
                    <span className={`${riskColor(c.intensity).split(' ')[0]} font-mono`}>
                      {c.intensity} ({c.distance_pct}%)
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Crypto GEX */}
        <div className="bg-background-card rounded-xl p-6 border border-gray-800">
          <h4 className="text-sm font-semibold text-fuchsia-400 mb-1">Crypto GEX (Deribit)</h4>
          <p className="text-xs text-text-muted mb-3">Direct equivalent of Net GEX</p>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-text-muted">Net GEX</span>
              <span className="text-text-primary font-mono">{data.crypto_gex?.net_gex?.toFixed(2) || '---'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Regime</span>
              <span className={`font-semibold ${signalColor(data.crypto_gex?.regime)}`}>{data.crypto_gex?.regime}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Call GEX</span>
              <span className="text-green-400 font-mono">{data.crypto_gex?.call_gex?.toFixed(2) || '---'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Put GEX</span>
              <span className="text-red-400 font-mono">{data.crypto_gex?.put_gex?.toFixed(2) || '---'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Max Pain / Flip</span>
              <span className="text-text-primary font-mono">{data.crypto_gex?.flip_point ? `$${data.crypto_gex.flip_point.toFixed(0)}` : '---'}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ==============================================================================
// POSITIONS TAB
// ==============================================================================

function PositionsTab({ data, loading }: { data: any[]; loading: boolean }) {
  if (loading) return <LoadingState />
  const positions = data || []

  if (positions.length === 0) {
    return (
      <div className="bg-background-card rounded-xl p-12 border border-gray-800 text-center">
        <Eye className="w-12 h-12 text-text-muted mx-auto mb-4" />
        <p className="text-text-muted text-lg">No open positions</p>
        <p className="text-text-secondary text-sm mt-1">AGAPE is hunting for opportunities</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {positions.map((pos: any) => (
        <div key={pos.position_id} className="bg-background-card rounded-xl p-6 border border-fuchsia-600/50">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-3">
              <span className={`px-2 py-1 rounded text-xs font-bold ${
                pos.side === 'long' ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'
              }`}>
                {pos.side?.toUpperCase()}
              </span>
              <span className="text-text-primary font-mono font-semibold">
                {pos.contracts}x /MET @ ${pos.entry_price?.toFixed(2)}
              </span>
              {/* Trailing status badge */}
              {pos.trailing_active && (
                <span className="px-2 py-0.5 bg-fuchsia-900/50 text-fuchsia-300 text-xs rounded font-mono">
                  TRAILING @ ${pos.current_stop?.toFixed(2)}
                </span>
              )}
            </div>
            <span className={`text-lg font-mono font-bold ${
              (pos.unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
            }`}>
              ${pos.unrealized_pnl?.toFixed(2) || '0.00'}
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <div>
              <span className="text-text-muted">Stop Loss</span>
              <p className="text-red-400 font-mono">{pos.stop_loss ? `$${pos.stop_loss.toFixed(2)}` : 'Trailing'}</p>
            </div>
            <div>
              <span className="text-text-muted">Take Profit</span>
              <p className="text-green-400 font-mono">{pos.take_profit ? `$${pos.take_profit.toFixed(2)}` : 'No-Loss Trail'}</p>
            </div>
            <div>
              <span className="text-text-muted">Funding Regime</span>
              <p className="text-text-primary">{pos.funding_regime_at_entry}</p>
            </div>
            <div>
              <span className="text-text-muted">Oracle</span>
              <p className="text-text-primary">
                {pos.oracle_advice || 'Advisory'}
                {pos.oracle_win_probability ? ` (${(pos.oracle_win_probability * 100).toFixed(0)}%)` : ''}
              </p>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ==============================================================================
// ACTIVITY TAB
// ==============================================================================

function ActivityTab({ data }: { data: any[] }) {
  const scans = data || []

  if (scans.length === 0) {
    return <div className="text-text-muted text-center py-12">No scan activity yet</div>
  }

  return (
    <div className="bg-background-card rounded-xl border border-gray-800 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="text-left px-4 py-3 text-text-muted font-medium">Time</th>
              <th className="text-left px-4 py-3 text-text-muted font-medium">ETH</th>
              <th className="text-left px-4 py-3 text-text-muted font-medium">Funding</th>
              <th className="text-left px-4 py-3 text-text-muted font-medium">Signal</th>
              <th className="text-left px-4 py-3 text-text-muted font-medium">Oracle</th>
              <th className="text-left px-4 py-3 text-text-muted font-medium">Outcome</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {scans.map((scan: any, i: number) => (
              <tr key={i} className="hover:bg-background-hover">
                <td className="px-4 py-2 text-text-secondary font-mono text-xs">
                  {scan.timestamp ? new Date(scan.timestamp).toLocaleTimeString() : '---'}
                </td>
                <td className="px-4 py-2 text-text-primary font-mono">
                  ${scan.eth_price?.toFixed(2) || '---'}
                </td>
                <td className="px-4 py-2">
                  <span className="text-xs text-text-secondary">{scan.funding_regime}</span>
                </td>
                <td className="px-4 py-2">
                  <span className={`text-xs font-semibold ${
                    scan.combined_signal === 'LONG' ? 'text-green-400' :
                    scan.combined_signal === 'SHORT' ? 'text-red-400' :
                    scan.combined_signal === 'RANGE_BOUND' ? 'text-yellow-400' :
                    'text-text-muted'
                  }`}>
                    {scan.combined_signal} {scan.combined_confidence && `(${scan.combined_confidence})`}
                  </span>
                </td>
                <td className="px-4 py-2 text-xs text-text-secondary">{scan.oracle_advice || 'Advisory'}</td>
                <td className="px-4 py-2">
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    scan.outcome?.includes('TRADED') ? 'bg-fuchsia-900/50 text-fuchsia-300' :
                    scan.outcome?.includes('SAR') ? 'bg-violet-900/50 text-violet-300' :
                    scan.outcome?.includes('ERROR') ? 'bg-red-900/50 text-red-300' :
                    scan.outcome?.includes('LOSS_STREAK') ? 'bg-orange-900/50 text-orange-300' :
                    'bg-gray-800 text-text-muted'
                  }`}>
                    {scan.outcome}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ==============================================================================
// HISTORY TAB
// ==============================================================================

function HistoryTab({ data }: { data: any[] }) {
  const trades = data || []

  if (trades.length === 0) {
    return <div className="text-text-muted text-center py-12">No closed trades yet</div>
  }

  return (
    <div className="bg-background-card rounded-xl border border-gray-800 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="text-left px-4 py-3 text-text-muted font-medium">Closed</th>
              <th className="text-left px-4 py-3 text-text-muted font-medium">Side</th>
              <th className="text-left px-4 py-3 text-text-muted font-medium">Entry</th>
              <th className="text-left px-4 py-3 text-text-muted font-medium">Exit</th>
              <th className="text-left px-4 py-3 text-text-muted font-medium">P&L</th>
              <th className="text-left px-4 py-3 text-text-muted font-medium">Reason</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {trades.map((trade: any, i: number) => (
              <tr key={i} className="hover:bg-background-hover">
                <td className="px-4 py-2 text-text-secondary font-mono text-xs">
                  {trade.close_time ? new Date(trade.close_time).toLocaleString() : '---'}
                </td>
                <td className="px-4 py-2">
                  <span className={`text-xs font-bold ${
                    trade.side === 'long' ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {trade.side?.toUpperCase()}
                  </span>
                </td>
                <td className="px-4 py-2 text-text-primary font-mono">${trade.entry_price?.toFixed(2)}</td>
                <td className="px-4 py-2 text-text-primary font-mono">${trade.close_price?.toFixed(2) || '---'}</td>
                <td className="px-4 py-2">
                  <span className={`font-mono font-semibold ${
                    (trade.realized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                  }`}>
                    ${trade.realized_pnl?.toFixed(2) || '0.00'}
                  </span>
                </td>
                <td className="px-4 py-2">
                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                    trade.close_reason?.includes('SAR') ? 'bg-violet-900/30 text-violet-300' :
                    trade.close_reason?.includes('TRAIL') ? 'bg-fuchsia-900/30 text-fuchsia-300' :
                    trade.close_reason?.includes('PROFIT') ? 'bg-green-900/30 text-green-300' :
                    trade.close_reason?.includes('EMERGENCY') ? 'bg-red-900/30 text-red-300' :
                    'text-text-secondary'
                  }`}>
                    {trade.close_reason}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ==============================================================================
// GEX MAPPING TAB
// ==============================================================================

function GexMappingTab({ data }: { data: any }) {
  if (!data) return <div className="text-text-muted text-center py-12">Loading mapping data...</div>

  return (
    <div className="space-y-6">
      <div className="bg-background-card rounded-xl p-6 border border-gray-800">
        <h3 className="text-lg font-semibold text-text-primary mb-2">{data.title}</h3>
        <p className="text-text-secondary text-sm mb-6">{data.description}</p>

        <div className="space-y-4">
          {data.mappings?.map((m: any, i: number) => (
            <div key={i} className="border border-gray-700 rounded-lg p-4">
              <div className="flex items-start justify-between mb-2">
                <div>
                  <span className="text-xs text-text-muted">Equity GEX:</span>
                  <p className="text-text-secondary font-mono text-sm">{m.gex_concept}</p>
                </div>
                <div className="text-right">
                  <span className="text-xs text-fuchsia-400">Crypto Equivalent:</span>
                  <p className="text-fuchsia-300 font-semibold text-sm">{m.crypto_equivalent}</p>
                </div>
              </div>
              <p className="text-text-secondary text-xs mt-2">{m.explanation}</p>
              {m.data_source && (
                <p className="text-text-muted text-xs mt-1">Source: {m.data_source}</p>
              )}
            </div>
          ))}
        </div>
      </div>

      {data.trade_instrument && (
        <div className="bg-background-card rounded-xl p-6 border border-fuchsia-600/30">
          <h4 className="text-sm font-semibold text-fuchsia-400 mb-3">Trade Instrument</h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            {Object.entries(data.trade_instrument).map(([key, val]: [string, any]) => (
              <div key={key}>
                <span className="text-text-muted text-xs">{key.replace(/_/g, ' ')}</span>
                <p className="text-text-primary font-mono">{val}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
