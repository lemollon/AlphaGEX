'use client'

import { useState, useEffect, useCallback } from 'react'
import { TrendingUp, TrendingDown, Activity, BarChart3, AlertTriangle, RefreshCw } from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useDataCache } from '@/hooks/useDataCache'
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
  flip_point?: number
  call_wall?: number
  put_wall?: number
  key_levels: {
    resistance: number[]
    support: number[]
  }
}

export default function GEXAnalysis() {
  const [symbol, setSymbol] = useState('SPY')
  const [gexData, setGexData] = useState<GEXData | null>(null)
  const [gexLevels, setGexLevels] = useState<GEXLevel[]>([])
  const [loading, setLoading] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { data: wsData, isConnected } = useWebSocket(symbol)

  // Cache for GEX data (5 minutes TTL)
  const gexCache = useDataCache<GEXData>({
    key: `gex-data-${symbol}`,
    ttl: 5 * 60 * 1000 // 5 minutes
  })

  const levelsCache = useDataCache<GEXLevel[]>({
    key: `gex-levels-${symbol}`,
    ttl: 5 * 60 * 1000
  })

  // Fetch GEX data
  const fetchData = useCallback(async (forceRefresh = false) => {
    // Use cached data if fresh and not forcing refresh
    if (!forceRefresh && gexCache.isCacheFresh && levelsCache.isCacheFresh) {
      if (gexCache.cachedData) setGexData(gexCache.cachedData)
      if (levelsCache.cachedData) setGexLevels(levelsCache.cachedData)
      return
    }

    try {
      forceRefresh ? setIsRefreshing(true) : setLoading(true)
      setError(null)

      const [gexResponse, levelsResponse] = await Promise.all([
        apiClient.getGEX(symbol),
        apiClient.getGEXLevels(symbol)
      ])

      // Transform API response to match frontend interface
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

      const levelsData = levelsResponse.data.levels || levelsResponse.data.data || []

      // Extract reference line values from levels response
      const flipPoint = levelsResponse.data.flip_point || 0
      const callWall = levelsResponse.data.call_wall || 0
      const putWall = levelsResponse.data.put_wall || 0

      // Update state and cache
      setGexData({
        ...transformedData,
        flip_point: flipPoint,
        call_wall: callWall,
        put_wall: putWall
      })
      setGexLevels(levelsData)
      gexCache.setCache(transformedData)
      levelsCache.setCache(levelsData)
    } catch (error: any) {
      console.error('Error fetching GEX data:', error)
      const errorMessage = error.response?.data?.detail || error.message || 'Failed to fetch GEX data'
      setError(errorMessage)
    } finally {
      setLoading(false)
      setIsRefreshing(false)
    }
  }, [symbol, gexCache, levelsCache])

  // Initial load and symbol change
  useEffect(() => {
    fetchData()
  }, [symbol])

  // Manual refresh handler
  const handleRefresh = () => {
    fetchData(true)
  }

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
          {/* Refresh Button */}
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-background-hover hover:bg-background-hover/70 text-text-primary transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            <span className="text-sm font-medium hidden sm:inline">
              {isRefreshing ? 'Refreshing...' : 'Refresh'}
            </span>
          </button>

          {/* Cache Status */}
          {gexCache.isCacheFresh && !isRefreshing && (
            <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary/10 text-primary text-sm">
              <Activity className="w-4 h-4" />
              <span>Cached {Math.floor(gexCache.timeUntilExpiry / 1000 / 60)}m</span>
            </div>
          )}

          {/* Live Status */}
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
              <div className="flex items-center gap-3">
                {loading && (
                  <div className="flex items-center gap-2 text-sm text-text-secondary">
                    <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                    <span>Loading data...</span>
                  </div>
                )}
                <BarChart3 className="text-primary w-6 h-6" />
              </div>
            </div>
            {gexLevels.length > 0 ? (
              <GEXProfileChart
                data={gexLevels}
                spotPrice={gexData.spot_price}
                flipPoint={gexData.flip_point}
                callWall={gexData.call_wall}
                putWall={gexData.put_wall}
                height={600}
              />
            ) : loading ? (
              <div className="h-96 bg-background-deep rounded-lg flex items-center justify-center border border-border">
                <div className="text-center">
                  <div className="w-16 h-16 border-4 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
                  <p className="text-text-primary font-medium mb-1">Loading GEX Profile</p>
                  <p className="text-text-secondary text-sm">Fetching strike-level data for {symbol}...</p>
                </div>
              </div>
            ) : (
              <div className="h-96 bg-background-deep rounded-lg flex items-center justify-center border border-border">
                <div className="text-center">
                  <BarChart3 className="w-16 h-16 text-text-muted mx-auto mb-2" />
                  <p className="text-text-secondary">No GEX profile data available for {symbol}</p>
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
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-xl font-semibold text-text-primary">Strike-Level GEX Breakdown</h2>
                <p className="text-sm text-text-secondary mt-1">
                  Detailed gamma exposure by strike price - {gexLevels.length} strikes loaded
                </p>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <div className="px-3 py-1 rounded bg-success/10 text-success">
                  <span className="font-medium">●</span> Call GEX
                </div>
                <div className="px-3 py-1 rounded bg-danger/10 text-danger">
                  <span className="font-medium">●</span> Put GEX
                </div>
              </div>
            </div>

            {gexLevels.length > 0 ? (
              <div className="overflow-x-auto -mx-4 sm:mx-0">
                <div className="inline-block min-w-full align-middle">
                  <div className="overflow-hidden border border-border rounded-lg">
                    <table className="min-w-full divide-y divide-border">
                      <thead className="bg-background-deep">
                        <tr>
                          <th scope="col" className="sticky left-0 z-10 bg-background-deep px-4 py-3.5 text-left text-sm font-semibold text-text-primary">
                            Strike
                          </th>
                          <th scope="col" className="px-4 py-3.5 text-right text-sm font-semibold text-text-primary">
                            Call GEX
                          </th>
                          <th scope="col" className="px-4 py-3.5 text-right text-sm font-semibold text-text-primary">
                            Put GEX
                          </th>
                          <th scope="col" className="px-4 py-3.5 text-right text-sm font-semibold text-text-primary">
                            Net GEX
                          </th>
                          <th scope="col" className="px-4 py-3.5 text-right text-sm font-semibold text-text-primary">
                            Call OI
                          </th>
                          <th scope="col" className="px-4 py-3.5 text-right text-sm font-semibold text-text-primary">
                            Put OI
                          </th>
                          <th scope="col" className="px-4 py-3.5 text-right text-sm font-semibold text-text-primary">
                            P/C Ratio
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border bg-background">
                        {gexLevels.map((level, idx) => {
                          const isAtMoney = Math.abs(level.strike - gexData.spot_price) < (gexData.spot_price * 0.005)
                          const distance = ((level.strike - gexData.spot_price) / gexData.spot_price * 100)

                          return (
                            <tr
                              key={idx}
                              className={`hover:bg-background-hover transition-colors ${
                                isAtMoney ? 'bg-primary/10 border-l-4 border-l-primary' : ''
                              }`}
                            >
                              <td className="sticky left-0 z-10 bg-background whitespace-nowrap px-4 py-3 text-sm">
                                <div className="flex flex-col">
                                  <span className={`font-semibold ${isAtMoney ? 'text-primary' : 'text-text-primary'}`}>
                                    {formatCurrency(level.strike)}
                                  </span>
                                  <span className="text-xs text-text-muted">
                                    {distance > 0 ? '+' : ''}{distance.toFixed(1)}%
                                  </span>
                                </div>
                              </td>
                              <td className="whitespace-nowrap px-4 py-3 text-sm text-right">
                                <div className="flex flex-col items-end">
                                  <span className="font-medium text-success">{formatGEX(level.call_gex)}</span>
                                  <div className="w-full max-w-[80px] h-1 bg-background-deep rounded-full mt-1">
                                    <div
                                      className="h-full bg-success rounded-full"
                                      style={{
                                        width: `${Math.min(100, (Math.abs(level.call_gex) / Math.max(...gexLevels.map(l => Math.abs(l.call_gex)))) * 100)}%`
                                      }}
                                    />
                                  </div>
                                </div>
                              </td>
                              <td className="whitespace-nowrap px-4 py-3 text-sm text-right">
                                <div className="flex flex-col items-end">
                                  <span className="font-medium text-danger">{formatGEX(Math.abs(level.put_gex))}</span>
                                  <div className="w-full max-w-[80px] h-1 bg-background-deep rounded-full mt-1">
                                    <div
                                      className="h-full bg-danger rounded-full"
                                      style={{
                                        width: `${Math.min(100, (Math.abs(level.put_gex) / Math.max(...gexLevels.map(l => Math.abs(l.put_gex)))) * 100)}%`
                                      }}
                                    />
                                  </div>
                                </div>
                              </td>
                              <td className="whitespace-nowrap px-4 py-3 text-sm text-right">
                                <span className={`font-bold ${
                                  level.total_gex > 0 ? 'text-success' : 'text-danger'
                                }`}>
                                  {formatGEX(level.total_gex)}
                                </span>
                              </td>
                              <td className="whitespace-nowrap px-4 py-3 text-sm text-right text-text-secondary">
                                {level.call_oi.toLocaleString()}
                              </td>
                              <td className="whitespace-nowrap px-4 py-3 text-sm text-right text-text-secondary">
                                {level.put_oi.toLocaleString()}
                              </td>
                              <td className="whitespace-nowrap px-4 py-3 text-sm text-right">
                                <span className={`font-medium ${
                                  level.pcr > 1.5 ? 'text-danger' : level.pcr < 0.7 ? 'text-success' : 'text-text-primary'
                                }`}>
                                  {level.pcr.toFixed(2)}
                                </span>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-12 border border-border rounded-lg">
                <BarChart3 className="w-12 h-12 text-text-muted mx-auto mb-3" />
                <p className="text-text-secondary">No strike-level data available</p>
              </div>
            )}
          </div>
        </>
      ) : error ? (
        <div className="card text-center py-12">
          <div className="max-w-2xl mx-auto">
            <AlertTriangle className="w-16 h-16 text-danger mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-text-primary mb-2">Failed to Load GEX Data</h3>
            <p className="text-text-secondary mb-4">{error}</p>
            <div className="flex items-center justify-center gap-4">
              <button
                onClick={handleRefresh}
                className="px-6 py-2 bg-primary hover:bg-primary/80 text-white rounded-lg font-medium transition-all"
              >
                Try Again
              </button>
              <a
                href="https://alphagex-api.onrender.com/api/diagnostic"
                target="_blank"
                rel="noopener noreferrer"
                className="px-6 py-2 bg-background-hover hover:bg-background-hover/70 text-text-primary rounded-lg font-medium transition-all"
              >
                View Diagnostics
              </a>
            </div>
          </div>
        </div>
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
