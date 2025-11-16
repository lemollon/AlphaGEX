'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Navigation from '@/components/Navigation'
import StatusCard from '@/components/StatusCard'
import TradingViewChart from '@/components/TradingViewChart'
import MarketCommentary from '@/components/MarketCommentary'
import DailyTradingPlan from '@/components/DailyTradingPlan'
import { apiClient } from '@/lib/api'
import { useWebSocket } from '@/hooks/useWebSocket'
import { LineData } from 'lightweight-charts'
import {
  TrendingDown,
  Zap,
  Target,
  Activity,
  TrendingUp,
  ArrowUpRight,
  ArrowDownRight,
  DollarSign,
  Download
} from 'lucide-react'

interface Position {
  id: number
  symbol: string
  strike: number
  option_type: string
  contracts: number
  entry_price: number
  current_price: number
  entry_date: string
  unrealized_pnl: number
}

interface TradeLogEntry {
  time: string
  action: string
  details: string
  pnl: number
}

export default function Dashboard() {
  const router = useRouter()
  const [gexData, setGexData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [chartData, setChartData] = useState<LineData[]>([])
  const [performanceData, setPerformanceData] = useState<LineData[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [tradeLog, setTradeLog] = useState<TradeLogEntry[]>([])
  const [performance, setPerformance] = useState<any>(null)
  const { data: wsData, isConnected } = useWebSocket('SPY')

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)

        // Fetch ALL data in parallel - REAL DATA ONLY
        const [gexRes, perfRes, positionsRes, tradeLogRes, equityCurveRes, priceHistoryRes] = await Promise.all([
          apiClient.getGEX('SPY'),
          apiClient.getTraderPerformance(),
          apiClient.getOpenPositions(),
          apiClient.getTradeLog(),
          apiClient.getEquityCurve(30),
          apiClient.getPriceHistory('SPY', 90)
        ])

        // Set GEX data
        if (gexRes.data.success) {
          setGexData(gexRes.data.data)
        }

        // Set REAL performance data
        if (perfRes.data.success) {
          setPerformance(perfRes.data.data)
        }

        // Set REAL equity curve from trade history
        if (equityCurveRes.data.success && equityCurveRes.data.data.length > 0) {
          const perfData: LineData[] = equityCurveRes.data.data.map((point: any) => ({
            time: point.timestamp as any,
            value: point.equity
          }))
          setPerformanceData(perfData)
        } else {
          // No trade history yet - show empty state
          setPerformanceData([])
        }

        // Set REAL SPY price history
        if (priceHistoryRes.data.success && priceHistoryRes.data.data) {
          const spyData: LineData[] = priceHistoryRes.data.data.map((point: any) => ({
            time: point.time as any,
            value: point.value
          }))
          setChartData(spyData)
        }

        // Set REAL open positions
        if (positionsRes.data.success) {
          setPositions(positionsRes.data.data)
        }

        // Set REAL trade log
        if (tradeLogRes.data.success) {
          setTradeLog(tradeLogRes.data.data)
        }

        setLoading(false)
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error)
        setLoading(false)
      }
    }

    fetchData()

    // No auto-refresh - protects API rate limit (20 calls/min shared across all users)
    // Users can manually refresh or navigate away and back to get fresh data
  }, [])

  // Update data from WebSocket
  useEffect(() => {
    if (wsData?.type === 'market_update' && wsData.data) {
      setGexData(wsData.data)
    }
  }, [wsData])

  const formatCurrency = (value: number) => {
    const absValue = Math.abs(value)
    if (absValue >= 1e9) {
      return `${(value / 1e9).toFixed(1)}B`
    }
    if (absValue >= 1e6) {
      return `${(value / 1e6).toFixed(0)}M`
    }
    return value.toFixed(2)
  }

  const formatTime = (timeStr: string) => {
    // Format time in Central Time
    try {
      return new Intl.DateTimeFormat('en-US', {
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
        timeZone: 'America/Chicago'
      }).format(new Date(timeStr))
    } catch {
      return timeStr
    }
  }

  const downloadTradeHistory = async () => {
    try {
      // Fetch full trade history from API
      const response = await apiClient.getTradeLog()

      if (!response.data.success || !response.data.data.length) {
        alert('No trade history available to download')
        return
      }

      const trades = response.data.data

      // Create CSV content
      const headers = ['Date/Time (Central)', 'Action', 'Details', 'P&L']
      const csvRows = [headers.join(',')]

      trades.forEach((trade: TradeLogEntry) => {
        const row = [
          `"${new Date(trade.time).toLocaleString('en-US', { timeZone: 'America/Chicago' })}"`,
          `"${trade.action}"`,
          `"${trade.details}"`,
          trade.pnl ? trade.pnl.toFixed(2) : '0.00'
        ]
        csvRows.push(row.join(','))
      })

      const csvContent = csvRows.join('\n')

      // Create download link
      const blob = new Blob([csvContent], { type: 'text/csv' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `alphagex-trade-history-${new Date().toISOString().split('T')[0]}.csv`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error('Failed to download trade history:', error)
      alert('Failed to download trade history. Please try again.')
    }
  }

  const getMMState = (netGex: number, spot: number, flip: number) => {
    if (netGex < -2e9) return { state: 'PANICKING', color: 'text-danger' }
    if (netGex < -1e9) {
      return spot < flip
        ? { state: 'SQUEEZE', color: 'text-success' }
        : { state: 'BREAKDOWN', color: 'text-danger' }
    }
    if (netGex > 1e9) return { state: 'DEFENDING', color: 'text-warning' }
    return { state: 'NEUTRAL', color: 'text-text-secondary' }
  }

  if (loading) {
    return (
      <div className="min-h-screen">
        <Navigation />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-8">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="skeleton h-32 rounded-lg"></div>
            ))}
          </div>
        </main>
      </div>
    )
  }

  const netGex = gexData?.net_gex || 0
  const spotPrice = gexData?.spot_price || 0
  const flipPoint = gexData?.flip_point || 0
  const mmState = getMMState(netGex, spotPrice, flipPoint)

  return (
    <div className="min-h-screen">
      <Navigation />

      <main className="pt-16 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Status Cards - REAL DATA */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-8">
          <StatusCard
            icon={TrendingDown}
            label="SPY GEX"
            value={`$${formatCurrency(netGex)}`}
            change={netGex < 0 ? '↓ Negative' : '↑ Positive'}
            changeType={netGex < 0 ? 'negative' : 'positive'}
          />

          <StatusCard
            icon={Activity}
            label="Net Gamma"
            value={`${formatCurrency(netGex)}`}
            subtitle={netGex < 0 ? 'Short Gamma' : 'Long Gamma'}
          />

          <StatusCard
            icon={Zap}
            label="Flip Point"
            value={`$${flipPoint.toFixed(2)}`}
            change={spotPrice < flipPoint ? `$${(flipPoint - spotPrice).toFixed(2)} away` : 'Above flip'}
            changeType="neutral"
          />

          <StatusCard
            icon={Target}
            label="MM State"
            value={mmState.state}
            subtitle={netGex < -1e9 ? 'Forced hedging' : 'Balanced'}
          />

          <StatusCard
            icon={TrendingUp}
            label="Win Rate"
            value={performance ? `${performance.win_rate.toFixed(1)}%` : '-'}
            change={performance ? `${performance.winning_trades} / ${performance.total_trades} trades` : 'No trades yet'}
            changeType="positive"
            subtitle="All time"
          />
        </div>

        {/* AI Intelligence Widgets */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <MarketCommentary />
          <DailyTradingPlan />
        </div>

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          {/* Market Overview Chart - REAL SPY DATA */}
          <div className="lg:col-span-2">
            <div className="card">
              <h2 className="text-xl font-semibold mb-4 flex items-center space-x-2">
                <TrendingUp className="w-5 h-5 text-primary" />
                <span>SPY Market Overview (90 Days)</span>
                {isConnected && (
                  <span className="flex items-center space-x-1 text-xs text-success">
                    <div className="w-2 h-2 rounded-full bg-success animate-pulse"></div>
                    <span>Live</span>
                  </span>
                )}
              </h2>

              <div className="bg-background-deep rounded-lg overflow-hidden">
                {chartData.length > 0 ? (
                  <TradingViewChart
                    data={chartData}
                    type="area"
                    height={320}
                    colors={{
                      lineColor: '#3b82f6',
                      areaTopColor: 'rgba(59, 130, 246, 0.3)',
                      areaBottomColor: 'rgba(59, 130, 246, 0.0)',
                    }}
                  />
                ) : (
                  <div className="h-80 flex items-center justify-center">
                    <div className="text-center text-text-muted">
                      <TrendingUp className="w-12 h-12 mx-auto mb-2 opacity-50" />
                      <p className="text-sm">Loading SPY price data...</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Active Positions - REAL DATA FROM DATABASE */}
          <div className="card">
            <h3 className="text-lg font-semibold mb-4 flex items-center justify-between">
              <span className="flex items-center space-x-2">
                <DollarSign className="w-5 h-5 text-success" />
                <span>Active Positions</span>
              </span>
              <span className="text-sm font-normal text-text-secondary">({positions.length})</span>
            </h3>

            <div className="space-y-3">
              {positions.length === 0 ? (
                <div className="text-center py-8 text-text-muted">
                  <p>No open positions</p>
                  <p className="text-sm mt-2">Trader will open positions when opportunities arise</p>
                </div>
              ) : (
                positions.map((pos) => (
                  <div key={pos.id} className="bg-background-hover rounded-lg p-4 hover:bg-background-deep transition-colors">
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <div className="font-semibold text-text-primary flex items-center space-x-2">
                          <span>{pos.symbol} {pos.strike}{pos.option_type === 'CALL' ? 'C' : 'P'}</span>
                          {pos.unrealized_pnl >= 0 ? (
                            <ArrowUpRight className="w-4 h-4 text-success" />
                          ) : (
                            <ArrowDownRight className="w-4 h-4 text-danger" />
                          )}
                        </div>
                        <div className="text-xs text-text-muted">{pos.entry_date}</div>
                      </div>
                      <div className="text-right">
                        <div className={`font-semibold ${pos.unrealized_pnl >= 0 ? 'text-success' : 'text-danger'}`}>
                          {pos.unrealized_pnl >= 0 ? '+' : ''}{((pos.unrealized_pnl / (pos.entry_price * pos.contracts * 100)) * 100).toFixed(1)}%
                        </div>
                        <div className="text-xs text-text-muted">
                          {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl.toFixed(2)}
                        </div>
                      </div>
                    </div>
                    <div className="text-sm space-y-1">
                      <div className="flex justify-between text-text-secondary">
                        <span>Entry:</span>
                        <span className="text-text-primary font-mono">${pos.entry_price.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between text-text-secondary">
                        <span>Current:</span>
                        <span className="text-text-primary font-mono">${pos.current_price.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between text-text-secondary">
                        <span>Contracts:</span>
                        <span className="text-text-primary font-mono">{pos.contracts}</span>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Quick Actions - NOW FUNCTIONAL */}
        <div className="card mb-8">
          <h3 className="text-lg font-semibold mb-4">⚡ Quick Actions</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <button
              onClick={() => router.push('/scanner')}
              className="btn-primary flex flex-col items-center space-y-2 py-4"
            >
              <span className="text-2xl">🔍</span>
              <span>Scan Market</span>
            </button>
            <button
              onClick={() => router.push('/gex')}
              className="btn-secondary flex flex-col items-center space-y-2 py-4"
            >
              <span className="text-2xl">📊</span>
              <span>GEX Analysis</span>
            </button>
            <button
              onClick={() => router.push('/gamma')}
              className="btn-secondary flex flex-col items-center space-y-2 py-4"
            >
              <span className="text-2xl">⚡</span>
              <span>Gamma Intel</span>
            </button>
            <button
              onClick={() => router.push('/psychology')}
              className="btn-secondary flex flex-col items-center space-y-2 py-4"
            >
              <span className="text-2xl">🧠</span>
              <span>Psychology</span>
            </button>
            <button
              onClick={() => router.push('/trader')}
              className="btn-secondary flex flex-col items-center space-y-2 py-4"
            >
              <span className="text-2xl">🤖</span>
              <span>Trader</span>
            </button>
          </div>
        </div>

        {/* Bottom Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Trade Log - REAL DATA FROM DATABASE (Central Time) */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">📅 Today's Trade Log (Central Time)</h3>
              <button
                onClick={downloadTradeHistory}
                className="flex items-center gap-2 px-3 py-1.5 bg-primary/20 hover:bg-primary/30 text-primary rounded-lg transition-colors text-sm"
                title="Download full trade history as CSV"
              >
                <Download className="w-4 h-4" />
                <span>Download History</span>
              </button>
            </div>
            <div className="space-y-2">
              {tradeLog.length === 0 ? (
                <div className="text-center py-8 text-text-muted">
                  <p>No trades today</p>
                  <p className="text-sm mt-2">Check back during market hours</p>
                </div>
              ) : (
                tradeLog.map((entry, idx) => (
                  <div key={idx} className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
                    <div className="flex items-center space-x-3">
                      <div className="text-xs text-text-muted">{formatTime(entry.time)}</div>
                      <div className="text-sm text-text-primary">{entry.action}: {entry.details}</div>
                    </div>
                    {entry.pnl && (
                      <div className={`text-sm ${entry.pnl >= 0 ? 'text-success' : 'text-danger'}`}>
                        {entry.pnl >= 0 ? '+' : ''}${entry.pnl.toFixed(2)}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Performance - REAL DATA */}
          <div className="card">
            <h3 className="text-lg font-semibold mb-4">📊 Performance Equity Curve</h3>
            <div className="bg-background-deep rounded-lg">
              {performanceData.length > 0 ? (
                <TradingViewChart
                  data={performanceData}
                  type="area"
                  height={192}
                  colors={{
                    lineColor: '#10b981',
                    areaTopColor: 'rgba(16, 185, 129, 0.4)',
                    areaBottomColor: 'rgba(16, 185, 129, 0.0)',
                  }}
                />
              ) : (
                <div className="h-48 flex items-center justify-center">
                  <div className="text-center text-text-muted">
                    <TrendingUp className="w-12 h-12 mx-auto mb-2 opacity-50" />
                    <p className="text-sm">No performance data yet</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
        </div>
      </main>
    </div>
  )
}
