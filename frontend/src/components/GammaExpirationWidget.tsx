'use client'

import { useState } from 'react'
import { AlertTriangle, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react'
import { useGammaExpiration } from '@/lib/hooks/useMarketData'

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
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['prediction', 'today']))

  const { data: response, error, isLoading, isValidating, mutate } = useGammaExpiration(symbol)

  const data = response?.data as GammaExpirationData | undefined
  const loading = isLoading && !data
  const refreshing = isValidating
  const lastUpdated = data ? new Date() : null

  const popularSymbols = ['SPY', 'QQQ', 'IWM']

  // Manual refresh handler
  const handleRefresh = () => {
    mutate()
  }

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

  // Generate intelligent trade recommendation based on market conditions
  const getTradeRecommendation = () => {
    if (!data || !data.directional_prediction) return null

    const direction = data.directional_prediction.direction
    const probability = data.directional_prediction.probability
    const netGex = data.net_gex
    const isPositiveGamma = netGex > 0
    const isHighConfidence = probability >= 65
    const isMidWeek = ['Monday', 'Tuesday', 'Wednesday'].includes(data.current_day)

    // SIDEWAYS: Favor premium selling (high win rate)
    if (direction === 'SIDEWAYS') {
      if (isPositiveGamma && isMidWeek) {
        return {
          strategy: 'Iron Condor',
          strategyEmoji: '🦅',
          winRate: '65-75%',
          type: 'Premium Selling',
          typeColor: 'text-success',
          borderColor: 'border-success',
          bgColor: 'bg-success/10',
          description: 'Positive gamma + sideways = range-bound. Sell premium to collect theta.',
          structure: [
            { label: 'Sell OTM Put', value: `$${(data.spot_price * 0.98).toFixed(0)} (0.20 delta)` },
            { label: 'Buy OTM Put', value: `$${(data.spot_price * 0.96).toFixed(0)} (protection)` },
            { label: 'Sell OTM Call', value: `$${(data.spot_price * 1.02).toFixed(0)} (0.20 delta)` },
            { label: 'Buy OTM Call', value: `$${(data.spot_price * 1.04).toFixed(0)} (protection)` },
            { label: 'Expiration', value: 'Friday (weekly)' },
            { label: 'Credit', value: '$0.80 - $1.50 per spread' },
          ],
          exitRules: 'Close at 50% profit or if price approaches short strikes',
          stopLoss: 'Close if either short strike is breached',
          sizing: '3-5% account risk',
          edge: `Positive GEX (${formatGamma(netGex)}) keeps dealers hedging = mean reversion. ${probability}% sideways probability.`
        }
      } else {
        return {
          strategy: 'Cash / Reduced Size',
          strategyEmoji: '💵',
          winRate: 'N/A',
          type: 'Capital Preservation',
          typeColor: 'text-warning',
          borderColor: 'border-warning',
          bgColor: 'bg-warning/10',
          description: 'Sideways with weak signals. Wait for clearer setup.',
          structure: [
            { label: 'Action', value: 'Stay in cash or reduce position size' },
            { label: 'Alternative', value: 'Small Iron Butterfly if IV is elevated' },
          ],
          exitRules: 'Wait for directional signal or positive gamma regime',
          stopLoss: 'N/A',
          sizing: '0-1% account risk',
          edge: `Low confidence (${probability}%) in sideways. Better opportunities may arise.`
        }
      }
    }

    // UPWARD: Bull spreads (defined risk, directional)
    if (direction === 'UPWARD') {
      if (isHighConfidence) {
        return {
          strategy: 'Bull Call Spread',
          strategyEmoji: '📈',
          winRate: '55-60%',
          type: 'Directional (Bullish)',
          typeColor: 'text-success',
          borderColor: 'border-success',
          bgColor: 'bg-success/10',
          description: 'High probability upward move. Define risk with vertical spread.',
          structure: [
            { label: 'Buy ATM Call', value: `$${data.spot_price.toFixed(0)} strike` },
            { label: 'Sell OTM Call', value: `$${(data.spot_price * 1.01).toFixed(0)} strike (+$${(data.spot_price * 0.01).toFixed(0)})` },
            { label: 'Expiration', value: '1-2 DTE' },
            { label: 'Debit', value: '$0.40 - $0.60 per spread' },
            { label: 'Max Profit', value: 'Spread width minus debit' },
          ],
          exitRules: 'Close at 50-70% of max profit or if direction reverses',
          stopLoss: 'Close if premium drops 50%',
          sizing: '2-3% account risk',
          edge: `${probability}% upward probability. GEX: ${formatGamma(netGex)}. Spot above flip point.`
        }
      } else {
        return {
          strategy: 'Small Long Call',
          strategyEmoji: '📈',
          winRate: '45-55%',
          type: 'Directional (Cautious)',
          typeColor: 'text-primary',
          borderColor: 'border-primary',
          bgColor: 'bg-primary/10',
          description: 'Moderate bullish signal. Keep position small.',
          structure: [
            { label: 'Buy Call', value: `$${data.spot_price.toFixed(0)} or $${(data.spot_price + 1).toFixed(0)} strike` },
            { label: 'Expiration', value: '1-3 DTE' },
            { label: 'Debit', value: '$0.50 - $1.00' },
          ],
          exitRules: 'Take profit at 30-50% gain',
          stopLoss: '30% stop loss on premium',
          sizing: '1% account risk (small)',
          edge: `Moderate ${probability}% upward probability. Position small due to uncertainty.`
        }
      }
    }

    // DOWNWARD: Bear spreads (defined risk, directional)
    if (direction === 'DOWNWARD') {
      if (isHighConfidence) {
        return {
          strategy: 'Bear Put Spread',
          strategyEmoji: '📉',
          winRate: '55-60%',
          type: 'Directional (Bearish)',
          typeColor: 'text-danger',
          borderColor: 'border-danger',
          bgColor: 'bg-danger/10',
          description: 'High probability downward move. Define risk with vertical spread.',
          structure: [
            { label: 'Buy ATM Put', value: `$${data.spot_price.toFixed(0)} strike` },
            { label: 'Sell OTM Put', value: `$${(data.spot_price * 0.99).toFixed(0)} strike (-$${(data.spot_price * 0.01).toFixed(0)})` },
            { label: 'Expiration', value: '1-2 DTE' },
            { label: 'Debit', value: '$0.40 - $0.60 per spread' },
            { label: 'Max Profit', value: 'Spread width minus debit' },
          ],
          exitRules: 'Close at 50-70% of max profit or if direction reverses',
          stopLoss: 'Close if premium drops 50%',
          sizing: '2-3% account risk',
          edge: `${probability}% downward probability. GEX: ${formatGamma(netGex)}. Spot below flip point.`
        }
      } else {
        return {
          strategy: 'Small Long Put',
          strategyEmoji: '📉',
          winRate: '45-55%',
          type: 'Directional (Cautious)',
          typeColor: 'text-warning',
          borderColor: 'border-warning',
          bgColor: 'bg-warning/10',
          description: 'Moderate bearish signal. Keep position small.',
          structure: [
            { label: 'Buy Put', value: `$${data.spot_price.toFixed(0)} or $${(data.spot_price - 1).toFixed(0)} strike` },
            { label: 'Expiration', value: '1-3 DTE' },
            { label: 'Debit', value: '$0.50 - $1.00' },
          ],
          exitRules: 'Take profit at 30-50% gain',
          stopLoss: '30% stop loss on premium',
          sizing: '1% account risk (small)',
          edge: `Moderate ${probability}% downward probability. Position small due to uncertainty.`
        }
      }
    }

    return null
  }

  const toggleSection = (section: string) => {
    setExpandedSections(prev => {
      const next = new Set(prev)
      if (next.has(section)) {
        next.delete(section)
      } else {
        next.add(section)
      }
      return next
    })
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
          <p className="text-text-secondary text-sm mb-3">{error?.message || 'No data available'}</p>
          <button
            onClick={() => mutate()}
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
            <p className="text-sm text-text-secondary">
              Week of {getCurrentWeekRange()} | Today: <strong className="text-primary">{data.current_day}</strong>
              {lastUpdated && (
                <span className="ml-2 text-text-muted" suppressHydrationWarning>
                  | Updated {lastUpdated.toLocaleTimeString('en-US', {
                    hour: '2-digit',
                    minute: '2-digit',
                    hour12: true,
                    timeZone: 'America/Chicago'
                  })} CT
                  {refreshing && <span className="ml-1 text-primary">(refreshing...)</span>}
                </span>
              )}
            </p>
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
              onClick={handleRefresh}
              disabled={refreshing}
              className={`flex items-center gap-1 px-3 py-1 rounded-lg bg-background-hover hover:bg-background-hover/70 text-text-primary transition-all ${refreshing ? 'opacity-50' : ''}`}
            >
              <RefreshCw className={`w-3 h-3 ${refreshing ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </div>

      {/* DIRECTIONAL PREDICTION */}
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
              <div className={`text-2xl font-black ${
                data.directional_prediction.direction === 'UPWARD' ? 'text-success' :
                data.directional_prediction.direction === 'DOWNWARD' ? 'text-danger' :
                'text-warning'
              }`}>
                {data.directional_prediction.direction_emoji} {data.directional_prediction.direction}
              </div>
              <div className={`text-lg font-bold ${
                data.directional_prediction.direction === 'UPWARD' ? 'text-success' :
                data.directional_prediction.direction === 'DOWNWARD' ? 'text-danger' :
                'text-warning'
              }`}>
                {data.directional_prediction.probability}% Probability
              </div>
            </div>
            {expandedSections.has('prediction') ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
          </button>

          {expandedSections.has('prediction') && (
            <div className="mt-4 pt-4 border-t border-border">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm mb-4">
                <div className="flex flex-col">
                  <span className="text-primary font-bold text-xs">Current Price:</span>
                  <span className="text-text-primary font-bold text-lg">${data.spot_price.toFixed(2)}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-primary font-bold text-xs">Expected Range:</span>
                  <span className="text-text-primary">{data.directional_prediction.expected_range}</span>
                  <span className="text-text-muted text-xs">({data.directional_prediction.range_width_pct})</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-primary font-bold text-xs">Flip Point:</span>
                  <span className="text-text-primary">${data.flip_point.toFixed(2)}</span>
                  <span className="text-text-muted text-xs">({data.directional_prediction.spot_vs_flip_pct > 0 ? '+' : ''}{data.directional_prediction.spot_vs_flip_pct.toFixed(1)}% from spot)</span>
                </div>
              </div>

              <div className="border-t border-border pt-3 mb-3">
                <div className="font-bold text-primary mb-2 text-sm">Key Factors:</div>
                <ul className="list-disc list-inside space-y-1 text-xs text-text-secondary">
                  {data.directional_prediction.key_factors.map((factor, idx) => (
                    <li key={idx}>{factor}</li>
                  ))}
                </ul>
              </div>

              <div className="border-t border-border pt-3">
                <div className="font-bold text-warning text-sm">Expected Move:</div>
                <div className="text-text-primary text-sm mt-1">{data.directional_prediction.expected_move}</div>
              </div>

              <div className="mt-3 p-2 bg-background-hover/30 rounded-lg text-center">
                <div className="text-text-muted text-xs">
                  ⚠️ This prediction is based on current GEX structure, VIX ({data.directional_prediction.vix}), and historical patterns.
                  Markets can change rapidly. Use as one input among many for your trading decisions.
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* VIEW 1: TODAY'S IMPACT */}
      <div className="card">
        <button
          onClick={() => toggleSection('today')}
          className="w-full flex items-center justify-between mb-4"
        >
          <h3 className="text-lg font-bold text-text-primary flex items-center gap-2">
            ⚡ VIEW 1: TODAY'S IMPACT <span className="text-text-secondary text-sm">(Intraday Trading)</span>
          </h3>
          {expandedSections.has('today') ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
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
            <p className="text-xl font-bold text-danger">-{formatGamma(data.gamma_loss_today)} ({data.gamma_loss_pct}%)</p>
          </div>
        </div>

        <div className={`p-3 rounded-lg border mb-4 ${getRiskBgColor(data.risk_level)}`}>
          <span className="text-sm font-bold">🎯 RISK LEVEL: </span>
          <span className={`font-bold ${getRiskColor(data.risk_level)}`}>{data.risk_level}</span>
        </div>

        {expandedSections.has('today') && (
          <div className="space-y-4">
            <h4 className="text-md font-bold text-text-primary">💰 HOW TO PROFIT TODAY:</h4>

            {/* Strategy 1: Fade the Close */}
            <div className="p-3 bg-danger/5 border border-danger/20 rounded-lg">
              <div className="flex items-start gap-2 mb-2">
                <span className="px-2 py-0.5 bg-danger text-white text-xs font-bold rounded">HIGH PRIORITY</span>
                <h5 className="text-sm font-bold text-text-primary">Fade the Close</h5>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                <div>
                  <p className="text-text-secondary mb-1"><strong className="text-text-primary">Strategy:</strong> Buy directional options at 3:45pm, sell tomorrow morning</p>
                  <p className="text-text-secondary mb-1"><strong className="text-text-primary">Strike:</strong> 0.4 delta (first OTM) in trend direction</p>
                  <p className="text-text-secondary mb-1"><strong className="text-text-primary">Expiration:</strong> 0DTE or 1DTE</p>
                  <p className="text-text-secondary"><strong className="text-text-primary">Entry:</strong> {data.current_day} 3:45pm</p>
                </div>
                <div>
                  <p className="text-text-secondary mb-1"><strong className="text-text-primary">Exit:</strong> Tomorrow morning if gap move occurs</p>
                  <p className="text-text-secondary mb-1"><strong className="text-text-primary">Risk:</strong> 30% stop loss | Size: 2-3% account risk</p>
                  <p className="text-text-secondary"><strong className="text-primary">Why:</strong> Tomorrow loses {data.gamma_loss_pct}% gamma support - moves will be sharper without dealer hedging</p>
                </div>
              </div>
            </div>

            {/* Strategy 2: ATM Straddle */}
            <div className="p-3 bg-warning/5 border border-warning/20 rounded-lg">
              <div className="flex items-start gap-2 mb-2">
                <span className="px-2 py-0.5 bg-warning text-white text-xs font-bold rounded">MEDIUM PRIORITY</span>
                <h5 className="text-sm font-bold text-text-primary">ATM Straddle into Expiration</h5>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                <div>
                  <p className="text-text-secondary mb-1"><strong className="text-text-primary">Strategy:</strong> Buy volatility, not direction</p>
                  <p className="text-text-secondary mb-1"><strong className="text-text-primary">Strike:</strong> ATM (0.5 delta both sides)</p>
                  <p className="text-text-secondary mb-1"><strong className="text-text-primary">Expiration:</strong> 1DTE or 2DTE</p>
                  <p className="text-text-secondary"><strong className="text-text-primary">Entry:</strong> {data.current_day} 3:30pm</p>
                </div>
                <div>
                  <p className="text-text-secondary mb-1"><strong className="text-text-primary">Exit:</strong> Tomorrow morning on gap or quick move</p>
                  <p className="text-text-secondary mb-1"><strong className="text-text-primary">Risk:</strong> Defined (premium paid) | Size: 1-2% account risk</p>
                  <p className="text-text-secondary"><strong className="text-primary">Why:</strong> Gamma expiration creates volatility vacuum - expect {data.gamma_loss_pct}% regime shift overnight</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* VIEW 2: WEEKLY EVOLUTION */}
      <div className="card">
        <button
          onClick={() => toggleSection('weekly')}
          className="w-full flex items-center justify-between mb-4"
        >
          <h3 className="text-lg font-bold text-text-primary flex items-center gap-2">
            📅 VIEW 2: WEEKLY EVOLUTION <span className="text-text-secondary text-sm">(Positional Trading)</span>
          </h3>
          {expandedSections.has('weekly') ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
        </button>

        {/* Weekly Stats */}
        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="p-3 bg-background-hover rounded-lg text-center">
            <p className="text-text-muted text-xs mb-1">Monday Baseline</p>
            <p className="text-lg font-bold text-text-primary">{formatGamma(data.weekly_gamma.monday)}</p>
          </div>
          <div className="p-3 bg-background-hover rounded-lg text-center">
            <p className="text-text-muted text-xs mb-1">Friday End</p>
            <p className="text-lg font-bold text-text-primary">{formatGamma(data.weekly_gamma.friday)}</p>
          </div>
          <div className="p-3 bg-background-hover rounded-lg text-center">
            <p className="text-text-muted text-xs mb-1">Total Decay</p>
            <p className="text-lg font-bold text-danger">{data.weekly_gamma.total_decay_pct}%</p>
            <p className="text-xs text-warning">{data.weekly_gamma.decay_pattern}</p>
          </div>
        </div>

        {/* Week's Gamma Structure */}
        <h4 className="text-sm font-bold text-text-primary mb-2">Week's Gamma Structure:</h4>
        <div className="space-y-2 mb-4">
          {['monday', 'tuesday', 'wednesday', 'thursday', 'friday'].map((day) => {
            const dayName = day.charAt(0).toUpperCase() + day.slice(1)
            const gamma = data.weekly_gamma[day as keyof typeof data.weekly_gamma] as number
            const pct = Math.round((gamma / data.weekly_gamma.monday) * 100)
            const isToday = day === data.current_day.toLowerCase()

            return (
              <div key={day} className={`flex items-center gap-2 p-2 rounded-lg ${isToday ? 'bg-primary/10 border border-primary' : 'bg-background-hover'}`}>
                {isToday && <span className="text-primary text-xs">📍</span>}
                <span className="text-xs font-mono w-24 text-text-secondary">{dayName} {weekDates[day]}</span>
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

        {expandedSections.has('weekly') && (
          <div className="space-y-3">
            <h4 className="text-md font-bold text-text-primary">💰 HOW TO PROFIT THIS WEEK:</h4>

            {/* Weekly Strategy 1: Theta Farming */}
            <div className="p-3 bg-success/5 border border-success/20 rounded-lg">
              <h5 className="text-sm font-bold text-success mb-2">Aggressive Theta Farming (Mon-Wed)</h5>
              <p className="text-xs text-text-secondary mb-2"><strong className="text-text-primary">Description:</strong> Sell premium while gamma is strong</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                <div>
                  <p className="mb-1"><strong>Strategy:</strong> Iron Condor or Credit Spreads</p>
                  <p className="mb-1"><strong>Strikes:</strong> 0.15-0.20 delta wings (far OTM)</p>
                  <p><strong>Expiration:</strong> Friday (this week)</p>
                </div>
                <div>
                  <p className="mb-1"><strong>Entry:</strong> Monday or Tuesday morning</p>
                  <p className="mb-1"><strong>Exit:</strong> Wednesday close (50-60% profit)</p>
                  <p><strong>Size:</strong> 3-5% account risk per spread</p>
                </div>
              </div>
              <p className="text-xs mt-2"><strong className="text-primary">Why:</strong> Week starts with 100% of gamma - high mean-reversion, options will decay fast</p>
            </div>

            {/* Weekly Strategy 2: Delta Buying */}
            <div className="p-3 bg-primary/5 border border-primary/20 rounded-lg">
              <h5 className="text-sm font-bold text-primary mb-2">Delta Buying (Thu-Fri)</h5>
              <p className="text-xs text-text-secondary mb-2"><strong className="text-text-primary">Description:</strong> Switch to directional momentum plays</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                <div>
                  <p className="mb-1"><strong>Strategy:</strong> Long Calls or Puts</p>
                  <p className="mb-1"><strong>Strikes:</strong> ATM or first OTM (0.5-0.6 delta)</p>
                  <p><strong>Expiration:</strong> Next week (1 week DTE)</p>
                </div>
                <div>
                  <p className="mb-1"><strong>Entry:</strong> Thursday morning</p>
                  <p className="mb-1"><strong>Exit:</strong> Friday close or hold if strong trend</p>
                  <p><strong>Size:</strong> 2-3% account risk</p>
                </div>
              </div>
              <p className="text-xs mt-2"><strong className="text-primary">Why:</strong> By Thursday, only 12% gamma remains - low hedging = directional moves</p>
            </div>

            {/* Weekly Strategy 3: Dynamic Position Sizing */}
            <div className="p-3 bg-warning/5 border border-warning/20 rounded-lg">
              <h5 className="text-sm font-bold text-warning mb-2">Dynamic Position Sizing</h5>
              <p className="text-xs text-text-secondary mb-2"><strong className="text-text-primary">Description:</strong> Adjust size based on gamma regime through week</p>
              <div className="space-y-1 text-xs">
                <p><strong>Mon-Tue:</strong> 100% normal size (gamma protects you)</p>
                <p><strong>Wed:</strong> 75% size (transition)</p>
                <p><strong>Thu-Fri:</strong> 50% size (gamma gone, vol spikes)</p>
              </div>
              <p className="text-xs mt-2"><strong className="text-primary">Why:</strong> Risk management: {data.weekly_gamma.total_decay_pct}% weekly decay means vol will increase significantly late week</p>
            </div>
          </div>
        )}
      </div>

      {/* VIEW 3: VOLATILITY CLIFFS */}
      <div className="card">
        <button
          onClick={() => toggleSection('cliffs')}
          className="w-full flex items-center justify-between mb-4"
        >
          <h3 className="text-lg font-bold text-text-primary flex items-center gap-2">
            ⚠️ VIEW 3: VOLATILITY CLIFFS <span className="text-text-secondary text-sm">(Risk Management)</span>
          </h3>
          {expandedSections.has('cliffs') ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
        </button>

        <h4 className="text-sm font-bold text-text-primary mb-3">Relative Expiration Risk by Day:</h4>
        <div className="grid grid-cols-5 gap-2 mb-4">
          {['monday', 'tuesday', 'wednesday', 'thursday', 'friday'].map((day) => {
            const dayName = day.charAt(0).toUpperCase() + day.slice(1, 3)
            const risk = data.daily_risks[day as keyof typeof data.daily_risks]
            const isToday = day === data.current_day.toLowerCase()
            const riskLevel = getDayRiskLevel(risk)

            return (
              <div
                key={day}
                className={`p-2 rounded-lg border text-center ${isToday ? 'border-primary bg-primary/10' : 'border-border bg-background-hover'}`}
              >
                {isToday && <div className="text-primary text-xs font-bold mb-1">📍 TODAY</div>}
                <div className="text-xl mb-1">{getDayIcon(risk)}</div>
                <div className="text-xs font-bold text-text-primary mb-1">{dayName}</div>
                <div className="text-lg font-bold mb-1" style={{ color: risk >= 70 ? '#ef4444' : risk >= 50 ? '#f59e0b' : '#3b82f6' }}>
                  {risk}%
                </div>
                <div className="text-xs font-semibold" style={{ color: risk >= 70 ? '#ef4444' : risk >= 50 ? '#f59e0b' : '#3b82f6' }}>
                  {riskLevel}
                </div>
              </div>
            )
          })}
        </div>

        {expandedSections.has('cliffs') && (
          <div className="space-y-3">
            <h4 className="text-md font-bold text-text-primary">💰 STRATEGIES FOR HIGHEST RISK DAY (Friday):</h4>

            {/* Cliff Strategy 1 */}
            <div className="p-3 bg-danger/5 border border-danger/20 rounded-lg">
              <div className="flex items-start gap-2 mb-2">
                <span className="px-2 py-0.5 bg-danger text-white text-xs font-bold rounded">HIGH PRIORITY</span>
                <h5 className="text-sm font-bold text-danger">Pre-Expiration Volatility Scalp</h5>
              </div>
              <p className="text-xs text-text-secondary mb-2"><strong className="text-text-primary">Strategy:</strong> Capture chaos of gamma expiration, not direction</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                <div>
                  <p className="mb-1"><strong>Type:</strong> ATM Straddle</p>
                  <p className="mb-1"><strong>Strike:</strong> ATM (0.5 delta both sides)</p>
                  <p className="mb-1"><strong>Expiration:</strong> 0DTE (expiring Friday)</p>
                  <p><strong>Entry:</strong> Friday 10:00-11:00am</p>
                </div>
                <div>
                  <p className="mb-1"><strong>Exit:</strong> Friday 2:00-3:00pm (BEFORE 4pm)</p>
                  <p className="mb-1"><strong>Risk:</strong> Defined (premium paid)</p>
                  <p><strong>Size:</strong> 2-3% account risk</p>
                </div>
              </div>
              <p className="text-xs mt-2"><strong className="text-primary">Why:</strong> Friday has 100% gamma decay - massive expiration creates intraday volatility spike. Exit before pin risk at 4pm.</p>
            </div>

            {/* Cliff Strategy 2 */}
            <div className="p-3 bg-warning/5 border border-warning/20 rounded-lg">
              <div className="flex items-start gap-2 mb-2">
                <span className="px-2 py-0.5 bg-warning text-white text-xs font-bold rounded">MEDIUM PRIORITY</span>
                <h5 className="text-sm font-bold text-warning">Post-Expiration Directional Positioning</h5>
              </div>
              <p className="text-xs text-text-secondary mb-2"><strong className="text-text-primary">Strategy:</strong> Position day-before for explosive move day-after</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                <div>
                  <p className="mb-1"><strong>Type:</strong> Long Calls or Puts</p>
                  <p className="mb-1"><strong>Strike:</strong> 0.4-0.5 delta in expected direction</p>
                  <p className="mb-1"><strong>Expiration:</strong> 1DTE or 2DTE</p>
                  <p><strong>Entry:</strong> Friday 3:45pm</p>
                </div>
                <div>
                  <p className="mb-1"><strong>Exit:</strong> Next day morning if profit target hit</p>
                  <p className="mb-1"><strong>Risk:</strong> 30% stop loss</p>
                  <p><strong>Size:</strong> 2% account risk</p>
                </div>
              </div>
              <p className="text-xs mt-2"><strong className="text-primary">Why:</strong> After Friday gamma expires, next day will have explosive moves in prevailing trend direction</p>
            </div>

            {/* Cliff Strategy 3: Avoidance */}
            <div className="p-3 bg-primary/5 border border-primary/20 rounded-lg">
              <div className="flex items-start gap-2 mb-2">
                <span className="px-2 py-0.5 bg-primary text-white text-xs font-bold rounded">LOW PRIORITY</span>
                <h5 className="text-sm font-bold text-primary">The Avoidance Strategy</h5>
              </div>
              <p className="text-xs text-text-secondary mb-2"><strong className="text-text-primary">Strategy:</strong> Sometimes the best trade is no trade</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                <div>
                  <p className="mb-1"><strong>Type:</strong> Cash / Sidelines</p>
                  <p><strong>Entry:</strong> Close all positions day before</p>
                </div>
                <div>
                  <p className="mb-1"><strong>Exit:</strong> Re-enter next Monday</p>
                  <p><strong>Risk:</strong> 0% (no positions)</p>
                </div>
              </div>
              <p className="text-xs mt-2"><strong className="text-primary">Why:</strong> Friday shows 100% decay - if you're uncomfortable with chaos, sit out and preserve capital</p>
            </div>
          </div>
        )}
      </div>

      {/* ACTIONABLE TRADE PLAYBOOK - Dynamic based on market conditions */}
      {(() => {
        const recommendation = getTradeRecommendation()
        if (!recommendation) return null

        return (
          <div className={`card ${recommendation.bgColor} border ${recommendation.borderColor}`}>
            <h3 className="text-lg font-bold text-text-primary mb-3">🎯 Actionable Trade Playbook - Today's Opportunity</h3>

            <div className="p-3 bg-background-card rounded-lg mb-3">
              <div className="flex items-center justify-between mb-3">
                <h4 className={`text-md font-bold ${recommendation.typeColor}`}>
                  {recommendation.strategyEmoji} {recommendation.strategy}
                </h4>
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-1 rounded text-xs font-bold ${recommendation.bgColor} ${recommendation.typeColor}`}>
                    {recommendation.type}
                  </span>
                  <span className="px-2 py-1 bg-background-hover rounded text-xs font-bold text-text-primary">
                    Win Rate: {recommendation.winRate}
                  </span>
                </div>
              </div>

              <div className="mb-3">
                <p className="text-sm text-text-secondary">{recommendation.description}</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div className="space-y-2">
                  <div>
                    <h5 className="font-bold text-text-primary">📋 Trade Structure:</h5>
                    <div className="space-y-0.5 mt-1">
                      {recommendation.structure.map((item, idx) => (
                        <p key={idx}><strong>{item.label}:</strong> {typeof item.value === 'object' ? JSON.stringify(item.value) : item.value}</p>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="space-y-2">
                  <div>
                    <h5 className="font-bold text-text-primary">🎯 Exit Rules:</h5>
                    <p className="text-text-secondary">{recommendation.exitRules}</p>
                  </div>
                  <div>
                    <h5 className="font-bold text-text-primary">🛑 Stop Loss:</h5>
                    <p className="text-text-secondary">{recommendation.stopLoss}</p>
                  </div>
                  <div>
                    <h5 className="font-bold text-text-primary">💰 Position Size:</h5>
                    <p className="text-text-secondary">{recommendation.sizing}</p>
                  </div>
                </div>
              </div>

              <div className="mt-3 p-2 bg-background-hover rounded-lg">
                <h5 className="font-bold text-primary text-xs mb-1">🧠 Edge:</h5>
                <p className="text-xs text-text-secondary">{recommendation.edge}</p>
              </div>
            </div>

            {/* Current Conditions */}
            <div className="p-3 bg-background-hover rounded-lg">
              <h4 className="font-bold text-text-primary text-sm mb-2">Current Conditions:</h4>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs">
                <div>
                  <span className="text-text-muted">Symbol:</span>
                  <span className="ml-2 font-semibold text-primary">{data.symbol}</span>
                </div>
                <div>
                  <span className="text-text-muted">Net GEX:</span>
                  <span className={`ml-2 font-semibold ${data.net_gex > 0 ? 'text-success' : 'text-danger'}`}>
                    {formatGamma(data.net_gex)} ({data.net_gex > 0 ? 'Long Gamma' : 'Short Gamma'})
                  </span>
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
                  <span className="text-text-muted">Direction:</span>
                  <span className={`ml-2 font-semibold ${
                    data.directional_prediction?.direction === 'UPWARD' ? 'text-success' :
                    data.directional_prediction?.direction === 'DOWNWARD' ? 'text-danger' : 'text-warning'
                  }`}>
                    {data.directional_prediction?.direction_emoji} {data.directional_prediction?.direction} ({data.directional_prediction?.probability}%)
                  </span>
                </div>
                <div>
                  <span className="text-text-muted">Day:</span>
                  <span className="ml-2 font-semibold text-text-primary">{data.current_day}</span>
                </div>
              </div>
            </div>
          </div>
        )
      })()}

      {/* Evidence-based footer */}
      <div className="card bg-background-hover">
        <h4 className="text-xs font-bold text-text-primary mb-1">📚 EVIDENCE-BASED THRESHOLDS</h4>
        <p className="text-xs text-text-secondary">
          Thresholds based on: Academic research (Dim, Eraker, Vilkov 2023), SpotGamma professional analysis, ECB Financial Stability Review 2023,
          and validated production trading data. Context-aware adjustments for Friday expirations and high-VIX environments.
        </p>
      </div>
    </div>
  )
}
