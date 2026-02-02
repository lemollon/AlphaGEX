'use client'

import { useState, useEffect } from 'react'
import useSWR from 'swr'
import Link from 'next/link'
import {
  ChartBarIcon,
  ArrowTrendingUpIcon,
  ArrowTrendingDownIcon,
  CurrencyDollarIcon,
  ClockIcon,
  BoltIcon,
  ChartPieIcon,
  Cog6ToothIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://alphagex-api.onrender.com'

const fetcher = (url: string) => fetch(url).then(res => res.json())

interface Position {
  position_id: string
  symbol: string
  direction: string
  contracts: number
  entry_price: number
  current_stop: number
  trailing_active: boolean
  gamma_regime: string
  open_time: string
  unrealized_pnl?: number
}

interface ClosedTrade {
  position_id: string
  symbol: string
  direction: string
  contracts: number
  entry_price: number
  exit_price: number
  realized_pnl: number
  gamma_regime: string
  close_reason: string
  close_time: string
}

interface WinTracker {
  win_probability: number
  total_trades: number
  positive_gamma_wins: number
  positive_gamma_losses: number
  negative_gamma_wins: number
  negative_gamma_losses: number
  should_use_ml: boolean
}

export default function HERACLESPage() {
  const [activeTab, setActiveTab] = useState<'overview' | 'positions' | 'history' | 'signals'>('overview')

  // Fetch data
  const { data: status, error: statusError, isLoading: statusLoading } = useSWR(
    `${API_URL}/api/heracles/status`,
    fetcher,
    { refreshInterval: 5000 }
  )

  const { data: closedTrades } = useSWR(
    activeTab === 'history' ? `${API_URL}/api/heracles/closed-trades?limit=50` : null,
    fetcher
  )

  const { data: signals } = useSWR(
    activeTab === 'signals' ? `${API_URL}/api/heracles/signals/recent?limit=50` : null,
    fetcher
  )

  const { data: equityCurve } = useSWR(
    `${API_URL}/api/heracles/equity-curve?days=30`,
    fetcher,
    { refreshInterval: 60000 }
  )

  if (statusError) {
    return (
      <div className="min-h-screen bg-gray-900 text-white p-8">
        <div className="max-w-7xl mx-auto">
          <div className="bg-red-900/50 border border-red-500 rounded-lg p-6">
            <h2 className="text-xl font-bold text-red-400 flex items-center gap-2">
              <ExclamationTriangleIcon className="h-6 w-6" />
              HERACLES Not Available
            </h2>
            <p className="text-red-300 mt-2">
              The HERACLES futures bot is not currently available. This may be due to:
            </p>
            <ul className="list-disc list-inside text-red-300 mt-2 space-y-1">
              <li>Module not deployed yet</li>
              <li>API server restarting</li>
              <li>Configuration error</li>
            </ul>
          </div>
        </div>
      </div>
    )
  }

  const positions: Position[] = status?.positions?.positions || []
  const performance = status?.performance || {}
  const config = status?.config || {}
  const winTracker: WinTracker = status?.win_tracker || {}
  const todayStats = status?.today || {}

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <div className="bg-gradient-to-r from-orange-900 via-amber-900 to-yellow-900 p-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-orange-600 rounded-lg">
                <BoltIcon className="h-8 w-8 text-white" />
              </div>
              <div>
                <h1 className="text-3xl font-bold">HERACLES</h1>
                <p className="text-orange-200">MES Futures Scalping Bot</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className={`px-4 py-2 rounded-full ${
                status?.market_open
                  ? 'bg-green-600 text-white'
                  : 'bg-red-600 text-white'
              }`}>
                {status?.market_open ? 'Market Open' : 'Market Closed'}
              </div>
              <div className={`px-4 py-2 rounded-full ${
                status?.mode === 'paper'
                  ? 'bg-yellow-600 text-white'
                  : 'bg-green-600 text-white'
              }`}>
                {status?.mode?.toUpperCase() || 'PAPER'}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="bg-gray-800 border-b border-gray-700">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex space-x-8">
            {[
              { id: 'overview', label: 'Overview', icon: ChartBarIcon },
              { id: 'positions', label: 'Positions', icon: CurrencyDollarIcon },
              { id: 'history', label: 'Trade History', icon: ClockIcon },
              { id: 'signals', label: 'Signals', icon: BoltIcon },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`flex items-center gap-2 py-4 px-2 border-b-2 transition-colors ${
                  activeTab === tab.id
                    ? 'border-orange-500 text-orange-400'
                    : 'border-transparent text-gray-400 hover:text-gray-200'
                }`}
              >
                <tab.icon className="h-5 w-5" />
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto p-6">
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard
                title="Total P&L"
                value={`$${(performance.total_pnl || 0).toFixed(2)}`}
                positive={(performance.total_pnl || 0) >= 0}
                icon={CurrencyDollarIcon}
              />
              <StatCard
                title="Win Rate"
                value={`${(performance.win_rate || 0).toFixed(1)}%`}
                positive={(performance.win_rate || 0) >= 50}
                icon={ChartPieIcon}
              />
              <StatCard
                title="Total Trades"
                value={performance.total_trades || 0}
                icon={ChartBarIcon}
              />
              <StatCard
                title="Open Positions"
                value={positions.length}
                icon={BoltIcon}
              />
            </div>

            {/* Win Probability Tracker */}
            <div className="bg-gray-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <ChartPieIcon className="h-5 w-5 text-orange-400" />
                Bayesian Win Probability Tracker
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-gray-700/50 rounded-lg p-4">
                  <div className="text-sm text-gray-400">Overall Win Probability</div>
                  <div className="text-3xl font-bold text-orange-400 mt-1">
                    {((winTracker.win_probability || 0.5) * 100).toFixed(1)}%
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    Based on {winTracker.total_trades || 0} trades
                  </div>
                </div>
                <div className="bg-gray-700/50 rounded-lg p-4">
                  <div className="text-sm text-gray-400">Positive Gamma</div>
                  <div className="flex items-center gap-4 mt-2">
                    <span className="text-green-400">W: {winTracker.positive_gamma_wins || 0}</span>
                    <span className="text-red-400">L: {winTracker.positive_gamma_losses || 0}</span>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">Mean Reversion Strategy</div>
                </div>
                <div className="bg-gray-700/50 rounded-lg p-4">
                  <div className="text-sm text-gray-400">Negative Gamma</div>
                  <div className="flex items-center gap-4 mt-2">
                    <span className="text-green-400">W: {winTracker.negative_gamma_wins || 0}</span>
                    <span className="text-red-400">L: {winTracker.negative_gamma_losses || 0}</span>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">Momentum Strategy</div>
                </div>
              </div>
              {winTracker.should_use_ml && (
                <div className="mt-4 p-3 bg-green-900/30 border border-green-500/30 rounded-lg">
                  <span className="text-green-400">
                    Ready for ML transition (50+ trades collected)
                  </span>
                </div>
              )}
            </div>

            {/* Configuration */}
            <div className="bg-gray-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Cog6ToothIcon className="h-5 w-5 text-orange-400" />
                Configuration
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <ConfigItem label="Symbol" value={status?.symbol || '/MESH6'} />
                <ConfigItem label="Capital" value={`$${(config.capital || 10000).toLocaleString()}`} />
                <ConfigItem label="Risk/Trade" value={`${config.risk_per_trade_pct || 1}%`} />
                <ConfigItem label="Max Contracts" value={config.max_contracts || 5} />
                <ConfigItem label="Initial Stop" value={`${config.initial_stop_points || 3} pts`} />
                <ConfigItem label="Breakeven At" value={`+${config.breakeven_activation_points || 2} pts`} />
                <ConfigItem label="Trail Distance" value={`${config.trailing_stop_points || 1} pt`} />
                <ConfigItem label="Max Positions" value={config.max_open_positions || 2} />
              </div>
            </div>

            {/* Today's Summary */}
            <div className="bg-gray-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4">Today&apos;s Activity</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-gray-700/50 rounded-lg p-4 text-center">
                  <div className="text-sm text-gray-400">Trades Closed</div>
                  <div className="text-2xl font-bold mt-1">{todayStats.positions_closed || 0}</div>
                </div>
                <div className="bg-gray-700/50 rounded-lg p-4 text-center">
                  <div className="text-sm text-gray-400">Realized P&L</div>
                  <div className={`text-2xl font-bold mt-1 ${
                    (todayStats.realized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                  }`}>
                    ${(todayStats.realized_pnl || 0).toFixed(2)}
                  </div>
                </div>
                <div className="bg-gray-700/50 rounded-lg p-4 text-center">
                  <div className="text-sm text-gray-400">Positive Gamma</div>
                  <div className="text-2xl font-bold mt-1 text-blue-400">
                    {todayStats.positive_gamma_trades || 0}
                  </div>
                </div>
                <div className="bg-gray-700/50 rounded-lg p-4 text-center">
                  <div className="text-sm text-gray-400">Negative Gamma</div>
                  <div className="text-2xl font-bold mt-1 text-purple-400">
                    {todayStats.negative_gamma_trades || 0}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'positions' && (
          <div className="space-y-6">
            <h2 className="text-xl font-semibold">Open Positions ({positions.length})</h2>

            {positions.length === 0 ? (
              <div className="bg-gray-800 rounded-lg p-8 text-center">
                <BoltIcon className="h-12 w-12 text-gray-600 mx-auto mb-4" />
                <p className="text-gray-400">No open positions</p>
                <p className="text-gray-500 text-sm mt-2">
                  HERACLES will open positions when GEX signals meet criteria
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {positions.map((position) => (
                  <div key={position.position_id} className="bg-gray-800 rounded-lg p-6">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-4">
                        <div className={`p-2 rounded-lg ${
                          position.direction === 'LONG'
                            ? 'bg-green-900/50 text-green-400'
                            : 'bg-red-900/50 text-red-400'
                        }`}>
                          {position.direction === 'LONG'
                            ? <ArrowTrendingUpIcon className="h-6 w-6" />
                            : <ArrowTrendingDownIcon className="h-6 w-6" />
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
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                      <div>
                        <span className="text-gray-400">Stop:</span>
                        <span className="ml-2 font-mono">{position.current_stop?.toFixed(2)}</span>
                      </div>
                      <div>
                        <span className="text-gray-400">Trailing:</span>
                        <span className={`ml-2 ${position.trailing_active ? 'text-green-400' : 'text-gray-500'}`}>
                          {position.trailing_active ? 'Active' : 'Inactive'}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-400">Opened:</span>
                        <span className="ml-2">
                          {new Date(position.open_time).toLocaleTimeString()}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-400">ID:</span>
                        <span className="ml-2 font-mono text-xs">{position.position_id}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'history' && (
          <div className="space-y-6">
            <h2 className="text-xl font-semibold">Trade History</h2>

            {!closedTrades?.trades?.length ? (
              <div className="bg-gray-800 rounded-lg p-8 text-center">
                <ClockIcon className="h-12 w-12 text-gray-600 mx-auto mb-4" />
                <p className="text-gray-400">No trade history yet</p>
              </div>
            ) : (
              <div className="bg-gray-800 rounded-lg overflow-hidden">
                <table className="w-full">
                  <thead className="bg-gray-700">
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
                  <tbody className="divide-y divide-gray-700">
                    {closedTrades.trades.map((trade: ClosedTrade) => (
                      <tr key={trade.position_id} className="hover:bg-gray-700/50">
                        <td className="px-4 py-3 text-sm">
                          {new Date(trade.close_time).toLocaleString()}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-1 rounded text-xs ${
                            trade.direction === 'LONG'
                              ? 'bg-green-900/50 text-green-400'
                              : 'bg-red-900/50 text-red-400'
                          }`}>
                            {trade.direction}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-1 rounded text-xs ${
                            trade.gamma_regime === 'POSITIVE'
                              ? 'bg-blue-900/50 text-blue-400'
                              : 'bg-purple-900/50 text-purple-400'
                          }`}>
                            {trade.gamma_regime}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right font-mono">
                          {trade.entry_price?.toFixed(2)}
                        </td>
                        <td className="px-4 py-3 text-right font-mono">
                          {trade.exit_price?.toFixed(2)}
                        </td>
                        <td className={`px-4 py-3 text-right font-mono ${
                          trade.realized_pnl >= 0 ? 'text-green-400' : 'text-red-400'
                        }`}>
                          ${trade.realized_pnl?.toFixed(2)}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-400">
                          {trade.close_reason}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {activeTab === 'signals' && (
          <div className="space-y-6">
            <h2 className="text-xl font-semibold">Recent Signals</h2>

            {!signals?.signals?.length ? (
              <div className="bg-gray-800 rounded-lg p-8 text-center">
                <BoltIcon className="h-12 w-12 text-gray-600 mx-auto mb-4" />
                <p className="text-gray-400">No signals yet</p>
              </div>
            ) : (
              <div className="space-y-3">
                {signals.signals.map((signal: any, index: number) => (
                  <div
                    key={index}
                    className={`bg-gray-800 rounded-lg p-4 border-l-4 ${
                      signal.was_executed
                        ? 'border-green-500'
                        : 'border-gray-500'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <span className={`px-2 py-1 rounded text-xs ${
                          signal.direction === 'LONG'
                            ? 'bg-green-900/50 text-green-400'
                            : 'bg-red-900/50 text-red-400'
                        }`}>
                          {signal.direction}
                        </span>
                        <span className="text-sm text-gray-400">{signal.source}</span>
                        <span className="text-sm">
                          @ {signal.current_price?.toFixed(2)}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {signal.was_executed ? (
                          <span className="flex items-center gap-1 text-green-400 text-sm">
                            <CheckCircleIcon className="h-4 w-4" />
                            Executed
                          </span>
                        ) : (
                          <span className="text-gray-400 text-sm">
                            {signal.skip_reason || 'Skipped'}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="text-sm text-gray-400">
                      Win Prob: {(signal.win_probability * 100).toFixed(1)}% |
                      Confidence: {(signal.confidence * 100).toFixed(1)}% |
                      {signal.gamma_regime} GAMMA
                    </div>
                    {signal.reasoning && (
                      <div className="mt-2 text-xs text-gray-500 bg-gray-700/50 p-2 rounded">
                        {signal.reasoning}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// Helper Components
function StatCard({
  title,
  value,
  positive,
  icon: Icon,
}: {
  title: string
  value: string | number
  positive?: boolean
  icon: React.ComponentType<{ className?: string }>
}) {
  return (
    <div className="bg-gray-800 rounded-lg p-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm text-gray-400">{title}</div>
          <div
            className={`text-2xl font-bold mt-1 ${
              positive === undefined
                ? 'text-white'
                : positive
                ? 'text-green-400'
                : 'text-red-400'
            }`}
          >
            {value}
          </div>
        </div>
        <Icon className="h-8 w-8 text-orange-500/50" />
      </div>
    </div>
  )
}

function ConfigItem({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-gray-700/50 rounded-lg p-3">
      <div className="text-xs text-gray-400">{label}</div>
      <div className="font-mono text-sm mt-1">{value}</div>
    </div>
  )
}
