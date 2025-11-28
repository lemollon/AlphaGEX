'use client'

import { useState, useEffect, useCallback } from 'react'
import { AlertTriangle, TrendingUp, TrendingDown, Clock, Zap, Target, Calendar, Activity, RefreshCw, BarChart3, DollarSign } from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import { useRouter } from 'next/navigation'

interface DirectionalPrediction {
  direction: string
  direction_emoji: string
  probability: number
  bullish_score: number
  expected_move: string
  expected_range: string
  range_width_pct: string
  spot_vs_flip_pct: number
  distance_to_call_wall_pct: number | null
  distance_to_put_wall_pct: number | null
  key_factors: string[]
  vix: number
}

interface GammaExpirationData {
  symbol: string
  current_day: string
  current_gamma: number
  after_close_gamma: number
  gamma_loss_today: number
  gamma_loss_pct: number
  risk_level: string
  weekly_gamma: {
    monday: number
    tuesday: number
    wednesday: number
    thursday: number
    friday: number
    total_decay_pct: number
    decay_pattern: string
  }
  daily_risks: {
    monday: number
    tuesday: number
    wednesday: number
    thursday: number
    friday: number
  }
  spot_price: number
  flip_point: number
  net_gex: number
  call_wall: number
  put_wall: number
  directional_prediction: DirectionalPrediction | null
}

