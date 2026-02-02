'use client'

import { useState } from 'react'
import {
  Activity,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Clock,
  Zap,
  PieChart,
  Settings,
  AlertTriangle,
  CheckCircle,
  Eye,
  GraduationCap,
  RefreshCw,
  Wallet,
  History,
  LayoutDashboard,
} from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import Navigation from '@/components/Navigation'
import { useSidebarPadding } from '@/hooks/useSidebarPadding'
import {
  BotPageHeader,
  StatCard,
  LoadingState,
  BOT_BRANDS,
} from '@/components/trader'
import {
  useHERACLESStatus,
  useHERACLESClosedTrades,
  useHERACLESEquityCurve,
  useHERACLESIntradayEquity,
  useHERACLESScanActivity,
  useHERACLESMLTrainingData,
  useHERACLESSignals,
} from '@/lib/hooks/useMarketData'

// ==============================================================================
// TIMEFRAME OPTIONS
// ==============================================================================

const EQUITY_TIMEFRAMES = [
  { id: 'intraday', label: 'Today', days: 0 },
  { id: '7d', label: '7D', days: 7 },
  { id: '14d', label: '14D', days: 14 },
  { id: '30d', label: '30D', days: 30 },
  { id: '90d', label: '90D', days: 90 },
]

// ==============================================================================
// TABS
// ==============================================================================

const HERACLES_TABS = [
  { id: 'portfolio' as const, label: 'Portfolio', icon: Wallet, description: 'Live P&L and positions' },
  { id: 'overview' as const, label: 'Overview', icon: LayoutDashboard, description: 'Bot status and metrics' },
  { id: 'activity' as const, label: 'Activity', icon: Activity, description: 'Scans and signals' },
  { id: 'history' as const, label: 'History', icon: History, description: 'Closed trades' },
  { id: 'config' as const, label: 'Config', icon: Settings, description: 'Settings' },
]
type HERACLESTabId = typeof HERACLES_TABS[number]['id']

// ==============================================================================
// MAIN COMPONENT
// ==============================================================================

