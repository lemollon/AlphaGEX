'use client'

import { useState, useEffect } from 'react'
import { BarChart3, TrendingUp, TrendingDown, Activity, RefreshCw } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, CandlestickChart } from 'recharts'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'

interface PricePoint {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export default function AdvancedCharts() {
  const [loading, setLoading] = useState(true)
  const [priceData, setPriceData] = useState<PricePoint[]>([])
  const [symbol, setSymbol] = useState('SPY')
  const [timeframe, setTimeframe] = useState<'1M' | '3M' | '6M' | '1Y'>('3M')
  const [error, setError] = useState<string | null>(null)

  const fetchData = async () => {
    try {
      setLoading(true)
      const days = timeframe === '1M' ? 30 : timeframe === '3M' ? 90 : timeframe === '6M' ? 180 : 365
      const res = await apiClient.getPriceHistory(symbol, days).catch(() => ({ data: { success: false } }))

      if (res.data.success && res.data.data) {
        setPriceData(res.data.data)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load price data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [symbol, timeframe])

  const latestPrice = priceData.length > 0 ? priceData[priceData.length - 1]?.close : null
  const firstPrice = priceData.length > 0 ? priceData[0]?.close : null
  const priceChange = latestPrice && firstPrice ? ((latestPrice - firstPrice) / firstPrice) * 100 : 0
  const isPositive = priceChange >= 0

  return (
    <div className="min-h-screen">
      <Navigation />
      <main className="pt-16 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div>
                <div className="flex items-center gap-3">
                  <BarChart3 className="w-8 h-8 text-primary" />
                  <h1 className="text-3xl font-bold text-text-primary">Advanced Charts</h1>
                </div>
                <p className="text-text-secondary mt-1">Price history and technical analysis</p>
              </div>

              <div className="flex items-center gap-3">
                {/* Symbol Selector */}
                <select
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  className="px-4 py-2 bg-background-hover border border-border rounded-lg text-text-primary"
                >
                  <option value="SPY">SPY</option>
                  <option value="QQQ">QQQ</option>
                  <option value="IWM">IWM</option>
                  <option value="SPX">SPX</option>
                </select>

                {/* Timeframe Selector */}
                <div className="flex bg-background-hover rounded-lg p-1">
                  {(['1M', '3M', '6M', '1Y'] as const).map((tf) => (
                    <button
                      key={tf}
                      onClick={() => setTimeframe(tf)}
                      className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                        timeframe === tf
                          ? 'bg-primary text-white'
                          : 'text-text-secondary hover:text-text-primary'
                      }`}
                    >
                      {tf}
                    </button>
                  ))}
                </div>

                <button
                  onClick={fetchData}
                  disabled={loading}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg font-semibold bg-primary text-white hover:bg-primary/90 disabled:opacity-50"
                >
                  <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                </button>
              </div>
            </div>

            {/* Price Summary */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="card">
                <p className="text-text-secondary text-sm">Symbol</p>
                <p className="text-2xl font-bold text-text-primary mt-1">{symbol}</p>
              </div>
              <div className="card">
                <p className="text-text-secondary text-sm">Current Price</p>
                <p className="text-2xl font-bold text-text-primary mt-1">
                  ${latestPrice?.toFixed(2) || '--'}
                </p>
              </div>
              <div className="card">
                <p className="text-text-secondary text-sm">Period Change</p>
                <p className={`text-2xl font-bold mt-1 ${isPositive ? 'text-success' : 'text-danger'}`}>
                  {isPositive ? '+' : ''}{priceChange.toFixed(2)}%
                </p>
              </div>
              <div className="card">
                <p className="text-text-secondary text-sm">Data Points</p>
                <p className="text-2xl font-bold text-text-primary mt-1">{priceData.length}</p>
              </div>
            </div>

            {/* Main Chart */}
            <div className="card">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold text-text-primary">{symbol} Price Chart</h2>
                <span className="text-sm text-text-muted">{timeframe} timeframe</span>
              </div>

              {loading ? (
                <div className="h-96 flex items-center justify-center">
                  <Activity className="w-8 h-8 text-primary animate-spin" />
                </div>
              ) : priceData.length > 0 ? (
                <div className="h-96">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={priceData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={isPositive ? "#10b981" : "#ef4444"} stopOpacity={0.3}/>
                          <stop offset="95%" stopColor={isPositive ? "#10b981" : "#ef4444"} stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis
                        dataKey="date"
                        stroke="#9ca3af"
                        tick={{ fontSize: 12 }}
                        tickFormatter={(value) => new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                      />
                      <YAxis
                        stroke="#9ca3af"
                        tick={{ fontSize: 12 }}
                        domain={['auto', 'auto']}
                        tickFormatter={(value) => `$${value}`}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#1f2937',
                          border: '1px solid #374151',
                          borderRadius: '8px'
                        }}
                        labelFormatter={(value) => new Date(value).toLocaleDateString()}
                        formatter={(value: number) => [`$${value.toFixed(2)}`, 'Close']}
                      />
                      <Area
                        type="monotone"
                        dataKey="close"
                        stroke={isPositive ? "#10b981" : "#ef4444"}
                        strokeWidth={2}
                        fillOpacity={1}
                        fill="url(#colorPrice)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="h-96 flex items-center justify-center">
                  <div className="text-center">
                    <BarChart3 className="w-12 h-12 text-text-muted mx-auto mb-3" />
                    <p className="text-text-secondary">No price data available</p>
                    <p className="text-text-muted text-sm mt-1">Try a different symbol or timeframe</p>
                  </div>
                </div>
              )}
            </div>

            {/* OHLC Data Table */}
            {priceData.length > 0 && (
              <div className="card">
                <h2 className="text-xl font-semibold text-text-primary mb-4">Recent Price Data</h2>
                <div className="overflow-x-auto max-h-96">
                  <table className="w-full">
                    <thead className="sticky top-0 bg-background-card">
                      <tr className="border-b border-border">
                        <th className="text-left py-3 px-4 text-text-secondary font-medium">Date</th>
                        <th className="text-right py-3 px-4 text-text-secondary font-medium">Open</th>
                        <th className="text-right py-3 px-4 text-text-secondary font-medium">High</th>
                        <th className="text-right py-3 px-4 text-text-secondary font-medium">Low</th>
                        <th className="text-right py-3 px-4 text-text-secondary font-medium">Close</th>
                        <th className="text-right py-3 px-4 text-text-secondary font-medium">Change</th>
                      </tr>
                    </thead>
                    <tbody>
                      {priceData.slice(-20).reverse().map((point, idx) => {
                        const change = ((point.close - point.open) / point.open) * 100
                        return (
                          <tr key={idx} className="border-b border-border/50 hover:bg-background-hover">
                            <td className="py-3 px-4 text-text-primary">
                              {new Date(point.date).toLocaleDateString()}
                            </td>
                            <td className="py-3 px-4 text-right text-text-primary">${point.open?.toFixed(2)}</td>
                            <td className="py-3 px-4 text-right text-success">${point.high?.toFixed(2)}</td>
                            <td className="py-3 px-4 text-right text-danger">${point.low?.toFixed(2)}</td>
                            <td className="py-3 px-4 text-right text-text-primary font-semibold">${point.close?.toFixed(2)}</td>
                            <td className={`py-3 px-4 text-right font-semibold ${change >= 0 ? 'text-success' : 'text-danger'}`}>
                              {change >= 0 ? '+' : ''}{change.toFixed(2)}%
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
