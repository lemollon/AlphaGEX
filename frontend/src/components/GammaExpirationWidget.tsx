'use client'

import { logger } from '@/lib/logger'

import { useState, useEffect, useCallback } from 'react'
import { AlertTriangle, TrendingUp, TrendingDown, Clock, Zap, Target, Calendar, Activity, RefreshCw, BarChart3, DollarSign, ChevronDown, ChevronUp } from 'lucide-react'
import { apiClient } from '@/lib/api'

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

export default function GammaExpirationWidget() {
  const [symbol, setSymbol] = useState('SPY')
  const [data, setData] = useState<GammaExpirationData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedSection, setExpandedSection] = useState<string | null>('prediction')

  const popularSymbols = ['SPY', 'QQQ', 'IWM']

  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      const response = await apiClient.getGammaExpiration(symbol)
      const expirationData = response.data.data

      setData(expirationData)
    } catch (error: any) {
      logger.error('Error fetching expiration data:', error)
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
    const dayOfWeek = today.getDay()

    const monday = new Date(today)
    monday.setDate(today.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1))

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
    const dayOfWeek = today.getDay()

    const monday = new Date(today)
    monday.setDate(today.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1))

    const friday = new Date(monday)
    friday.setDate(monday.getDate() + 4)

    return `${formatDate(monday)} to ${formatDate(friday)}`
  }

  const weekDates = getCurrentWeekDates()

  const toggleSection = (section: string) => {
    setExpandedSection(expandedSection === section ? null : section)
  }

  if (loading) {
    return (
      <div className="card">
        <div className="flex items-center justify-center h-32">
          <RefreshCw className="w-6 h-6 text-primary animate-spin" />
          <span className="ml-2 text-text-secondary">Loading 0DTE data...</span>
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="card">
        <div className="bg-danger/10 border border-danger/30 rounded-lg p-4 text-center">
          <AlertTriangle className="w-8 h-8 text-danger mx-auto mb-2" />
          <h3 className="text-lg font-bold text-danger mb-1">Failed to Load 0DTE Data</h3>
          <p className="text-text-secondary text-sm mb-3">{error || 'No data available'}</p>
          <button
            onClick={() => fetchData()}
            className="px-3 py-1 bg-primary text-white text-sm rounded-lg hover:bg-primary/80"
          >
            <RefreshCw className="w-3 h-3 inline mr-1" />
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header with Symbol Selector */}
      <div className="card">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-text-primary">0DTE Gamma Expiration Tracker</h2>
            <p className="text-sm text-text-secondary">Week of {getCurrentWeekRange()} | Today: <strong className="text-primary">{data.current_day}</strong></p>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex gap-1">
              {popularSymbols.map((sym) => (
                <button
                  key={sym}
                  onClick={() => setSymbol(sym)}
                  className={`px-3 py-1 rounded-lg text-sm font-medium transition-all ${
                    symbol === sym
                      ? 'bg-primary text-white'
                      : 'bg-background-hover text-text-secondary hover:bg-background-hover/70'
                  }`}
                >
                  {sym}
                </button>
              ))}
            </div>
            <button
              onClick={fetchData}
              className="flex items-center gap-1 px-3 py-1 rounded-lg bg-background-hover hover:bg-background-hover/70 text-text-primary transition-all"
            >
              <RefreshCw className="w-3 h-3" />
            </button>
          </div>
        </div>
      </div>

      {/* Directional Prediction - Collapsible */}
      {data.directional_prediction && (
        <div className={`card border-l-4 ${
          data.directional_prediction.direction === 'UPWARD' ? 'border-success bg-success/5' :
          data.directional_prediction.direction === 'DOWNWARD' ? 'border-danger bg-danger/5' :
          'border-warning bg-warning/5'
        }`}>
          <button
            onClick={() => toggleSection('prediction')}
            className="w-full flex items-center justify-between"
          >
            <div className="flex items-center gap-4">
              <div className={`text-3xl font-black ${
                data.directional_prediction.direction === 'UPWARD' ? 'text-success' :
                data.directional_prediction.direction === 'DOWNWARD' ? 'text-danger' :
                'text-warning'
              }`}>
                {data.directional_prediction.direction_emoji} {data.directional_prediction.direction}
              </div>
              <div className={`text-xl font-bold ${
                data.directional_prediction.direction === 'UPWARD' ? 'text-success' :
                data.directional_prediction.direction === 'DOWNWARD' ? 'text-danger' :
                'text-warning'
              }`}>
                {data.directional_prediction.probability}% Probability
              </div>
            </div>
            {expandedSection === 'prediction' ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
          </button>

          {expandedSection === 'prediction' && (
            <div className="mt-4 pt-4 border-t border-border">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm mb-4">
                <div>
                  <span className="text-primary font-bold">Current Price:</span>
                  <span className="ml-2 text-text-primary font-bold">${data.spot_price.toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-primary font-bold">Expected Range:</span>
                  <span className="ml-2 text-text-primary">{data.directional_prediction.expected_range}</span>
                </div>
                <div>
                  <span className="text-primary font-bold">Flip Point:</span>
                  <span className="ml-2 text-text-primary">${data.flip_point.toFixed(2)}</span>
                </div>
              </div>
              <div className="border-t border-border pt-3">
                <div className="font-bold text-primary mb-2 text-sm">Key Factors:</div>
                <ul className="list-disc list-inside space-y-1 text-xs text-text-secondary">
                  {data.directional_prediction.key_factors.map((factor, idx) => (
                    <li key={idx}>{factor}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Today's Impact - Compact */}
      <div className="card">
        <button
          onClick={() => toggleSection('today')}
          className="w-full flex items-center justify-between mb-4"
        >
          <h3 className="text-lg font-bold text-text-primary flex items-center gap-2">
            ⚡ Today's Impact
          </h3>
          {expandedSection === 'today' ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
        </button>

        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="p-3 bg-background-hover rounded-lg text-center">
            <p className="text-text-muted text-xs mb-1">Current Gamma</p>
            <p className="text-xl font-bold text-success">{formatGamma(data.current_gamma)}</p>
          </div>
          <div className="p-3 bg-background-hover rounded-lg text-center">
            <p className="text-text-muted text-xs mb-1">After 4pm</p>
            <p className="text-xl font-bold text-warning">{formatGamma(data.after_close_gamma)}</p>
          </div>
          <div className="p-3 bg-background-hover rounded-lg text-center">
            <p className="text-text-muted text-xs mb-1">Loss Today</p>
            <p className="text-xl font-bold text-danger">-{data.gamma_loss_pct}%</p>
          </div>
        </div>

        <div className={`p-3 rounded-lg border ${getRiskBgColor(data.risk_level)}`}>
          <span className="text-sm font-bold">Risk Level: </span>
          <span className={`font-bold ${getRiskColor(data.risk_level)}`}>{data.risk_level}</span>
        </div>

        {expandedSection === 'today' && (
          <div className="mt-4 pt-4 border-t border-border space-y-3">
            <div className="p-3 bg-danger/5 border border-danger/20 rounded-lg">
              <h4 className="text-sm font-bold text-text-primary mb-2">Fade the Close Strategy</h4>
              <p className="text-xs text-text-secondary">Buy directional options at 3:45pm, sell tomorrow morning. Gamma loss of {data.gamma_loss_pct}% creates overnight volatility.</p>
            </div>
            <div className="p-3 bg-warning/5 border border-warning/20 rounded-lg">
              <h4 className="text-sm font-bold text-text-primary mb-2">ATM Straddle into Expiration</h4>
              <p className="text-xs text-text-secondary">Buy volatility at 3:30pm with 1-2DTE. Exit tomorrow morning on gap move.</p>
            </div>
          </div>
        )}
      </div>

      {/* Weekly Evolution - Compact */}
      <div className="card">
        <button
          onClick={() => toggleSection('weekly')}
          className="w-full flex items-center justify-between mb-4"
        >
          <h3 className="text-lg font-bold text-text-primary flex items-center gap-2">
            📅 Weekly Evolution
          </h3>
          {expandedSection === 'weekly' ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
        </button>

        <div className="space-y-2">
          {['monday', 'tuesday', 'wednesday', 'thursday', 'friday'].map((day) => {
            const dayName = day.charAt(0).toUpperCase() + day.slice(1, 3)
            const gamma = data.weekly_gamma[day as keyof typeof data.weekly_gamma] as number
            const pct = Math.round((gamma / data.weekly_gamma.monday) * 100)
            const isToday = day === data.current_day.toLowerCase()

            return (
              <div key={day} className={`flex items-center gap-2 p-2 rounded-lg ${isToday ? 'bg-primary/10 border border-primary' : 'bg-background-hover'}`}>
                {isToday && <span className="text-primary text-xs">📍</span>}
                <span className="text-xs font-mono w-8 text-text-secondary">{dayName}</span>
                <div className="flex-1 h-4 bg-background-deep rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-success to-danger transition-all"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="text-xs font-bold text-text-primary w-16">{formatGamma(gamma)}</span>
                <span className="text-xs text-text-muted w-10">({pct}%)</span>
              </div>
            )
          })}
        </div>

        <div className="mt-3 p-2 bg-background-hover rounded-lg text-center">
          <span className="text-xs text-text-muted">Total Weekly Decay: </span>
          <span className="text-sm font-bold text-danger">{data.weekly_gamma.total_decay_pct}%</span>
          <span className="text-xs text-warning ml-2">({data.weekly_gamma.decay_pattern})</span>
        </div>

        {expandedSection === 'weekly' && (
          <div className="mt-4 pt-4 border-t border-border space-y-3">
            <div className="p-3 bg-success/5 border border-success/20 rounded-lg">
              <h4 className="text-sm font-bold text-success mb-1">Mon-Wed: Theta Farming</h4>
              <p className="text-xs text-text-secondary">Sell premium (Iron Condors, Credit Spreads). Exit at 50-60% profit.</p>
            </div>
            <div className="p-3 bg-primary/5 border border-primary/20 rounded-lg">
              <h4 className="text-sm font-bold text-primary mb-1">Thu-Fri: Delta Buying</h4>
              <p className="text-xs text-text-secondary">Switch to directional plays. Low gamma = momentum moves.</p>
            </div>
          </div>
        )}
      </div>

      {/* Volatility Cliffs - Compact */}
      <div className="card">
        <button
          onClick={() => toggleSection('cliffs')}
          className="w-full flex items-center justify-between mb-4"
        >
          <h3 className="text-lg font-bold text-text-primary flex items-center gap-2">
            ⚠️ Daily Risk Levels
          </h3>
          {expandedSection === 'cliffs' ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
        </button>

        <div className="grid grid-cols-5 gap-2">
          {['monday', 'tuesday', 'wednesday', 'thursday', 'friday'].map((day) => {
            const dayName = day.charAt(0).toUpperCase() + day.slice(1, 3)
            const risk = data.daily_risks[day as keyof typeof data.daily_risks]
            const isToday = day === data.current_day.toLowerCase()

            return (
              <div
                key={day}
                className={`p-2 rounded-lg border text-center ${isToday ? 'border-primary bg-primary/10' : 'border-border bg-background-hover'}`}
              >
                {isToday && <div className="text-primary text-xs font-bold mb-1">TODAY</div>}
                <div className="text-lg mb-1">{getDayIcon(risk)}</div>
                <div className="text-xs font-bold text-text-primary">{dayName}</div>
                <div className="text-sm font-bold" style={{ color: risk >= 70 ? '#ef4444' : risk >= 50 ? '#f59e0b' : '#3b82f6' }}>
                  {risk}%
                </div>
              </div>
            )
          })}
        </div>

        {expandedSection === 'cliffs' && (
          <div className="mt-4 pt-4 border-t border-border">
            <h4 className="text-sm font-bold text-text-primary mb-3">Friday Strategies (Highest Risk):</h4>
            <div className="space-y-2">
              <div className="p-2 bg-danger/5 border border-danger/20 rounded-lg">
                <span className="text-xs font-bold text-danger">Pre-Expiration Scalp:</span>
                <span className="text-xs text-text-secondary ml-2">ATM Straddle 10am → Exit 2-3pm</span>
              </div>
              <div className="p-2 bg-warning/5 border border-warning/20 rounded-lg">
                <span className="text-xs font-bold text-warning">Post-Expiration Position:</span>
                <span className="text-xs text-text-secondary ml-2">Buy direction at 3:45pm Friday</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Quick Trade Playbook */}
      <div className="card bg-gradient-to-br from-primary/10 to-success/10 border border-primary">
        <h3 className="text-lg font-bold text-text-primary mb-3">🎯 Today's Trade Opportunity</h3>

        <div className="grid grid-cols-2 gap-3 text-sm mb-3">
          <div>
            <span className="text-text-muted">Strategy:</span>
            <span className="ml-2 font-semibold text-primary">0DTE ATM Straddle</span>
          </div>
          <div>
            <span className="text-text-muted">Entry:</span>
            <span className="ml-2 font-semibold text-text-primary">9:30-10:30am ET</span>
          </div>
          <div>
            <span className="text-text-muted">Strike:</span>
            <span className="ml-2 font-semibold text-text-primary">${data.spot_price.toFixed(2)} (ATM)</span>
          </div>
          <div>
            <span className="text-text-muted">Exit:</span>
            <span className="ml-2 font-semibold text-text-primary">1:00pm or +$2 ITM</span>
          </div>
        </div>

        <div className="p-2 bg-background-hover/50 rounded-lg text-xs text-text-secondary">
          <strong>Edge:</strong> {data.gamma_loss_pct}% gamma loss = dealers stop hedging = big intraday moves
        </div>
      </div>
    </div>
  )
}