export default function HERACLESPage() {
  const sidebarPadding = useSidebarPadding()
  const [activeTab, setActiveTab] = useState<HERACLESTabId>('portfolio')
  const [equityTimeframe, setEquityTimeframe] = useState('intraday')

  // Get days for current timeframe
  const selectedTimeframe = EQUITY_TIMEFRAMES.find(t => t.id === equityTimeframe) || EQUITY_TIMEFRAMES[0]
  const isIntraday = equityTimeframe === 'intraday'

  // Data hooks
  const { data: statusData, error: statusError, isLoading: statusLoading, mutate: refreshStatus } = useHERACLESStatus()
  const { data: closedTradesData } = useHERACLESClosedTrades(50)
  const { data: equityCurveData } = useHERACLESEquityCurve(selectedTimeframe.days || 30)
  const { data: intradayEquityData } = useHERACLESIntradayEquity()
  const { data: scanActivityData, mutate: mutateScanActivity } = useHERACLESScanActivity(100)
  const { data: mlTrainingData } = useHERACLESMLTrainingData()
  const { data: signalsData } = useHERACLESSignals(50)

  // Extract data
  const status = statusData || {}
  const positions = status?.positions?.positions || []
  const performance = status?.performance || {}
  const config = status?.config || {}
  const winTracker = status?.win_tracker || {}
  const paperAccount = status?.paper_account || null
  const closedTrades = closedTradesData?.trades || []
  const dailyEquityCurve = equityCurveData?.equity_curve || []
  const intradayEquityCurve = intradayEquityData?.equity_curve || []
  const scans = scanActivityData?.scans || []
  const scanSummary = scanActivityData?.summary || {}
  const signals = signalsData?.signals || []

  // Brand
  const brand = BOT_BRANDS.HERACLES

  // Select appropriate equity curve based on timeframe
  const equityCurve = isIntraday ? intradayEquityCurve : dailyEquityCurve

  // Format equity curve data for chart
  const equityChartData = equityCurve.map((point: any) => ({
    date: isIntraday ? point.snapshot_time || point.timestamp : point.date,
    equity: point.equity,
    pnl: isIntraday ? point.unrealized_pnl : point.cumulative_pnl,
    return: point.return_pct || 0,
  }))

  // Loading state
  if (statusLoading) {
    return (
      <>
        <Navigation />
        <div className="flex items-center justify-center h-screen">
          <LoadingState message="Loading HERACLES..." />
        </div>
      </>
    )
  }

  // Error state
  if (statusError) {
    return (
      <>
        <Navigation />
        <main className={`min-h-screen bg-black text-white px-4 pb-4 pt-24 transition-all duration-300 ${sidebarPadding}`}>
          <div className="max-w-7xl mx-auto">
            <div className="bg-red-900/50 border border-red-500 rounded-lg p-6">
              <h2 className="text-xl font-bold text-red-400 flex items-center gap-2">
                <AlertTriangle className="h-6 w-6" />
                HERACLES Not Available
              </h2>
              <p className="text-red-300 mt-2">
                The HERACLES futures bot is not currently available. Check backend deployment.
              </p>
            </div>
          </div>
        </main>
      </>
    )
  }

  return (
    <>
      <Navigation />
      <main className={`min-h-screen bg-black text-white px-4 pb-4 md:px-6 md:pb-6 pt-24 transition-all duration-300 ${sidebarPadding}`}>
        <div className="max-w-7xl mx-auto space-y-6">

          {/* Header - Branded */}
          <BotPageHeader
            botName="HERACLES"
            isActive={status?.market_open || false}
            onRefresh={() => refreshStatus()}
            isRefreshing={statusLoading}
            scanIntervalMinutes={1}
          />

          {/* Paper Trading Info Banner */}
          <div className={`bg-yellow-900/30 border border-yellow-500/50 rounded-lg p-4`}>
            <div className="flex items-start gap-3">
              <Wallet className="w-5 h-5 text-yellow-400 mt-0.5 flex-shrink-0" />
              <div className="flex-1">
                <h3 className="text-yellow-400 font-semibold">Paper Trading Mode - MES Futures Scalping</h3>
                <p className="text-gray-300 text-sm mt-1">
                  HERACLES is paper trading MES futures with $100k simulated capital. Uses GEX signals for mean reversion (positive gamma) and momentum (negative gamma).
                </p>
                <p className="text-gray-400 text-xs mt-2">
                  24/5 trading: Sun 5pm - Fri 4pm CT with 4-5pm daily maintenance break.
                </p>
              </div>
            </div>
          </div>

          {/* Tab Navigation */}
          <div className="flex gap-2 border-b border-gray-800 overflow-x-auto pb-px">
            {HERACLES_TABS.map((tab) => {
              const Icon = tab.icon
              const isActive = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-all ${
                    isActive
                      ? 'border-yellow-500 text-yellow-400'
                      : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-600'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {tab.label}
                </button>
              )
            })}
          </div>

          {/* Tab Content */}
          {activeTab === 'portfolio' && (
            <div className="space-y-6">
              {/* Paper Account Summary */}
              {paperAccount && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-4">
                    <div className="text-sm text-gray-400">Starting Capital</div>
                    <div className="text-2xl font-bold text-white mt-1">
                      ${(paperAccount.starting_capital || 100000).toLocaleString()}
                    </div>
                  </div>
                  <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-4">
                    <div className="text-sm text-gray-400">Current Balance</div>
                    <div className={`text-2xl font-bold mt-1 ${
                      (paperAccount.current_balance || 0) >= (paperAccount.starting_capital || 100000)
                        ? 'text-green-400' : 'text-red-400'
                    }`}>
                      ${(paperAccount.current_balance || 100000).toLocaleString()}
                    </div>
                  </div>
                  <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-4">
                    <div className="text-sm text-gray-400">Cumulative P&L</div>
                    <div className={`text-2xl font-bold mt-1 ${
                      (paperAccount.cumulative_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      ${(paperAccount.cumulative_pnl || 0) >= 0 ? '+' : ''}{(paperAccount.cumulative_pnl || 0).toFixed(2)}
                    </div>
                  </div>
                  <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-4">
                    <div className="text-sm text-gray-400">Return</div>
                    <div className={`text-2xl font-bold mt-1 ${
                      (paperAccount.return_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {(paperAccount.return_pct || 0) >= 0 ? '+' : ''}{(paperAccount.return_pct || 0).toFixed(2)}%
                    </div>
                  </div>
                </div>
              )}

              {/* Open Positions */}
              <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-6">
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <Activity className="h-5 w-5 text-yellow-400" />
                  Open Positions ({positions.length})
                </h3>

                {positions.length === 0 ? (
                  <div className="text-center py-8">
                    <Zap className="h-12 w-12 text-gray-600 mx-auto mb-4" />
                    <p className="text-gray-400">No open positions</p>
                    <p className="text-gray-500 text-sm mt-2">
                      HERACLES will open positions when GEX signals meet criteria
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {positions.map((position: any) => (
                      <div key={position.position_id} className="bg-gray-900/50 rounded-lg p-4 border border-gray-800">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-4">
                            <div className={`p-2 rounded-lg ${
                              position.direction === 'LONG'
                                ? 'bg-green-900/50 text-green-400'
                                : 'bg-red-900/50 text-red-400'
                            }`}>
                              {position.direction === 'LONG'
                                ? <TrendingUp className="h-5 w-5" />
                                : <TrendingDown className="h-5 w-5" />
                              }
                            </div>
                            <div>
                              <div className="font-semibold">{position.symbol}</div>
                              <div className="text-sm text-gray-400">
                                {position.contracts} contracts @ {position.entry_price?.toFixed(2)}
                              </div>
                            </div>
                          </div>
                          <div className={`px-3 py-1 rounded-full text-sm ${
                            position.gamma_regime === 'POSITIVE'
                              ? 'bg-blue-900/50 text-blue-400'
                              : 'bg-purple-900/50 text-purple-400'
                          }`}>
                            {position.gamma_regime} GAMMA
                          </div>
                        </div>
                        <div className="grid grid-cols-4 gap-4 mt-3 text-sm text-gray-400">
                          <div>Stop: <span className="text-white font-mono">{position.current_stop?.toFixed(2)}</span></div>
                          <div>Trailing: <span className={position.trailing_active ? 'text-green-400' : 'text-gray-500'}>{position.trailing_active ? 'Active' : 'Inactive'}</span></div>
                          <div>Opened: <span className="text-white">{new Date(position.open_time).toLocaleTimeString()}</span></div>
                          <div>ID: <span className="text-white font-mono text-xs">{position.position_id?.slice(0, 8)}</span></div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Equity Curve */}
              <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold flex items-center gap-2">
                    <TrendingUp className="h-5 w-5 text-yellow-400" />
                    Equity Curve
                  </h3>
                  {/* Timeframe Selector */}
                  <div className="flex gap-1">
                    {EQUITY_TIMEFRAMES.map((tf) => (
                      <button
                        key={tf.id}
                        onClick={() => setEquityTimeframe(tf.id)}
                        className={`px-3 py-1 text-xs rounded transition-colors ${
                          equityTimeframe === tf.id
                            ? 'bg-yellow-500 text-black font-semibold'
                            : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                        }`}
                      >
                        {tf.label}
                      </button>
                    ))}
                  </div>
                </div>
                {equityChartData.length > 0 ? (
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={equityChartData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis
                          dataKey="date"
                          stroke="#9CA3AF"
                          tick={{ fill: '#9CA3AF', fontSize: 11 }}
                          tickFormatter={(value) => {
                            if (!value) return ''
                            const date = new Date(value)
                            if (isIntraday) {
                              // Show time for intraday (e.g., "9:30 AM")
                              return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })
                            }
                            // Show date for daily (e.g., "Jan 15")
                            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                          }}
                        />
                        <YAxis
                          stroke="#9CA3AF"
                          tick={{ fill: '#9CA3AF', fontSize: 12 }}
                          tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
                          domain={['dataMin - 1000', 'dataMax + 1000']}
                        />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: '#1F2937',
                            border: '1px solid #374151',
                            borderRadius: '8px',
                          }}
                          labelFormatter={(value) => {
                            if (!value) return ''
                            const date = new Date(value)
                            if (isIntraday) {
                              return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })
                            }
                            return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
                          }}
                          formatter={(value: number, name: string) => [
                            `$${value.toLocaleString()}`,
                            name === 'equity' ? 'Equity' : 'P&L'
                          ]}
                        />
                        <ReferenceLine
                          y={paperAccount?.starting_capital || 100000}
                          stroke="#EF4444"
                          strokeDasharray="5 5"
                        />
                        <Line
                          type="monotone"
                          dataKey="equity"
                          stroke={brand.hexPrimary}
                          strokeWidth={2}
                          dot={equityChartData.length < 20}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="h-64 flex items-center justify-center text-gray-500">
                    <div className="text-center">
                      <Clock className="h-8 w-8 mx-auto mb-2 opacity-50" />
                      <p>No equity data for {selectedTimeframe.label}</p>
                      <p className="text-xs mt-1">Data will appear after trades are executed</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'overview' && (
            <div className="space-y-6">
              {/* Stats Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <StatCard
                  label="Total P&L"
                  value={`$${(performance.total_pnl || 0).toFixed(2)}`}
                  trend={(performance.total_pnl || 0) >= 0 ? 'up' : 'down'}
                />
                <StatCard
                  label="Win Rate"
                  value={`${(performance.win_rate || 0).toFixed(1)}%`}
                  trend={(performance.win_rate || 0) >= 50 ? 'up' : 'down'}
                />
                <StatCard
                  label="Total Trades"
                  value={performance.total_trades || 0}
                />
                <StatCard
                  label="Open Positions"
                  value={positions.length}
                />
              </div>

              {/* Win Probability Tracker */}
              <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-6">
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <PieChart className="h-5 w-5 text-yellow-400" />
                  Bayesian Win Probability Tracker
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="bg-gray-900/50 rounded-lg p-4">
                    <div className="text-sm text-gray-400">Overall Win Probability</div>
                    <div className="text-3xl font-bold text-yellow-400 mt-1">
                      {((winTracker.win_probability || 0.5) * 100).toFixed(1)}%
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      Based on {winTracker.total_trades || 0} trades
                    </div>
                  </div>
                  <div className="bg-gray-900/50 rounded-lg p-4">
                    <div className="text-sm text-gray-400">Positive Gamma (Mean Reversion)</div>
                    <div className="flex items-center gap-4 mt-2">
                      <span className="text-green-400">W: {winTracker.positive_gamma_wins || 0}</span>
                      <span className="text-red-400">L: {winTracker.positive_gamma_losses || 0}</span>
                    </div>
                  </div>
                  <div className="bg-gray-900/50 rounded-lg p-4">
                    <div className="text-sm text-gray-400">Negative Gamma (Momentum)</div>
                    <div className="flex items-center gap-4 mt-2">
                      <span className="text-green-400">W: {winTracker.negative_gamma_wins || 0}</span>
                      <span className="text-red-400">L: {winTracker.negative_gamma_losses || 0}</span>
                    </div>
                  </div>
                </div>
                {winTracker.should_use_ml && (
                  <div className="mt-4 p-3 bg-green-900/30 border border-green-500/30 rounded-lg">
                    <span className="text-green-400 flex items-center gap-2">
                      <CheckCircle className="h-4 w-4" />
                      Ready for ML model training (50+ trades collected)
                    </span>
                  </div>
                )}
              </div>

              {/* ML Training Status */}
              <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-6">
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <GraduationCap className="h-5 w-5 text-yellow-400" />
                  ML Training Data Status
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-gray-900/50 rounded-lg p-4">
                    <div className="text-sm text-gray-400">Training Samples</div>
                    <div className="text-2xl font-bold text-white mt-1">
                      {mlTrainingData?.total_samples || 0}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">Need 50 for ML</div>
                  </div>
                  <div className="bg-gray-900/50 rounded-lg p-4">
                    <div className="text-sm text-gray-400">Win/Loss Samples</div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-green-400 text-lg font-bold">{mlTrainingData?.wins || 0}W</span>
                      <span className="text-gray-500">/</span>
                      <span className="text-red-400 text-lg font-bold">{mlTrainingData?.losses || 0}L</span>
                    </div>
                  </div>
                  <div className="bg-gray-900/50 rounded-lg p-4">
                    <div className="text-sm text-gray-400">Sample Win Rate</div>
                    <div className="text-2xl font-bold text-yellow-400 mt-1">
                      {(mlTrainingData?.win_rate || 0).toFixed(1)}%
                    </div>
                  </div>
                  <div className="bg-gray-900/50 rounded-lg p-4">
                    <div className="text-sm text-gray-400">Ready for Training</div>
                    <div className={`text-xl font-bold mt-1 flex items-center gap-2 ${
                      mlTrainingData?.ready_for_training ? 'text-green-400' : 'text-yellow-400'
                    }`}>
                      {mlTrainingData?.ready_for_training ? (
                        <><CheckCircle className="h-5 w-5" /> Yes</>
                      ) : (
                        <><RefreshCw className="h-5 w-5" /> {50 - (mlTrainingData?.total_samples || 0)} more</>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'activity' && (
            <div className="space-y-6">
              {/* Scan Summary */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-4 text-center">
                  <div className="text-sm text-gray-400">Total Scans</div>
                  <div className="text-2xl font-bold mt-1">{scanActivityData?.count || 0}</div>
                </div>
                <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-4 text-center">
                  <div className="text-sm text-gray-400">Traded</div>
                  <div className="text-2xl font-bold mt-1 text-green-400">{scanSummary.traded || 0}</div>
                </div>
                <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-4 text-center">
                  <div className="text-sm text-gray-400">No Trade</div>
                  <div className="text-2xl font-bold mt-1 text-yellow-400">{scanSummary.no_trade || 0}</div>
                </div>
                <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-4 text-center">
                  <div className="text-sm text-gray-400">Skipped</div>
                  <div className="text-2xl font-bold mt-1 text-gray-400">{scanSummary.skip || 0}</div>
                </div>
                <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-4 text-center">
                  <div className="text-sm text-gray-400">Trade Rate</div>
                  <div className="text-2xl font-bold mt-1 text-yellow-400">{(scanSummary.trade_rate_pct || 0).toFixed(1)}%</div>
                </div>
              </div>

              {/* Scan Activity Table */}
              <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 overflow-hidden">
                <div className="p-4 border-b border-gray-800 flex items-center justify-between">
                  <h3 className="font-semibold flex items-center gap-2">
                    <Eye className="h-5 w-5 text-yellow-400" />
                    Scan Activity (ML Training Data)
                  </h3>
                  <button
                    onClick={() => mutateScanActivity()}
                    className="flex items-center gap-2 px-3 py-1.5 bg-yellow-600 rounded-lg hover:bg-yellow-700 transition-colors text-sm"
                  >
                    <RefreshCw className="h-4 w-4" />
                    Refresh
                  </button>
                </div>

                {scans.length === 0 ? (
                  <div className="p-8 text-center">
                    <Eye className="h-12 w-12 text-gray-600 mx-auto mb-4" />
                    <p className="text-gray-400">No scan activity yet</p>
                    <p className="text-gray-500 text-sm mt-2">Scans will appear here once HERACLES starts running</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-900">
                        <tr>
                          <th className="px-4 py-3 text-left text-gray-400">Time</th>
                          <th className="px-4 py-3 text-left text-gray-400">Outcome</th>
                          <th className="px-4 py-3 text-left text-gray-400">Regime</th>
                          <th className="px-4 py-3 text-right text-gray-400">Price</th>
                          <th className="px-4 py-3 text-left text-gray-400">Signal</th>
                          <th className="px-4 py-3 text-right text-gray-400">Win Prob</th>
                          <th className="px-4 py-3 text-left text-gray-400">Decision</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-800">
                        {scans.slice(0, 50).map((scan: any) => (
                          <tr key={scan.scan_id} className="hover:bg-gray-900/50">
                            <td className="px-4 py-3 font-mono text-xs">
                              {new Date(scan.scan_time).toLocaleTimeString()}
                            </td>
                            <td className="px-4 py-3">
                              <span className={`px-2 py-1 rounded text-xs ${
                                scan.outcome === 'TRADED' ? 'bg-green-900/50 text-green-400' :
                                scan.outcome === 'NO_TRADE' ? 'bg-yellow-900/50 text-yellow-400' :
                                scan.outcome === 'SKIP' ? 'bg-gray-700 text-gray-400' :
                                'bg-red-900/50 text-red-400'
                              }`}>
                                {scan.outcome}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              {scan.gamma_regime && (
                                <span className={`px-2 py-1 rounded text-xs ${
                                  scan.gamma_regime === 'POSITIVE' ? 'bg-blue-900/50 text-blue-400' :
                                  scan.gamma_regime === 'NEGATIVE' ? 'bg-purple-900/50 text-purple-400' :
                                  'bg-gray-700 text-gray-400'
                                }`}>
                                  {scan.gamma_regime}
                                </span>
                              )}
                            </td>
                            <td className="px-4 py-3 text-right font-mono">
                              {scan.underlying_price?.toFixed(2) || '-'}
                            </td>
                            <td className="px-4 py-3">
                              {scan.signal_direction && (
                                <span className={`px-2 py-1 rounded text-xs ${
                                  scan.signal_direction === 'LONG' ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'
                                }`}>
                                  {scan.signal_direction}
                                </span>
                              )}
                            </td>
                            <td className="px-4 py-3 text-right">
                              {scan.signal_win_probability ? `${(scan.signal_win_probability * 100).toFixed(0)}%` : '-'}
                            </td>
                            <td className="px-4 py-3 text-gray-400 truncate max-w-xs" title={scan.decision_summary}>
                              {scan.decision_summary || scan.skip_reason || '-'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'history' && (
            <div className="space-y-6">
              <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 overflow-hidden">
                <div className="p-4 border-b border-gray-800">
                  <h3 className="font-semibold flex items-center gap-2">
                    <History className="h-5 w-5 text-yellow-400" />
                    Closed Trades ({closedTrades.length})
                  </h3>
                </div>

                {closedTrades.length === 0 ? (
                  <div className="p-8 text-center">
                    <Clock className="h-12 w-12 text-gray-600 mx-auto mb-4" />
                    <p className="text-gray-400">No trade history yet</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead className="bg-gray-900">
                        <tr>
                          <th className="px-4 py-3 text-left text-sm text-gray-400">Time</th>
                          <th className="px-4 py-3 text-left text-sm text-gray-400">Direction</th>
                          <th className="px-4 py-3 text-left text-sm text-gray-400">Regime</th>
                          <th className="px-4 py-3 text-right text-sm text-gray-400">Entry</th>
                          <th className="px-4 py-3 text-right text-sm text-gray-400">Exit</th>
                          <th className="px-4 py-3 text-right text-sm text-gray-400">P&L</th>
                          <th className="px-4 py-3 text-left text-sm text-gray-400">Reason</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-800">
                        {closedTrades.map((trade: any) => (
                          <tr key={trade.position_id} className="hover:bg-gray-900/50">
                            <td className="px-4 py-3 text-sm">
                              {new Date(trade.close_time).toLocaleString()}
                            </td>
                            <td className="px-4 py-3">
                              <span className={`px-2 py-1 rounded text-xs ${
                                trade.direction === 'LONG' ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'
                              }`}>
                                {trade.direction}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <span className={`px-2 py-1 rounded text-xs ${
                                trade.gamma_regime === 'POSITIVE' ? 'bg-blue-900/50 text-blue-400' : 'bg-purple-900/50 text-purple-400'
                              }`}>
                                {trade.gamma_regime}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-right font-mono">{trade.entry_price?.toFixed(2)}</td>
                            <td className="px-4 py-3 text-right font-mono">{trade.exit_price?.toFixed(2)}</td>
                            <td className={`px-4 py-3 text-right font-mono ${
                              trade.realized_pnl >= 0 ? 'text-green-400' : 'text-red-400'
                            }`}>
                              ${trade.realized_pnl?.toFixed(2)}
                            </td>
                            <td className="px-4 py-3 text-sm text-gray-400">{trade.close_reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'config' && (
            <div className="space-y-6">
              <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-6">
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <Settings className="h-5 w-5 text-yellow-400" />
                  HERACLES Configuration
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <ConfigItem label="Symbol" value={status?.symbol || '/MESH6'} />
                  <ConfigItem label="Capital" value={`$${(paperAccount?.starting_capital || config.capital || 100000).toLocaleString()}`} />
                  <ConfigItem label="Risk/Trade" value={`${config.risk_per_trade_pct || 1}%`} />
                  <ConfigItem label="Max Contracts" value={config.max_contracts || 5} />
                  <ConfigItem label="Initial Stop" value={`${config.initial_stop_points || 3} pts`} />
                  <ConfigItem label="Breakeven At" value={`+${config.breakeven_activation_points || 2} pts`} />
                  <ConfigItem label="Trail Distance" value={`${config.trailing_stop_points || 1} pt`} />
                  <ConfigItem label="Max Positions" value={config.max_open_positions || 2} />
                </div>
              </div>

              <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-6">
                <h3 className="text-lg font-semibold mb-4">MES Futures Specifications</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div className="bg-gray-900/50 rounded-lg p-3">
                    <div className="text-gray-400">Point Value</div>
                    <div className="font-mono mt-1">$5.00/point</div>
                  </div>
                  <div className="bg-gray-900/50 rounded-lg p-3">
                    <div className="text-gray-400">Tick Size</div>
                    <div className="font-mono mt-1">0.25 points</div>
                  </div>
                  <div className="bg-gray-900/50 rounded-lg p-3">
                    <div className="text-gray-400">Tick Value</div>
                    <div className="font-mono mt-1">$1.25/tick</div>
                  </div>
                  <div className="bg-gray-900/50 rounded-lg p-3">
                    <div className="text-gray-400">Day Margin</div>
                    <div className="font-mono mt-1">~$1,500</div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </>
  )
}

// ==============================================================================
// HELPER COMPONENTS
// ==============================================================================

function ConfigItem({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-gray-900/50 rounded-lg p-3">
      <div className="text-xs text-gray-400">{label}</div>
      <div className="font-mono text-sm mt-1">{value}</div>
    </div>
  )
}
