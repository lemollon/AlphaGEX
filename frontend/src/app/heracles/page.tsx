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
  XCircle,
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
  useHERACLESMLTrainingDataStats,
  useHERACLESMLStatus,
  useHERACLESMLFeatureImportance,
  useHERACLESMLApprovalStatus,
  useHERACLESABTestStatus,
  useHERACLESABTestResults,
  trainHERACLESML,
  approveHERACLESML,
  revokeHERACLESML,
  rejectHERACLESML,
  enableHERACLESABTest,
  disableHERACLESABTest,
  useHERACLESSignals,
  useUnifiedBotSummary,
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
  const [isTraining, setIsTraining] = useState(false)
  const [trainingResult, setTrainingResult] = useState<any>(null)
  const [isApproving, setIsApproving] = useState(false)
  const [isRevoking, setIsRevoking] = useState(false)  // BUG FIX: Separate state for revoke to avoid race condition
  const [isRejecting, setIsRejecting] = useState(false)
  const [isTogglingABTest, setIsTogglingABTest] = useState(false)

  // Get days for current timeframe
  const selectedTimeframe = EQUITY_TIMEFRAMES.find(t => t.id === equityTimeframe) || EQUITY_TIMEFRAMES[0]
  const isIntraday = equityTimeframe === 'intraday'

  // Data hooks
  const { data: statusData, error: statusError, isLoading: statusLoading, mutate: refreshStatus } = useHERACLESStatus()
  const { data: closedTradesData } = useHERACLESClosedTrades(1000)
  const { data: equityCurveData } = useHERACLESEquityCurve(selectedTimeframe.days || 30)
  const { data: intradayEquityData } = useHERACLESIntradayEquity()
  const { data: scanActivityData, mutate: mutateScanActivity } = useHERACLESScanActivity(1000)
  const { data: mlTrainingData } = useHERACLESMLTrainingData()
  const { data: mlTrainingDataStats, mutate: refreshTrainingStats } = useHERACLESMLTrainingDataStats()
  const { data: mlStatus, mutate: refreshMLStatus } = useHERACLESMLStatus()
  const { data: featureImportance, mutate: refreshFeatureImportance } = useHERACLESMLFeatureImportance()
  const { data: mlApprovalStatus, mutate: refreshApprovalStatus } = useHERACLESMLApprovalStatus()
  const { data: abTestStatus, mutate: refreshABTestStatus } = useHERACLESABTestStatus()
  const { data: abTestResults, mutate: refreshABTestResults } = useHERACLESABTestResults()
  const { data: signalsData } = useHERACLESSignals(50)

  // ML Training handler
  const handleTrainML = async () => {
    setIsTraining(true)
    setTrainingResult(null)
    try {
      const result = await trainHERACLESML(50)
      setTrainingResult(result)
      if (result.success) {
        // Refresh ML status, feature importance, training stats, and approval status
        refreshMLStatus()
        refreshFeatureImportance()
        refreshApprovalStatus()
        refreshTrainingStats()
      }
    } catch (error: any) {
      setTrainingResult({ success: false, error: error.message || 'Training failed' })
    } finally {
      setIsTraining(false)
    }
  }

  // ML Approval handler
  const handleApproveML = async () => {
    setIsApproving(true)
    try {
      const result = await approveHERACLESML()
      if (result.success) {
        refreshApprovalStatus()
        refreshMLStatus()
      }
    } catch (error) {
      console.error('Failed to approve ML:', error)
    } finally {
      setIsApproving(false)
    }
  }

  // ML Revoke handler - Uses separate isRevoking state to avoid race condition with Approve
  const handleRevokeML = async () => {
    setIsRevoking(true)
    try {
      const result = await revokeHERACLESML()
      if (result.success) {
        refreshApprovalStatus()
        refreshMLStatus()
      }
    } catch (error) {
      console.error('Failed to revoke ML:', error)
    } finally {
      setIsRevoking(false)
    }
  }

  // ML Reject handler (completely discard newly trained model)
  const handleRejectML = async () => {
    setIsRejecting(true)
    try {
      const result = await rejectHERACLESML()
      if (result.success) {
        setTrainingResult(null)  // Clear training result UI
        refreshApprovalStatus()
        refreshMLStatus()
      }
    } catch (error) {
      console.error('Failed to reject ML:', error)
    } finally {
      setIsRejecting(false)
    }
  }

  // A/B Test toggle handler
  const handleToggleABTest = async () => {
    setIsTogglingABTest(true)
    try {
      if (abTestStatus?.ab_test_enabled) {
        const result = await disableHERACLESABTest()
        if (result.success) {
          refreshABTestStatus()
          refreshABTestResults()
        }
      } else {
        const result = await enableHERACLESABTest()
        if (result.success) {
          refreshABTestStatus()
          refreshABTestResults()
        }
      }
    } catch (error) {
      console.error('Failed to toggle A/B test:', error)
    } finally {
      setIsTogglingABTest(false)
    }
  }

  // Unified metrics for consistent data (single source of truth)
  const { data: unifiedData, mutate: refreshUnified } = useUnifiedBotSummary('HERACLES')
  const unifiedMetrics = unifiedData?.data

  // Extract data
  const status = statusData || {}
  const positions = status?.positions?.positions || []
  const performance = status?.performance || {}

  // SINGLE SOURCE OF TRUTH for starting capital
  // Priority: unified metrics -> paper account -> config -> default
  const startingCapital = unifiedMetrics?.starting_capital ??
    status?.paper_account?.starting_capital ??
    status?.config?.capital ??
    100000
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

          {/* ML Status Banner - Shows when ML is active or awaiting approval */}
          {mlStatus?.model_trained && (
            <div className={`rounded-lg p-4 border ${
              mlApprovalStatus?.ml_approved
                ? 'bg-green-900/30 border-green-500/50'
                : 'bg-yellow-900/30 border-yellow-500/50'
            }`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-3 h-3 rounded-full ${
                    mlApprovalStatus?.ml_approved ? 'bg-green-500 animate-pulse' : 'bg-yellow-500'
                  }`} />
                  <div>
                    <h3 className={`font-semibold ${
                      mlApprovalStatus?.ml_approved ? 'text-green-400' : 'text-yellow-400'
                    }`}>
                      {mlApprovalStatus?.ml_approved
                        ? 'ML Model ACTIVE - Using ML Predictions'
                        : 'ML Model Trained - Awaiting Approval'}
                    </h3>
                    <p className="text-gray-300 text-sm">
                      {mlApprovalStatus?.ml_approved
                        ? `Win probability calculated via XGBoost ML (${((mlStatus.accuracy || 0) * 100).toFixed(1)}% accuracy)`
                        : `Currently using Bayesian fallback. Approve to use ML (${((mlStatus.accuracy || 0) * 100).toFixed(1)}% accuracy)`}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                    mlApprovalStatus?.probability_source === 'ML'
                      ? 'bg-green-600/50 text-green-200'
                      : 'bg-blue-600/50 text-blue-200'
                  }`}>
                    Source: {mlApprovalStatus?.probability_source || 'BAYESIAN'}
                  </span>
                  {!mlApprovalStatus?.ml_approved && (
                    <button
                      onClick={handleApproveML}
                      disabled={isApproving}
                      className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg font-semibold transition-colors disabled:opacity-50"
                    >
                      {isApproving ? (
                        <>
                          <RefreshCw className="h-4 w-4 animate-spin" />
                          Approving...
                        </>
                      ) : (
                        <>
                          <CheckCircle className="h-4 w-4" />
                          Approve ML
                        </>
                      )}
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

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
                      ${startingCapital.toLocaleString()}
                    </div>
                  </div>
                  <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-4">
                    <div className="text-sm text-gray-400">Current Balance</div>
                    <div className={`text-2xl font-bold mt-1 ${
                      (paperAccount.current_balance || 0) >= startingCapital
                        ? 'text-green-400' : 'text-red-400'
                    }`}>
                      ${(paperAccount?.current_balance || startingCapital).toLocaleString()}
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
                    Equity Curve ({selectedTimeframe.label})
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
                          y={startingCapital}
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
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold flex items-center gap-2">
                    <GraduationCap className="h-5 w-5 text-yellow-400" />
                    ML Training Data Status
                  </h3>
                  {/* Train Button */}
                  <button
                    onClick={handleTrainML}
                    disabled={isTraining || !mlTrainingDataStats?.ready_for_ml_training}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
                      isTraining
                        ? 'bg-yellow-600/50 text-yellow-300 cursor-wait'
                        : mlTrainingDataStats?.ready_for_ml_training
                          ? 'bg-yellow-600 hover:bg-yellow-500 text-black'
                          : 'bg-gray-700 text-gray-400 cursor-not-allowed'
                    }`}
                  >
                    {isTraining ? (
                      <>
                        <RefreshCw className="h-4 w-4 animate-spin" />
                        Training...
                      </>
                    ) : (
                      <>
                        <GraduationCap className="h-4 w-4" />
                        Train Model
                      </>
                    )}
                  </button>
                </div>

                {/* Parameter Version Warning Banner */}
                {mlTrainingDataStats && (
                  <div className={`mb-4 p-4 rounded-lg border ${
                    mlTrainingDataStats.ready_for_ml_training
                      ? 'bg-green-900/20 border-green-500/50'
                      : 'bg-yellow-900/20 border-yellow-500/50'
                  }`}>
                    <div className="flex items-center gap-2 mb-2">
                      <AlertTriangle className={`h-5 w-5 ${
                        mlTrainingDataStats.ready_for_ml_training ? 'text-green-400' : 'text-yellow-400'
                      }`} />
                      <span className={`font-semibold ${
                        mlTrainingDataStats.ready_for_ml_training ? 'text-green-400' : 'text-yellow-400'
                      }`}>
                        Parameter Version {mlTrainingDataStats.parameter_version}
                      </span>
                    </div>
                    <p className="text-sm text-gray-300 mb-3">
                      {mlTrainingDataStats.parameter_description}
                    </p>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div className="bg-red-900/30 rounded-lg p-3 border border-red-500/30">
                        <div className="text-red-400 font-medium">Old Parameters (Garbage Data)</div>
                        <div className="text-xl font-bold text-red-300 mt-1">
                          {mlTrainingDataStats.old_parameter_trades?.count || 0} trades
                        </div>
                        <div className="text-xs text-gray-400">
                          Win Rate: {mlTrainingDataStats.old_parameter_trades?.win_rate || 0}%
                          <span className="text-red-400 ml-2">(asymmetric risk/reward)</span>
                        </div>
                      </div>
                      <div className="bg-green-900/30 rounded-lg p-3 border border-green-500/30">
                        <div className="text-green-400 font-medium">New Parameters (Quality Data)</div>
                        <div className="text-xl font-bold text-green-300 mt-1">
                          {mlTrainingDataStats.new_parameter_trades?.count || 0} trades
                        </div>
                        <div className="text-xs text-gray-400">
                          {mlTrainingDataStats.ready_for_ml_training ? (
                            <span className="text-green-400">Ready for ML training!</span>
                          ) : (
                            <span className="text-yellow-400">
                              Need {mlTrainingDataStats.trades_needed_for_ml} more trades
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <p className="text-xs text-gray-500 mt-2">
                      ML will ONLY train on new parameter trades. Old data had big losses/small wins.
                    </p>
                  </div>
                )}

                {/* Training Data Stats */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-gray-900/50 rounded-lg p-4">
                    <div className="text-sm text-gray-400">New Param Trades</div>
                    <div className="text-2xl font-bold text-white mt-1">
                      {mlTrainingDataStats?.new_parameter_trades?.count || 0}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">Need 50 for ML</div>
                  </div>
                  <div className="bg-gray-900/50 rounded-lg p-4">
                    <div className="text-sm text-gray-400">Win/Loss (New)</div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-green-400 text-lg font-bold">{mlTrainingDataStats?.new_parameter_trades?.wins || 0}W</span>
                      <span className="text-gray-500">/</span>
                      <span className="text-red-400 text-lg font-bold">{mlTrainingDataStats?.new_parameter_trades?.losses || 0}L</span>
                    </div>
                  </div>
                  <div className="bg-gray-900/50 rounded-lg p-4">
                    <div className="text-sm text-gray-400">New Win Rate</div>
                    <div className="text-2xl font-bold text-yellow-400 mt-1">
                      {(mlTrainingDataStats?.new_parameter_trades?.win_rate || 0).toFixed(1)}%
                    </div>
                  </div>
                  <div className="bg-gray-900/50 rounded-lg p-4">
                    <div className="text-sm text-gray-400">Ready for Training</div>
                    <div className={`text-xl font-bold mt-1 flex items-center gap-2 ${
                      mlTrainingDataStats?.ready_for_ml_training ? 'text-green-400' : 'text-yellow-400'
                    }`}>
                      {mlTrainingDataStats?.ready_for_ml_training ? (
                        <><CheckCircle className="h-5 w-5" /> Yes</>
                      ) : (
                        <><RefreshCw className="h-5 w-5" /> {mlTrainingDataStats?.trades_needed_for_ml || 50} more</>
                      )}
                    </div>
                  </div>
                </div>

                {/* Training Results (shown after training) */}
                {trainingResult && (
                  <div className={`mt-4 p-4 rounded-lg border ${
                    trainingResult.success
                      ? 'bg-green-900/20 border-green-500/50'
                      : 'bg-red-900/20 border-red-500/50'
                  }`}>
                    {trainingResult.success ? (
                      <div className="space-y-4">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2 text-green-400 font-semibold">
                            <CheckCircle className="h-5 w-5" />
                            Model Trained Successfully
                          </div>
                          {/* Approve/Reject Buttons after training */}
                          {!mlApprovalStatus?.ml_approved && (
                            <div className="flex items-center gap-2">
                              <button
                                onClick={handleRejectML}
                                disabled={isRejecting || isApproving}
                                className="flex items-center gap-2 px-4 py-2 bg-red-600/80 hover:bg-red-600 text-white rounded-lg font-semibold transition-colors disabled:opacity-50"
                              >
                                {isRejecting ? (
                                  <>
                                    <RefreshCw className="h-4 w-4 animate-spin" />
                                    Rejecting...
                                  </>
                                ) : (
                                  <>
                                    <XCircle className="h-4 w-4" />
                                    Reject Model
                                  </>
                                )}
                              </button>
                              <button
                                onClick={handleApproveML}
                                disabled={isApproving || isRejecting}
                                className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg font-semibold transition-colors disabled:opacity-50 animate-pulse"
                              >
                                {isApproving ? (
                                  <>
                                    <RefreshCw className="h-4 w-4 animate-spin" />
                                    Approving...
                                  </>
                                ) : (
                                  <>
                                    <CheckCircle className="h-4 w-4" />
                                    Approve & Activate ML
                                  </>
                                )}
                              </button>
                            </div>
                          )}
                        </div>

                        {/* New vs Previous Comparison */}
                        {trainingResult.comparison && (
                          <div className={`p-3 rounded-lg border ${
                            trainingResult.comparison.is_improvement
                              ? 'bg-green-900/30 border-green-600/50'
                              : trainingResult.comparison.regressions?.length > 0
                                ? 'bg-yellow-900/30 border-yellow-600/50'
                                : 'bg-blue-900/30 border-blue-600/50'
                          }`}>
                            <div className="flex items-center gap-2 mb-2">
                              {trainingResult.comparison.is_improvement ? (
                                <TrendingUp className="h-4 w-4 text-green-400" />
                              ) : trainingResult.comparison.regressions?.length > 0 ? (
                                <AlertTriangle className="h-4 w-4 text-yellow-400" />
                              ) : (
                                <Eye className="h-4 w-4 text-blue-400" />
                              )}
                              <span className={`font-medium ${
                                trainingResult.comparison.is_improvement ? 'text-green-400' :
                                trainingResult.comparison.regressions?.length > 0 ? 'text-yellow-400' : 'text-blue-400'
                              }`}>
                                {trainingResult.comparison.recommendation}
                              </span>
                            </div>

                            {/* Improvement Reasons */}
                            {trainingResult.comparison.improvement_reasons?.length > 0 && (
                              <ul className="text-sm text-gray-300 space-y-1 ml-6">
                                {trainingResult.comparison.improvement_reasons.map((reason: string, i: number) => (
                                  <li key={i} className="flex items-center gap-2">
                                    <CheckCircle className="h-3 w-3 text-green-500" />
                                    {reason}
                                  </li>
                                ))}
                              </ul>
                            )}

                            {/* Regressions */}
                            {trainingResult.comparison.regressions?.length > 0 && (
                              <ul className="text-sm text-yellow-300 space-y-1 ml-6 mt-2">
                                {trainingResult.comparison.regressions.map((regression: string, i: number) => (
                                  <li key={i} className="flex items-center gap-2">
                                    <AlertTriangle className="h-3 w-3 text-yellow-500" />
                                    {regression}
                                  </li>
                                ))}
                              </ul>
                            )}

                            {/* Previous vs New comparison table */}
                            {trainingResult.comparison.previous && (
                              <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                                <div className="text-gray-500">Metric</div>
                                <div className="text-gray-500">Previous</div>
                                <div className="text-gray-500">New</div>

                                <div className="text-gray-400">Accuracy</div>
                                <div className="text-gray-300">{(trainingResult.comparison.previous.accuracy * 100).toFixed(1)}%</div>
                                <div className={trainingResult.comparison.changes?.accuracy > 0 ? 'text-green-400' : trainingResult.comparison.changes?.accuracy < 0 ? 'text-red-400' : 'text-white'}>
                                  {((trainingResult.metrics?.accuracy || 0) * 100).toFixed(1)}%
                                  {trainingResult.comparison.changes?.accuracy !== 0 && (
                                    <span className="ml-1">
                                      ({trainingResult.comparison.changes?.accuracy > 0 ? '+' : ''}{(trainingResult.comparison.changes?.accuracy * 100).toFixed(1)}%)
                                    </span>
                                  )}
                                </div>

                                <div className="text-gray-400">AUC-ROC</div>
                                <div className="text-gray-300">{trainingResult.comparison.previous.auc_roc.toFixed(3)}</div>
                                <div className={trainingResult.comparison.changes?.auc_roc > 0 ? 'text-green-400' : trainingResult.comparison.changes?.auc_roc < 0 ? 'text-red-400' : 'text-white'}>
                                  {(trainingResult.metrics?.auc_roc || 0).toFixed(3)}
                                  {trainingResult.comparison.changes?.auc_roc !== 0 && (
                                    <span className="ml-1">
                                      ({trainingResult.comparison.changes?.auc_roc > 0 ? '+' : ''}{trainingResult.comparison.changes?.auc_roc.toFixed(3)})
                                    </span>
                                  )}
                                </div>

                                <div className="text-gray-400">Samples</div>
                                <div className="text-gray-300">{trainingResult.comparison.previous.training_samples}</div>
                                <div className="text-white">
                                  {trainingResult.training_samples}
                                  {trainingResult.comparison.changes?.samples_added > 0 && (
                                    <span className="ml-1 text-green-400">(+{trainingResult.comparison.changes?.samples_added})</span>
                                  )}
                                </div>
                              </div>
                            )}
                          </div>
                        )}

                        {/* Core metrics */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                          <div>
                            <span className="text-gray-400">Accuracy:</span>
                            <span className="ml-2 text-white font-mono">{((trainingResult.metrics?.accuracy || 0) * 100).toFixed(1)}%</span>
                          </div>
                          <div>
                            <span className="text-gray-400">Precision:</span>
                            <span className="ml-2 text-white font-mono">{((trainingResult.metrics?.precision || 0) * 100).toFixed(1)}%</span>
                          </div>
                          <div>
                            <span className="text-gray-400">Recall:</span>
                            <span className="ml-2 text-white font-mono">{((trainingResult.metrics?.recall || 0) * 100).toFixed(1)}%</span>
                          </div>
                          <div>
                            <span className="text-gray-400">F1 Score:</span>
                            <span className="ml-2 text-white font-mono">{((trainingResult.metrics?.f1_score || 0) * 100).toFixed(1)}%</span>
                          </div>
                        </div>
                        <div className="text-xs text-gray-400">
                          Trained on {trainingResult.training_samples} samples - Model saved to database
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 text-red-400">
                        <AlertTriangle className="h-5 w-5" />
                        Training Failed: {trainingResult.error}
                      </div>
                    )}
                  </div>
                )}

                {/* Model Status */}
                {mlStatus && (
                  <div className="mt-4 p-4 bg-gray-900/30 rounded-lg border border-gray-700">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className={`w-3 h-3 rounded-full ${
                          mlApprovalStatus?.ml_approved && mlStatus.model_trained
                            ? 'bg-green-500'
                            : mlStatus.model_trained
                              ? 'bg-yellow-500'
                              : 'bg-gray-500'
                        }`} />
                        <span className="font-medium">
                          {mlApprovalStatus?.ml_approved && mlStatus.model_trained
                            ? 'ML Model Active'
                            : mlStatus.model_trained
                              ? 'ML Model Trained (Awaiting Approval)'
                              : 'ML Model Not Trained'}
                        </span>
                      </div>
                      {mlStatus.model_trained && mlStatus.last_trained && (
                        <span className="text-sm text-gray-400">
                          Last trained: {new Date(mlStatus.last_trained).toLocaleString()}
                        </span>
                      )}
                    </div>
                    {mlStatus.model_trained && (
                      <>
                        <div className="mt-3 grid grid-cols-3 gap-4 text-sm">
                          <div>
                            <span className="text-gray-400">Model Accuracy:</span>
                            <span className="ml-2 text-yellow-400 font-mono">{((mlStatus.accuracy || 0) * 100).toFixed(1)}%</span>
                          </div>
                          <div>
                            <span className="text-gray-400">Training Samples:</span>
                            <span className="ml-2 text-white font-mono">{mlStatus.training_samples || 0}</span>
                          </div>
                          <div>
                            <span className="text-gray-400">Probability Source:</span>
                            <span className={`ml-2 font-mono ${mlApprovalStatus?.probability_source === 'ML' ? 'text-green-400' : 'text-blue-400'}`}>
                              {mlApprovalStatus?.probability_source || 'BAYESIAN'}
                            </span>
                          </div>
                        </div>

                        {/* ML Approval Controls */}
                        <div className="mt-4 flex items-center gap-4">
                          {mlApprovalStatus?.ml_approved ? (
                            <button
                              onClick={handleRevokeML}
                              disabled={isRevoking}
                              className="flex items-center gap-2 px-4 py-2 bg-red-600/80 hover:bg-red-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
                            >
                              {isRevoking ? (
                                <>
                                  <RefreshCw className="h-4 w-4 animate-spin" />
                                  Revoking...
                                </>
                              ) : (
                                <>
                                  <AlertTriangle className="h-4 w-4" />
                                  Revoke ML Approval
                                </>
                              )}
                            </button>
                          ) : (
                            <div className="flex items-center gap-2">
                              <button
                                onClick={handleRejectML}
                                disabled={isRejecting || isApproving}
                                className="flex items-center gap-2 px-4 py-2 bg-red-600/80 hover:bg-red-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
                              >
                                {isRejecting ? (
                                  <>
                                    <RefreshCw className="h-4 w-4 animate-spin" />
                                    Rejecting...
                                  </>
                                ) : (
                                  <>
                                    <XCircle className="h-4 w-4" />
                                    Reject Model
                                  </>
                                )}
                              </button>
                              <button
                                onClick={handleApproveML}
                                disabled={isApproving || isRejecting}
                                className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
                              >
                                {isApproving ? (
                                  <>
                                    <RefreshCw className="h-4 w-4 animate-spin" />
                                    Approving...
                                  </>
                                ) : (
                                  <>
                                    <CheckCircle className="h-4 w-4" />
                                    Approve ML Model
                                  </>
                                )}
                              </button>
                            </div>
                          )}
                          <span className="text-sm text-gray-400">
                            {mlApprovalStatus?.ml_approved
                              ? 'ML predictions are being used for win probability'
                              : 'Using Bayesian fallback - approve to use ML predictions'}
                          </span>
                        </div>
                      </>
                    )}
                  </div>
                )}

                {/* A/B Test for Dynamic Stops */}
                <div className="mt-4 p-4 bg-gray-900/30 rounded-lg border border-gray-700">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <PieChart className="h-5 w-5 text-purple-400" />
                      <span className="font-medium">A/B Test: Fixed vs Dynamic Stops</span>
                    </div>
                    <button
                      onClick={handleToggleABTest}
                      disabled={isTogglingABTest}
                      className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
                        abTestStatus?.ab_test_enabled
                          ? 'bg-purple-600 hover:bg-purple-500 text-white'
                          : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                      } disabled:opacity-50`}
                    >
                      {isTogglingABTest ? (
                        <>
                          <RefreshCw className="h-4 w-4 animate-spin" />
                          {abTestStatus?.ab_test_enabled ? 'Disabling...' : 'Enabling...'}
                        </>
                      ) : abTestStatus?.ab_test_enabled ? (
                        'Disable A/B Test'
                      ) : (
                        'Enable A/B Test'
                      )}
                    </button>
                  </div>
                  <p className="text-sm text-gray-400 mb-3">
                    {abTestStatus?.ab_test_enabled
                      ? '50% of trades use FIXED stops, 50% use DYNAMIC stops. Need 100+ trades for comparison.'
                      : 'When enabled, randomly assigns trades to FIXED or DYNAMIC stops for comparison.'}
                  </p>

                  {/* A/B Test Results */}
                  {abTestResults?.results && (
                    <div className="mt-3 space-y-3">
                      <div className="grid grid-cols-2 gap-4">
                        {/* Fixed Results */}
                        <div className="p-3 bg-gray-800/50 rounded-lg">
                          <div className="text-sm font-medium text-blue-400 mb-2">FIXED Stops</div>
                          <div className="grid grid-cols-2 gap-2 text-sm">
                            <div>
                              <span className="text-gray-400">Trades:</span>
                              <span className="ml-1 text-white">{abTestResults.results.fixed.trades}</span>
                            </div>
                            <div>
                              <span className="text-gray-400">Win Rate:</span>
                              <span className="ml-1 text-white">{abTestResults.results.fixed.win_rate.toFixed(1)}%</span>
                            </div>
                            <div>
                              <span className="text-gray-400">Total P&L:</span>
                              <span className={`ml-1 ${abTestResults.results.fixed.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                ${abTestResults.results.fixed.total_pnl.toFixed(2)}
                              </span>
                            </div>
                            <div>
                              <span className="text-gray-400">Avg P&L:</span>
                              <span className={`ml-1 ${abTestResults.results.fixed.avg_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                ${abTestResults.results.fixed.avg_pnl.toFixed(2)}
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Dynamic Results */}
                        <div className="p-3 bg-gray-800/50 rounded-lg">
                          <div className="text-sm font-medium text-purple-400 mb-2">DYNAMIC Stops</div>
                          <div className="grid grid-cols-2 gap-2 text-sm">
                            <div>
                              <span className="text-gray-400">Trades:</span>
                              <span className="ml-1 text-white">{abTestResults.results.dynamic.trades}</span>
                            </div>
                            <div>
                              <span className="text-gray-400">Win Rate:</span>
                              <span className="ml-1 text-white">{abTestResults.results.dynamic.win_rate.toFixed(1)}%</span>
                            </div>
                            <div>
                              <span className="text-gray-400">Total P&L:</span>
                              <span className={`ml-1 ${abTestResults.results.dynamic.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                ${abTestResults.results.dynamic.total_pnl.toFixed(2)}
                              </span>
                            </div>
                            <div>
                              <span className="text-gray-400">Avg P&L:</span>
                              <span className={`ml-1 ${abTestResults.results.dynamic.avg_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                ${abTestResults.results.dynamic.avg_pnl.toFixed(2)}
                              </span>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Summary */}
                      {abTestResults.results.summary && (
                        <div className={`p-3 rounded-lg ${
                          abTestResults.results.summary.recommended_stop === 'FIXED'
                            ? 'bg-blue-900/30 border border-blue-700'
                            : abTestResults.results.summary.recommended_stop === 'DYNAMIC'
                              ? 'bg-purple-900/30 border border-purple-700'
                              : 'bg-gray-800/50'
                        }`}>
                          <div className="text-sm">
                            <span className="text-gray-400">Status:</span>
                            <span className="ml-2 text-white">{abTestResults.results.summary.message}</span>
                          </div>
                          {abTestResults.results.summary.recommended_stop && abTestResults.results.summary.recommended_stop !== 'INCONCLUSIVE' && (
                            <div className="mt-1 text-sm">
                              <span className="text-gray-400">Recommendation:</span>
                              <span className={`ml-2 font-medium ${
                                abTestResults.results.summary.recommended_stop === 'FIXED' ? 'text-blue-400' : 'text-purple-400'
                              }`}>
                                Use {abTestResults.results.summary.recommended_stop} stops
                              </span>
                              <span className="ml-2 text-gray-500">
                                (Confidence: {abTestResults.results.summary.confidence})
                              </span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Feature Importance (shown when model is trained) */}
              {featureImportance && featureImportance.features && featureImportance.features.length > 0 && (
                <div className="bg-[#0a0a0a] rounded-lg border border-gray-800 p-6">
                  <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                    <PieChart className="h-5 w-5 text-yellow-400" />
                    ML Feature Importance
                  </h3>
                  <div className="space-y-2">
                    {featureImportance.features.slice(0, 10).map((feature: { name: string; importance: number }, idx: number) => (
                      <div key={feature.name} className="flex items-center gap-3">
                        <span className="text-xs text-gray-500 w-4">{idx + 1}</span>
                        <span className="text-sm text-gray-300 w-48 truncate" title={feature.name}>
                          {feature.name.replace(/_/g, ' ')}
                        </span>
                        <div className="flex-1 h-4 bg-gray-800 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-yellow-600 to-yellow-400 rounded-full"
                            style={{ width: `${(feature.importance * 100)}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-400 w-12 text-right font-mono">
                          {(feature.importance * 100).toFixed(1)}%
                        </span>
                      </div>
                    ))}
                  </div>
                  <p className="text-xs text-gray-500 mt-4">
                    Features ranked by their contribution to predicting trade outcomes. Higher importance = more predictive power.
                  </p>
                </div>
              )}
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
                  <ConfigItem label="Capital" value={`$${startingCapital.toLocaleString()}`} />
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
