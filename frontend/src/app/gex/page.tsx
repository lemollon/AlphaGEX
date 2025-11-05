'use client'

import { useState, useEffect } from 'react'
import { TrendingUp, TrendingDown, Activity, BarChart3, AlertTriangle } from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import { useWebSocket } from '@/hooks/useWebSocket'
import GEXProfileChart from '@/components/GEXProfileChart'

interface GEXLevel {
  strike: number
  call_gex: number
  put_gex: number
  total_gex: number
  call_oi: number
  put_oi: number
  pcr: number
}

interface GEXData {
  symbol: string
  spot_price: number
  total_call_gex: number
  total_put_gex: number
  net_gex: number
  gex_flip_point: number
  key_levels: {
    resistance: number[]
    support: number[]
  }
}

export default function GEXAnalysis() {
  const [symbol, setSymbol] = useState('SPY')
  const [gexData, setGexData] = useState<GEXData | null>(null)
  const [gexLevels, setGexLevels] = useState<GEXLevel[]>([])
  const [loading, setLoading] = useState(true)
  const { data: wsData, isConnected } = useWebSocket(symbol)

  // Fetch GEX data
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)
        const [gexResponse, levelsResponse] = await Promise.all([
          apiClient.getGEX(symbol),
          apiClient.getGEXLevels(symbol)
        ])
        // Fix: Transform API response to match frontend interface
        const rawData = gexResponse.data.data
        const transformedData = {
          symbol: rawData.symbol || symbol,
          spot_price: rawData.spot_price || 0,
          total_call_gex: rawData.total_call_gex || 0,
          total_put_gex: rawData.total_put_gex || 0,
          net_gex: rawData.net_gex || 0,
          gex_flip_point: rawData.flip_point || rawData.gex_flip_point || 0,
          key_levels: {
            resistance: rawData.key_levels?.resistance || [],
            support: rawData.key_levels?.support || []
          }
        }
        setGexData(transformedData)
        setGexLevels(levelsResponse.data.levels || levelsResponse.data.data || [])
      } catch (error) {
        console.error('Error fetching GEX data:', error)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [symbol])

  // Update from WebSocket
  useEffect(() => {
    if (wsData?.type === 'gex_update' && wsData.data) {
      setGexData(wsData.data)
    }
  }, [wsData])

  const formatGEX = (value: number) => {
    const absValue = Math.abs(value)
    if (absValue >= 1e9) return `${(value / 1e9).toFixed(2)}B`
    if (absValue >= 1e6) return `${(value / 1e6).toFixed(2)}M`
    return value.toFixed(2)
  }

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2
    }).format(value)
  }

  const popularSymbols = ['SPY', 'QQQ', 'IWM', 'AAPL', 'TSLA', 'NVDA', 'AMD', 'AMZN']

  return (
    <div className="min-h-screen">
      <Navigation />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="space-y-6">
          {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-text-primary">GEX Analysis</h1>
          <p className="text-text-secondary mt-1">Deep dive into Gamma Exposure levels</p>
        </div>
        <div className="flex items-center gap-2">
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg ${
            isConnected ? 'bg-success/10 text-success' : 'bg-danger/10 text-danger'
          }`}>
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-success' : 'bg-danger'} animate-pulse`} />
            <span className="text-sm font-medium">{isConnected ? 'Live' : 'Disconnected'}</span>
          </div>
        </div>
      </div>

      {/* Symbol Selector */}
      <div className="card">
        <div className="flex items-center gap-4 flex-wrap">
          <label className="text-text-secondary font-medium">Symbol:</label>
          <div className="flex gap-2 flex-wrap">
            {popularSymbols.map((sym) => (
              <button
                key={sym}
                onClick={() => setSymbol(sym)}
                className={`px-4 py-2 rounded-lg font-medium transition-all ${
                  symbol === sym
                    ? 'bg-primary text-white'
                    : 'bg-background-hover text-text-secondary hover:bg-background-hover/70 hover:text-text-primary'
                }`}
              >
                {sym}
              </button>
            ))}
          </div>
          <input
            type="text"
            placeholder="Custom symbol..."
            className="input flex-1 min-w-[200px]"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                const value = (e.target as HTMLInputElement).value.trim().toUpperCase()
                if (value) setSymbol(value)
              }
            }}
          />
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="card h-24 skeleton" />
          ))}
        </div>
      ) : gexData ? (
        <>
          {/* Key Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="card">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-text-secondary text-sm">Spot Price</p>
                  <p className="text-2xl font-bold text-text-primary mt-1">
                    {formatCurrency(gexData.spot_price)}
                  </p>
                </div>
                <Activity className="text-primary w-8 h-8" />
              </div>
            </div>

            <div className="card">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-text-secondary text-sm">Net GEX</p>
                  <p className={`text-2xl font-bold mt-1 ${
                    gexData.net_gex > 0 ? 'text-success' : 'text-danger'
                  }`}>
                    {formatGEX(gexData.net_gex)}
                  </p>
                </div>
                {gexData.net_gex > 0 ? (
                  <TrendingUp className="text-success w-8 h-8" />
                ) : (
                  <TrendingDown className="text-danger w-8 h-8" />
                )}
              </div>
            </div>

            <div className="card">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-text-secondary text-sm">Call GEX</p>
                  <p className="text-2xl font-bold text-success mt-1">
                    {formatGEX(gexData.total_call_gex)}
                  </p>
                </div>
                <TrendingUp className="text-success w-8 h-8" />
              </div>
            </div>

            <div className="card">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-text-secondary text-sm">Put GEX</p>
                  <p className="text-2xl font-bold text-danger mt-1">
                    {formatGEX(Math.abs(gexData.total_put_gex))}
                  </p>
                </div>
                <TrendingDown className="text-danger w-8 h-8" />
              </div>
            </div>
          </div>

          {/* GEX Profile Chart */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-text-primary">GEX Profile</h2>
              <BarChart3 className="text-primary w-6 h-6" />
            </div>
            {gexLevels.length > 0 ? (
              <GEXProfileChart
                data={gexLevels}
                spotPrice={gexData.spot_price}
                height={384}
              />
            ) : (
              <div className="h-96 bg-background-deep rounded-lg flex items-center justify-center border border-border">
                <div className="text-center">
                  <BarChart3 className="w-16 h-16 text-text-muted mx-auto mb-2" />
                  <p className="text-text-secondary">Loading GEX profile...</p>
                </div>
              </div>
            )}
          </div>

          {/* Key Levels */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Resistance Levels */}
            <div className="card">
              <div className="flex items-center gap-2 mb-4">
                <TrendingUp className="text-danger w-5 h-5" />
                <h2 className="text-lg font-semibold text-text-primary">Resistance Levels</h2>
              </div>
              <div className="space-y-2">
                {gexData.key_levels.resistance.map((level, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-3 bg-danger/5 border border-danger/20 rounded-lg"
                  >
                    <span className="text-text-secondary">R{idx + 1}</span>
                    <span className="text-danger font-semibold">{formatCurrency(level)}</span>
                    <span className="text-text-muted text-sm">
                      {((level - gexData.spot_price) / gexData.spot_price * 100).toFixed(2)}% away
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Support Levels */}
            <div className="card">
              <div className="flex items-center gap-2 mb-4">
                <TrendingDown className="text-success w-5 h-5" />
                <h2 className="text-lg font-semibold text-text-primary">Support Levels</h2>
              </div>
              <div className="space-y-2">
                {gexData.key_levels.support.map((level, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-3 bg-success/5 border border-success/20 rounded-lg"
                  >
                    <span className="text-text-secondary">S{idx + 1}</span>
                    <span className="text-success font-semibold">{formatCurrency(level)}</span>
                    <span className="text-text-muted text-sm">
                      {((gexData.spot_price - level) / gexData.spot_price * 100).toFixed(2)}% away
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* GEX Flip Point Alert */}
          <div className="card bg-warning/5 border border-warning/20">
            <div className="flex items-start gap-3">
              <AlertTriangle className="text-warning w-6 h-6 flex-shrink-0 mt-1" />
              <div>
                <h3 className="text-lg font-semibold text-warning mb-2">GEX Flip Point</h3>
                <p className="text-text-secondary mb-2">
                  The point where Net GEX changes from positive to negative, indicating a shift in market dynamics.
                </p>
                <div className="flex items-center gap-4 mt-3">
                  <div>
                    <p className="text-text-muted text-sm">Flip Point</p>
                    <p className="text-2xl font-bold text-warning">{formatCurrency(gexData.gex_flip_point)}</p>
                  </div>
                  <div>
                    <p className="text-text-muted text-sm">Distance</p>
                    <p className="text-xl font-semibold text-text-primary">
                      {((gexData.gex_flip_point - gexData.spot_price) / gexData.spot_price * 100).toFixed(2)}%
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* GEX Levels Table */}
          <div className="card">
            <h2 className="text-xl font-semibold text-text-primary mb-4">Strike-Level GEX Breakdown</h2>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-3 px-4 text-text-secondary font-medium">Strike</th>
                    <th className="text-right py-3 px-4 text-text-secondary font-medium">Call GEX</th>
                    <th className="text-right py-3 px-4 text-text-secondary font-medium">Put GEX</th>
                    <th className="text-right py-3 px-4 text-text-secondary font-medium">Total GEX</th>
                    <th className="text-right py-3 px-4 text-text-secondary font-medium">Call OI</th>
                    <th className="text-right py-3 px-4 text-text-secondary font-medium">Put OI</th>
                    <th className="text-right py-3 px-4 text-text-secondary font-medium">P/C Ratio</th>
                  </tr>
                </thead>
                <tbody>
                  {gexLevels.slice(0, 20).map((level, idx) => (
                    <tr
                      key={idx}
                      className={`border-b border-border/50 hover:bg-background-hover transition-colors ${
                        level.strike === Math.round(gexData.spot_price) ? 'bg-primary/5' : ''
                      }`}
                    >
                      <td className="py-3 px-4 font-medium text-text-primary">
                        {formatCurrency(level.strike)}
                      </td>
                      <td className="py-3 px-4 text-right text-success">{formatGEX(level.call_gex)}</td>
                      <td className="py-3 px-4 text-right text-danger">{formatGEX(level.put_gex)}</td>
                      <td className={`py-3 px-4 text-right font-semibold ${
                        level.total_gex > 0 ? 'text-success' : 'text-danger'
                      }`}>
                        {formatGEX(level.total_gex)}
                      </td>
                      <td className="py-3 px-4 text-right text-text-secondary">
                        {level.call_oi.toLocaleString()}
                      </td>
                      <td className="py-3 px-4 text-right text-text-secondary">
                        {level.put_oi.toLocaleString()}
                      </td>
                      <td className="py-3 px-4 text-right text-text-primary">{level.pcr.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : (
        <div className="card text-center py-12">
          <p className="text-text-secondary">No data available for {symbol}</p>
        </div>
      )}
        </div>
      </main>
    </div>
  )
}
