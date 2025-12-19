'use client'

import { useState, useEffect } from 'react'
import { Sword, TrendingUp, TrendingDown, Activity, DollarSign, Target, CheckCircle, Clock, RefreshCw, BarChart3, ChevronDown, ChevronUp, Eye, Brain, Zap, Server, Play, AlertTriangle } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import Navigation from '@/components/Navigation'
import DecisionLogViewer from '@/components/trader/DecisionLogViewer'
import { apiClient } from '@/lib/api'

interface ARESStatus {
  mode: string
  capital: number
  total_pnl: number
  trade_count: number
  win_rate: number
  open_positions: number
  closed_positions: number
  traded_today: boolean
  in_trading_window: boolean
  current_time: string
  is_active: boolean
  high_water_mark: number
  sandbox_connected?: boolean
  paper_mode_type?: 'sandbox' | 'simulated'
  config: {
    risk_per_trade: number
    spread_width: number
    sd_multiplier: number
    ticker: string
  }
}

interface IronCondorPosition {
  position_id: string
  open_date: string
  expiration: string
  put_long_strike: number
  put_short_strike: number
  call_short_strike: number
  call_long_strike: number
  total_credit: number
  max_loss: number
  contracts: number
  underlying_at_entry: number
  vix_at_entry: number
  status: string
}

interface EquityPoint {
  date: string
  equity: number
  pnl: number
  daily_pnl: number
  return_pct: number
}

interface Performance {
  total_trades: number
  closed_trades: number
  open_positions: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  total_pnl: number
  avg_pnl_per_trade: number
  best_trade: number
  worst_trade: number
  current_capital: number
  return_pct: number
  high_water_mark: number
  max_drawdown_pct: number
}

interface MarketData {
  ticker: string
  underlying_price: number
  vix: number
  expected_move: number
  timestamp: string
  source: string
}

interface GEXData {
  spot_price: number
  call_wall: number
  put_wall: number
  zero_gamma: number
  regime: string
  gex_value: number
  timestamp: string
}

interface OracleRecommendation {
  advice: string
  win_probability: number
  confidence: number
  reasoning: string
  top_factors: [string, number][]
}

interface MLStatus {
  model_trained: boolean
  model_version: string
  last_prediction?: {
    advice: string
    probability: number
  }
}

interface TradierAccountStatus {
  connected: boolean
  account_type: string
  buying_power: number
  cash: number
  total_equity: number
  pending_orders: number
  open_positions: number
}