export default function GammaExpirationTracker() {
  const router = useRouter()
  const [symbol, setSymbol] = useState('SPY')
  const [data, setData] = useState<GammaExpirationData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const popularSymbols = ['SPY', 'QQQ', 'IWM']

  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      const response = await apiClient.getGammaExpiration(symbol)
      const expirationData = response.data.data

      setData(expirationData)
    } catch (error: any) {
      console.error('Error fetching expiration data:', error)
      setError(error.message || 'Failed to fetch data')
    } finally {
      setLoading(false)
    }
  }, [symbol])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const getRiskColor = (level: string) => {
    switch (level.toUpperCase()) {
      case 'EXTREME': return 'text-danger'
      case 'HIGH': return 'text-warning'
      case 'MODERATE': return 'text-primary'
      default: return 'text-success'
    }
  }

  const getRiskBgColor = (level: string) => {
    switch (level.toUpperCase()) {
      case 'EXTREME': return 'bg-danger/10 border-danger/30'
      case 'HIGH': return 'bg-warning/10 border-warning/30'
      case 'MODERATE': return 'bg-primary/10 border-primary/30'
      default: return 'bg-success/10 border-success/30'
    }
  }

  const formatGamma = (value: number) => {
    return `$${(value / 1e9).toFixed(2)}B`
  }

  const getDayIcon = (risk: number) => {
    if (risk >= 70) return '🚨'
    if (risk >= 50) return '🔶'
    return '⚠️'
  }

  const getDayRiskLevel = (risk: number) => {
    if (risk >= 70) return 'EXTREME'
    if (risk >= 50) return 'HIGH'
    return 'MODERATE'
  }

  const formatDate = (date: Date) => {
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  }

  const getCurrentWeekDates = () => {
    const today = new Date()
    const dayOfWeek = today.getDay() // 0 = Sunday, 1 = Monday, etc.

    // Calculate Monday of current week
    const monday = new Date(today)
    monday.setDate(today.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1))

    // Generate dates for each day of the week
    const weekDates: { [key: string]: string } = {}
    const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']

    days.forEach((day, idx) => {
      const date = new Date(monday)
      date.setDate(monday.getDate() + idx)
      weekDates[day] = formatDate(date)
    })

    return weekDates
  }

  const getCurrentWeekRange = () => {
    const today = new Date()
    const dayOfWeek = today.getDay() // 0 = Sunday, 1 = Monday, etc.

    // Calculate Monday of current week
    const monday = new Date(today)
    monday.setDate(today.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1))

    // Calculate Friday of current week
    const friday = new Date(monday)
    friday.setDate(monday.getDate() + 4)

    return `${formatDate(monday)} to ${formatDate(friday)}`
  }

  // Get week dates for display
  const weekDates = getCurrentWeekDates()

  if (loading) {
    return (
      <div className="min-h-screen">
        <Navigation />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex items-center justify-center h-64">
            <RefreshCw className="w-8 h-8 text-primary animate-spin" />
          </div>
        </main>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="min-h-screen">
        <Navigation />
        <main className="pt-16 transition-all duration-300">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
            <div className="bg-danger/10 border border-danger/30 rounded-lg p-6 text-center">
              <AlertTriangle className="w-12 h-12 text-danger mx-auto mb-4" />
              <h2 className="text-xl font-bold text-danger mb-2">Failed to Load Data</h2>
              <p className="text-text-secondary mb-4">{error || 'No data available'}</p>
              <button
                onClick={() => fetchData()}
                className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/80"
              >
                <RefreshCw className="w-4 h-4 inline mr-2" />
                Retry
              </button>
            </div>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <Navigation />
      <main className="pt-16 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-text-primary">0DTE Gamma Expiration Tracker</h1>
              <p className="text-text-secondary mt-1">Daily expiration opportunities and risk management</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={fetchData}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-background-hover hover:bg-background-hover/70 text-text-primary transition-all"
              >
                <RefreshCw className="w-4 h-4" />
                <span className="text-sm font-medium hidden sm:inline">Refresh</span>
              </button>
            </div>
          </div>

          {/* Symbol Selector */}
          <div className="card">
            <div className="flex items-center gap-4">
              <label className="text-text-secondary font-medium">Symbol:</label>
              <div className="flex gap-2">
                {popularSymbols.map((sym) => (
                  <button
                    key={sym}
                    onClick={() => setSymbol(sym)}
                    className={`px-4 py-2 rounded-lg font-medium transition-all ${
                      symbol === sym
                        ? 'bg-primary text-white'
                        : 'bg-background-hover text-text-secondary hover:bg-background-hover/70'
                    }`}
                  >
                    {sym}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Market Maker State Header */}
          <div className="card border-l-4 border-primary">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-2xl font-bold text-text-primary">📊 Gamma Expiration Intelligence - Current Week Only</h2>
            </div>
            <div className="flex items-center gap-4 text-sm text-text-secondary">
              <span>Week of {getCurrentWeekRange()}</span>
              <span className="text-primary">|</span>
              <span>Today: <strong className="text-primary">{data.current_day}</strong></span>
            </div>
          </div>

          {/* DIRECTIONAL PREDICTION - SPY Up/Down/Sideways */}
          {data.directional_prediction && (
            <div className={`card border-l-4 ${
              data.directional_prediction.direction === 'UPWARD' ? 'border-success bg-success/5' :
              data.directional_prediction.direction === 'DOWNWARD' ? 'border-danger bg-danger/5' :
              'border-warning bg-warning/5'
            }`}>
              <div className="text-center mb-6">
                <div className={`text-lg font-black uppercase tracking-wider mb-2 ${
                  data.directional_prediction.direction === 'UPWARD' ? 'text-success' :
                  data.directional_prediction.direction === 'DOWNWARD' ? 'text-danger' :
                  'text-warning'
                }`}>
                  {data.directional_prediction.direction_emoji} SPY DIRECTIONAL FORECAST - TODAY
                </div>
                <div className="text-5xl font-black text-text-primary my-4">
                  {data.directional_prediction.direction}
                </div>
                <div className={`text-3xl font-bold ${
                  data.directional_prediction.direction === 'UPWARD' ? 'text-success' :
                  data.directional_prediction.direction === 'DOWNWARD' ? 'text-danger' :
                  'text-warning'
                }`}>
                  {data.directional_prediction.probability}% Probability
                </div>
              </div>

              <div className="bg-background-card/50 rounded-lg p-6 space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                  <div>
                    <span className="text-primary font-bold">Current Price:</span>
                    <span className="ml-2 text-text-primary font-bold">${data.spot_price.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-primary font-bold">Expected Range:</span>
                    <span className="ml-2 text-text-primary">{data.directional_prediction.expected_range}</span>
                    <span className="ml-1 text-text-muted">({data.directional_prediction.range_width_pct})</span>
                  </div>
                  <div>
                    <span className="text-primary font-bold">Flip Point:</span>
                    <span className="ml-2 text-text-primary">${data.flip_point.toFixed(2)}</span>
                    <span className="ml-1 text-text-muted">({data.directional_prediction.spot_vs_flip_pct > 0 ? '+' : ''}{data.directional_prediction.spot_vs_flip_pct.toFixed(1)}% from spot)</span>
                  </div>
                </div>

                <div className="border-t border-border pt-4">
                  <div className="font-bold text-primary mb-2">Key Factors:</div>
                  <ul className="list-disc list-inside space-y-1 text-sm text-text-secondary">
                    {data.directional_prediction.key_factors.map((factor, idx) => (
                      <li key={idx}>{factor}</li>
                    ))}
                  </ul>
                </div>

                <div className="border-t border-border pt-4">
                  <div className="font-bold text-warning">Expected Move:</div>
                  <div className="text-text-primary text-sm mt-1">{data.directional_prediction.expected_move}</div>
                </div>
              </div>

              <div className="mt-4 p-3 bg-background-hover/30 rounded-lg text-center">
                <div className="text-text-muted text-xs">
                  ⚠️ This prediction is based on current GEX structure, VIX ({data.directional_prediction.vix}), and historical patterns.
                  Markets can change rapidly. Use as one input among many for your trading decisions.
                </div>
              </div>
            </div>
          )}

          {/* VIEW 1: TODAY'S IMPACT */}
          <div className="card">
            <h2 className="text-2xl font-bold text-text-primary mb-4 flex items-center gap-2">
              ⚡ VIEW 1: TODAY'S IMPACT <span className="text-text-secondary text-base">(Intraday Trading)</span>
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <div className="p-4 bg-background-hover rounded-lg">
                <p className="text-text-muted text-sm mb-1">Current Gamma</p>
                <p className="text-3xl font-bold text-success">{formatGamma(data.current_gamma)}</p>
              </div>
              <div className="p-4 bg-background-hover rounded-lg">
                <p className="text-text-muted text-sm mb-1">After 4pm</p>
                <p className="text-3xl font-bold text-warning">{formatGamma(data.after_close_gamma)}</p>
              </div>
              <div className="p-4 bg-background-hover rounded-lg">
                <p className="text-text-muted text-sm mb-1">Loss Today</p>
                <p className="text-3xl font-bold text-danger">
                  -{formatGamma(data.gamma_loss_today)} ({data.gamma_loss_pct}%)
                </p>
              </div>
            </div>

            <div className={`p-4 rounded-lg border mb-6 ${getRiskBgColor(data.risk_level)}`}>
              <h3 className="text-lg font-bold mb-2">🎯 RISK LEVEL: <span className={getRiskColor(data.risk_level)}>{data.risk_level}</span></h3>
              <p className="text-text-secondary text-sm">Standard thresholds applied</p>
            </div>

            <h3 className="text-xl font-bold text-text-primary mb-4">💰 HOW TO PROFIT TODAY:</h3>

            {/* Strategy 1 */}
            <div className="mb-6 p-4 bg-danger/5 border border-danger/20 rounded-lg">
              <div className="flex items-start gap-3 mb-3">
                <span className="px-2 py-1 bg-danger text-white text-xs font-bold rounded">HIGH PRIORITY</span>
                <h4 className="text-lg font-bold text-text-primary">Fade the Close</h4>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-text-secondary mb-2"><strong className="text-text-primary">Strategy:</strong> Buy directional options at 3:45pm, sell tomorrow morning</p>
                  <p className="text-text-secondary mb-2"><strong className="text-text-primary">Strike:</strong> 0.4 delta (first OTM) in trend direction</p>
                  <p className="text-text-secondary mb-2"><strong className="text-text-primary">Expiration:</strong> 0DTE or 1DTE</p>
                  <p className="text-text-secondary mb-2"><strong className="text-text-primary">Entry:</strong> {data.current_day} 3:45pm</p>
                </div>
                <div>
                  <p className="text-text-secondary mb-2"><strong className="text-text-primary">Exit:</strong> Tomorrow morning if gap move occurs</p>
                  <p className="text-text-secondary mb-2"><strong className="text-text-primary">Risk:</strong> 30% stop loss | Size: 2-3% account risk</p>
                  <p className="text-text-secondary"><strong className="text-primary">Why:</strong> Tomorrow loses {data.gamma_loss_pct}% gamma support - moves will be sharper without dealer hedging</p>
                </div>
              </div>
            </div>

            {/* Strategy 2 */}
            <div className="p-4 bg-warning/5 border border-warning/20 rounded-lg">
              <div className="flex items-start gap-3 mb-3">
                <span className="px-2 py-1 bg-warning text-white text-xs font-bold rounded">MEDIUM PRIORITY</span>
                <h4 className="text-lg font-bold text-text-primary">ATM Straddle into Expiration</h4>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-text-secondary mb-2"><strong className="text-text-primary">Strategy:</strong> Buy volatility, not direction</p>
                  <p className="text-text-secondary mb-2"><strong className="text-text-primary">Strike:</strong> ATM (0.5 delta both sides)</p>
                  <p className="text-text-secondary mb-2"><strong className="text-text-primary">Expiration:</strong> 1DTE or 2DTE</p>
                  <p className="text-text-secondary mb-2"><strong className="text-text-primary">Entry:</strong> {data.current_day} 3:30pm</p>
                </div>
                <div>
                  <p className="text-text-secondary mb-2"><strong className="text-text-primary">Exit:</strong> Tomorrow morning on gap or quick move</p>
                  <p className="text-text-secondary mb-2"><strong className="text-text-primary">Risk:</strong> Defined (premium paid) | Size: 1-2% account risk</p>
                  <p className="text-text-secondary"><strong className="text-primary">Why:</strong> Gamma expiration creates volatility vacuum - expect {data.gamma_loss_pct}% regime shift overnight</p>
                </div>
              </div>
            </div>
          </div>

          {/* VIEW 2: WEEKLY EVOLUTION */}
          <div className="card">
            <h2 className="text-2xl font-bold text-text-primary mb-4 flex items-center gap-2">
              📅 VIEW 2: WEEKLY EVOLUTION <span className="text-text-secondary text-base">(Positional Trading)</span>
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <div className="p-4 bg-background-hover rounded-lg">
                <p className="text-text-muted text-sm mb-1">Monday Baseline</p>
                <p className="text-2xl font-bold text-text-primary">{formatGamma(data.weekly_gamma.monday)}</p>
              </div>
              <div className="p-4 bg-background-hover rounded-lg">
                <p className="text-text-muted text-sm mb-1">Friday End</p>
                <p className="text-2xl font-bold text-text-primary">{formatGamma(data.weekly_gamma.friday)}</p>
              </div>
              <div className="p-4 bg-background-hover rounded-lg">
                <p className="text-text-muted text-sm mb-1">Total Decay</p>
                <p className="text-2xl font-bold text-danger">{data.weekly_gamma.total_decay_pct}%</p>
                <p className="text-xs text-warning mt-1">{data.weekly_gamma.decay_pattern}</p>
              </div>
            </div>

            <h3 className="text-lg font-bold text-text-primary mb-4">Week's Gamma Structure:</h3>
            <div className="space-y-2 mb-6">
              {['monday', 'tuesday', 'wednesday', 'thursday', 'friday'].map((day, idx) => {
                const dayName = day.charAt(0).toUpperCase() + day.slice(1)
                const gamma = data.weekly_gamma[day as keyof typeof data.weekly_gamma] as number
                const pct = Math.round((gamma / data.weekly_gamma.monday) * 100)
                const isToday = day === data.current_day.toLowerCase()

                return (
                  <div key={day} className={`flex items-center gap-3 p-3 rounded-lg ${isToday ? 'bg-primary/10 border border-primary' : 'bg-background-hover'}`}>
                    {isToday && <span className="text-primary font-bold">📍</span>}
                    <span className="text-sm font-mono w-32 text-text-secondary">
                      {dayName} {weekDates[day]}
                    </span>
                    <div className="flex-1 h-6 bg-background-deep rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-success to-danger transition-all"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="text-sm font-bold text-text-primary w-24">{formatGamma(gamma)}</span>
                    <span className="text-sm text-text-muted w-12">({pct}%)</span>
                  </div>
                )
              })}
            </div>

            <h3 className="text-xl font-bold text-text-primary mb-4">💰 HOW TO PROFIT THIS WEEK:</h3>

            <div className="space-y-4">
              {/* Weekly Strategy 1 */}
              <div className="p-4 bg-success/5 border border-success/20 rounded-lg">
                <h4 className="text-lg font-bold text-success mb-3">Aggressive Theta Farming (Mon-Wed)</h4>
                <p className="text-text-secondary mb-3"><strong className="text-text-primary">Description:</strong> Sell premium while gamma is strong</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="mb-2"><strong>Strategy:</strong> Iron Condor or Credit Spreads</p>
                    <p className="mb-2"><strong>Strikes:</strong> 0.15-0.20 delta wings (far OTM)</p>
                    <p className="mb-2"><strong>Expiration:</strong> Friday (this week)</p>
                  </div>
                  <div>
                    <p className="mb-2"><strong>Entry:</strong> Monday or Tuesday morning</p>
                    <p className="mb-2"><strong>Exit:</strong> Wednesday close (50-60% profit)</p>
                    <p className="mb-2"><strong>Size:</strong> 3-5% account risk per spread</p>
                  </div>
                </div>
                <p className="text-sm mt-3"><strong className="text-primary">Why:</strong> Week starts with 100% of gamma - high mean-reversion, options will decay fast</p>
              </div>

              {/* Weekly Strategy 2 */}
              <div className="p-4 bg-primary/5 border border-primary/20 rounded-lg">
                <h4 className="text-lg font-bold text-primary mb-3">Delta Buying (Thu-Fri)</h4>
                <p className="text-text-secondary mb-3"><strong className="text-text-primary">Description:</strong> Switch to directional momentum plays</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="mb-2"><strong>Strategy:</strong> Long Calls or Puts</p>
                    <p className="mb-2"><strong>Strikes:</strong> ATM or first OTM (0.5-0.6 delta)</p>
                    <p className="mb-2"><strong>Expiration:</strong> Next week (1 week DTE)</p>
                  </div>
                  <div>
                    <p className="mb-2"><strong>Entry:</strong> Thursday morning</p>
                    <p className="mb-2"><strong>Exit:</strong> Friday close or hold if strong trend</p>
                    <p className="mb-2"><strong>Size:</strong> 2-3% account risk</p>
                  </div>
                </div>
                <p className="text-sm mt-3"><strong className="text-primary">Why:</strong> By Thursday, only 12% gamma remains - low hedging = directional moves</p>
              </div>

              {/* Weekly Strategy 3 */}
              <div className="p-4 bg-warning/5 border border-warning/20 rounded-lg">
                <h4 className="text-lg font-bold text-warning mb-3">Dynamic Position Sizing</h4>
                <p className="text-text-secondary mb-3"><strong className="text-text-primary">Description:</strong> Adjust size based on gamma regime through week</p>
                <div className="space-y-2 text-sm">
                  <p><strong>Mon-Tue:</strong> 100% normal size (gamma protects you)</p>
                  <p><strong>Wed:</strong> 75% size (transition)</p>
                  <p><strong>Thu-Fri:</strong> 50% size (gamma gone, vol spikes)</p>
                </div>
                <p className="text-sm mt-3"><strong className="text-primary">Why:</strong> Risk management: {data.weekly_gamma.total_decay_pct}% weekly decay means vol will increase significantly late week</p>
              </div>
            </div>
          </div>

          {/* VIEW 3: VOLATILITY CLIFFS */}
          <div className="card">
            <h2 className="text-2xl font-bold text-text-primary mb-4 flex items-center gap-2">
              ⚠️ VIEW 3: VOLATILITY CLIFFS <span className="text-text-secondary text-base">(Risk Management)</span>
            </h2>

            <h3 className="text-lg font-bold text-text-primary mb-4">Relative Expiration Risk by Day:</h3>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-3 mb-6">
              {['monday', 'tuesday', 'wednesday', 'thursday', 'friday'].map((day, idx) => {
                const dayName = day.charAt(0).toUpperCase() + day.slice(1).substring(0, 3)
                const risk = data.daily_risks[day as keyof typeof data.daily_risks]
                const isToday = day === data.current_day.toLowerCase()
                const riskLevel = getDayRiskLevel(risk)

                return (
                  <div
                    key={day}
                    className={`p-4 rounded-lg border ${isToday ? 'border-primary bg-primary/10' : 'border-border bg-background-hover'}`}
                  >
                    <div className="text-center">
                      {isToday && <div className="text-primary font-bold mb-1">📍 TODAY</div>}
                      <div className="text-3xl mb-2">{getDayIcon(risk)}</div>
                      <div className="font-bold text-text-primary mb-1">{dayName}</div>
                      <div className="text-2xl font-bold mb-1" style={{ color: risk >= 70 ? '#ef4444' : risk >= 50 ? '#f59e0b' : '#3b82f6' }}>
                        {risk}%
                      </div>
                      <div className="text-xs font-semibold" style={{ color: risk >= 70 ? '#ef4444' : risk >= 50 ? '#f59e0b' : '#3b82f6' }}>
                        {riskLevel}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>

            <h3 className="text-xl font-bold text-text-primary mb-4">💰 STRATEGIES FOR HIGHEST RISK DAY (Friday):</h3>

            <div className="space-y-4">
              {/* Cliff Strategy 1 */}
              <div className="p-4 bg-danger/5 border border-danger/20 rounded-lg">
                <div className="flex items-start gap-3 mb-3">
                  <span className="px-2 py-1 bg-danger text-white text-xs font-bold rounded">HIGH PRIORITY</span>
                  <h4 className="text-lg font-bold text-danger">Pre-Expiration Volatility Scalp</h4>
                </div>
                <p className="text-text-secondary mb-3"><strong className="text-text-primary">Strategy:</strong> Capture chaos of gamma expiration, not direction</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="mb-2"><strong>Type:</strong> ATM Straddle</p>
                    <p className="mb-2"><strong>Strike:</strong> ATM (0.5 delta both sides)</p>
                    <p className="mb-2"><strong>Expiration:</strong> 0DTE (expiring Friday)</p>
                    <p className="mb-2"><strong>Entry:</strong> Friday 10:00-11:00am</p>
                  </div>
                  <div>
                    <p className="mb-2"><strong>Exit:</strong> Friday 2:00-3:00pm (BEFORE 4pm)</p>
                    <p className="mb-2"><strong>Risk:</strong> Defined (premium paid)</p>
                    <p className="mb-2"><strong>Size:</strong> 2-3% account risk</p>
                  </div>
                </div>
                <p className="text-sm mt-3"><strong className="text-primary">Why:</strong> Friday has 100% gamma decay - massive expiration creates intraday volatility spike. Exit before pin risk at 4pm.</p>
              </div>

              {/* Cliff Strategy 2 */}
              <div className="p-4 bg-warning/5 border border-warning/20 rounded-lg">
                <div className="flex items-start gap-3 mb-3">
                  <span className="px-2 py-1 bg-warning text-white text-xs font-bold rounded">MEDIUM PRIORITY</span>
                  <h4 className="text-lg font-bold text-warning">Post-Expiration Directional Positioning</h4>
                </div>
                <p className="text-text-secondary mb-3"><strong className="text-text-primary">Strategy:</strong> Position day-before for explosive move day-after</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="mb-2"><strong>Type:</strong> Long Calls or Puts</p>
                    <p className="mb-2"><strong>Strike:</strong> 0.4-0.5 delta in expected direction</p>
                    <p className="mb-2"><strong>Expiration:</strong> 1DTE or 2DTE</p>
                    <p className="mb-2"><strong>Entry:</strong> Friday 3:45pm</p>
                  </div>
                  <div>
                    <p className="mb-2"><strong>Exit:</strong> Next day morning if profit target hit</p>
                    <p className="mb-2"><strong>Risk:</strong> 30% stop loss</p>
                    <p className="mb-2"><strong>Size:</strong> 2% account risk</p>
                  </div>
                </div>
                <p className="text-sm mt-3"><strong className="text-primary">Why:</strong> After Friday gamma expires, next day will have explosive moves in prevailing trend direction</p>
              </div>

              {/* Cliff Strategy 3 */}
              <div className="p-4 bg-primary/5 border border-primary/20 rounded-lg">
                <div className="flex items-start gap-3 mb-3">
                  <span className="px-2 py-1 bg-primary text-white text-xs font-bold rounded">LOW PRIORITY</span>
                  <h4 className="text-lg font-bold text-primary">The Avoidance Strategy</h4>
                </div>
                <p className="text-text-secondary mb-3"><strong className="text-text-primary">Strategy:</strong> Sometimes the best trade is no trade</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="mb-2"><strong>Type:</strong> Cash / Sidelines</p>
                    <p className="mb-2"><strong>Entry:</strong> Close all positions day before</p>
                  </div>
                  <div>
                    <p className="mb-2"><strong>Exit:</strong> Re-enter next Monday</p>
                    <p className="mb-2"><strong>Risk:</strong> 0% (no positions)</p>
                  </div>
                </div>
                <p className="text-sm mt-3"><strong className="text-primary">Why:</strong> Friday shows 100% decay - if you're uncomfortable with chaos, sit out and preserve capital</p>
              </div>
            </div>
          </div>

          {/* Actionable Trade Playbook */}
          <div className="card bg-gradient-to-br from-primary/10 to-success/10 border-2 border-primary">
            <h2 className="text-2xl font-bold text-text-primary mb-4">🎯 Actionable Trade Playbook - Today's Opportunity</h2>

            <div className="p-4 bg-background-card rounded-lg mb-4">
              <h3 className="text-xl font-bold text-danger mb-3">📊 🔥 0DTE Straddle - Volatility Explosion</h3>

              <div className="mb-4">
                <h4 className="font-bold text-text-primary mb-2">📍 Current Market Scenario:</h4>
                <p className="text-text-secondary">{data.current_day} Expiration + Massive gamma decay = Volatility spike</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-4">
                  <div>
                    <h4 className="font-bold text-text-primary mb-2">💼 Strategy:</h4>
                    <p className="text-text-secondary">Long 0DTE ATM Straddle</p>
                  </div>

                  <div>
                    <h4 className="font-bold text-text-primary mb-2">⏰ Entry Timing:</h4>
                    <p className="text-text-secondary">9:30 AM - 10:30 AM ET (Early to capture full move)</p>
                  </div>

                  <div>
                    <h4 className="font-bold text-text-primary mb-2">📋 Trade Structure:</h4>
                    <div className="space-y-1 text-sm">
                      <p><strong>Buy ATM Call:</strong> ${data.spot_price.toFixed(2)} strike</p>
                      <p><strong>Buy ATM Put:</strong> ${data.spot_price.toFixed(2)} strike</p>
                      <p><strong>Expiration:</strong> TODAY (0DTE)</p>
                      <p><strong>Debit:</strong> $1.50 - $2.50 per straddle</p>
                      <p><strong>Breakevens:</strong> ${(data.spot_price - 2).toFixed(2)} / ${(data.spot_price + 2).toFixed(2)}</p>
                    </div>
                  </div>
                </div>

                <div className="space-y-4">
                  <div>
                    <h4 className="font-bold text-text-primary mb-2">🎯 Exit Rules:</h4>
                    <p className="text-text-secondary mb-1"><strong>Target:</strong> Exit when either leg is ITM by $2+ OR at 1:00 PM ET</p>
                    <p className="text-text-secondary"><strong>Stop:</strong> Exit at 11:30 AM if no movement (down 30-40%) or at $100 loss per straddle</p>
                  </div>

                  <div>
                    <h4 className="font-bold text-text-primary mb-2">💰 Risk Management:</h4>
                    <p className="text-text-secondary"><strong>Size:</strong> 1-2% of account (aggressive but defined risk)</p>
                  </div>

                  <div>
                    <h4 className="font-bold text-text-primary mb-2">🧠 Edge:</h4>
                    <p className="text-text-secondary">Low gamma = dealers stop hedging = big intraday moves. Friday afternoon typically sees 1-2% swings</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="p-4 bg-background-hover rounded-lg">
              <h4 className="font-bold text-text-primary mb-2">Current Conditions:</h4>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
                <div>
                  <span className="text-text-muted">Symbol:</span>
                  <span className="ml-2 font-semibold text-primary">{data.symbol}</span>
                </div>
                <div>
                  <span className="text-text-muted">Net GEX:</span>
                  <span className="ml-2 font-semibold text-text-primary">{formatGamma(data.net_gex)}</span>
                </div>
                <div>
                  <span className="text-text-muted">Spot Price:</span>
                  <span className="ml-2 font-semibold text-text-primary">${data.spot_price.toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-text-muted">Flip Point:</span>
                  <span className="ml-2 font-semibold text-warning">${data.flip_point.toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-text-muted">Day:</span>
                  <span className="ml-2 font-semibold text-text-primary">{data.current_day}</span>
                </div>
                <div>
                  <span className="text-text-muted">Expiration Today:</span>
                  <span className="ml-2 font-semibold text-danger">Yes</span>
                </div>
              </div>
            </div>
          </div>

          {/* Evidence-based footer */}
          <div className="card bg-background-hover">
            <h3 className="text-sm font-bold text-text-primary mb-2">📚 EVIDENCE-BASED THRESHOLDS</h3>
            <p className="text-xs text-text-secondary">
              Thresholds based on: Academic research (Dim, Eraker, Vilkov 2023), SpotGamma professional analysis, ECB Financial Stability Review 2023,
              and validated production trading data. Context-aware adjustments for Friday expirations and high-VIX environments.
            </p>
          </div>
        </div>
        </div>
      </main>
    </div>
  )
}
