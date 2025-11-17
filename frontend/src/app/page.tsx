'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Navigation from '@/components/Navigation'
import StatusCard from '@/components/StatusCard'
import TradingViewChart from '@/components/TradingViewChart'
import TradingViewWidget from '@/components/TradingViewWidget'
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
  Download,
  BarChart3,
  Brain,
  Search,
  Shield,
  Flame,
  Clock,
  TrendingUpIcon
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
  const [performanceData, setPerformanceData] = useState<LineData[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [tradeLog, setTradeLog] = useState<TradeLogEntry[]>([])
  const [performance, setPerformance] = useState<any>(null)
  const { data: wsData, isConnected } = useWebSocket('SPY')

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)

        const [gexRes, perfRes, positionsRes, tradeLogRes, equityCurveRes] = await Promise.all([
          apiClient.getGEX('SPY'),
          apiClient.getTraderPerformance(),
          apiClient.getOpenPositions(),
          apiClient.getTradeLog(),
          apiClient.getEquityCurve(30)
        ])

        if (gexRes.data.success) {
          setGexData(gexRes.data.data)
        }

        if (perfRes.data.success) {
          setPerformance(perfRes.data.data)
        }

        if (equityCurveRes.data.success && equityCurveRes.data.data.length > 0) {
          const perfData: LineData[] = equityCurveRes.data.data.map((point: any) => ({
            time: point.timestamp as any,
            value: point.equity
          }))
          setPerformanceData(perfData)
        } else {
          setPerformanceData([])
        }

        if (positionsRes.data.success) {
          setPositions(positionsRes.data.data)
        }

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
  }, [])

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
      const response = await apiClient.getTradeLog()

      if (!response.data.success || !response.data.data.length) {
        alert('No trade history available to download')
        return
      }

      const trades = response.data.data
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
    if (netGex < -2e9) return { state: 'PANICKING', color: 'text-danger', bg: 'bg-danger/10' }
    if (netGex < -1e9) {
      return spot < flip
        ? { state: 'SQUEEZE', color: 'text-success', bg: 'bg-success/10' }
        : { state: 'BREAKDOWN', color: 'text-danger', bg: 'bg-danger/10' }
    }
    if (netGex > 1e9) return { state: 'DEFENDING', color: 'text-warning', bg: 'bg-warning/10' }
    return { state: 'NEUTRAL', color: 'text-text-secondary', bg: 'bg-background-deep' }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-background via-background to-background-deep">
        <Navigation />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="space-y-6 animate-pulse">
            <div className="h-64 bg-background-hover rounded-2xl"></div>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="h-32 bg-background-hover rounded-xl"></div>
              ))}
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="h-96 bg-background-hover rounded-xl"></div>
              <div className="h-96 bg-background-hover rounded-xl"></div>
            </div>
          </div>
        </main>
      </div>
    )
  }

  const netGex = gexData?.net_gex || 0
  const spotPrice = gexData?.spot_price || 0
  const flipPoint = gexData?.flip_point || 0
  const mmState = getMMState(netGex, spotPrice, flipPoint)

  const todayPnL = tradeLog.reduce((sum, trade) => sum + (trade.pnl || 0), 0)
  const todayPnLPercent = performance ? (todayPnL / 5000) * 100 : 0
  const unrealizedPnL = positions.reduce((sum, pos) => sum + pos.unrealized_pnl, 0)
  const totalPnL = todayPnL + unrealizedPnL

  const bestTrade = tradeLog.length > 0 ? tradeLog.reduce((best, trade) =>
    (trade.pnl || 0) > (best.pnl || 0) ? trade : best
  , tradeLog[0]) : null

  const worstTrade = tradeLog.length > 0 ? tradeLog.reduce((worst, trade) =>
    (trade.pnl || 0) < (worst.pnl || 0) ? trade : worst
  , tradeLog[0]) : null

  const currentEquity = 5000 + (performance?.total_pnl || 0)
  const peakEquity = currentEquity
  const currentDrawdown = ((peakEquity - currentEquity) / peakEquity * 100)
  const dailyLossUsed = todayPnL < 0 ? Math.abs((todayPnL / currentEquity) * 100) : 0
  const totalExposure = positions.reduce((sum, pos) => sum + (pos.entry_price * pos.contracts * 100), 0)
  const exposurePercent = (totalExposure / currentEquity) * 100

  const now = new Date()
  const centralTime = new Date(now.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  const hour = centralTime.getHours()
  const minute = centralTime.getMinutes()
  const isMarketHours = (hour === 8 && minute >= 30) || (hour > 8 && hour < 15) || (hour === 15 && minute === 0)
  const marketClose = new Date(centralTime)
  marketClose.setHours(15, 0, 0, 0)
  const timeToClose = isMarketHours ? Math.max(0, Math.floor((marketClose.getTime() - centralTime.getTime()) / 1000 / 60)) : 0
  const hoursToClose = Math.floor(timeToClose / 60)
  const minutesToClose = timeToClose % 60

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-background-deep">
      <Navigation />

      <main className="pt-16 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* Hero Performance Card */}
        <div className="mb-8 relative overflow-hidden rounded-3xl bg-gradient-to-br from-primary/10 via-background-card to-background-card border-2 border-primary/20 shadow-2xl">
          <div className="absolute inset-0 bg-gradient-to-tr from-primary/5 to-transparent"></div>
          <div className="relative p-8">
            <div className="flex items-center justify-between mb-6">
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <h1 className="text-3xl font-bold text-text-primary">AlphaGEX Trading Dashboard</h1>
                  {isConnected && (
                    <div className="flex items-center gap-2 px-3 py-1 bg-success/20 rounded-full">
                      <div className="w-2 h-2 rounded-full bg-success animate-pulse"></div>
                      <span className="text-xs font-semibold text-success">Live Data</span>
                    </div>
                  )}
                </div>
                <p className="text-text-secondary">Real-time market intelligence • Autonomous options trading</p>
              </div>
              {isMarketHours && (
                <div className="flex items-center gap-2 px-4 py-2 bg-warning/20 rounded-xl border border-warning/30">
                  <Clock className="w-5 h-5 text-warning" />
                  <div className="text-right">
                    <div className="text-sm font-semibold text-warning">Market Closes In</div>
                    <div className="text-2xl font-bold text-warning">{hoursToClose}h {minutesToClose}m</div>
                  </div>
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Today's P&L */}
              <div className={`p-6 rounded-2xl border-2 ${totalPnL >= 0 ? 'bg-success/10 border-success/30' : 'bg-danger/10 border-danger/30'} backdrop-blur-sm`}>
                <div className="flex items-center gap-2 mb-2">
                  {totalPnL >= 0 ? <TrendingUp className="w-5 h-5 text-success" /> : <TrendingDown className="w-5 h-5 text-danger" />}
                  <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wide">Today's P&L</h3>
                </div>
                <div className={`text-5xl font-bold mb-2 ${totalPnL >= 0 ? 'text-success' : 'text-danger'}`}>
                  {totalPnL >= 0 ? '+' : ''}${totalPnL.toFixed(2)}
                </div>
                <div className="flex items-center gap-4 text-sm text-text-secondary">
                  <span>Realized: <span className={totalPnL >= 0 ? 'text-success font-semibold' : 'text-danger font-semibold'}>{todayPnL >= 0 ? '+' : ''}${todayPnL.toFixed(2)}</span></span>
                  <span>•</span>
                  <span>{tradeLog.length} trades</span>
                </div>
              </div>

              {/* Account Equity */}
              <div className="p-6 rounded-2xl bg-primary/10 border-2 border-primary/30 backdrop-blur-sm">
                <div className="flex items-center gap-2 mb-2">
                  <DollarSign className="w-5 h-5 text-primary" />
                  <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wide">Account Value</h3>
                </div>
                <div className="text-5xl font-bold mb-2 text-primary">
                  ${currentEquity.toFixed(2)}
                </div>
                <div className="flex items-center gap-4 text-sm text-text-secondary">
                  <span>Start: $5,000.00</span>
                  <span>•</span>
                  <span className={performance && performance.total_pnl >= 0 ? 'text-success font-semibold' : 'text-danger font-semibold'}>
                    {performance && performance.total_pnl >= 0 ? '+' : ''}{performance?.total_pnl?.toFixed(2) || '0.00'}
                  </span>
                </div>
              </div>

              {/* Win Rate */}
              <div className="p-6 rounded-2xl bg-background-card border-2 border-border backdrop-blur-sm">
                <div className="flex items-center gap-2 mb-2">
                  <Flame className="w-5 h-5 text-warning" />
                  <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wide">Win Rate</h3>
                </div>
                <div className="text-5xl font-bold mb-2 text-text-primary">
                  {performance ? `${performance.win_rate.toFixed(1)}%` : '0%'}
                </div>
                <div className="flex items-center gap-4 text-sm text-text-secondary">
                  <span className="text-success">{performance?.winning_trades || 0}W</span>
                  <span>•</span>
                  <span className="text-danger">{performance?.losing_trades || 0}L</span>
                  <span>•</span>
                  <span>{performance?.total_trades || 0} total</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Market Intelligence Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <div className="card bg-gradient-to-br from-background-card to-background-deep hover:shadow-xl transition-all duration-300 border border-border">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <TrendingDown className="w-5 h-5 text-danger" />
                  <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wide">Net GEX</h4>
                </div>
                <div className={`text-3xl font-bold mb-1 ${netGex < 0 ? 'text-danger' : 'text-success'}`}>
                  ${formatCurrency(netGex)}
                </div>
                <p className="text-xs text-text-muted">{netGex < 0 ? 'Short Gamma' : 'Long Gamma'}</p>
              </div>
            </div>
          </div>

          <div className="card bg-gradient-to-br from-background-card to-background-deep hover:shadow-xl transition-all duration-300 border border-border">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <Zap className="w-5 h-5 text-warning" />
                  <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wide">Flip Point</h4>
                </div>
                <div className="text-3xl font-bold mb-1 text-warning">
                  ${flipPoint.toFixed(2)}
                </div>
                <p className="text-xs text-text-muted">
                  {spotPrice < flipPoint ? `$${(flipPoint - spotPrice).toFixed(2)} away` : 'Above flip'}
                </p>
              </div>
            </div>
          </div>

          <div className="card bg-gradient-to-br from-background-card to-background-deep hover:shadow-xl transition-all duration-300 border border-border">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <Target className="w-5 h-5 text-primary" />
                  <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wide">MM State</h4>
                </div>
                <div className={`text-3xl font-bold mb-1 ${mmState.color}`}>
                  {mmState.state}
                </div>
                <p className="text-xs text-text-muted">{netGex < -1e9 ? 'Forced hedging' : 'Balanced'}</p>
              </div>
            </div>
          </div>

          <div className="card bg-gradient-to-br from-background-card to-background-deep hover:shadow-xl transition-all duration-300 border border-border">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <Activity className="w-5 h-5 text-success" />
                  <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wide">SPY Price</h4>
                </div>
                <div className="text-3xl font-bold mb-1 text-text-primary">
                  ${spotPrice.toFixed(2)}
                </div>
                <p className="text-xs text-text-muted">{positions.length} open positions</p>
              </div>
            </div>
          </div>
        </div>

        {/* Risk Metrics */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          <div className="card bg-gradient-to-br from-background-card to-background-deep border border-border hover:shadow-xl transition-all">
            <div className="flex items-center gap-2 mb-4">
              <Shield className="w-5 h-5 text-danger" />
              <h3 className="text-lg font-semibold">Drawdown</h3>
            </div>
            <div className="flex items-end gap-4">
              <div>
                <div className={`text-4xl font-bold ${currentDrawdown > 10 ? 'text-danger' : currentDrawdown > 5 ? 'text-warning' : 'text-success'}`}>
                  {currentDrawdown.toFixed(2)}%
                </div>
                <p className="text-xs text-text-muted mt-1">Max: 20%</p>
              </div>
              <div className="flex-1 mb-2">
                <div className="w-full bg-background-deep rounded-full h-3">
                  <div
                    className={`h-3 rounded-full transition-all ${currentDrawdown > 10 ? 'bg-danger' : currentDrawdown > 5 ? 'bg-warning' : 'bg-success'}`}
                    style={{width: `${Math.min(100, (currentDrawdown / 20) * 100)}%`}}
                  ></div>
                </div>
              </div>
            </div>
          </div>

          <div className="card bg-gradient-to-br from-background-card to-background-deep border border-border hover:shadow-xl transition-all">
            <div className="flex items-center gap-2 mb-4">
              <TrendingDown className="w-5 h-5 text-warning" />
              <h3 className="text-lg font-semibold">Daily Loss</h3>
            </div>
            <div className="flex items-end gap-4">
              <div>
                <div className={`text-4xl font-bold ${dailyLossUsed > 3 ? 'text-danger' : dailyLossUsed > 1.5 ? 'text-warning' : 'text-success'}`}>
                  {dailyLossUsed.toFixed(2)}%
                </div>
                <p className="text-xs text-text-muted mt-1">Limit: 5%</p>
              </div>
              <div className="flex-1 mb-2">
                <div className="w-full bg-background-deep rounded-full h-3">
                  <div
                    className={`h-3 rounded-full transition-all ${dailyLossUsed > 3 ? 'bg-danger' : dailyLossUsed > 1.5 ? 'bg-warning' : 'bg-success'}`}
                    style={{width: `${Math.min(100, (dailyLossUsed / 5) * 100)}%`}}
                  ></div>
                </div>
              </div>
            </div>
          </div>

          <div className="card bg-gradient-to-br from-background-card to-background-deep border border-border hover:shadow-xl transition-all">
            <div className="flex items-center gap-2 mb-4">
              <DollarSign className="w-5 h-5 text-primary" />
              <h3 className="text-lg font-semibold">Exposure</h3>
            </div>
            <div className="flex items-end gap-4">
              <div>
                <div className={`text-4xl font-bold ${exposurePercent > 50 ? 'text-danger' : exposurePercent > 25 ? 'text-warning' : 'text-success'}`}>
                  {exposurePercent.toFixed(1)}%
                </div>
                <p className="text-xs text-text-muted mt-1">${totalExposure.toFixed(0)}</p>
              </div>
              <div className="flex-1 mb-2">
                <div className="w-full bg-background-deep rounded-full h-3">
                  <div
                    className={`h-3 rounded-full transition-all ${exposurePercent > 50 ? 'bg-danger' : exposurePercent > 25 ? 'bg-warning' : 'bg-success'}`}
                    style={{width: `${Math.min(100, exposurePercent)}%`}}
                  ></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Main Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          {/* Equity Curve */}
          <div className="card bg-gradient-to-br from-background-card to-background-deep border border-border">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <TrendingUpIcon className="w-6 h-6 text-success" />
                <h3 className="text-xl font-bold">Performance</h3>
              </div>
              <span className="text-xs text-text-muted">30-day equity curve</span>
            </div>
            <div className="bg-background-deep rounded-xl overflow-hidden">
              {performanceData.length > 0 ? (
                <TradingViewChart
                  data={performanceData}
                  type="area"
                  height={350}
                  colors={{
                    lineColor: '#10b981',
                    areaTopColor: 'rgba(16, 185, 129, 0.4)',
                    areaBottomColor: 'rgba(16, 185, 129, 0.0)',
                  }}
                />
              ) : (
                <div className="h-[350px] flex items-center justify-center">
                  <div className="text-center text-text-muted">
                    <TrendingUpIcon className="w-16 h-16 mx-auto mb-4 opacity-30" />
                    <p className="font-semibold">No Performance Data</p>
                    <p className="text-sm mt-2">Start trading to build your equity curve</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Active Positions */}
          <div className="card bg-gradient-to-br from-background-card to-background-deep border border-border">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <DollarSign className="w-6 h-6 text-primary" />
                <h3 className="text-xl font-bold">Active Positions</h3>
              </div>
              <span className="px-3 py-1 bg-primary/20 text-primary text-sm font-semibold rounded-full">
                {positions.length}
              </span>
            </div>
            <div className="space-y-3 max-h-[350px] overflow-y-auto custom-scrollbar">
              {positions.length === 0 ? (
                <div className="h-[350px] flex items-center justify-center">
                  <div className="text-center text-text-muted">
                    <DollarSign className="w-16 h-16 mx-auto mb-4 opacity-30" />
                    <p className="font-semibold">No Open Positions</p>
                    <p className="text-sm mt-2">Waiting for high-probability setups</p>
                  </div>
                </div>
              ) : (
                positions.map((pos) => (
                  <div key={pos.id} className="p-4 rounded-xl bg-background-hover border border-border hover:border-primary/50 transition-all">
                    <div className="flex items-start justify-between mb-3">
                      <div>
                        <div className="font-bold text-text-primary flex items-center gap-2">
                          <span className="text-lg">{pos.symbol} ${pos.strike}{pos.option_type === 'CALL' ? 'C' : 'P'}</span>
                          {pos.unrealized_pnl >= 0 ? (
                            <ArrowUpRight className="w-5 h-5 text-success" />
                          ) : (
                            <ArrowDownRight className="w-5 h-5 text-danger" />
                          )}
                        </div>
                        <div className="text-xs text-text-muted mt-1">{pos.entry_date}</div>
                      </div>
                      <div className="text-right">
                        <div className={`text-2xl font-bold ${pos.unrealized_pnl >= 0 ? 'text-success' : 'text-danger'}`}>
                          {pos.unrealized_pnl >= 0 ? '+' : ''}{((pos.unrealized_pnl / (pos.entry_price * pos.contracts * 100)) * 100).toFixed(1)}%
                        </div>
                        <div className="text-sm text-text-muted">
                          {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl.toFixed(2)}
                        </div>
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-4 text-sm">
                      <div>
                        <div className="text-text-muted text-xs">Entry</div>
                        <div className="font-mono font-semibold text-text-primary">${pos.entry_price.toFixed(2)}</div>
                      </div>
                      <div>
                        <div className="text-text-muted text-xs">Current</div>
                        <div className="font-mono font-semibold text-text-primary">${pos.current_price.toFixed(2)}</div>
                      </div>
                      <div>
                        <div className="text-text-muted text-xs">Contracts</div>
                        <div className="font-mono font-semibold text-text-primary">{pos.contracts}</div>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* SPY Chart - Full Width */}
        <div className="mb-8">
          <div className="card bg-gradient-to-br from-background-card to-background-deep border border-border">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <BarChart3 className="w-7 h-7 text-primary" />
                <div>
                  <h2 className="text-2xl font-bold">SPY Market Overview</h2>
                  <p className="text-sm text-text-secondary">90-day candlestick • Live market data</p>
                </div>
              </div>
              {isConnected && (
                <div className="flex items-center gap-2 px-3 py-1 bg-success/20 rounded-full">
                  <div className="w-2 h-2 rounded-full bg-success animate-pulse"></div>
                  <span className="text-xs font-semibold text-success">Live</span>
                </div>
              )}
            </div>
            <div className="bg-background-deep rounded-xl overflow-hidden" style={{ height: 'calc(100vh - 400px)', minHeight: '600px' }}>
              <TradingViewWidget
                symbol="SPY"
                interval="D"
                theme="dark"
                height={600}
                autosize={true}
              />
            </div>
          </div>
        </div>

        {/* AI Intelligence */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <MarketCommentary />
          <DailyTradingPlan />
        </div>

        {/* Trade Activity */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          {/* Trade Log */}
          <div className="lg:col-span-2 card bg-gradient-to-br from-background-card to-background-deep border border-border">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Activity className="w-6 h-6 text-primary" />
                <h3 className="text-xl font-bold">Trade Activity</h3>
              </div>
              <button
                onClick={downloadTradeHistory}
                className="flex items-center gap-2 px-4 py-2 bg-primary/20 hover:bg-primary/30 text-primary rounded-lg transition-colors text-sm font-semibold"
              >
                <Download className="w-4 h-4" />
                Export CSV
              </button>
            </div>
            <div className="space-y-2 max-h-[400px] overflow-y-auto custom-scrollbar">
              {tradeLog.length === 0 ? (
                <div className="h-[400px] flex items-center justify-center">
                  <div className="text-center text-text-muted">
                    <Activity className="w-16 h-16 mx-auto mb-4 opacity-30" />
                    <p className="font-semibold">No Trades Today</p>
                    <p className="text-sm mt-2">Activity will appear during market hours</p>
                  </div>
                </div>
              ) : (
                tradeLog.map((entry, idx) => (
                  <div key={idx} className="flex items-center justify-between p-4 bg-background-hover rounded-lg hover:bg-background-deep transition-all border border-transparent hover:border-primary/30">
                    <div className="flex items-center gap-4">
                      <div className="text-xs text-text-muted font-mono bg-background-deep px-2 py-1 rounded">{formatTime(entry.time)}</div>
                      <div className="text-sm font-medium text-text-primary">{entry.action}</div>
                      <div className="text-sm text-text-secondary">{entry.details}</div>
                    </div>
                    {entry.pnl && (
                      <div className={`text-sm font-bold px-3 py-1 rounded-full ${entry.pnl >= 0 ? 'bg-success/20 text-success' : 'bg-danger/20 text-danger'}`}>
                        {entry.pnl >= 0 ? '+' : ''}${entry.pnl.toFixed(2)}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Best/Worst Trades */}
          <div className="space-y-4">
            <div className="card bg-gradient-to-br from-success/10 to-background-deep border-2 border-success/30">
              <div className="flex items-center gap-2 mb-3">
                <TrendingUp className="w-5 h-5 text-success" />
                <h3 className="text-lg font-bold text-success">Best Trade</h3>
              </div>
              {bestTrade && (bestTrade.pnl || 0) > 0 ? (
                <div>
                  <div className="text-4xl font-bold text-success mb-2">
                    +${(bestTrade.pnl || 0).toFixed(2)}
                  </div>
                  <div className="text-sm text-text-secondary mb-1">{bestTrade.details}</div>
                  <div className="text-xs text-text-muted">{formatTime(bestTrade.time)}</div>
                </div>
              ) : (
                <div className="py-8 text-center text-text-muted">
                  <p className="text-sm">No wins yet today</p>
                </div>
              )}
            </div>

            <div className="card bg-gradient-to-br from-danger/10 to-background-deep border-2 border-danger/30">
              <div className="flex items-center gap-2 mb-3">
                <TrendingDown className="w-5 h-5 text-danger" />
                <h3 className="text-lg font-bold text-danger">Worst Trade</h3>
              </div>
              {worstTrade && (worstTrade.pnl || 0) < 0 ? (
                <div>
                  <div className="text-4xl font-bold text-danger mb-2">
                    ${(worstTrade.pnl || 0).toFixed(2)}
                  </div>
                  <div className="text-sm text-text-secondary mb-1">{worstTrade.details}</div>
                  <div className="text-xs text-text-muted">{formatTime(worstTrade.time)}</div>
                </div>
              ) : (
                <div className="py-8 text-center text-text-muted">
                  <p className="text-sm">No losses yet today</p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="card bg-gradient-to-br from-background-card to-background-deep border border-border">
          <h3 className="text-xl font-bold mb-6 flex items-center gap-2">
            <Zap className="w-6 h-6 text-warning" />
            Quick Actions
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {[
              { icon: '🔍', label: 'Scanner', path: '/scanner', color: 'primary' },
              { icon: '📊', label: 'GEX', path: '/gex', color: 'success' },
              { icon: '⚡', label: 'Gamma', path: '/gamma', color: 'warning' },
              { icon: '🧠', label: 'Psychology', path: '/psychology', color: 'danger' },
              { icon: '🤖', label: 'Trader', path: '/trader', color: 'success' },
            ].map((action, idx) => (
              <button
                key={idx}
                onClick={() => router.push(action.path)}
                className="group p-6 rounded-xl bg-background-hover border border-border hover:border-primary/50 hover:bg-background-deep transition-all duration-300 hover:scale-105"
              >
                <div className="text-4xl mb-3 transform group-hover:scale-110 transition-transform">{action.icon}</div>
                <div className="text-sm font-semibold text-text-primary group-hover:text-primary transition-colors">{action.label}</div>
              </button>
            ))}
          </div>
        </div>

        </div>
      </main>

      <style jsx global>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 6px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: rgba(0, 0, 0, 0.1);
          border-radius: 10px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(99, 102, 241, 0.5);
          border-radius: 10px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(99, 102, 241, 0.7);
        }
      `}</style>
    </div>
  )
}