export default function ARESPage() {
  const [status, setStatus] = useState<ARESStatus | null>(null)
  const [positions, setPositions] = useState<IronCondorPosition[]>([])
  const [closedPositions, setClosedPositions] = useState<IronCondorPosition[]>([])
  const [equityData, setEquityData] = useState<EquityPoint[]>([])
  const [performance, setPerformance] = useState<Performance | null>(null)
  const [marketData, setMarketData] = useState<MarketData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date())
  const [activeTab, setActiveTab] = useState<'overview' | 'positions' | 'logs'>('overview')
  const [showClosedPositions, setShowClosedPositions] = useState(false)

  // AlphaGEX Analysis Data
  const [gexData, setGexData] = useState<GEXData | null>(null)
  const [oracleRec, setOracleRec] = useState<OracleRecommendation | null>(null)
  const [mlStatus, setMlStatus] = useState<MLStatus | null>(null)
  const [tradierStatus, setTradierStatus] = useState<TradierAccountStatus | null>(null)

  const fetchData = async () => {
    try {
      setLoading(true)
      setError(null)

      // Fetch ARES trading data
      const [statusRes, performanceRes, equityRes, positionsRes, marketRes] = await Promise.all([
        apiClient.getARESPageStatus().catch(() => ({ data: null })),
        apiClient.getARESPerformance().catch(() => ({ data: null })),
        apiClient.getARESEquityCurve(30).catch(() => ({ data: null })),
        apiClient.getARESPositions().catch(() => ({ data: null })),
        apiClient.getARESMarketData().catch(() => ({ data: null }))
      ])

      if (statusRes.data?.data) setStatus(statusRes.data.data)
      if (performanceRes.data?.data) setPerformance(performanceRes.data.data)
      if (equityRes.data?.data?.equity_curve) setEquityData(equityRes.data.data.equity_curve)
      if (positionsRes.data?.data?.open_positions) setPositions(positionsRes.data.data.open_positions)
      if (positionsRes.data?.data?.closed_positions) setClosedPositions(positionsRes.data.data.closed_positions)
      if (marketRes.data?.data) setMarketData(marketRes.data.data)

      // Fetch AlphaGEX analysis data
      const [gexRes, oracleRes, mlRes] = await Promise.all([
        apiClient.getGEX('SPX').catch(() => ({ data: null })),
        apiClient.getOracleStatus().catch(() => ({ data: null })),
        apiClient.getMLStatus().catch(() => ({ data: null }))
      ])

      if (gexRes.data?.data) {
        setGexData({
          spot_price: gexRes.data.data.spot_price,
          call_wall: gexRes.data.data.call_wall,
          put_wall: gexRes.data.data.put_wall,
          zero_gamma: gexRes.data.data.zero_gamma || gexRes.data.data.gex_flip,
          regime: gexRes.data.data.regime || 'UNKNOWN',
          gex_value: gexRes.data.data.net_gex || gexRes.data.data.gex_value || 0,
          timestamp: gexRes.data.data.timestamp || new Date().toISOString()
        })
      }

      if (oracleRes.data?.oracle) {
        const oracle = oracleRes.data.oracle
        // If there's a recent prediction, show it
        if (oracleRes.data?.last_prediction) {
          setOracleRec(oracleRes.data.last_prediction)
        }
      }

      if (mlRes.data) {
        setMlStatus({
          model_trained: mlRes.data.model_trained || false,
          model_version: mlRes.data.model_version || 'unknown',
          last_prediction: mlRes.data.last_prediction
        })
      }

      // Check Tradier sandbox status from ARES status
      if (statusRes.data?.data) {
        setTradierStatus({
          connected: statusRes.data.data.sandbox_connected || false,
          account_type: statusRes.data.data.paper_mode_type === 'sandbox' ? 'Tradier Sandbox' : 'Simulated',
          buying_power: statusRes.data.data.capital || 0,
          cash: statusRes.data.data.capital || 0,
          total_equity: statusRes.data.data.capital + (statusRes.data.data.total_pnl || 0),
          pending_orders: 0,
          open_positions: statusRes.data.data.open_positions || 0
        })
      }

      setLastUpdate(new Date())
    } catch (err) {
      setError('Failed to fetch ARES data')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [])

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(value)
  }

  const formatPercent = (value: number) => {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
  }

  return (
    <div className="min-h-screen bg-gray-900">
      <Navigation />
      <main className="lg:pl-64 pt-16 lg:pt-0">
        <div className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <Sword className="w-8 h-8 text-red-500" />
              <div>
                <h1 className="text-2xl font-bold text-white">ARES - Aggressive Iron Condor</h1>
                <p className="text-gray-400">Targeting 10% Monthly Returns via Daily SPX 0DTE Iron Condors</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                  status?.mode === 'live' ? 'bg-green-900 text-green-300' : 'bg-yellow-900 text-yellow-300'
                }`}>
                  {status?.mode?.toUpperCase() || 'PAPER'}
                </span>
                {status?.mode === 'paper' && (
                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                    status?.sandbox_connected
                      ? 'bg-blue-900 text-blue-300'
                      : 'bg-purple-900 text-purple-300'
                  }`}>
                    {status?.sandbox_connected ? 'SANDBOX' : 'SIMULATED'}
                  </span>
                )}
              </div>
              <button
                onClick={fetchData}
                className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>
          </div>

          {error && (
            <div className="mb-6 p-4 bg-red-900/50 border border-red-500 rounded-lg text-red-300">
              {error}
            </div>
          )}

          {/* Tab Navigation */}
          <div className="flex gap-2 mb-6 border-b border-gray-700">
            {(['overview', 'positions', 'logs'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 text-sm font-medium capitalize transition-colors ${
                  activeTab === tab
                    ? 'text-red-400 border-b-2 border-red-400'
                    : 'text-gray-400 hover:text-gray-300'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Overview Tab */}
          {activeTab === 'overview' && (
            <>
              {/* Section 1: AlphaGEX Analysis */}
              <div className="mb-8">
                <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2 border-b border-gray-700 pb-2">
                  <Zap className="w-5 h-5 text-yellow-500" />
                  AlphaGEX Analysis
                  <span className="text-xs text-gray-500 ml-2">System Recommendations</span>
                </h2>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {/* GEX Analysis */}
                  <div className="bg-gradient-to-br from-yellow-900/20 to-gray-800 rounded-lg p-4 border border-yellow-700/50">
                    <div className="flex items-center justify-between mb-3">
                      <h4 className="text-sm font-medium text-yellow-400 flex items-center gap-2">
                        <Activity className="w-4 h-4" />
                        GEX Regime
                      </h4>
                      <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                        gexData?.regime === 'POSITIVE' ? 'bg-green-900 text-green-300' :
                        gexData?.regime === 'NEGATIVE' ? 'bg-red-900 text-red-300' :
                        'bg-gray-700 text-gray-300'
                      }`}>
                        {gexData?.regime || 'UNKNOWN'}
                      </span>
                    </div>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-400">Call Wall</span>
                        <span className="text-green-400 font-mono">{gexData?.call_wall?.toLocaleString() || '--'}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Put Wall</span>
                        <span className="text-red-400 font-mono">{gexData?.put_wall?.toLocaleString() || '--'}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Zero Gamma</span>
                        <span className="text-purple-400 font-mono">{gexData?.zero_gamma?.toLocaleString() || '--'}</span>
                      </div>
                    </div>
                  </div>

                  {/* ORACLE Recommendation */}
                  <div className="bg-gradient-to-br from-purple-900/20 to-gray-800 rounded-lg p-4 border border-purple-700/50">
                    <div className="flex items-center justify-between mb-3">
                      <h4 className="text-sm font-medium text-purple-400 flex items-center gap-2">
                        <Eye className="w-4 h-4" />
                        ORACLE Advice
                      </h4>
                      <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                        oracleRec?.advice === 'TRADE_FULL' ? 'bg-green-900 text-green-300' :
                        oracleRec?.advice === 'TRADE_REDUCED' ? 'bg-yellow-900 text-yellow-300' :
                        oracleRec?.advice === 'SKIP' ? 'bg-red-900 text-red-300' :
                        'bg-gray-700 text-gray-300'
                      }`}>
                        {oracleRec?.advice || 'NO DATA'}
                      </span>
                    </div>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-400">Win Probability</span>
                        <span className="text-white">{oracleRec?.win_probability ? `${(oracleRec.win_probability * 100).toFixed(1)}%` : '--'}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Confidence</span>
                        <span className="text-white">{oracleRec?.confidence ? `${oracleRec.confidence.toFixed(1)}%` : '--'}</span>
                      </div>
                      {oracleRec?.reasoning && (
                        <p className="text-xs text-gray-500 mt-2 line-clamp-2">{oracleRec.reasoning}</p>
                      )}
                    </div>
                  </div>

                  {/* ML Model Status */}
                  <div className="bg-gradient-to-br from-blue-900/20 to-gray-800 rounded-lg p-4 border border-blue-700/50">
                    <div className="flex items-center justify-between mb-3">
                      <h4 className="text-sm font-medium text-blue-400 flex items-center gap-2">
                        <Brain className="w-4 h-4" />
                        PROMETHEUS ML
                      </h4>
                      <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                        mlStatus?.model_trained ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-300'
                      }`}>
                        {mlStatus?.model_trained ? 'TRAINED' : 'NOT READY'}
                      </span>
                    </div>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-400">Model Version</span>
                        <span className="text-white font-mono text-xs">{mlStatus?.model_version || '--'}</span>
                      </div>
                      {mlStatus?.last_prediction && (
                        <>
                          <div className="flex justify-between">
                            <span className="text-gray-400">Last Advice</span>
                            <span className="text-white">{mlStatus.last_prediction.advice}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-400">Probability</span>
                            <span className="text-white">{(mlStatus.last_prediction.probability * 100).toFixed(1)}%</span>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Section 2: Paper Trading (Simulated) */}
              <div className="mb-8">
                <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2 border-b border-gray-700 pb-2">
                  <Play className="w-5 h-5 text-purple-500" />
                  Paper Trading (Simulated)
                  <span className="text-xs text-gray-500 ml-2">Internal Simulation</span>
                  {!tradierStatus?.connected && (
                    <span className="ml-auto px-2 py-0.5 rounded text-xs bg-purple-900 text-purple-300">ACTIVE</span>
                  )}
                </h2>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400">Status</span>
                      {status?.in_trading_window ? (
                        <CheckCircle className="w-5 h-5 text-green-500" />
                      ) : (
                        <Clock className="w-5 h-5 text-gray-500" />
                      )}
                    </div>
                    <div className="mt-2">
                      <span className="text-lg font-bold text-white">
                        {status?.in_trading_window ? 'Active' : 'Waiting'}
                      </span>
                      <p className="text-xs text-gray-500 mt-1">
                        {status?.traded_today ? 'Traded today' : 'No trade today'}
                      </p>
                    </div>
                  </div>

                  <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400">Simulated Capital</span>
                      <DollarSign className="w-5 h-5 text-purple-500" />
                    </div>
                    <div className="mt-2">
                      <span className="text-2xl font-bold text-white">
                        {formatCurrency(performance?.current_capital || status?.capital || 200000)}
                      </span>
                    </div>
                  </div>

                  <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400">Simulated P&L</span>
                      {(performance?.total_pnl || 0) >= 0 ? (
                        <TrendingUp className="w-5 h-5 text-green-500" />
                      ) : (
                        <TrendingDown className="w-5 h-5 text-red-500" />
                      )}
                    </div>
                    <div className="mt-2">
                      <span className={`text-2xl font-bold ${
                        (performance?.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                      }`}>
                        {formatCurrency(performance?.total_pnl || 0)}
                      </span>
                      <span className="text-sm text-gray-500 ml-2">
                        ({formatPercent(performance?.return_pct || 0)})
                      </span>
                    </div>
                  </div>

                  <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400">Win Rate</span>
                      <Target className="w-5 h-5 text-purple-500" />
                    </div>
                    <div className="mt-2">
                      <span className="text-2xl font-bold text-white">
                        {(performance?.win_rate || 0).toFixed(1)}%
                      </span>
                      <span className="text-sm text-gray-500 ml-2">
                        ({performance?.closed_trades || 0} trades)
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Section 3: Tradier Paper Trading (Sandbox) */}
              <div className="mb-8">
                <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2 border-b border-gray-700 pb-2">
                  <Server className="w-5 h-5 text-blue-500" />
                  Tradier Paper Trading (Sandbox)
                  <span className="text-xs text-gray-500 ml-2">Real Execution on Paper Account</span>
                  {tradierStatus?.connected ? (
                    <span className="ml-auto px-2 py-0.5 rounded text-xs bg-green-900 text-green-300">CONNECTED</span>
                  ) : (
                    <span className="ml-auto px-2 py-0.5 rounded text-xs bg-red-900 text-red-300">DISCONNECTED</span>
                  )}
                </h2>

                {tradierStatus?.connected ? (
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div className="bg-gradient-to-br from-blue-900/20 to-gray-800 rounded-lg p-4 border border-blue-700/50">
                      <div className="flex items-center justify-between">
                        <span className="text-gray-400">Account Type</span>
                        <Server className="w-5 h-5 text-blue-500" />
                      </div>
                      <div className="mt-2">
                        <span className="text-lg font-bold text-blue-300">{tradierStatus.account_type}</span>
                      </div>
                    </div>

                    <div className="bg-gradient-to-br from-blue-900/20 to-gray-800 rounded-lg p-4 border border-blue-700/50">
                      <div className="flex items-center justify-between">
                        <span className="text-gray-400">Buying Power</span>
                        <DollarSign className="w-5 h-5 text-blue-500" />
                      </div>
                      <div className="mt-2">
                        <span className="text-2xl font-bold text-white">
                          {formatCurrency(tradierStatus.buying_power)}
                        </span>
                      </div>
                    </div>

                    <div className="bg-gradient-to-br from-blue-900/20 to-gray-800 rounded-lg p-4 border border-blue-700/50">
                      <div className="flex items-center justify-between">
                        <span className="text-gray-400">Total Equity</span>
                        <TrendingUp className="w-5 h-5 text-blue-500" />
                      </div>
                      <div className="mt-2">
                        <span className="text-2xl font-bold text-white">
                          {formatCurrency(tradierStatus.total_equity)}
                        </span>
                      </div>
                    </div>

                    <div className="bg-gradient-to-br from-blue-900/20 to-gray-800 rounded-lg p-4 border border-blue-700/50">
                      <div className="flex items-center justify-between">
                        <span className="text-gray-400">Open Positions</span>
                        <Activity className="w-5 h-5 text-blue-500" />
                      </div>
                      <div className="mt-2">
                        <span className="text-2xl font-bold text-white">{tradierStatus.open_positions}</span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="bg-gray-800/50 rounded-lg p-6 border border-gray-700 text-center">
                    <AlertTriangle className="w-12 h-12 text-yellow-500 mx-auto mb-3" />
                    <h4 className="text-white font-semibold mb-2">Tradier Sandbox Not Connected</h4>
                    <p className="text-gray-400 text-sm mb-4">
                      Paper trading is running in simulation mode. Connect Tradier sandbox for real paper execution.
                    </p>
                    <p className="text-xs text-gray-500">
                      Set TRADIER_ACCESS_TOKEN and enable sandbox mode to connect
                    </p>
                  </div>
                )}
              </div>

              {/* Market Data & Strategy Config */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
                <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                  <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                    <Activity className="w-5 h-5 text-blue-500" />
                    Live Market Data
                  </h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-400">SPX Price</span>
                      <span className="text-white font-mono">
                        {marketData?.underlying_price ? `$${marketData.underlying_price.toLocaleString()}` : '--'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">VIX</span>
                      <span className="text-white">{marketData?.vix?.toFixed(2) || '--'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Expected Move (1 SD)</span>
                      <span className="text-white">${marketData?.expected_move?.toFixed(2) || '--'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Data Source</span>
                      <span className="text-green-400 text-xs">{marketData?.source || 'Tradier Production'}</span>
                    </div>
                  </div>
                </div>

                <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                  <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                    <Sword className="w-5 h-5 text-red-500" />
                    Strategy Configuration
                  </h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-400">Ticker</span>
                      <span className="text-white font-mono">{status?.config?.ticker || 'SPX'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Spread Width</span>
                      <span className="text-white">${status?.config?.spread_width || 10}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Risk Per Trade</span>
                      <span className="text-white">{status?.config?.risk_per_trade || 10}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Strike Distance</span>
                      <span className="text-white">{status?.config?.sd_multiplier || 1} SD</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Monthly Target</span>
                      <span className="text-green-400">10%</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Equity Curve */}
              <div className="bg-gray-800 rounded-lg p-4 border border-gray-700 mb-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                    <BarChart3 className="w-5 h-5 text-blue-500" />
                    Equity Curve (30 Days)
                  </h3>
                  <div className="text-sm text-gray-400">
                    Max Drawdown: <span className="text-red-400">{formatPercent(-(performance?.max_drawdown_pct || 0))}</span>
                  </div>
                </div>
                <div className="h-64">
                  {equityData.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={equityData}>
                        <defs>
                          <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#EF4444" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#EF4444" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis dataKey="date" stroke="#9CA3AF" fontSize={12} />
                        <YAxis stroke="#9CA3AF" fontSize={12} tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
                        <Tooltip
                          contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                          labelStyle={{ color: '#9CA3AF' }}
                          formatter={(value: number) => [formatCurrency(value), 'Equity']}
                        />
                        <Area
                          type="monotone"
                          dataKey="equity"
                          stroke="#EF4444"
                          strokeWidth={2}
                          fill="url(#colorEquity)"
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex items-center justify-center h-full text-gray-500">
                      No equity data available yet - trades will appear after first Iron Condor
                    </div>
                  )}
                </div>
              </div>

              {/* Performance Metrics */}
              <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <h3 className="text-lg font-semibold text-white mb-4">Performance Metrics</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div>
                    <span className="text-gray-400">Total Trades</span>
                    <p className="text-white text-lg font-bold">{performance?.total_trades || 0}</p>
                  </div>
                  <div>
                    <span className="text-gray-400">Winners / Losers</span>
                    <p className="text-white text-lg font-bold">
                      <span className="text-green-400">{performance?.winning_trades || 0}</span>
                      {' / '}
                      <span className="text-red-400">{performance?.losing_trades || 0}</span>
                    </p>
                  </div>
                  <div>
                    <span className="text-gray-400">Best Trade</span>
                    <p className="text-green-400 text-lg font-bold">{formatCurrency(performance?.best_trade || 0)}</p>
                  </div>
                  <div>
                    <span className="text-gray-400">Worst Trade</span>
                    <p className="text-red-400 text-lg font-bold">{formatCurrency(performance?.worst_trade || 0)}</p>
                  </div>
                </div>
              </div>
            </>
          )}

          {/* Positions Tab */}
          {activeTab === 'positions' && (
            <>
              {/* Open Positions */}
              <div className="bg-gray-800 rounded-lg p-4 border border-gray-700 mb-6">
                <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                  <Activity className="w-5 h-5 text-yellow-500" />
                  Open Iron Condor Positions ({positions.length})
                </h3>
                {positions.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-gray-400 border-b border-gray-700">
                          <th className="text-left py-2 px-3">Position ID</th>
                          <th className="text-left py-2 px-3">Opened</th>
                          <th className="text-left py-2 px-3">Expiration</th>
                          <th className="text-center py-2 px-3">Put Spread</th>
                          <th className="text-center py-2 px-3">Call Spread</th>
                          <th className="text-right py-2 px-3">Credit</th>
                          <th className="text-right py-2 px-3">Max Loss</th>
                          <th className="text-right py-2 px-3">Contracts</th>
                        </tr>
                      </thead>
                      <tbody>
                        {positions.map((pos) => (
                          <tr key={pos.position_id} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                            <td className="py-2 px-3 font-mono text-white">{pos.position_id}</td>
                            <td className="py-2 px-3 text-gray-300">{pos.open_date}</td>
                            <td className="py-2 px-3 text-gray-300">{pos.expiration}</td>
                            <td className="py-2 px-3 text-center">
                              <span className="text-red-400">{pos.put_long_strike}</span>
                              <span className="text-gray-500 mx-1">/</span>
                              <span className="text-red-300">{pos.put_short_strike}</span>
                            </td>
                            <td className="py-2 px-3 text-center">
                              <span className="text-green-300">{pos.call_short_strike}</span>
                              <span className="text-gray-500 mx-1">/</span>
                              <span className="text-green-400">{pos.call_long_strike}</span>
                            </td>
                            <td className="py-2 px-3 text-right text-green-400">
                              {formatCurrency(pos.total_credit * 100 * pos.contracts)}
                            </td>
                            <td className="py-2 px-3 text-right text-red-400">
                              {formatCurrency(pos.max_loss * 100 * pos.contracts)}
                            </td>
                            <td className="py-2 px-3 text-right text-white">{pos.contracts}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="text-center py-8 text-gray-500">
                    No open positions - next trade at 9:35 AM ET
                  </div>
                )}
              </div>

              {/* Closed Positions */}
              <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <button
                  onClick={() => setShowClosedPositions(!showClosedPositions)}
                  className="flex items-center justify-between w-full text-left"
                >
                  <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                    <BarChart3 className="w-5 h-5 text-gray-500" />
                    Closed Positions ({closedPositions.length})
                  </h3>
                  {showClosedPositions ? (
                    <ChevronUp className="w-5 h-5 text-gray-400" />
                  ) : (
                    <ChevronDown className="w-5 h-5 text-gray-400" />
                  )}
                </button>
                {showClosedPositions && closedPositions.length > 0 && (
                  <div className="overflow-x-auto mt-4">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-gray-400 border-b border-gray-700">
                          <th className="text-left py-2 px-3">Position ID</th>
                          <th className="text-left py-2 px-3">Opened</th>
                          <th className="text-left py-2 px-3">Closed</th>
                          <th className="text-center py-2 px-3">Spreads</th>
                          <th className="text-right py-2 px-3">P&L</th>
                          <th className="text-left py-2 px-3">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {closedPositions.map((pos) => (
                          <tr key={pos.position_id} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                            <td className="py-2 px-3 font-mono text-white">{pos.position_id}</td>
                            <td className="py-2 px-3 text-gray-300">{pos.open_date}</td>
                            <td className="py-2 px-3 text-gray-300">{pos.expiration}</td>
                            <td className="py-2 px-3 text-center text-gray-400">
                              {pos.put_short_strike}P / {pos.call_short_strike}C
                            </td>
                            <td className="py-2 px-3 text-right">
                              <span className={pos.total_credit > 0 ? 'text-green-400' : 'text-red-400'}>
                                {formatCurrency(pos.total_credit * 100 * pos.contracts)}
                              </span>
                            </td>
                            <td className="py-2 px-3 text-gray-400">{pos.status}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}

          {/* Logs Tab */}
          {activeTab === 'logs' && (
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Sword className="w-5 h-5 text-red-500" />
                ARES Decision Log
              </h3>
              <DecisionLogViewer defaultBot="ARES" />
            </div>
          )}

          {/* Footer */}
          <div className="mt-6 text-center text-sm text-gray-500">
            Last updated: {lastUpdate.toLocaleTimeString()} | Auto-refresh every 30 seconds
          </div>
        </div>
      </main>
    </div>
  )
}
