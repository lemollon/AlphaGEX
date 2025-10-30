'use client'

import { useEffect, useState } from 'react'
import Navigation from '@/components/Navigation'
import StatusCard from '@/components/StatusCard'
import { apiClient } from '@/lib/api'
import { useWebSocket } from '@/hooks/useWebSocket'
import {
  TrendingDown,
  Zap,
  Target,
  Activity,
  TrendingUp,
  ArrowUpRight,
  ArrowDownRight,
  DollarSign
} from 'lucide-react'

export default function Dashboard() {
  const [gexData, setGexData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const { data: wsData, isConnected } = useWebSocket('SPY')

  useEffect(() => {
    // Fetch initial GEX data
    const fetchData = async () => {
      try {
        const response = await apiClient.getGEX('SPY')
        setGexData(response.data.data)
        setLoading(false)
      } catch (error) {
        console.error('Failed to fetch GEX data:', error)
        setLoading(false)
      }
    }

    fetchData()
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

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Status Cards */}
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
            changeType={spotPrice < flipPoint ? 'warning' : 'neutral'}
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
            value="62%"
            change="18 / 29 trades"
            changeType="positive"
            subtitle="Last 30 days"
          />
        </div>

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          {/* Market Overview Chart */}
          <div className="lg:col-span-2">
            <div className="card">
              <h2 className="text-xl font-semibold mb-4 flex items-center space-x-2">
                <TrendingUp className="w-5 h-5 text-primary" />
                <span>Market Overview</span>
                {isConnected && (
                  <span className="flex items-center space-x-1 text-xs text-success">
                    <div className="w-2 h-2 rounded-full bg-success animate-pulse"></div>
                    <span>Live</span>
                  </span>
                )}
              </h2>

              <div className="bg-background-deep rounded-lg p-6 h-80 flex items-center justify-center">
                <div className="text-center text-text-muted">
                  <TrendingUp className="w-16 h-16 mx-auto mb-4 opacity-50" />
                  <p>Chart Component</p>
                  <p className="text-sm">TradingView chart will be integrated here</p>
                </div>
              </div>

              <div className="mt-4 p-4 bg-background-hover rounded-lg">
                <p className="text-sm text-text-secondary mb-2">Today's Recommendation (from AI):</p>
                <p className="text-text-primary">
                  🤖 "Negative GEX squeeze setup forming. Consider SPY 585C for momentum play.
                  Target: $590 (Call Wall) | Stop: $575 (-1.5% risk)"
                </p>
              </div>
            </div>
          </div>

          {/* Active Positions */}
          <div className="card">
            <h3 className="text-lg font-semibold mb-4 flex items-center justify-between">
              <span className="flex items-center space-x-2">
                <DollarSign className="w-5 h-5 text-success" />
                <span>Active Positions</span>
              </span>
              <span className="text-sm font-normal text-text-secondary">(3)</span>
            </h3>

            <div className="space-y-3">
              {/* Position Card 1 */}
              <div className="bg-background-hover rounded-lg p-4 hover:bg-background-deep transition-colors cursor-pointer">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <div className="font-semibold text-text-primary flex items-center space-x-2">
                      <span>SPY 580C</span>
                      <ArrowUpRight className="w-4 h-4 text-success" />
                    </div>
                    <div className="text-xs text-text-muted">Opened today</div>
                  </div>
                  <div className="text-right">
                    <div className="text-success font-semibold">+38%</div>
                    <div className="text-xs text-text-muted">+$160</div>
                  </div>
                </div>
                <div className="text-sm space-y-1">
                  <div className="flex justify-between text-text-secondary">
                    <span>Entry:</span>
                    <span className="text-text-primary font-mono">$4.20</span>
                  </div>
                  <div className="flex justify-between text-text-secondary">
                    <span>Current:</span>
                    <span className="text-text-primary font-mono">$5.80</span>
                  </div>
                </div>
                <button className="w-full mt-3 text-xs btn bg-background-deep text-text-secondary hover:text-text-primary">
                  Close Position
                </button>
              </div>

              {/* Position Card 2 */}
              <div className="bg-background-hover rounded-lg p-4 hover:bg-background-deep transition-colors cursor-pointer">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <div className="font-semibold text-text-primary flex items-center space-x-2">
                      <span>QQQ 390P</span>
                      <ArrowDownRight className="w-4 h-4 text-danger" />
                    </div>
                    <div className="text-xs text-text-muted">2 days ago</div>
                  </div>
                  <div className="text-right">
                    <div className="text-danger font-semibold">-12%</div>
                    <div className="text-xs text-text-muted">-$25</div>
                  </div>
                </div>
                <div className="text-sm space-y-1">
                  <div className="flex justify-between text-text-secondary">
                    <span>Entry:</span>
                    <span className="text-text-primary font-mono">$2.10</span>
                  </div>
                  <div className="flex justify-between text-text-secondary">
                    <span>Current:</span>
                    <span className="text-text-primary font-mono">$1.85</span>
                  </div>
                </div>
                <button className="w-full mt-3 text-xs btn bg-background-deep text-text-secondary hover:text-text-primary">
                  Close Position
                </button>
              </div>

              {/* Position Card 3 */}
              <div className="bg-background-hover rounded-lg p-4 hover:bg-background-deep transition-colors cursor-pointer">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <div className="font-semibold text-text-primary flex items-center space-x-2">
                      <span>AAPL 185C</span>
                      <ArrowUpRight className="w-4 h-4 text-success" />
                    </div>
                    <div className="text-xs text-text-muted">3 days ago</div>
                  </div>
                  <div className="text-right">
                    <div className="text-success font-semibold">+22%</div>
                    <div className="text-xs text-text-muted">+$88</div>
                  </div>
                </div>
                <div className="text-sm space-y-1">
                  <div className="flex justify-between text-text-secondary">
                    <span>Entry:</span>
                    <span className="text-text-primary font-mono">$4.00</span>
                  </div>
                  <div className="flex justify-between text-text-secondary">
                    <span>Current:</span>
                    <span className="text-text-primary font-mono">$4.88</span>
                  </div>
                </div>
                <button className="w-full mt-3 text-xs btn bg-background-deep text-text-secondary hover:text-text-primary">
                  Close Position
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="card mb-8">
          <h3 className="text-lg font-semibold mb-4">⚡ Quick Actions</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <button className="btn-primary flex flex-col items-center space-y-2 py-4">
              <span className="text-2xl">🤖</span>
              <span>Ask AI</span>
            </button>
            <button className="btn-secondary flex flex-col items-center space-y-2 py-4">
              <span className="text-2xl">📊</span>
              <span>Scan Market</span>
            </button>
            <button className="btn-secondary flex flex-col items-center space-y-2 py-4">
              <span className="text-2xl">💰</span>
              <span>Position Sizer</span>
            </button>
            <button className="btn-secondary flex flex-col items-center space-y-2 py-4">
              <span className="text-2xl">🔔</span>
              <span>Alerts</span>
            </button>
            <button className="btn-secondary flex flex-col items-center space-y-2 py-4">
              <span className="text-2xl">⚙️</span>
              <span>Settings</span>
            </button>
          </div>
        </div>

        {/* Bottom Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Trade Log */}
          <div className="card">
            <h3 className="text-lg font-semibold mb-4">📅 Today's Trade Log</h3>
            <div className="space-y-2">
              <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
                <div className="flex items-center space-x-3">
                  <div className="text-xs text-text-muted">09:45 AM</div>
                  <div className="text-sm text-text-primary">Opened SPY 580C</div>
                </div>
                <div className="text-success text-sm">+$160</div>
              </div>
              <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
                <div className="flex items-center space-x-3">
                  <div className="text-xs text-text-muted">10:23 AM</div>
                  <div className="text-sm text-text-primary">Closed QQQ 385P</div>
                </div>
                <div className="text-danger text-sm">-$35</div>
              </div>
              <div className="flex items-center justify-between p-3 bg-background-hover rounded-lg">
                <div className="flex items-center space-x-3">
                  <div className="text-xs text-text-muted">11:02 AM</div>
                  <div className="text-sm text-text-primary">Opened AAPL 185C</div>
                </div>
                <div className="text-success text-sm">+$88</div>
              </div>
            </div>
          </div>

          {/* Performance */}
          <div className="card">
            <h3 className="text-lg font-semibold mb-4">📊 Performance (Last 30 Days)</h3>
            <div className="bg-background-deep rounded-lg p-6 h-48 flex items-center justify-center">
              <div className="text-center text-text-muted">
                <TrendingUp className="w-12 h-12 mx-auto mb-2 opacity-50" />
                <p className="text-sm">Equity Curve Chart</p>
                <p className="text-xs">$5,000 → $5,420 (+8.4%)</p>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
