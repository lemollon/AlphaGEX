'use client'

/**
 * ARGUS (0DTE Gamma Live) - Real-time 0DTE Net Gamma Visualization
 * Premium design with actionable insights
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import {
  Eye,
  RefreshCw,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Target,
  Zap,
  Brain,
  ChevronUp,
  ChevronDown,
  Minus,
  Bell,
  Clock,
  Bot,
  BarChart3,
  Info,
  Activity,
  Shield,
  Flame,
  ArrowRight,
  ChevronRight,
  Gauge,
  Lock,
  Unlock,
  Layers,
  Compass,
  Download,
  FileSpreadsheet,
  History,
  Play,
  Pause,
  CalendarOff,
  Search,
  CheckCircle2,
  XCircle,
  Lightbulb,
  Repeat,
  DollarSign,
  Percent,
  ArrowUpRight,
  ArrowDownRight,
  Calendar,
  Sun
} from 'lucide-react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'

// Types
interface StrikeData {
  strike: number
  net_gamma: number
  probability: number
  gamma_change_pct: number
  roc_1min: number
  roc_5min: number
  roc_30min: number
  roc_1hr: number
  roc_4hr: number
  roc_trading_day: number  // ROC since market open (8:30 AM CT)
  is_magnet: boolean
  magnet_rank: number | null
  is_pin: boolean
  is_danger: boolean
  danger_type: string | null
  gamma_flipped: boolean
  flip_direction: string | null
}

interface Magnet {
  rank: number
  strike: number
  net_gamma: number
  probability: number
}

interface DangerZone {
  strike: number
  danger_type: string
  roc_1min: number
  roc_5min: number
}

interface Alert {
  alert_type: string
  strike: number | null
  message: string
  priority: string
  triggered_at: string
}

interface Commentary {
  id: number
  text: string
  timestamp: string
  spot_price: number
  top_magnet: number
  likely_pin: number
  pin_probability: number
  danger_zones: string[] | null
  vix: number | null
}

interface ExpectedMoveChange {
  current: number
  prior_day: number | null
  at_open: number | null
  change_from_prior: number
  change_from_open: number
  pct_change_prior: number
  pct_change_open: number
  signal: 'UP' | 'DOWN' | 'FLAT' | 'WIDEN'
  sentiment: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'VOLATILE'
  interpretation: string
}

interface GammaData {
  symbol: string
  expiration_date: string
  snapshot_time: string
  spot_price: number
  expected_move: number
  expected_move_change: ExpectedMoveChange
  vix: number
  total_net_gamma: number
  gamma_regime: string
  regime_flipped: boolean
  market_status: string
  is_mock: boolean
  is_stale?: boolean  // True when showing cached live data during market hours
  is_cached?: boolean  // True when showing cached data
  cache_age_seconds?: number  // How old the cached data is
  fetched_at?: string  // Timestamp when data was fetched (Central timezone)
  data_timestamp?: string  // When Tradier data was actually fetched
  strikes: StrikeData[]
  magnets: Magnet[]
  likely_pin: number
  pin_probability: number
  danger_zones: DangerZone[]
  gamma_flips: any[]
  pinning_status?: {
    is_pinning: boolean
    pin_strike?: number
    distance_to_pin_pct?: number
    avg_roc?: number
    message?: string
    trade_idea?: string
  }
}

interface DangerZoneLog {
  id: number
  detected_at: string
  strike: number
  danger_type: string
  roc_1min: number
  roc_5min: number
  spot_price: number
  distance_from_spot_pct: number
  is_active: boolean
  resolved_at: string | null
}

interface StrikeTrend {
  dominant_status: 'BUILDING' | 'COLLAPSING' | 'SPIKE' | 'NEUTRAL'
  dominant_duration_mins: number
  current_status: string | null
  current_duration_mins: number
  status_counts: { BUILDING: number; COLLAPSING: number; SPIKE: number }
  status_durations: { BUILDING: number; COLLAPSING: number; SPIKE: number }
  total_events: number
}

interface GammaFlip30m {
  strike: number
  direction: 'POS_TO_NEG' | 'NEG_TO_POS'
  flipped_at: string
  gamma_before: number
  gamma_after: number
  mins_ago: number
}

interface Expiration {
  day: string
  date: string
  is_today: boolean
  is_past: boolean
  is_future: boolean
}

interface MarketContext {
  gamma_walls: {
    call_wall: number | null
    call_wall_distance: number | null
    call_wall_strength: string | null
    put_wall: number | null
    put_wall_distance: number | null
    put_wall_strength: string | null
    net_gamma_regime: string | null
  }
  psychology_traps: {
    active_trap: string | null
    liberation_setup: boolean
    liberation_target: number | null
    false_floor: boolean
    false_floor_strike: number | null
    polr: string | null
    polr_confidence: number | null
  }
  vix_context: {
    current: number | null
    spike_detected: boolean
    volatility_regime: string | null
  }
  rsi_alignment: {
    rsi_5m: number | null
    rsi_15m: number | null
    rsi_1h: number | null
    rsi_4h: number | null
    rsi_1d: number | null
    aligned_overbought: boolean
    aligned_oversold: boolean
  }
  monthly_magnets: {
    above: number | null
    below: number | null
  }
  regime: {
    type: string | null
    confidence: number | null
    direction: string | null
    risk_level: string | null
  }
}

// New interfaces for enhanced features - matched to actual API responses
interface AccuracyMetrics {
  date: string | null
  pin_accuracy_7d: number
  pin_accuracy_30d: number
  direction_accuracy_7d: number
  direction_accuracy_30d: number
  magnet_hit_rate_7d: number
  magnet_hit_rate_30d: number
  total_predictions: number
  message?: string
}

interface BotPosition {
  bot: string  // ARES, ATHENA, PHOENIX
  strategy: string  // Iron Condor, Directional Spread, etc.
  status: string  // open, watching, closed
  strikes?: string  // "590/610" format
  direction?: string  // BULLISH, BEARISH
  pnl?: number
  safe?: boolean
}

interface TradeIdea {
  id: string
  setup_type: string
  direction: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
  entry: number
  target: number
  stop: number
  risk_reward: number
  confidence: number
  rationale: string
  expires_at?: string
}

interface PatternMatch {
  date: string
  similarity_score: number
  outcome_direction: 'UP' | 'DOWN' | 'FLAT'
  outcome_pct: number
  price_change: number
  gamma_regime_then: string
  mm_state: string
  // Price details
  open_price: number | null
  close_price: number | null
  day_high: number | null
  day_low: number | null
  day_range: number | null
  // Key levels
  flip_point: number | null
  call_wall: number | null
  put_wall: number | null
  // Summary
  summary: string
}

interface PatternData {
  patterns: PatternMatch[]
  current_structure?: {
    gamma_regime: string
    top_magnet: number | null
    likely_pin: number | null
  }
  message?: string
}

interface EMTrendPoint {
  time: string
  expected_move: number
  pct_change: number
}

// EOD Strike Statistics for summary table
interface EODStrikeStat {
  strike: number
  spikeCount: number
  flipCount: number
  peakRoc: number
  timeAsMagnet: number  // minutes
  trend: 'BUILDING' | 'COLLAPSING' | 'STABLE' | 'VOLATILE'
  yesterdaySpikes?: number  // for comparison
}

// 0DTE symbols supported by ARGUS (all have daily expirations Mon-Fri)
const AVAILABLE_SYMBOLS = [
  { symbol: 'SPY', name: 'S&P 500 ETF', supported: true },
  { symbol: 'QQQ', name: 'Nasdaq 100 ETF', supported: true },
  { symbol: 'IWM', name: 'Russell 2000 ETF', supported: true },
  { symbol: 'SPX', name: 'S&P 500 Index', supported: true },
  { symbol: 'DIA', name: 'Dow Jones ETF', supported: true },
]

export default function ArgusPage() {
  const [gammaData, setGammaData] = useState<GammaData | null>(null)
  const [lastLiveData, setLastLiveData] = useState<GammaData | null>(null)  // Preserve last live data during market hours
  const [expirations, setExpirations] = useState<Expiration[]>([])
  const [activeDay, setActiveDay] = useState<string>('today')
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [commentary, setCommentary] = useState<Commentary[]>([])
  const [dangerZoneLogs, setDangerZoneLogs] = useState<DangerZoneLog[]>([])
  const [strikeTrends, setStrikeTrends] = useState<Record<string, StrikeTrend>>({})
  const [gammaFlips30m, setGammaFlips30m] = useState<GammaFlip30m[]>([])
  const [timeToExpiry, setTimeToExpiry] = useState<string>('')
  const [marketContext, setMarketContext] = useState<MarketContext | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [dataTimestamp, setDataTimestamp] = useState<Date | null>(null)  // When data was actually fetched
  const [selectedStrike, setSelectedStrike] = useState<StrikeData | null>(null)

  // New state for enhanced features
  const [selectedSymbol, setSelectedSymbol] = useState<string>('SPY')
  const [symbolSearch, setSymbolSearch] = useState<string>('')
  const [showSymbolDropdown, setShowSymbolDropdown] = useState(false)
  const [accuracyMetrics, setAccuracyMetrics] = useState<AccuracyMetrics | null>(null)
  const [botPositions, setBotPositions] = useState<BotPosition[]>([])
  const [tradeIdeas, setTradeIdeas] = useState<TradeIdea[]>([])
  const [patternMatches, setPatternMatches] = useState<PatternMatch[]>([])
  const [emTrend, setEmTrend] = useState<EMTrendPoint[]>([])
  const [showAccuracyPanel, setShowAccuracyPanel] = useState(true)
  const [showTradeIdeas, setShowTradeIdeas] = useState(true)

  // Next-day gamma data (tomorrow's expiration)
  const [tomorrowGammaData, setTomorrowGammaData] = useState<GammaData | null>(null)

  // EOD Strike Statistics
  const [eodStats, setEodStats] = useState<EODStrikeStat[]>([])

  // ROC timeframe selector - for extra long timeframes only (4hr, day)
  // 1m, 5m, 30m, 1hr ROC are always visible in the table
  type RocTimeframe = '4hr' | 'day'
  const [selectedRocTimeframe, setSelectedRocTimeframe] = useState<RocTimeframe>('4hr')

  const rocTimeframeOptions: { value: RocTimeframe; label: string; shortLabel: string }[] = [
    { value: '4hr', label: '4 Hours', shortLabel: '4h' },
    { value: 'day', label: 'Trading Day', shortLabel: 'Day' },
  ]

  // Helper to get ROC value for selected longer timeframe (4hr or Day)
  const getLongRocValue = (strike: StrikeData): number => {
    switch (selectedRocTimeframe) {
      case '4hr': return strike.roc_4hr ?? 0
      case 'day': return strike.roc_trading_day ?? 0
      default: return strike.roc_4hr ?? 0
    }
  }

  // EMA smoothed maxGamma state
  const [smoothedMaxGamma, setSmoothedMaxGamma] = useState<number>(1)

  // Refs for stability improvements
  const initialLoadRef = useRef(true)
  const previousStrikesRef = useRef<Map<number, StrikeData>>(new Map())

  // Reset data when symbol changes
  useEffect(() => {
    // Clear cached data when switching symbols
    setLastLiveData(null)
    setGammaData(null)
    setTomorrowGammaData(null)
    setError(null)
    setSmoothedMaxGamma(1)
    previousStrikesRef.current = new Map()
    initialLoadRef.current = true
  }, [selectedSymbol])

  // EMA smoothing for maxGamma to prevent scale jumping
  const EMA_ALPHA = 0.3  // 30% new value, 70% previous - same as backend EM smoothing
  const rawMaxGamma = gammaData?.strikes && gammaData.strikes.length > 0
    ? Math.max(...gammaData.strikes.map(s => Math.abs(s.net_gamma || 0)), 1)
    : 1

  useEffect(() => {
    if (rawMaxGamma > 0) {
      setSmoothedMaxGamma(prev => {
        if (prev === 1 && rawMaxGamma !== 1) {
          // First real value - initialize immediately
          return rawMaxGamma
        }
        // EMA: smoothed = alpha * new + (1 - alpha) * previous
        return EMA_ALPHA * rawMaxGamma + (1 - EMA_ALPHA) * prev
      })
    }
  }, [rawMaxGamma])

  // Polling intervals (in milliseconds)
  const FAST_POLL_INTERVAL = 15000  // 15 seconds for gamma data
  const MEDIUM_POLL_INTERVAL = 30000  // 30 seconds for alerts and context
  const SLOW_POLL_INTERVAL = 60000  // 60 seconds for commentary

  // Check if market is currently open (9:30 AM - 4:00 PM CT, Mon-Fri)
  const isMarketOpen = useCallback(() => {
    const now = new Date()
    const ct = new Date(now.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
    const day = ct.getDay()
    const hour = ct.getHours()
    const minute = ct.getMinutes()
    const timeInMinutes = hour * 60 + minute
    // Mon-Fri (1-5), 9:30 AM (570 min) to 4:00 PM (960 min)
    return day >= 1 && day <= 5 && timeInMinutes >= 570 && timeInMinutes <= 960
  }, [])

  // Expand/Collapse State for sections - default to expanded
  const [alertsExpanded, setAlertsExpanded] = useState(true)
  const [dangerZonesExpanded, setDangerZonesExpanded] = useState(true)

  // Historical Replay State
  const [replayMode, setReplayMode] = useState(false)
  const [replayDates, setReplayDates] = useState<string[]>([])
  const [selectedReplayDate, setSelectedReplayDate] = useState<string>('')
  const [replayTimes, setReplayTimes] = useState<string[]>([])
  const [selectedReplayTime, setSelectedReplayTime] = useState<string>('')

  // Removed single refreshIntervalRef - now using separate refs for different polling speeds
  // Ref to access lastLiveData without adding to deps (prevents circular dependency)
  const lastLiveDataRef = useRef<GammaData | null>(null)
  useEffect(() => {
    lastLiveDataRef.current = lastLiveData
  }, [lastLiveData])

  // Fetch functions
  const fetchGammaData = useCallback(async (day?: string) => {
    try {
      // Only show loading on initial load, not on refresh
      if (initialLoadRef.current) {
        setLoading(true)
      }
      const expiration = day && day !== 'today' ? day.toLowerCase() : undefined
      const response = await apiClient.getArgusGamma(selectedSymbol, expiration)
      if (response.data?.success && response.data?.data) {
        const newData = response.data.data

        // If we receive mock data during market hours and have last live data, use last live data
        if (newData.is_mock && isMarketOpen() && lastLiveDataRef.current) {
          console.log('[ARGUS] Mock data received during market hours, using last live data')
          // Keep displaying last live data but mark it as stale
          setGammaData(prev => prev ? { ...prev, is_stale: true } : lastLiveDataRef.current ? { ...lastLiveDataRef.current, is_stale: true } : null)
        } else {
          // MERGE STRATEGY: Only update strikes that changed, preserving array reference stability
          setGammaData(prev => {
            if (!prev) return newData

            // Guard against missing strikes array
            if (!newData.strikes || !Array.isArray(newData.strikes)) {
              return newData
            }

            // Create a map of previous strikes for quick lookup
            const prevStrikesMap = new Map(prev.strikes?.map(s => [s.strike, s]) || [])

            // Merge strikes: update existing, add new ones
            const mergedStrikes = newData.strikes.map((newStrike: StrikeData) => {
              const prevStrike = prevStrikesMap.get(newStrike.strike)
              if (!prevStrike) return newStrike

              // Check if anything actually changed
              const hasChanged =
                prevStrike.net_gamma !== newStrike.net_gamma ||
                prevStrike.probability !== newStrike.probability ||
                prevStrike.is_magnet !== newStrike.is_magnet ||
                prevStrike.is_pin !== newStrike.is_pin ||
                prevStrike.is_danger !== newStrike.is_danger

              // Only return new object if something changed
              return hasChanged ? newStrike : prevStrike
            })

            // Update previous strikes ref for EOD tracking
            newData.strikes.forEach((s: StrikeData) => {
              previousStrikesRef.current.set(s.strike, s)
            })

            return { ...newData, strikes: mergedStrikes }
          })

          // Store live data for fallback during market hours
          if (!newData.is_mock) {
            setLastLiveData(newData)
          }
        }

        // Use backend's data_timestamp (when Tradier data was actually fetched)
        const dataTime = newData.data_timestamp
          ? new Date(newData.data_timestamp)
          : new Date(newData.fetched_at || Date.now())
        setDataTimestamp(dataTime)

        // Use backend's fetched_at timestamp for display
        const fetchedAt = newData.fetched_at
          ? new Date(newData.fetched_at)
          : new Date()
        setLastUpdated(fetchedAt)
        setError(null)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch data')
    } finally {
      setLoading(false)
      initialLoadRef.current = false
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSymbol, isMarketOpen])  // Removed lastLiveData - accessed via ref to prevent circular dependency

  // Helper to get tomorrow's expiration date (handles weekends and holidays)
  const getTomorrowExpiration = useCallback((): string => {
    const now = new Date()
    const ct = new Date(now.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
    const tomorrow = new Date(ct)
    tomorrow.setDate(tomorrow.getDate() + 1)

    // If tomorrow is Saturday, skip to Monday
    if (tomorrow.getDay() === 6) {
      tomorrow.setDate(tomorrow.getDate() + 2)
    }
    // If tomorrow is Sunday, skip to Monday
    else if (tomorrow.getDay() === 0) {
      tomorrow.setDate(tomorrow.getDate() + 1)
    }

    return tomorrow.toISOString().split('T')[0]
  }, [])

  // Fetch tomorrow's gamma data for next-day overlay
  const fetchTomorrowGammaData = useCallback(async () => {
    try {
      const tomorrowDate = getTomorrowExpiration()
      const response = await apiClient.getArgusGamma(selectedSymbol, tomorrowDate)
      if (response.data?.success && response.data?.data) {
        setTomorrowGammaData(response.data.data)
      }
    } catch (err) {
      console.error('[ARGUS] Error fetching tomorrow gamma data:', err)
      // Don't show error to user - tomorrow's data is optional enhancement
    }
  }, [selectedSymbol, getTomorrowExpiration])

  const fetchDangerZoneLogs = useCallback(async () => {
    try {
      const response = await apiClient.getArgusDangerZoneLogs()
      if (response.data?.success && response.data?.data?.logs) {
        setDangerZoneLogs(response.data.data.logs)
      }
    } catch (err) {
      console.error('[ARGUS] Error fetching danger zone logs:', err)
    }
  }, [])

  const fetchExpirations = useCallback(async () => {
    try {
      const response = await apiClient.getArgusExpirations()
      if (response.data?.success && response.data?.data?.expirations) {
        setExpirations(response.data.data.expirations)
        const today = response.data.data.expirations.find((e: Expiration) => e.is_today)
        if (today) setActiveDay(today.day)
      }
    } catch (err) {}
  }, [])

  const fetchAlerts = useCallback(async () => {
    try {
      const response = await apiClient.getArgusAlerts()
      if (response.data?.success && response.data?.data?.alerts) {
        setAlerts(response.data.data.alerts)
      }
    } catch (err) {}
  }, [])

  const fetchCommentary = useCallback(async () => {
    try {
      console.log('[ARGUS] Fetching commentary...')
      const response = await apiClient.getArgusCommentary()
      console.log('[ARGUS] Commentary response:', response)
      if (response.data?.success && response.data?.data?.commentary) {
        setCommentary(response.data.data.commentary)
        console.log('[ARGUS] Commentary loaded:', response.data.data.commentary.length, 'entries')
      } else {
        console.warn('[ARGUS] No commentary data in response:', response.data?.data?.message || 'Unknown')
      }
    } catch (err) {
      console.error('[ARGUS] Error fetching commentary:', err)
    }
  }, [])

  const fetchContext = useCallback(async () => {
    try {
      const response = await apiClient.getArgusContext()
      if (response.data?.success && response.data?.data) {
        setMarketContext(response.data.data)
      }
    } catch (err) {}
  }, [])

  const fetchStrikeTrends = useCallback(async () => {
    try {
      const response = await apiClient.getArgusStrikeTrends()
      if (response.data?.success && response.data?.data?.trends) {
        setStrikeTrends(response.data.data.trends)
      }
    } catch (err) {
      console.error('[ARGUS] Error fetching strike trends:', err)
    }
  }, [])

  const fetchGammaFlips30m = useCallback(async () => {
    try {
      const response = await apiClient.getArgusGammaFlips()
      if (response.data?.success && response.data?.data?.flips) {
        setGammaFlips30m(response.data.data.flips)
      }
    } catch (err) {
      console.error('[ARGUS] Error fetching gamma flips:', err)
    }
  }, [])

  // Fetch accuracy metrics
  const fetchAccuracyMetrics = useCallback(async () => {
    try {
      const response = await apiClient.getArgusAccuracy()
      if (response.data?.success && response.data?.data) {
        setAccuracyMetrics(response.data.data)
      }
    } catch (err) {
      console.error('[ARGUS] Error fetching accuracy metrics:', err)
    }
  }, [])

  // Fetch bot positions - API returns 'positions' array
  const fetchBotPositions = useCallback(async () => {
    try {
      const response = await apiClient.getArgusBots()
      if (response.data?.success && response.data?.data?.positions) {
        setBotPositions(response.data.data.positions)
      } else if (response.data?.success) {
        // No positions - that's okay, show empty state
        setBotPositions([])
      }
    } catch (err) {
      console.error('[ARGUS] Error fetching bot positions:', err)
      // Don't set fake data - just leave as empty array
    }
  }, [])

  // Fetch pattern matches - API may return empty patterns with message
  const fetchPatternMatches = useCallback(async () => {
    try {
      const response = await apiClient.getArgusPatterns()
      if (response.data?.success && response.data?.data) {
        // Patterns may be empty with a message - that's expected
        setPatternMatches(response.data.data.patterns || [])
      }
    } catch (err) {
      console.error('[ARGUS] Error fetching pattern matches:', err)
      // Don't set fake data
    }
  }, [])

  // Generate trade ideas based on current gamma structure
  const generateTradeIdeas = useCallback(() => {
    if (!gammaData) return

    const ideas: TradeIdea[] = []
    const { spot_price, gamma_regime, magnets, likely_pin, expected_move, danger_zones } = gammaData

    // Idea 1: Magnet Play
    if (magnets[0] && Math.abs(magnets[0].strike - spot_price) > 0.5) {
      const targetMagnet = magnets[0].strike
      const isAbove = targetMagnet > spot_price
      ideas.push({
        id: 'magnet-play',
        setup_type: 'Gamma Magnet',
        direction: isAbove ? 'BULLISH' : 'BEARISH',
        entry: spot_price,
        target: targetMagnet,
        stop: isAbove ? spot_price - (targetMagnet - spot_price) * 0.5 : spot_price + (spot_price - targetMagnet) * 0.5,
        risk_reward: 2.0,
        confidence: Math.min(magnets[0].probability, 85),
        rationale: `Price gravitating toward ${isAbove ? 'call' : 'put'} magnet at $${targetMagnet}. ${gamma_regime} gamma supports this move.`
      })
    }

    // Idea 2: Pin Play (if close to expiry)
    if (likely_pin && Math.abs(likely_pin - spot_price) < expected_move) {
      ideas.push({
        id: 'pin-play',
        setup_type: 'Expiry Pin',
        direction: 'NEUTRAL',
        entry: spot_price,
        target: likely_pin,
        stop: likely_pin - expected_move * 1.5,
        risk_reward: 1.5,
        confidence: gammaData.pin_probability,
        rationale: `Max pain at $${likely_pin}. Iron Condor or credit spread around this strike could capture decay.`
      })
    }

    // Idea 3: Regime Play
    if (gamma_regime === 'NEGATIVE' && danger_zones.length < 2) {
      ideas.push({
        id: 'regime-momentum',
        setup_type: 'Negative Gamma Momentum',
        direction: 'BULLISH', // or BEARISH based on direction
        entry: spot_price,
        target: spot_price + expected_move * 0.8,
        stop: spot_price - expected_move * 0.4,
        risk_reward: 2.0,
        confidence: 65,
        rationale: 'Negative gamma amplifies directional moves. Momentum scalps favored over mean reversion.'
      })
    }

    setTradeIdeas(ideas)
  }, [gammaData])

  // Build EM trend from history
  const buildEMTrend = useCallback(() => {
    if (!gammaData?.expected_move_change) return

    // For now, use current + prior day data to show trend
    const trend: EMTrendPoint[] = []
    const now = new Date()

    if (gammaData.expected_move_change.prior_day) {
      trend.push({
        time: 'Prior Close',
        expected_move: gammaData.expected_move_change.prior_day,
        pct_change: 0
      })
    }

    if (gammaData.expected_move_change.at_open) {
      trend.push({
        time: 'Open',
        expected_move: gammaData.expected_move_change.at_open,
        pct_change: gammaData.expected_move_change.pct_change_open || 0
      })
    }

    trend.push({
      time: 'Now',
      expected_move: gammaData.expected_move_change.current,
      pct_change: gammaData.expected_move_change.pct_change_prior || 0
    })

    setEmTrend(trend)
  }, [gammaData])

  // Effect to generate trade ideas when gamma data updates
  useEffect(() => {
    generateTradeIdeas()
    buildEMTrend()
  }, [generateTradeIdeas, buildEMTrend])

  // Calculate time to expiry (market close at 3:00 PM CT / 4:00 PM ET)
  useEffect(() => {
    const calculateTimeToExpiry = () => {
      const now = new Date()
      const ct = new Date(now.toLocaleString('en-US', { timeZone: 'America/Chicago' }))
      const marketClose = new Date(ct)
      marketClose.setHours(15, 0, 0, 0) // 3:00 PM CT

      // If past close time, show "EXPIRED"
      if (ct > marketClose) {
        setTimeToExpiry('EXPIRED')
        return
      }

      const diff = marketClose.getTime() - ct.getTime()
      const hours = Math.floor(diff / (1000 * 60 * 60))
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
      const seconds = Math.floor((diff % (1000 * 60)) / 1000)

      if (hours > 0) {
        setTimeToExpiry(`${hours}h ${minutes}m`)
      } else if (minutes > 0) {
        setTimeToExpiry(`${minutes}m ${seconds}s`)
      } else {
        setTimeToExpiry(`${seconds}s`)
      }
    }

    calculateTimeToExpiry()
    const timer = setInterval(calculateTimeToExpiry, 1000)
    return () => clearInterval(timer)
  }, [])

  // Historical Replay Functions
  const fetchReplayDates = useCallback(async () => {
    try {
      const response = await apiClient.getArgusReplayDates()
      if (response.data?.success && response.data?.data?.dates) {
        setReplayDates(response.data.data.dates)
        if (response.data.data.dates.length > 0 && !selectedReplayDate) {
          setSelectedReplayDate(response.data.data.dates[0])
        }
      }
    } catch (err) {}
  }, [selectedReplayDate])

  const fetchReplayData = useCallback(async (date: string, time?: string) => {
    try {
      setLoading(true)
      const response = await apiClient.getArgusReplay(date, time)
      if (response.data?.success && response.data?.data) {
        setGammaData(response.data.data)
        // Use backend's fetched_at timestamp (when data was recorded), not local time
        const fetchedAt = response.data.data.fetched_at
          ? new Date(response.data.data.fetched_at)
          : new Date()
        setLastUpdated(fetchedAt)
        // Set available times if returned
        if (response.data.data.available_times) {
          setReplayTimes(response.data.data.available_times)
        }
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch replay data')
    } finally {
      setLoading(false)
    }
  }, [])

  const toggleReplayMode = () => {
    if (replayMode) {
      // Exiting replay mode - go back to live
      setReplayMode(false)
      setAutoRefresh(true)
      fetchGammaData(activeDay)
    } else {
      // Entering replay mode
      setReplayMode(true)
      setAutoRefresh(false)
      fetchReplayDates()
    }
  }

  useEffect(() => {
    // Fetch all data in parallel for faster initial load
    const fetchAllData = async () => {
      try {
        await Promise.all([
          fetchExpirations(),
          fetchGammaData(),
          fetchTomorrowGammaData(),  // Fetch next-day data
          fetchAlerts(),
          fetchCommentary(),
          fetchContext(),
          fetchDangerZoneLogs(),
          fetchStrikeTrends(),
          fetchGammaFlips30m(),
          fetchAccuracyMetrics(),
          fetchBotPositions(),
          fetchPatternMatches()
        ])
      } catch (err) {
        console.error('Error fetching initial data:', err)
      }
    }
    fetchAllData()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSymbol])  // Simplified deps - fetch on mount and symbol change only

  // Check if market is closed or holiday
  const isMarketClosed = gammaData?.market_status === 'closed' || gammaData?.market_status === 'holiday'
  const isHoliday = gammaData?.market_status === 'holiday'
  // Check if showing simulated data
  const isMockData = gammaData?.is_mock === true

  // Refs for multiple polling intervals
  const fastPollRef = useRef<NodeJS.Timeout | null>(null)
  const mediumPollRef = useRef<NodeJS.Timeout | null>(null)
  const slowPollRef = useRef<NodeJS.Timeout | null>(null)

  // ALWAYS poll when autoRefresh is enabled - don't depend on gammaData state
  // This ensures live updates regardless of API responses
  useEffect(() => {
    // Clear any existing intervals first
    if (fastPollRef.current) clearInterval(fastPollRef.current)
    if (mediumPollRef.current) clearInterval(mediumPollRef.current)
    if (slowPollRef.current) clearInterval(slowPollRef.current)

    if (autoRefresh) {
      console.log('[ARGUS] Starting auto-refresh polling...')

      // Fast polling: Gamma data and danger zones every 15 seconds
      fastPollRef.current = setInterval(() => {
        console.log('[ARGUS] Fast poll: fetching gamma data and danger zone logs')
        fetchGammaData(activeDay)
        fetchDangerZoneLogs()
      }, 15000)

      // Medium polling: Alerts, context, trends, flips, bots every 30 seconds
      mediumPollRef.current = setInterval(() => {
        console.log('[ARGUS] Medium poll: fetching alerts, context, trends, flips, bots')
        fetchAlerts()
        fetchContext()
        fetchStrikeTrends()
        fetchGammaFlips30m()
        fetchBotPositions()
      }, 30000)

      // Slow polling: Commentary, accuracy, patterns, tomorrow's data every 60 seconds
      slowPollRef.current = setInterval(() => {
        fetchCommentary()
        fetchAccuracyMetrics()
        fetchPatternMatches()
        fetchTomorrowGammaData()
      }, 60000)
    }

    return () => {
      if (fastPollRef.current) clearInterval(fastPollRef.current)
      if (mediumPollRef.current) clearInterval(mediumPollRef.current)
      if (slowPollRef.current) clearInterval(slowPollRef.current)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, activeDay]) // Intentionally minimal deps - fetch functions are stable, avoid re-creating intervals

  // Compute EOD Strike Statistics from danger zone logs and strike trends
  // MUST be before early returns to satisfy React hooks rules
  const computedEodStats = useMemo((): EODStrikeStat[] => {
    if (!gammaData?.strikes) return []

    const strikeStats = new Map<number, EODStrikeStat>()

    // Initialize with all current strikes
    gammaData.strikes.forEach(strike => {
      strikeStats.set(strike.strike, {
        strike: strike.strike,
        spikeCount: 0,
        flipCount: 0,
        peakRoc: Math.max(Math.abs(strike.roc_1min), Math.abs(strike.roc_5min)),
        timeAsMagnet: 0,
        trend: 'STABLE'
      })
    })

    // Count spikes from danger zone logs
    dangerZoneLogs.forEach(log => {
      const stat = strikeStats.get(log.strike)
      if (stat) {
        if (log.danger_type === 'SPIKE') {
          stat.spikeCount++
        }
        stat.peakRoc = Math.max(stat.peakRoc, Math.abs(log.roc_5min))
      }
    })

    // Count flips from gamma flips data
    gammaFlips30m.forEach(flip => {
      const stat = strikeStats.get(flip.strike)
      if (stat) {
        stat.flipCount++
      }
    })

    // Get trends from strike trends data
    Object.entries(strikeTrends).forEach(([strikeKey, trend]) => {
      const strikeNum = parseFloat(strikeKey)
      const stat = strikeStats.get(strikeNum)
      if (stat) {
        stat.timeAsMagnet = trend.status_durations?.BUILDING || 0
        if (trend.dominant_status === 'BUILDING') stat.trend = 'BUILDING'
        else if (trend.dominant_status === 'COLLAPSING') stat.trend = 'COLLAPSING'
        else if (trend.total_events > 5) stat.trend = 'VOLATILE'
        else stat.trend = 'STABLE'
      }
    })

    // Sort by activity (spikes + flips) and return top 5
    return Array.from(strikeStats.values())
      .sort((a, b) => (b.spikeCount + b.flipCount + b.peakRoc) - (a.spikeCount + a.flipCount + a.peakRoc))
      .slice(0, 5)
  }, [gammaData?.strikes, dangerZoneLogs, gammaFlips30m, strikeTrends])

  const handleDayChange = (day: string) => {
    setActiveDay(day)
    fetchGammaData(day)
  }

  // Helpers
  const formatGamma = (value: number): string => {
    const absValue = Math.abs(value)
    if (absValue >= 1e9) return `${(value / 1e9).toFixed(1)}B`
    if (absValue >= 1e6) return `${(value / 1e6).toFixed(1)}M`
    if (absValue >= 1e3) return `${(value / 1e3).toFixed(1)}K`
    return value.toFixed(0)
  }

  // Download logs to CSV/Excel
  const downloadAlertsToExcel = () => {
    if (alerts.length === 0) return
    const headers = ['Time (CT)', 'Type', 'Strike', 'Message', 'Priority']
    const rows = alerts.map(a => [
      new Date(a.triggered_at).toLocaleString('en-US', { timeZone: 'America/Chicago' }),
      a.alert_type,
      a.strike ? `$${a.strike}` : '-',
      a.message,
      a.priority
    ])
    const csv = [headers.join(','), ...rows.map(r => r.map(c => `"${c}"`).join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `argus_alerts_${new Date().toISOString().split('T')[0]}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const downloadDangerZonesToExcel = () => {
    if (dangerZoneLogs.length === 0) return
    const headers = ['Detected At (CT)', 'Strike', 'Type', 'ROC 1min', 'ROC 5min', 'Spot Price', 'Distance %', 'Status', 'Resolved At']
    const rows = dangerZoneLogs.map(log => [
      new Date(log.detected_at).toLocaleString('en-US', { timeZone: 'America/Chicago' }),
      `$${log.strike}`,
      log.danger_type,
      `${log.roc_1min.toFixed(1)}%`,
      `${log.roc_5min.toFixed(1)}%`,
      log.spot_price ? `$${log.spot_price.toFixed(2)}` : '-',
      `${log.distance_from_spot_pct.toFixed(2)}%`,
      log.is_active ? 'Active' : 'Resolved',
      log.resolved_at ? new Date(log.resolved_at).toLocaleString('en-US', { timeZone: 'America/Chicago' }) : '-'
    ])
    const csv = [headers.join(','), ...rows.map(r => r.map(c => `"${c}"`).join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `argus_danger_zones_${new Date().toISOString().split('T')[0]}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const getBarColor = (strike: StrikeData): string => {
    if (strike.is_pin) return 'bg-purple-500'
    if (strike.is_magnet && strike.magnet_rank === 1) return 'bg-yellow-400'
    if (strike.is_magnet) return 'bg-yellow-500'
    if (strike.is_danger) return 'bg-orange-500'
    if (strike.net_gamma > 0) return 'bg-emerald-500'
    return 'bg-rose-500'
  }

  const getBarHeightPx = (gamma: number, maxGamma: number): number => {
    if (maxGamma === 0) return 20
    return Math.max(20, Math.min(160, (Math.abs(gamma) / maxGamma) * 160))
  }

  // Generate AI insight based on current data
  const generateInsight = (): string => {
    if (!gammaData) return "Loading market analysis..."

    const { spot_price, gamma_regime, magnets, likely_pin, danger_zones, vix } = gammaData
    const topMagnet = magnets[0]
    const dangerCount = danger_zones?.length || 0

    let insight = ""

    if (gamma_regime === 'POSITIVE') {
      insight = `Market makers are in POSITIVE gamma territory. This typically means price action will be more stable with dealers selling into rallies and buying dips. `
    } else if (gamma_regime === 'NEGATIVE') {
      insight = `Market makers are in NEGATIVE gamma territory. Expect amplified moves as dealers must buy into rallies and sell into dips. Increased volatility likely. `
    } else {
      insight = `Market is in NEUTRAL gamma regime near the flip point. Watch for directional breaks. `
    }

    if (topMagnet) {
      const distance = ((topMagnet.strike - spot_price) / spot_price * 100).toFixed(2)
      insight += `The strongest magnet is at $${topMagnet.strike} (${distance > '0' ? '+' : ''}${distance}% from spot) with ${topMagnet.probability.toFixed(0)}% probability. `
    }

    if (likely_pin && likely_pin !== topMagnet?.strike) {
      insight += `Pin risk at $${likely_pin} for expiration. `
    }

    if (dangerCount > 3) {
      insight += `⚠️ ${dangerCount} danger zones detected - gamma is shifting rapidly at multiple strikes. Exercise caution with directional trades.`
    } else if (dangerCount > 0) {
      insight += `${dangerCount} strike(s) showing unusual gamma activity.`
    }

    if (vix > 25) {
      insight += ` Elevated VIX (${vix.toFixed(1)}) suggests options are pricing significant moves.`
    }

    return insight
  }

  // Export to Excel
  const exportToExcel = () => {
    if (!gammaData) return

    // Create CSV content
    const headers = ['Strike', 'Net Gamma', 'Probability %', '1m ROC', '5m ROC', 'Is Pin', 'Is Magnet', 'Is Danger', 'Danger Type']
    const rows = gammaData.strikes.map(s => [
      s.strike,
      s.net_gamma,
      s.probability.toFixed(2),
      s.roc_1min.toFixed(2),
      s.roc_5min.toFixed(2),
      s.is_pin ? 'Yes' : 'No',
      s.is_magnet ? 'Yes' : 'No',
      s.is_danger ? 'Yes' : 'No',
      s.danger_type || ''
    ])

    // Add summary section
    const summary = [
      [],
      ['=== ARGUS Summary ==='],
      ['Export Time', new Date().toLocaleString()],
      ['Symbol', gammaData.symbol],
      ['Spot Price', gammaData.spot_price],
      ['Expected Move', `±${gammaData.expected_move.toFixed(2)}`],
      ['VIX', gammaData.vix.toFixed(2)],
      ['Gamma Regime', gammaData.gamma_regime],
      ['Likely Pin', gammaData.likely_pin],
      ['Pin Probability', `${gammaData.pin_probability.toFixed(1)}%`],
      [],
      ['=== Top Magnets ==='],
      ...gammaData.magnets.map((m, i) => [`Magnet #${i + 1}`, `$${m.strike}`, `${m.probability.toFixed(1)}%`]),
      [],
      ['=== Expected Move Change ==='],
      ['Signal', gammaData.expected_move_change?.signal || 'N/A'],
      ['Sentiment', gammaData.expected_move_change?.sentiment || 'N/A'],
      ['Prior Day EM', gammaData.expected_move_change?.prior_day ? `±$${gammaData.expected_move_change.prior_day.toFixed(2)}` : 'N/A'],
      ['Current EM', `±$${gammaData.expected_move_change?.current.toFixed(2) || 'N/A'}`],
      ['Change %', `${gammaData.expected_move_change?.pct_change_prior.toFixed(1) || 0}%`],
      [],
      ['=== Danger Zones ==='],
      ...gammaData.danger_zones.map(d => [d.danger_type, `$${d.strike}`, `ROC: ${d.roc_5min.toFixed(1)}%`]),
      [],
      ['=== Alerts ==='],
      ...alerts.map(a => [a.priority, a.message, new Date(a.triggered_at).toLocaleTimeString('en-US', { timeZone: 'America/Chicago', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true }) + ' CT']),
      [],
      ['=== Strike Data ==='],
      headers
    ]

    const csvContent = [...summary.map(row => row.join(',')), ...rows.map(row => row.join(','))].join('\n')

    // Create download
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    const filename = `ARGUS_${gammaData.symbol}_${new Date().toISOString().split('T')[0]}.csv`
    link.href = URL.createObjectURL(blob)
    link.download = filename
    link.click()
    URL.revokeObjectURL(link.href)
  }

  // Loading
  if (loading && !gammaData) {
    return (
      <div className="min-h-screen bg-background">
        <Navigation />
        <main className="pt-24 px-4 max-w-7xl mx-auto">
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <RefreshCw className="w-10 h-10 text-purple-500 animate-spin mx-auto mb-4" />
              <p className="text-gray-400">Loading ARGUS data...</p>
            </div>
          </div>
        </main>
      </div>
    )
  }

  // maxGamma is smoothed via useEffect declared above, before early returns
  const maxGamma = smoothedMaxGamma

  // Calculate maxGamma for tomorrow's data (independent scale)
  const tomorrowMaxGamma = tomorrowGammaData?.strikes && tomorrowGammaData.strikes.length > 0
    ? Math.max(...tomorrowGammaData.strikes.map(s => Math.abs(s.net_gamma || 0)), 1)
    : 1

  const highPriorityAlerts = alerts.filter(a => a.priority === 'HIGH' || a.priority === 'MEDIUM')

  // Danger zones for MAIN DISPLAY - use ONLY current snapshot (real-time, not stale)
  // Event Log shows history with timestamps separately
  const buildingZones = gammaData?.danger_zones?.filter(d => d.danger_type === 'BUILDING') || []
  const collapsingZones = gammaData?.danger_zones?.filter(d => d.danger_type === 'COLLAPSING') || []
  const spikeZones = gammaData?.danger_zones?.filter(d => d.danger_type === 'SPIKE') || []

  return (
    <div className="min-h-screen bg-background">
      <Navigation />
      <main className="pt-24 px-4 sm:px-6 lg:px-8 max-w-[1600px] mx-auto pb-8">

        {/* Header */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-6">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-purple-500/20 flex items-center justify-center">
              <Eye className="w-6 h-6 text-purple-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">ARGUS</h1>
              <p className="text-gray-400 text-sm">0DTE Gamma Intelligence</p>
            </div>

            {/* Symbol Selector */}
            <div className="relative">
              <button
                onClick={() => setShowSymbolDropdown(!showSymbolDropdown)}
                className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 rounded-lg text-white font-bold transition-all"
              >
                <Search className="w-4 h-4" />
                {selectedSymbol}
                <ChevronDown className={`w-4 h-4 transition-transform ${showSymbolDropdown ? 'rotate-180' : ''}`} />
              </button>
              {showSymbolDropdown && (
                <div className="absolute top-full left-0 mt-2 w-64 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50 overflow-hidden">
                  <div className="p-2 border-b border-gray-700">
                    <input
                      type="text"
                      value={symbolSearch}
                      onChange={(e) => setSymbolSearch(e.target.value.toUpperCase())}
                      placeholder="Search symbol..."
                      className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:border-purple-500"
                      autoFocus
                    />
                  </div>
                  <div className="max-h-60 overflow-y-auto">
                    {AVAILABLE_SYMBOLS
                      .filter(s => s.symbol.includes(symbolSearch) || s.name.toLowerCase().includes(symbolSearch.toLowerCase()))
                      .map(s => (
                        <button
                          key={s.symbol}
                          onClick={() => {
                            if (s.supported) {
                              setSelectedSymbol(s.symbol)
                              setShowSymbolDropdown(false)
                              setSymbolSearch('')
                            }
                          }}
                          disabled={!s.supported}
                          className={`w-full px-4 py-3 flex items-center justify-between transition-colors ${
                            !s.supported ? 'opacity-50 cursor-not-allowed' :
                            selectedSymbol === s.symbol ? 'bg-purple-500/20' : 'hover:bg-gray-700'
                          }`}
                        >
                          <div className="text-left">
                            <div className={`font-bold ${s.supported ? 'text-white' : 'text-gray-500'}`}>{s.symbol}</div>
                            <div className="text-xs text-gray-400">
                              {s.name}
                              {!s.supported && <span className="ml-2 text-yellow-500">(Coming Soon)</span>}
                            </div>
                          </div>
                          {selectedSymbol === s.symbol && s.supported && (
                            <CheckCircle2 className="w-5 h-5 text-purple-400" />
                          )}
                        </button>
                      ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Expiration Tabs */}
            <div className="flex bg-gray-800/50 rounded-lg p-1">
              {expirations.map((exp) => (
                <button
                  key={exp.day}
                  onClick={() => handleDayChange(exp.day)}
                  disabled={exp.is_past}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                    activeDay === exp.day
                      ? 'bg-purple-500 text-white'
                      : exp.is_past
                      ? 'text-gray-600 cursor-not-allowed'
                      : 'text-gray-400 hover:text-white hover:bg-gray-700'
                  }`}
                >
                  {exp.day}
                  {exp.is_today && <span className="ml-1 text-[10px] opacity-70">•</span>}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2">
              {/* Live/Replay Toggle */}
              <button
                onClick={toggleReplayMode}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm ${
                  replayMode ? 'bg-orange-500/20 text-orange-400' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
                }`}
                title={replayMode ? 'Exit replay mode' : 'View historical data'}
              >
                <History className="w-4 h-4" />
                {replayMode ? 'Replay' : 'History'}
              </button>

              {/* Replay Controls - Show when in replay mode */}
              {replayMode && (
                <>
                  <select
                    value={selectedReplayDate}
                    onChange={(e) => {
                      setSelectedReplayDate(e.target.value)
                      setSelectedReplayTime('')
                      fetchReplayData(e.target.value)
                    }}
                    className="bg-gray-700 text-white text-sm rounded-lg px-3 py-1.5 border border-gray-600"
                  >
                    {replayDates.map(date => (
                      <option key={date} value={date}>{date}</option>
                    ))}
                  </select>
                  {replayTimes.length > 0 && (
                    <select
                      value={selectedReplayTime}
                      onChange={(e) => {
                        setSelectedReplayTime(e.target.value)
                        fetchReplayData(selectedReplayDate, e.target.value)
                      }}
                      className="bg-gray-700 text-white text-sm rounded-lg px-3 py-1.5 border border-gray-600"
                    >
                      <option value="">Select time...</option>
                      {replayTimes.map(time => (
                        <option key={time} value={time}>{time}</option>
                      ))}
                    </select>
                  )}
                </>
              )}

              {/* Live Controls - Show when not in replay mode */}
              {!replayMode && (
                <>
                  <button
                    onClick={() => setAutoRefresh(!autoRefresh)}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm ${
                      isMarketClosed && !isMockData
                        ? isHoliday
                          ? 'bg-purple-500/20 text-purple-400 cursor-not-allowed'
                          : 'bg-gray-700/50 text-gray-500 cursor-not-allowed'
                        : isMockData && autoRefresh
                        ? 'bg-orange-500/20 text-orange-400'
                        : autoRefresh
                        ? 'bg-emerald-500/20 text-emerald-400'
                        : 'bg-gray-700 text-gray-400'
                    }`}
                    title={
                      isMarketClosed && !isMockData
                        ? isHoliday ? 'Market holiday' : 'Market is closed'
                        : isMockData
                        ? autoRefresh ? 'Simulating - click to pause' : 'Click to simulate'
                        : autoRefresh ? 'Pause auto-refresh' : 'Enable auto-refresh'
                    }
                  >
                    <RefreshCw className={`w-4 h-4 ${autoRefresh && (!isMarketClosed || isMockData) ? 'animate-spin' : ''}`} />
                    {isMarketClosed && !isMockData
                      ? isHoliday ? 'Holiday' : 'Closed'
                      : isMockData
                      ? autoRefresh ? 'Simulating' : 'Paused'
                      : autoRefresh ? 'Live' : 'Paused'
                    }
                  </button>
                  <button
                    onClick={() => fetchGammaData(activeDay)}
                    className="p-2 bg-gray-700 hover:bg-gray-600 rounded-lg"
                    title="Refresh data"
                  >
                    <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                  </button>
                </>
              )}

              <button
                onClick={exportToExcel}
                disabled={!gammaData}
                className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg text-sm text-white"
                title="Export to CSV"
              >
                <FileSpreadsheet className="w-4 h-4" />
                Export
              </button>
            </div>
          </div>
        </div>

        {/* Replay Mode Banner */}
        {replayMode && (
          <div className="bg-orange-500/20 border border-orange-500/50 rounded-xl p-3 mb-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <History className="w-5 h-5 text-orange-400" />
              <div>
                <span className="text-orange-400 font-medium">Historical Replay Mode</span>
                <span className="text-gray-400 ml-2">
                  Viewing: {selectedReplayDate} {selectedReplayTime && `@ ${selectedReplayTime}`}
                </span>
              </div>
            </div>
            <button
              onClick={toggleReplayMode}
              className="px-3 py-1 bg-orange-500 hover:bg-orange-400 text-white text-sm rounded-lg flex items-center gap-2"
            >
              <Play className="w-4 h-4" />
              Return to Live
            </button>
          </div>
        )}

        {/* Market Closed/Holiday Banner */}
        {isMarketClosed && !replayMode && (
          <div className={`rounded-xl p-3 mb-4 flex items-center justify-between ${
            gammaData?.is_mock
              ? 'bg-orange-500/10 border border-orange-500/30'
              : isHoliday
              ? 'bg-purple-500/10 border border-purple-500/30'
              : 'bg-gray-700/50 border border-gray-600/50'
          }`}>
            <div className="flex items-center gap-3">
              {isHoliday ? (
                <CalendarOff className={`w-5 h-5 ${gammaData?.is_mock ? 'text-orange-400' : 'text-purple-400'}`} />
              ) : (
                <Clock className={`w-5 h-5 ${gammaData?.is_mock ? 'text-orange-400' : 'text-gray-400'}`} />
              )}
              <div>
                <span className={`font-medium ${
                  gammaData?.is_mock ? 'text-orange-300' : isHoliday ? 'text-purple-300' : 'text-gray-300'
                }`}>
                  {isHoliday ? 'Market Holiday' : 'Market Closed'}
                </span>
                <span className={`ml-2 ${
                  gammaData?.is_mock ? 'text-orange-400/70' : isHoliday ? 'text-purple-400/70' : 'text-gray-500'
                }`}>
                  {gammaData?.is_mock
                    ? 'Displaying simulated data for demonstration. Values update randomly.'
                    : isHoliday
                    ? 'Markets are closed for the holiday. Showing last trading day\'s data.'
                    : 'Showing last trading day\'s data. Auto-refresh paused until market opens.'
                  }
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Expected Move Change Banner - TOP PRIORITY */}
        {gammaData?.expected_move_change && (
          <div className={`rounded-xl p-5 mb-6 border-2 ${
            gammaData.expected_move_change.sentiment === 'BULLISH'
              ? 'bg-emerald-500/10 border-emerald-500/50'
              : gammaData.expected_move_change.sentiment === 'BEARISH'
              ? 'bg-rose-500/10 border-rose-500/50'
              : gammaData.expected_move_change.sentiment === 'VOLATILE'
              ? 'bg-orange-500/10 border-orange-500/50'
              : 'bg-gray-800/50 border-gray-600/50'
          }`}>
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <div className={`w-14 h-14 rounded-xl flex items-center justify-center ${
                  gammaData.expected_move_change.sentiment === 'BULLISH'
                    ? 'bg-emerald-500/20'
                    : gammaData.expected_move_change.sentiment === 'BEARISH'
                    ? 'bg-rose-500/20'
                    : gammaData.expected_move_change.sentiment === 'VOLATILE'
                    ? 'bg-orange-500/20'
                    : 'bg-gray-700/50'
                }`}>
                  {gammaData.expected_move_change.signal === 'UP' && <TrendingUp className="w-7 h-7 text-emerald-400" />}
                  {gammaData.expected_move_change.signal === 'DOWN' && <TrendingDown className="w-7 h-7 text-rose-400" />}
                  {gammaData.expected_move_change.signal === 'FLAT' && <Minus className="w-7 h-7 text-gray-400" />}
                  {gammaData.expected_move_change.signal === 'WIDEN' && <Zap className="w-7 h-7 text-orange-400" />}
                </div>
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs text-gray-400 uppercase tracking-wide">Expected Move vs Prior Day</span>
                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                      gammaData.expected_move_change.sentiment === 'BULLISH'
                        ? 'bg-emerald-500 text-white'
                        : gammaData.expected_move_change.sentiment === 'BEARISH'
                        ? 'bg-rose-500 text-white'
                        : gammaData.expected_move_change.sentiment === 'VOLATILE'
                        ? 'bg-orange-500 text-white'
                        : 'bg-gray-600 text-white'
                    }`}>
                      {gammaData.expected_move_change.signal}
                    </span>
                  </div>
                  <p className={`text-lg font-semibold ${
                    gammaData.expected_move_change.sentiment === 'BULLISH'
                      ? 'text-emerald-400'
                      : gammaData.expected_move_change.sentiment === 'BEARISH'
                      ? 'text-rose-400'
                      : gammaData.expected_move_change.sentiment === 'VOLATILE'
                      ? 'text-orange-400'
                      : 'text-gray-300'
                  }`}>
                    {gammaData.expected_move_change.interpretation}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-6 lg:gap-8">
                <div className="text-center">
                  <div className="text-xs text-gray-500 mb-1">Prior Day</div>
                  <div className="text-lg font-bold text-gray-400">
                    ±${gammaData.expected_move_change.prior_day?.toFixed(2) || '-'}
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-xs text-gray-500 mb-1">Current</div>
                  <div className="text-lg font-bold text-white">
                    ±${gammaData.expected_move_change.current.toFixed(2)}
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-xs text-gray-500 mb-1">Change</div>
                  <div className={`text-lg font-bold ${
                    gammaData.expected_move_change.pct_change_prior > 0
                      ? 'text-emerald-400'
                      : gammaData.expected_move_change.pct_change_prior < 0
                      ? 'text-rose-400'
                      : 'text-gray-400'
                  }`}>
                    {gammaData.expected_move_change.pct_change_prior > 0 ? '+' : ''}{gammaData.expected_move_change.pct_change_prior.toFixed(1)}%
                  </div>
                </div>
              </div>
            </div>

            {/* Historical Edge Stats - Based on Backtest */}
            <div className="mt-4 pt-4 border-t border-gray-700/50">
              <div className="flex items-center gap-2 mb-3">
                <BarChart3 className="w-4 h-4 text-gray-500" />
                <span className="text-xs text-gray-500 uppercase tracking-wide">Historical Edge (2022-2025 Backtest)</span>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {gammaData.expected_move_change.signal === 'DOWN' && (
                  <>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">Signal Accuracy</div>
                      <div className="text-lg font-bold text-rose-400">51.0%</div>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">Avg Move</div>
                      <div className="text-lg font-bold text-rose-400">-0.26%</div>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">Occurrence</div>
                      <div className="text-lg font-bold text-gray-300">5.2%</div>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">Edge</div>
                      <div className="text-sm font-medium text-rose-400">Bearish bias confirmed</div>
                    </div>
                  </>
                )}
                {gammaData.expected_move_change.signal === 'UP' && (
                  <>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">Signal Accuracy</div>
                      <div className="text-lg font-bold text-emerald-400">53.3%</div>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">Avg Move</div>
                      <div className="text-lg font-bold text-emerald-400">+0.02%</div>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">Occurrence</div>
                      <div className="text-lg font-bold text-gray-300">19.7%</div>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">Edge</div>
                      <div className="text-sm font-medium text-emerald-400">Slight bullish bias</div>
                    </div>
                  </>
                )}
                {gammaData.expected_move_change.signal === 'FLAT' && (
                  <>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">Signal Accuracy</div>
                      <div className="text-lg font-bold text-gray-400">51.7%</div>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">Avg Move</div>
                      <div className="text-lg font-bold text-gray-400">+0.04%</div>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">Occurrence</div>
                      <div className="text-lg font-bold text-gray-300">74.2%</div>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">Edge</div>
                      <div className="text-sm font-medium text-gray-400">Range-bound expected</div>
                    </div>
                  </>
                )}
                {gammaData.expected_move_change.signal === 'WIDEN' && (
                  <>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">Signal Accuracy</div>
                      <div className="text-lg font-bold text-orange-400">88.9%</div>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">Avg Abs Move</div>
                      <div className="text-lg font-bold text-orange-400">±1.53%</div>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">Occurrence</div>
                      <div className="text-lg font-bold text-gray-300">0.9%</div>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">Edge</div>
                      <div className="text-sm font-medium text-orange-400">BIG MOVE LIKELY!</div>
                    </div>
                  </>
                )}
              </div>
              <div className="mt-3 text-xs text-gray-600 flex items-center gap-1">
                <Info className="w-3 h-3" />
                <span>Based on 990 trading days. DOWN vs UP directional edge: +0.27%</span>
              </div>
            </div>
          </div>
        )}

        {/* Key Metrics Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3 mb-6">
          <div className="bg-gray-800/50 rounded-xl p-4">
            <div className="text-gray-500 text-xs mb-1">SPY Spot</div>
            <div className="text-xl font-bold text-white">${gammaData?.spot_price?.toFixed(2) ?? '-'}</div>
          </div>
          <div className="bg-gray-800/50 rounded-xl p-4">
            <div className="text-gray-500 text-xs mb-1">Expected Move</div>
            <div className="text-xl font-bold text-blue-400">±${gammaData?.expected_move?.toFixed(2) ?? '-'}</div>
          </div>
          <div className="bg-gray-800/50 rounded-xl p-4">
            <div className="text-gray-500 text-xs mb-1">VIX</div>
            <div className={`text-xl font-bold ${(gammaData?.vix || 0) > 20 ? 'text-orange-400' : 'text-emerald-400'}`}>
              {gammaData?.vix?.toFixed(1) ?? '-'}
            </div>
          </div>
          <div className="bg-gray-800/50 rounded-xl p-4">
            <div className="text-gray-500 text-xs mb-1">Net GEX</div>
            <div className={`text-xl font-bold ${
              (gammaData?.total_net_gamma || 0) > 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}>
              {(gammaData?.total_net_gamma || 0) > 0 ? '+' : ''}{formatGamma(gammaData?.total_net_gamma || 0)}
              <span className="text-xs ml-1">{(gammaData?.total_net_gamma || 0) > 0 ? '(+γ)' : '(-γ)'}</span>
            </div>
          </div>
          <div className="bg-gray-800/50 rounded-xl p-4">
            <div className="text-gray-500 text-xs mb-1">Gamma Regime</div>
            <div className={`text-xl font-bold ${
              gammaData?.gamma_regime === 'POSITIVE' ? 'text-emerald-400' :
              gammaData?.gamma_regime === 'NEGATIVE' ? 'text-rose-400' : 'text-gray-400'
            }`}>
              {gammaData?.gamma_regime}
            </div>
          </div>
          <div className="bg-gray-800/50 rounded-xl p-4">
            <div className="text-gray-500 text-xs mb-1">Top Magnet</div>
            <div className="text-xl font-bold text-yellow-400">
              ${gammaData?.magnets[0]?.strike || '-'}
            </div>
          </div>
          <div className="bg-gray-800/50 rounded-xl p-4">
            <div className="text-gray-500 text-xs mb-1">Pin Strike</div>
            <div className="text-xl font-bold text-purple-400">
              ${gammaData?.likely_pin || '-'}
            </div>
          </div>
          <div className={`rounded-xl p-4 ${
            timeToExpiry === 'EXPIRED'
              ? 'bg-gray-800/50'
              : timeToExpiry.includes('m') && !timeToExpiry.includes('h')
                ? 'bg-orange-900/30 border border-orange-500/30'
                : 'bg-gray-800/50'
          }`}>
            <div className="text-gray-500 text-xs mb-1 flex items-center gap-1">
              <Clock className="w-3 h-3" />
              Time to Expiry
            </div>
            <div className={`text-xl font-bold font-mono ${
              timeToExpiry === 'EXPIRED'
                ? 'text-gray-500'
                : timeToExpiry.includes('m') && !timeToExpiry.includes('h')
                  ? 'text-orange-400 animate-pulse'
                  : 'text-cyan-400'
            }`}>
              {timeToExpiry || '--:--'}
            </div>
          </div>
        </div>

        {/* Trade Ideas Section */}
        <div className="mb-6">
          {/* Trade Ideas Generator */}
          <div className="bg-gradient-to-r from-emerald-900/30 to-blue-900/30 border border-emerald-500/30 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-white flex items-center gap-2">
                <Lightbulb className="w-5 h-5 text-yellow-400" />
                Trade Ideas
                <span className="text-xs bg-yellow-500/20 text-yellow-400 px-2 py-0.5 rounded">AI</span>
              </h3>
              <button
                onClick={() => setShowTradeIdeas(!showTradeIdeas)}
                className="text-xs text-gray-500 hover:text-white"
              >
                {showTradeIdeas ? 'Hide' : 'Show'}
              </button>
            </div>
            {showTradeIdeas && tradeIdeas.length > 0 ? (
              <div className="space-y-3">
                {tradeIdeas.slice(0, 3).map((idea) => (
                  <div
                    key={idea.id}
                    className={`p-3 rounded-lg border ${
                      idea.direction === 'BULLISH'
                        ? 'bg-emerald-500/10 border-emerald-500/30'
                        : idea.direction === 'BEARISH'
                        ? 'bg-rose-500/10 border-rose-500/30'
                        : 'bg-gray-700/30 border-gray-600/30'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className={`font-bold ${
                          idea.direction === 'BULLISH' ? 'text-emerald-400' :
                          idea.direction === 'BEARISH' ? 'text-rose-400' : 'text-gray-300'
                        }`}>
                          {idea.setup_type}
                        </span>
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          idea.direction === 'BULLISH' ? 'bg-emerald-500 text-white' :
                          idea.direction === 'BEARISH' ? 'bg-rose-500 text-white' : 'bg-gray-600 text-white'
                        }`}>
                          {idea.direction}
                        </span>
                      </div>
                      <span className="text-xs text-gray-500">{idea.confidence.toFixed(0)}% conf</span>
                    </div>
                    <div className="grid grid-cols-4 gap-2 text-xs mb-2">
                      <div>
                        <div className="text-gray-500">Entry</div>
                        <div className="font-mono text-white">${idea.entry.toFixed(2)}</div>
                      </div>
                      <div>
                        <div className="text-gray-500">Target</div>
                        <div className="font-mono text-emerald-400">${idea.target.toFixed(2)}</div>
                      </div>
                      <div>
                        <div className="text-gray-500">Stop</div>
                        <div className="font-mono text-rose-400">${idea.stop.toFixed(2)}</div>
                      </div>
                      <div>
                        <div className="text-gray-500">R:R</div>
                        <div className="font-mono text-cyan-400">{idea.risk_reward.toFixed(1)}:1</div>
                      </div>
                    </div>
                    <p className="text-xs text-gray-400">{idea.rationale}</p>
                  </div>
                ))}
              </div>
            ) : showTradeIdeas ? (
              <div className="text-center py-6 text-gray-500">
                <Lightbulb className="w-8 h-8 mx-auto mb-2 opacity-30" />
                <p className="text-sm">Analyzing gamma structure...</p>
              </div>
            ) : null}
          </div>
        </div>

        {/* Pattern Similarity Section - Enhanced with price details */}
        <div className="mb-6">
          <div className="bg-gray-800/50 rounded-xl p-5">
            <h3 className="font-bold text-white flex items-center gap-2 mb-4">
              <Repeat className="w-5 h-5 text-indigo-400" />
              Pattern Similarity
              <span className="text-xs text-gray-500 font-normal">vs Historical Days (90d)</span>
            </h3>
            {patternMatches.length > 0 ? (
              <div className="space-y-4">
                {patternMatches.slice(0, 5).map((match, idx) => (
                  <div key={match.date} className="p-4 bg-gray-900/50 rounded-lg border border-gray-700/50">
                    {/* Header row */}
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                          idx === 0 ? 'bg-indigo-500/30 text-indigo-300' :
                          idx === 1 ? 'bg-purple-500/30 text-purple-300' : 'bg-gray-700 text-gray-400'
                        }`}>#{idx + 1}</span>
                        <div>
                          <div className="font-mono text-white text-sm font-bold">{match.date}</div>
                          <div className="text-xs text-gray-500 flex items-center gap-2">
                            <span className={`${match.gamma_regime_then === 'POSITIVE' ? 'text-emerald-400' : match.gamma_regime_then === 'NEGATIVE' ? 'text-rose-400' : 'text-gray-400'}`}>
                              {match.gamma_regime_then} gamma
                            </span>
                            {match.mm_state && <span className="text-gray-600">• MMs {match.mm_state}</span>}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="text-center">
                          <div className="text-[10px] text-gray-500 uppercase">Match</div>
                          <div className="font-bold text-indigo-400">{match.similarity_score?.toFixed(0) || 0}%</div>
                        </div>
                        <div className="text-center">
                          <div className="text-[10px] text-gray-500 uppercase">Result</div>
                          <div className={`font-bold flex items-center gap-1 ${
                            match.outcome_direction === 'UP' ? 'text-emerald-400' :
                            match.outcome_direction === 'DOWN' ? 'text-rose-400' : 'text-gray-400'
                          }`}>
                            {match.outcome_direction === 'UP' ? <ArrowUpRight className="w-4 h-4" /> :
                             match.outcome_direction === 'DOWN' ? <ArrowDownRight className="w-4 h-4" /> : null}
                            {match.outcome_pct > 0 ? '+' : ''}{(match.outcome_pct || 0).toFixed(2)}%
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Price details row */}
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-3 py-2 border-t border-b border-gray-700/30">
                      <div>
                        <div className="text-[10px] text-gray-500 uppercase">Open</div>
                        <div className="text-sm font-mono text-white">${match.open_price?.toFixed(2) || '-'}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-gray-500 uppercase">Close</div>
                        <div className={`text-sm font-mono ${
                          (match.price_change || 0) > 0 ? 'text-emerald-400' :
                          (match.price_change || 0) < 0 ? 'text-rose-400' : 'text-white'
                        }`}>
                          ${match.close_price?.toFixed(2) || '-'}
                          <span className="text-xs ml-1">
                            ({(match.price_change || 0) > 0 ? '+' : ''}{(match.price_change || 0).toFixed(2)})
                          </span>
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] text-gray-500 uppercase">High</div>
                        <div className="text-sm font-mono text-emerald-400/80">${match.day_high?.toFixed(2) || '-'}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-gray-500 uppercase">Low</div>
                        <div className="text-sm font-mono text-rose-400/80">${match.day_low?.toFixed(2) || '-'}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-gray-500 uppercase">Range</div>
                        <div className="text-sm font-mono text-yellow-400">${match.day_range?.toFixed(2) || '-'}</div>
                      </div>
                    </div>

                    {/* Key levels row */}
                    {(match.flip_point || match.call_wall || match.put_wall) && (
                      <div className="flex flex-wrap gap-3 mb-3 text-xs">
                        {match.flip_point && (
                          <span className="px-2 py-1 bg-purple-500/20 text-purple-300 rounded">
                            Flip: ${match.flip_point.toFixed(0)}
                          </span>
                        )}
                        {match.call_wall && (
                          <span className="px-2 py-1 bg-emerald-500/20 text-emerald-300 rounded">
                            Call Wall: ${match.call_wall.toFixed(0)}
                          </span>
                        )}
                        {match.put_wall && (
                          <span className="px-2 py-1 bg-rose-500/20 text-rose-300 rounded">
                            Put Wall: ${match.put_wall.toFixed(0)}
                          </span>
                        )}
                      </div>
                    )}

                    {/* Summary */}
                    {match.summary && (
                      <div className="text-sm text-gray-400 leading-relaxed">
                        <span className="text-indigo-400 font-medium">Summary:</span> {match.summary}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-6 text-gray-500">
                <Repeat className="w-8 h-8 mx-auto mb-2 opacity-30" />
                <p className="text-sm">No similar patterns found in historical data</p>
                <p className="text-xs text-gray-600 mt-1">Comparing current gamma structure against 90 days of history</p>
              </div>
            )}
          </div>
        </div>

        {/* AI Analysis Banner */}
        <div className="bg-gradient-to-r from-purple-900/40 to-blue-900/40 border border-purple-500/30 rounded-xl p-5 mb-6">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center flex-shrink-0">
              <Brain className="w-5 h-5 text-purple-400" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <h3 className="font-bold text-white">ARGUS AI Analysis</h3>
                <span className="text-xs bg-purple-500/20 text-purple-400 px-2 py-0.5 rounded">Live</span>
              </div>
              <p className="text-gray-300 leading-relaxed">{generateInsight()}</p>
            </div>
            <div className="flex flex-col items-end gap-1">
              {dataTimestamp && (
                <div className="text-xs text-gray-500 flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {dataTimestamp.toLocaleTimeString('en-US', { timeZone: 'America/Chicago', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true })} CT
                </div>
              )}
              {autoRefresh && !isMarketClosed && (
                <div className="text-[10px] text-emerald-400 flex items-center gap-1">
                  <RefreshCw className="w-2.5 h-2.5 animate-spin" />
                  Updates every 15s
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Main Grid */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">

          {/* Left Column - Chart & Strikes */}
          <div className="xl:col-span-2 space-y-6">

            {/* Chart Section */}
            <div className="bg-gray-800/50 rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <h3 className="font-bold text-white flex items-center gap-2">
                    <BarChart3 className="w-5 h-5 text-blue-400" />
                    Net Gamma by Strike
                    {gammaData?.is_mock ? (
                      <span className="ml-2 px-2 py-0.5 bg-orange-500/20 text-orange-400 text-[10px] font-medium rounded border border-orange-500/30">
                        SIMULATED
                      </span>
                    ) : gammaData?.market_status === 'closed' ? (
                      <span className="ml-2 px-2 py-0.5 bg-gray-500/20 text-gray-400 text-[10px] font-medium rounded border border-gray-500/30">
                        CLOSED
                      </span>
                    ) : gammaData?.market_status === 'after_hours' ? (
                      <span className="ml-2 px-2 py-0.5 bg-purple-500/20 text-purple-400 text-[10px] font-medium rounded border border-purple-500/30">
                        AFTER HOURS
                      </span>
                    ) : gammaData?.market_status === 'pre_market' ? (
                      <span className="ml-2 px-2 py-0.5 bg-blue-500/20 text-blue-400 text-[10px] font-medium rounded border border-blue-500/30">
                        PRE-MARKET
                      </span>
                    ) : gammaData?.is_stale ? (
                      <span className="ml-2 px-2 py-0.5 bg-yellow-500/20 text-yellow-400 text-[10px] font-medium rounded border border-yellow-500/30">
                        STALE
                      </span>
                    ) : gammaData?.is_cached ? (
                      <span className="ml-2 px-2 py-0.5 bg-blue-500/20 text-blue-400 text-[10px] font-medium rounded border border-blue-500/30">
                        LIVE ({gammaData.cache_age_seconds}s ago)
                      </span>
                    ) : (
                      <span className="ml-2 px-2 py-0.5 bg-emerald-500/20 text-emerald-400 text-[10px] font-medium rounded border border-emerald-500/30 animate-pulse">
                        LIVE
                      </span>
                    )}
                  </h3>
                  {dataTimestamp && (
                    <span className="text-[10px] text-gray-500">
                      Data: {dataTimestamp.toLocaleTimeString('en-US', { timeZone: 'America/Chicago', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true })} CT
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3 text-xs flex-wrap">
                  <div className="flex items-center gap-1.5">
                    <div className="w-3 h-3 rounded bg-purple-500"></div>
                    <span className="text-gray-400">Pin</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-3 h-3 rounded bg-yellow-400"></div>
                    <span className="text-gray-400">Magnet</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-3 h-3 rounded bg-emerald-500"></div>
                    <span className="text-gray-400">+γ</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-3 h-3 rounded bg-rose-500"></div>
                    <span className="text-gray-400">-γ</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-4 h-0 border-t-2 border-blue-400"></div>
                    <span className="text-gray-400">EM</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-4 h-0 border-t border-dashed border-gray-500"></div>
                    <span className="text-gray-400">EM'</span>
                  </div>
                  {tomorrowGammaData && (
                    <div className="flex items-center gap-1.5">
                      <div className="w-3 h-3 rounded bg-cyan-500/40 border border-cyan-500/60"></div>
                      <span className="text-gray-400">Tomorrow</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Chart */}
              <div className="relative h-52 flex items-end justify-center gap-1 border-b border-gray-700 mb-2">
                {/* Tomorrow's bars (faded, behind today's) - aligned with today's strikes */}
                {tomorrowGammaData && gammaData?.strikes && (
                  <div className="absolute inset-0 flex items-end justify-center gap-1 pointer-events-none">
                    {gammaData.strikes.map((todayStrike) => {
                      // Find matching strike in tomorrow's data
                      const tomorrowStrike = tomorrowGammaData.strikes.find(s => s.strike === todayStrike.strike)
                      return (
                        <div
                          key={`tomorrow-${todayStrike.strike}`}
                          className="flex flex-col items-center"
                          style={{ flex: '1 1 0', maxWidth: '60px' }}
                        >
                          <div className="text-[10px] text-transparent mb-1">&nbsp;</div>
                          {tomorrowStrike ? (
                            <div
                              className="w-6 rounded-t bg-cyan-500/30 border border-cyan-500/40 transition-all"
                              style={{ height: `${getBarHeightPx(tomorrowStrike.net_gamma, maxGamma)}px` }}
                            />
                          ) : (
                            <div className="w-6" /> // Empty placeholder for alignment
                          )}
                        </div>
                      )
                    })}
                    {/* Tomorrow badge */}
                    <div className="absolute top-2 right-2 px-2 py-1 bg-cyan-500/20 border border-cyan-500/40 rounded text-[10px] text-cyan-400 font-medium">
                      <Calendar className="w-3 h-3 inline mr-1" />
                      Tomorrow
                    </div>
                  </div>
                )}

                {/* Today's bars (solid, on top) */}
                {gammaData?.strikes.map((strike) => (
                  <div
                    key={strike.strike}
                    className="flex flex-col items-center group cursor-pointer z-10"
                    style={{ flex: '1 1 0', maxWidth: '60px' }}
                    onClick={() => setSelectedStrike(strike)}
                  >
                    <div className="text-[10px] text-gray-500 mb-1">
                      {strike.probability > 0 ? `${strike.probability.toFixed(0)}%` : ''}
                    </div>
                    <div
                      className={`w-6 rounded-t ${getBarColor(strike)} transition-all hover:opacity-80 relative`}
                      style={{ height: `${getBarHeightPx(strike.net_gamma, maxGamma)}px` }}
                    >
                      {strike.is_pin && (
                        <Target className="absolute -top-5 left-1/2 -translate-x-1/2 w-4 h-4 text-purple-300" />
                      )}
                      {strike.is_magnet && strike.magnet_rank && !strike.is_pin && (
                        <span className="absolute -top-7 left-1/2 -translate-x-1/2 text-[9px] font-bold text-yellow-400 whitespace-nowrap">
                          #{strike.magnet_rank}
                        </span>
                      )}
                    </div>
                  </div>
                ))}

                {/* Spot Line */}
                {gammaData && gammaData.strikes.length > 1 && (
                  <div
                    className="absolute bottom-0 top-0 border-l-2 border-dashed border-emerald-400/60 z-10"
                    style={{
                      left: `${((gammaData.spot_price - gammaData.strikes[0].strike) /
                        (gammaData.strikes[gammaData.strikes.length - 1].strike - gammaData.strikes[0].strike)) * 100}%`
                    }}
                  >
                    <div className="absolute -top-1 left-1 text-[9px] text-emerald-400 font-bold bg-gray-900 px-1 rounded">
                      SPOT
                    </div>
                  </div>
                )}

                {/* Prior Day Expected Move Range - Dotted Lines */}
                {gammaData && gammaData.strikes.length > 1 && gammaData.expected_move_change?.prior_day && (() => {
                  const minStrike = gammaData.strikes[0].strike
                  const maxStrike = gammaData.strikes[gammaData.strikes.length - 1].strike
                  const range = maxStrike - minStrike
                  const priorEM = gammaData.expected_move_change.prior_day
                  const lowerPrior = ((gammaData.spot_price - priorEM - minStrike) / range) * 100
                  const upperPrior = ((gammaData.spot_price + priorEM - minStrike) / range) * 100
                  return (
                    <>
                      {lowerPrior >= 0 && lowerPrior <= 100 && (
                        <div
                          className="absolute bottom-0 top-0 border-l border-dashed border-gray-500/50 z-5"
                          style={{ left: `${lowerPrior}%` }}
                        >
                          <div className="absolute bottom-1 -left-3 text-[8px] text-gray-500">-EM'</div>
                        </div>
                      )}
                      {upperPrior >= 0 && upperPrior <= 100 && (
                        <div
                          className="absolute bottom-0 top-0 border-l border-dashed border-gray-500/50 z-5"
                          style={{ left: `${upperPrior}%` }}
                        >
                          <div className="absolute bottom-1 -left-3 text-[8px] text-gray-500">+EM'</div>
                        </div>
                      )}
                    </>
                  )
                })()}

                {/* Current Expected Move Range - Solid Lines */}
                {gammaData && gammaData.strikes.length > 1 && gammaData.expected_move && (() => {
                  const minStrike = gammaData.strikes[0].strike
                  const maxStrike = gammaData.strikes[gammaData.strikes.length - 1].strike
                  const range = maxStrike - minStrike
                  const currentEM = gammaData.expected_move
                  const lowerCurrent = ((gammaData.spot_price - currentEM - minStrike) / range) * 100
                  const upperCurrent = ((gammaData.spot_price + currentEM - minStrike) / range) * 100
                  return (
                    <>
                      {lowerCurrent >= 0 && lowerCurrent <= 100 && (
                        <div
                          className="absolute bottom-0 top-0 border-l-2 border-blue-400/70 z-5"
                          style={{ left: `${lowerCurrent}%` }}
                        >
                          <div className="absolute bottom-1 -left-3 text-[8px] text-blue-400 font-medium">-EM</div>
                        </div>
                      )}
                      {upperCurrent >= 0 && upperCurrent <= 100 && (
                        <div
                          className="absolute bottom-0 top-0 border-l-2 border-blue-400/70 z-5"
                          style={{ left: `${upperCurrent}%` }}
                        >
                          <div className="absolute bottom-1 -left-3 text-[8px] text-blue-400 font-medium">+EM</div>
                        </div>
                      )}
                    </>
                  )
                })()}
              </div>

              {/* Strike Labels */}
              <div className="flex justify-center gap-1">
                {gammaData?.strikes.map((strike) => (
                  <div
                    key={`label-${strike.strike}`}
                    className={`text-[11px] font-mono text-center ${
                      strike.is_pin ? 'text-purple-400 font-bold' :
                      strike.is_magnet ? 'text-yellow-400 font-bold' : 'text-gray-500'
                    }`}
                    style={{ flex: '1 1 0', maxWidth: '60px' }}
                  >
                    {strike.strike}
                  </div>
                ))}
              </div>
            </div>

            {/* EOD Strike Summary Table */}
            {computedEodStats.length > 0 && (
              <div className="bg-gray-800/50 rounded-xl p-5">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-bold text-white flex items-center gap-2">
                    <Sun className="w-5 h-5 text-orange-400" />
                    Daily Strike Activity
                    <span className="text-[10px] text-gray-500 font-normal ml-2">Top 5 most active</span>
                  </h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-700">
                        <th className="text-left py-2 px-2 text-gray-500 font-medium">Strike</th>
                        <th className="text-center py-2 px-2 text-gray-500 font-medium">Spikes</th>
                        <th className="text-center py-2 px-2 text-gray-500 font-medium">Flips</th>
                        <th className="text-right py-2 px-2 text-gray-500 font-medium">Peak ROC</th>
                        <th className="text-right py-2 px-2 text-gray-500 font-medium">Magnet Time</th>
                        <th className="text-center py-2 px-2 text-gray-500 font-medium">Trend</th>
                      </tr>
                    </thead>
                    <tbody>
                      {computedEodStats.map((stat, idx) => (
                        <tr
                          key={stat.strike}
                          className="border-b border-gray-700/50 hover:bg-gray-700/30"
                        >
                          <td className="py-2 px-2">
                            <span className="font-mono font-bold text-white">
                              ${stat.strike}
                              {idx === 0 && <span className="ml-1 text-orange-400">🔥</span>}
                            </span>
                          </td>
                          <td className="py-2 px-2 text-center">
                            <span className={`font-mono ${stat.spikeCount > 0 ? 'text-orange-400' : 'text-gray-600'}`}>
                              {stat.spikeCount}
                            </span>
                          </td>
                          <td className="py-2 px-2 text-center">
                            <span className={`font-mono ${stat.flipCount > 0 ? 'text-purple-400' : 'text-gray-600'}`}>
                              {stat.flipCount}
                            </span>
                          </td>
                          <td className={`py-2 px-2 text-right font-mono ${
                            stat.peakRoc > 10 ? 'text-rose-400' : stat.peakRoc > 5 ? 'text-yellow-400' : 'text-gray-400'
                          }`}>
                            {stat.peakRoc.toFixed(1)}%
                          </td>
                          <td className="py-2 px-2 text-right text-gray-400">
                            {stat.timeAsMagnet > 0 ? `${stat.timeAsMagnet}m` : '-'}
                          </td>
                          <td className="py-2 px-2 text-center">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${
                              stat.trend === 'BUILDING' ? 'bg-emerald-500/20 text-emerald-400' :
                              stat.trend === 'COLLAPSING' ? 'bg-rose-500/20 text-rose-400' :
                              stat.trend === 'VOLATILE' ? 'bg-orange-500/20 text-orange-400' :
                              'bg-gray-500/20 text-gray-400'
                            }`}>
                              {stat.trend}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Strike Details Table */}
            <div className="bg-gray-800/50 rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-bold text-white flex items-center gap-2">
                  <Activity className="w-5 h-5 text-blue-400" />
                  Strike Analysis
                </h3>
                {lastUpdated && (
                  <div className="flex items-center gap-2 text-xs text-gray-500">
                    <Clock className="w-3 h-3" />
                    <span>Last updated: {lastUpdated.toLocaleTimeString('en-US', { timeZone: 'America/Chicago', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true })} CT</span>
                  </div>
                )}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-700">
                      <th className="text-left py-2 px-2 text-gray-500 font-medium">Strike</th>
                      <th className="text-right py-2 px-2 text-gray-500 font-medium">Dist</th>
                      <th className="text-right py-2 px-2 text-gray-500 font-medium">Net Gamma</th>
                      <th className="text-right py-2 px-2 text-gray-500 font-medium">Prob %</th>
                      <th className="text-right py-2 px-2 text-gray-500 font-medium">1m ROC</th>
                      <th className="text-right py-2 px-2 text-gray-500 font-medium">5m ROC</th>
                      <th className="text-right py-2 px-2 text-gray-500 font-medium">30m ROC</th>
                      <th className="text-right py-2 px-2 text-gray-500 font-medium">1hr ROC</th>
                      <th className="text-right py-2 px-2 text-gray-500 font-medium">
                        <select
                          value={selectedRocTimeframe}
                          onChange={(e) => setSelectedRocTimeframe(e.target.value as RocTimeframe)}
                          className="bg-gray-800 border border-gray-600 rounded px-1 py-0.5 text-xs text-gray-300 cursor-pointer hover:border-purple-500 focus:outline-none focus:border-purple-500"
                        >
                          {rocTimeframeOptions.map(opt => (
                            <option key={opt.value} value={opt.value}>{opt.shortLabel} ROC</option>
                          ))}
                        </select>
                      </th>
                      <th className="text-center py-2 px-2 text-gray-500 font-medium">30m Trend</th>
                      <th className="text-center py-2 px-2 text-gray-500 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {gammaData?.strikes.map((strike) => (
                      <tr
                        key={strike.strike}
                        className={`border-b border-gray-700/50 hover:bg-gray-700/30 cursor-pointer ${
                          selectedStrike?.strike === strike.strike ? 'bg-purple-500/10' : ''
                        }`}
                        onClick={() => setSelectedStrike(strike)}
                      >
                        <td className="py-2 px-2">
                          <span className={`font-mono font-bold ${
                            strike.is_pin ? 'text-purple-400' :
                            strike.is_magnet ? 'text-yellow-400' : 'text-white'
                          }`}>
                            ${strike.strike}
                          </span>
                        </td>
                        <td className={`py-2 px-2 text-right font-mono text-xs ${
                          (() => {
                            const dist = gammaData?.spot_price ? ((strike.strike - gammaData.spot_price) / gammaData.spot_price * 100) : 0
                            return dist > 0 ? 'text-emerald-400' : dist < 0 ? 'text-rose-400' : 'text-gray-500'
                          })()
                        }`}>
                          {gammaData?.spot_price ? (
                            (() => {
                              const dist = ((strike.strike - gammaData.spot_price) / gammaData.spot_price * 100)
                              return `${dist > 0 ? '+' : ''}${dist.toFixed(2)}%`
                            })()
                          ) : '-'}
                        </td>
                        <td className={`py-2 px-2 text-right font-mono ${
                          strike.net_gamma > 0 ? 'text-emerald-400' : 'text-rose-400'
                        }`}>
                          {formatGamma(strike.net_gamma)}
                        </td>
                        <td className="py-2 px-2 text-right text-gray-300">
                          {strike.probability.toFixed(1)}%
                        </td>
                        <td className={`py-2 px-2 text-right font-mono ${
                          strike.roc_1min > 0 ? 'text-emerald-400' : strike.roc_1min < 0 ? 'text-rose-400' : 'text-gray-500'
                        }`}>
                          {strike.roc_1min > 0 ? '+' : ''}{strike.roc_1min.toFixed(1)}%
                        </td>
                        <td className={`py-2 px-2 text-right font-mono ${
                          strike.roc_5min > 0 ? 'text-emerald-400' : strike.roc_5min < 0 ? 'text-rose-400' : 'text-gray-500'
                        }`}>
                          {strike.roc_5min > 0 ? '+' : ''}{strike.roc_5min.toFixed(1)}%
                        </td>
                        <td className={`py-2 px-2 text-right font-mono ${
                          (strike.roc_30min ?? 0) > 0 ? 'text-emerald-400' : (strike.roc_30min ?? 0) < 0 ? 'text-rose-400' : 'text-gray-500'
                        }`}>
                          {(strike.roc_30min ?? 0) > 0 ? '+' : ''}{(strike.roc_30min ?? 0).toFixed(1)}%
                        </td>
                        <td className={`py-2 px-2 text-right font-mono ${
                          (strike.roc_1hr ?? 0) > 0 ? 'text-emerald-400' : (strike.roc_1hr ?? 0) < 0 ? 'text-rose-400' : 'text-gray-500'
                        }`}>
                          {(strike.roc_1hr ?? 0) > 0 ? '+' : ''}{(strike.roc_1hr ?? 0).toFixed(1)}%
                        </td>
                        <td className={`py-2 px-2 text-right font-mono ${
                          (() => {
                            const roc = getLongRocValue(strike)
                            return roc > 0 ? 'text-emerald-400' : roc < 0 ? 'text-rose-400' : 'text-gray-500'
                          })()
                        }`}>
                          {(() => {
                            const roc = getLongRocValue(strike)
                            return `${roc > 0 ? '+' : ''}${roc.toFixed(1)}%`
                          })()}
                        </td>
                        <td className="py-2 px-2 text-center">
                          {(() => {
                            // API returns keys as "683.0", frontend may have "683" - try both
                            const trend = strikeTrends[String(strike.strike)] ||
                                          strikeTrends[String(strike.strike) + '.0'] ||
                                          strikeTrends[String(parseFloat(String(strike.strike)).toFixed(1))]
                            if (!trend || trend.dominant_status === 'NEUTRAL') {
                              return <span className="text-gray-600 text-[10px]">—</span>
                            }
                            const statusColors: Record<string, string> = {
                              'BUILDING': 'text-emerald-400 bg-emerald-500/20',
                              'COLLAPSING': 'text-rose-400 bg-rose-500/20',
                              'SPIKE': 'text-orange-400 bg-orange-500/20'
                            }
                            const arrows: Record<string, string> = {
                              'BUILDING': '↑',
                              'COLLAPSING': '↓',
                              'SPIKE': '⚡'
                            }
                            return (
                              <span className={`px-1.5 py-0.5 rounded text-[10px] ${statusColors[trend.dominant_status] || 'text-gray-400'}`}>
                                {arrows[trend.dominant_status]} {trend.dominant_duration_mins.toFixed(0)}m
                              </span>
                            )
                          })()}
                        </td>
                        <td className="py-2 px-2 text-center">
                          <div className="flex items-center justify-center gap-1 flex-wrap">
                            {strike.is_pin && (
                              <span className="px-1.5 py-0.5 bg-purple-500/20 text-purple-400 rounded text-[10px]">PIN</span>
                            )}
                            {strike.is_magnet && (
                              <span className="px-1.5 py-0.5 bg-yellow-500/20 text-yellow-400 rounded text-[10px]">MAG</span>
                            )}
                            {strike.is_danger && (
                              <span className="px-1.5 py-0.5 bg-orange-500/20 text-orange-400 rounded text-[10px]">{strike.danger_type}</span>
                            )}
                            {(() => {
                              // Check for gamma flip - compare as numbers
                              const flip = gammaFlips30m.find(f => Math.abs(f.strike - strike.strike) < 0.01)
                              if (!flip) return null
                              return (
                                <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                                  flip.direction === 'POS_TO_NEG'
                                    ? 'bg-rose-500/20 text-rose-400'
                                    : 'bg-emerald-500/20 text-emerald-400'
                                }`}>
                                  FLIP {flip.mins_ago.toFixed(0)}m
                                </span>
                              )
                            })()}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Selected Strike ROC Detail Panel */}
            {selectedStrike && (
              <div className="bg-gray-800/50 rounded-xl p-5 border border-purple-500/30">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-bold text-white flex items-center gap-2">
                    <Activity className="w-5 h-5 text-purple-400" />
                    ROC Analysis: ${selectedStrike.strike}
                    {selectedStrike.is_pin && <span className="text-xs bg-purple-500/20 text-purple-300 px-2 py-0.5 rounded">PIN</span>}
                    {selectedStrike.is_magnet && <span className="text-xs bg-yellow-500/20 text-yellow-300 px-2 py-0.5 rounded">MAGNET</span>}
                  </h3>
                  <button
                    onClick={() => setSelectedStrike(null)}
                    className="text-gray-500 hover:text-white text-sm"
                  >
                    ✕ Close
                  </button>
                </div>

                {/* ROC Grid - All Timeframes */}
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                  {[
                    { label: '1 Min', value: selectedStrike.roc_1min, key: '1min', alwaysInTable: true },
                    { label: '5 Min', value: selectedStrike.roc_5min, key: '5min', alwaysInTable: true },
                    { label: '30 Min', value: selectedStrike.roc_30min ?? 0, key: '30min', alwaysInTable: true },
                    { label: '1 Hour', value: selectedStrike.roc_1hr ?? 0, key: '1hr', alwaysInTable: true },
                    { label: '4 Hour', value: selectedStrike.roc_4hr ?? 0, key: '4hr', alwaysInTable: false },
                    { label: 'Today', value: selectedStrike.roc_trading_day ?? 0, key: 'day', alwaysInTable: false },
                  ].map(({ label, value, key, alwaysInTable }) => (
                    <div
                      key={key}
                      className={`bg-gray-900/50 rounded-lg p-3 text-center transition-all ${
                        alwaysInTable
                          ? 'border border-gray-600'  // 1m and 5m are always shown
                          : selectedRocTimeframe === key
                            ? 'ring-2 ring-purple-500 cursor-pointer'
                            : 'hover:bg-gray-800/50 cursor-pointer'
                      }`}
                      onClick={() => !alwaysInTable && setSelectedRocTimeframe(key as RocTimeframe)}
                    >
                      <div className="text-xs text-gray-500 mb-1">
                        {label}
                        {alwaysInTable && <span className="ml-1 text-[9px] text-gray-600">(in table)</span>}
                      </div>
                      <div className={`text-lg font-mono font-bold ${
                        value > 0 ? 'text-emerald-400' : value < 0 ? 'text-rose-400' : 'text-gray-500'
                      }`}>
                        {value > 0 ? '+' : ''}{value.toFixed(1)}%
                      </div>
                      {/* Visual indicator bar */}
                      <div className="mt-2 h-1 bg-gray-700 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${
                            value > 0 ? 'bg-emerald-500' : value < 0 ? 'bg-rose-500' : 'bg-gray-600'
                          }`}
                          style={{
                            width: `${Math.min(Math.abs(value) * 2, 100)}%`,
                            marginLeft: value < 0 ? 'auto' : 0
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>

                {/* Additional Strike Info */}
                <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div className="bg-gray-900/30 rounded px-3 py-2">
                    <span className="text-gray-500">Net Gamma:</span>
                    <span className={`ml-2 font-mono ${selectedStrike.net_gamma > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {selectedStrike.net_gamma > 1e6
                        ? `${(selectedStrike.net_gamma / 1e6).toFixed(1)}M`
                        : selectedStrike.net_gamma > 1e3
                          ? `${(selectedStrike.net_gamma / 1e3).toFixed(1)}K`
                          : selectedStrike.net_gamma.toFixed(0)}
                    </span>
                  </div>
                  <div className="bg-gray-900/30 rounded px-3 py-2">
                    <span className="text-gray-500">Probability:</span>
                    <span className="ml-2 font-mono text-blue-400">{selectedStrike.probability.toFixed(1)}%</span>
                  </div>
                  <div className="bg-gray-900/30 rounded px-3 py-2">
                    <span className="text-gray-500">Distance:</span>
                    <span className={`ml-2 font-mono ${
                      gammaData?.spot_price && selectedStrike.strike > gammaData.spot_price ? 'text-emerald-400' : 'text-rose-400'
                    }`}>
                      {gammaData?.spot_price
                        ? `${((selectedStrike.strike - gammaData.spot_price) / gammaData.spot_price * 100) > 0 ? '+' : ''}${((selectedStrike.strike - gammaData.spot_price) / gammaData.spot_price * 100).toFixed(2)}%`
                        : '-'}
                    </span>
                  </div>
                  <div className="bg-gray-900/30 rounded px-3 py-2">
                    <span className="text-gray-500">Status:</span>
                    <span className={`ml-2 ${
                      selectedStrike.is_danger
                        ? 'text-orange-400'
                        : selectedStrike.gamma_flipped
                          ? 'text-yellow-400'
                          : 'text-gray-400'
                    }`}>
                      {selectedStrike.is_danger
                        ? selectedStrike.danger_type
                        : selectedStrike.gamma_flipped
                          ? `Flipped ${selectedStrike.flip_direction}`
                          : 'Normal'}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Live Commentary / ARGUS Log */}
            <div className="bg-gray-800/50 rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-bold text-white flex items-center gap-2">
                  <Activity className="w-5 h-5 text-cyan-400" />
                  ARGUS Live Log
                </h3>
                {commentary.length > 0 && (
                  <span className="text-xs text-gray-500">
                    {commentary.length} entries • Updates every 5 min
                  </span>
                )}
              </div>
              <div className="space-y-3 max-h-80 overflow-y-auto">
                {commentary.length > 0 ? (
                  commentary.slice(0, 20).map((entry) => (
                    <div
                      key={entry.id}
                      className="p-4 bg-gray-900/50 rounded-lg border-l-2 border-cyan-500/50"
                    >
                      {/* Timestamp Header */}
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <Clock className="w-3 h-3 text-cyan-400" />
                          <span className="text-xs text-cyan-400 font-medium">
                            {new Date(entry.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        </div>
                        <span className="text-[10px] text-gray-600">
                          {new Date(entry.timestamp).toLocaleDateString()}
                        </span>
                      </div>

                      {/* Commentary Text */}
                      <div className="text-sm text-gray-200 leading-relaxed whitespace-pre-line mb-3">
                        {entry.text}
                      </div>

                      {/* Market Context Row */}
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                        <div className="bg-gray-800/50 rounded px-2 py-1.5">
                          <span className="text-gray-500">SPY</span>
                          <span className="text-white ml-1 font-mono">${entry.spot_price?.toFixed(2) || '-'}</span>
                        </div>
                        <div className="bg-gray-800/50 rounded px-2 py-1.5">
                          <span className="text-gray-500">VIX</span>
                          <span className={`ml-1 font-mono ${(entry.vix || 0) > 20 ? 'text-orange-400' : 'text-emerald-400'}`}>
                            {entry.vix?.toFixed(1) || '-'}
                          </span>
                        </div>
                        <div className="bg-gray-800/50 rounded px-2 py-1.5">
                          <span className="text-gray-500">Magnet</span>
                          <span className="text-yellow-400 ml-1 font-mono">${entry.top_magnet || '-'}</span>
                        </div>
                        <div className="bg-gray-800/50 rounded px-2 py-1.5">
                          <span className="text-gray-500">Pin</span>
                          <span className="text-purple-400 ml-1 font-mono">
                            ${entry.likely_pin || '-'}
                            <span className="text-gray-600 text-[10px] ml-1">
                              ({entry.pin_probability?.toFixed(0) || 0}%)
                            </span>
                          </span>
                        </div>
                      </div>

                      {/* Danger Zones */}
                      {entry.danger_zones && entry.danger_zones.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          <span className="text-[10px] text-orange-400">Danger:</span>
                          {entry.danger_zones.slice(0, 5).map((dz, i) => (
                            <span key={i} className="px-1.5 py-0.5 bg-orange-500/20 text-orange-400 rounded text-[10px]">
                              {typeof dz === 'string' ? dz : JSON.stringify(dz)}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="text-center py-8 text-gray-500">
                    <Activity className="w-8 h-8 mx-auto mb-2 opacity-30" />
                    <p className="text-sm">No log entries yet</p>
                    <p className="text-xs text-gray-600 mt-1">AI commentary generates every 5 minutes during market hours</p>
                    <button
                      onClick={async () => {
                        try {
                          console.log('[ARGUS] Manually triggering commentary generation...')
                          await apiClient.generateArgusCommentary()
                          await fetchCommentary()
                        } catch (err) {
                          console.error('[ARGUS] Failed to generate commentary:', err)
                        }
                      }}
                      className="mt-3 px-3 py-1.5 bg-purple-500/20 text-purple-400 text-xs rounded-lg hover:bg-purple-500/30 transition-colors"
                    >
                      Generate Commentary Now
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Alerts & Danger Zones Row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Live Alerts */}
              <div className="bg-gray-800/50 rounded-xl p-5">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-bold text-white flex items-center gap-2">
                    <Bell className="w-5 h-5 text-yellow-400" />
                    Live Alerts
                    {alerts.length > 0 && (
                      <span className="px-2 py-0.5 bg-rose-500 text-white text-xs rounded-full font-bold">
                        {alerts.length}
                      </span>
                    )}
                  </h3>
                  <div className="flex items-center gap-2">
                    {alerts.length > 0 && (
                      <button
                        onClick={downloadAlertsToExcel}
                        className="p-1.5 hover:bg-gray-700 rounded-lg transition-colors"
                        title="Download alerts to CSV"
                      >
                        <Download className="w-4 h-4 text-gray-400 hover:text-white" />
                      </button>
                    )}
                    <button
                      onClick={() => setAlertsExpanded(!alertsExpanded)}
                      className="p-1.5 hover:bg-gray-700 rounded-lg transition-colors"
                      title={alertsExpanded ? 'Collapse' : 'Expand'}
                    >
                      {alertsExpanded ? (
                        <ChevronUp className="w-4 h-4 text-gray-400" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-gray-400" />
                      )}
                    </button>
                  </div>
                </div>
                <div className={`space-y-2 overflow-y-auto transition-all duration-300 ${alertsExpanded ? 'max-h-[500px]' : 'max-h-48'}`}>
                  {alerts.length > 0 ? (
                    alerts.slice(0, alertsExpanded ? 50 : 6).map((alert, idx) => (
                      <div
                        key={idx}
                        className={`p-2.5 rounded-lg border-l-4 ${
                          alert.priority === 'HIGH'
                            ? 'bg-rose-500/10 border-rose-500'
                            : alert.priority === 'MEDIUM'
                            ? 'bg-yellow-500/10 border-yellow-500'
                            : 'bg-gray-700/30 border-gray-600'
                        }`}
                      >
                        <div className="text-sm text-white">{alert.message}</div>
                        <div className="text-xs text-gray-500 mt-1">
                          {new Date(alert.triggered_at).toLocaleTimeString('en-US', { timeZone: 'America/Chicago', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true })} CT
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="text-center py-6 text-gray-500">
                      <Bell className="w-8 h-8 mx-auto mb-2 opacity-30" />
                      <p className="text-sm">No active alerts</p>
                    </div>
                  )}
                </div>
                {alerts.length > 6 && !alertsExpanded && (
                  <button
                    onClick={() => setAlertsExpanded(true)}
                    className="w-full mt-2 py-1.5 text-xs text-gray-400 hover:text-white hover:bg-gray-700/50 rounded transition-colors"
                  >
                    Show {alerts.length - 6} more alerts
                  </button>
                )}
              </div>

              {/* Danger Zones with Live Log */}
              <div className="bg-gray-800/50 rounded-xl p-5">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-bold text-white flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5 text-orange-400" />
                    Danger Zones
                    <span className="text-xs text-gray-500 font-normal">
                      {dangerZoneLogs.length > 0 ? `${dangerZoneLogs.length} events` : ''}
                    </span>
                  </h3>
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse"></span>
                    {dangerZoneLogs.length > 0 && (
                      <button
                        onClick={downloadDangerZonesToExcel}
                        className="p-1.5 hover:bg-gray-700 rounded-lg transition-colors"
                        title="Download danger zone logs to CSV"
                      >
                        <Download className="w-4 h-4 text-gray-400 hover:text-white" />
                      </button>
                    )}
                    <button
                      onClick={() => setDangerZonesExpanded(!dangerZonesExpanded)}
                      className="p-1.5 hover:bg-gray-700 rounded-lg transition-colors"
                      title={dangerZonesExpanded ? 'Collapse' : 'Expand'}
                    >
                      {dangerZonesExpanded ? (
                        <ChevronUp className="w-4 h-4 text-gray-400" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-gray-400" />
                      )}
                    </button>
                  </div>
                </div>

                {/* Current Active Danger Zones */}
                {(buildingZones.length > 0 || collapsingZones.length > 0 || spikeZones.length > 0) ? (
                  <div className="space-y-3 mb-4">
                    {spikeZones.length > 0 && (
                      <div>
                        <div className="flex items-center gap-2 mb-2">
                          <Zap className="w-4 h-4 text-yellow-400" />
                          <span className="text-sm text-yellow-400 font-medium">Spike (1min ROC ≥15%)</span>
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {spikeZones.slice(0, 4).map(dz => (
                            <span key={dz.strike} className="px-2 py-1 bg-yellow-500/20 text-yellow-400 rounded text-xs">
                              ${dz.strike} (+{dz.roc_1min.toFixed(0)}%)
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    {buildingZones.length > 0 && (
                      <div>
                        <div className="flex items-center gap-2 mb-2">
                          <Flame className="w-4 h-4 text-orange-400" />
                          <span className="text-sm text-orange-400 font-medium">Building (5min ROC ≥25%)</span>
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {buildingZones.slice(0, 4).map(dz => (
                            <span key={dz.strike} className="px-2 py-1 bg-orange-500/20 text-orange-400 rounded text-xs">
                              ${dz.strike} (+{dz.roc_5min.toFixed(0)}%)
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    {collapsingZones.length > 0 && (
                      <div>
                        <div className="flex items-center gap-2 mb-2">
                          <TrendingDown className="w-4 h-4 text-rose-400" />
                          <span className="text-sm text-rose-400 font-medium">Collapsing (5min ROC ≤-25%)</span>
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {collapsingZones.slice(0, 4).map(dz => (
                            <span key={dz.strike} className="px-2 py-1 bg-rose-500/20 text-rose-400 rounded text-xs">
                              ${dz.strike} ({dz.roc_5min.toFixed(0)}%)
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="mb-3 space-y-2">
                    {/* Pinning Status Alert */}
                    {gammaData?.pinning_status?.is_pinning ? (
                      <div className="p-3 bg-emerald-500/10 rounded-lg border border-emerald-500/20">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <Target className="w-5 h-5 text-emerald-400" />
                            <span className="text-sm font-medium text-emerald-400">Pinning Detected</span>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse"></span>
                            <span className="text-[10px] text-emerald-400/70">Stable</span>
                          </div>
                        </div>
                        <p className="text-xs text-gray-300 mb-2">{gammaData.pinning_status.message}</p>
                        {gammaData.pinning_status.trade_idea && (
                          <p className="text-[10px] text-blue-400 bg-blue-500/10 px-2 py-1 rounded">
                            💡 {gammaData.pinning_status.trade_idea}
                          </p>
                        )}
                        <div className="flex justify-between text-[10px] text-gray-500 mt-2">
                          <span>Avg ROC: {gammaData.pinning_status.avg_roc?.toFixed(1)}%</span>
                          <span>Pin Distance: {gammaData.pinning_status.distance_to_pin_pct?.toFixed(2)}%</span>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between p-3 bg-emerald-500/10 rounded-lg border border-emerald-500/20">
                        <div className="flex items-center gap-2">
                          <Shield className="w-5 h-5 text-emerald-400" />
                          <div>
                            <p className="text-sm font-medium text-emerald-400">All Clear</p>
                            <p className="text-[10px] text-gray-500">
                              All strikes stable (ROC within ±25%)
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse"></span>
                          <span className="text-[10px] text-emerald-400/70">Monitoring</span>
                        </div>
                      </div>
                    )}
                    {/* Show top ROC strikes even when calm */}
                    {gammaData && gammaData.strikes && gammaData.strikes.length > 0 && (
                      <div className="mt-2">
                        <div className="text-[10px] text-gray-600 mb-1">Top activity:</div>
                        <div className="grid grid-cols-3 gap-1">
                          {[...gammaData.strikes]
                            .sort((a, b) => Math.abs(b.roc_5min) - Math.abs(a.roc_5min))
                            .slice(0, 3)
                            .map(s => (
                              <div key={s.strike} className="px-2 py-1.5 bg-gray-700/40 rounded text-xs text-center">
                                <span className="text-white font-medium">${s.strike}</span>
                                <span className={`ml-1 ${s.roc_5min > 0 ? 'text-emerald-400' : s.roc_5min < 0 ? 'text-rose-400' : 'text-gray-500'}`}>
                                  {s.roc_5min > 0 ? '+' : ''}{s.roc_5min.toFixed(1)}%
                                </span>
                              </div>
                            ))
                          }
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Danger Zone Log History - ALWAYS VISIBLE */}
                <div className="border-t border-gray-700/50 pt-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-gray-500">Event Log</span>
                    <span className="text-[10px] text-emerald-400">Live • 15s refresh</span>
                  </div>
                  {dangerZoneLogs.length > 0 ? (
                    <div className={`space-y-1.5 overflow-y-auto transition-all duration-300 ${dangerZonesExpanded ? 'max-h-[400px]' : 'max-h-32'}`}>
                      {dangerZoneLogs.slice(0, dangerZonesExpanded ? 100 : 5).map((log) => (
                        <div
                          key={log.id}
                          className={`flex items-center justify-between text-xs px-2 py-1.5 rounded ${
                            log.is_active
                              ? log.danger_type === 'BUILDING' ? 'bg-orange-500/10' : 'bg-rose-500/10'
                              : 'bg-gray-700/30'
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            <span className={`font-mono ${log.is_active ? 'text-white' : 'text-gray-500'}`}>
                              ${log.strike}
                            </span>
                            <span className={`px-1 py-0.5 rounded text-[10px] ${
                              log.danger_type === 'BUILDING'
                                ? 'bg-orange-500/30 text-orange-400'
                                : log.danger_type === 'COLLAPSING'
                                ? 'bg-rose-500/30 text-rose-400'
                                : 'bg-yellow-500/30 text-yellow-400'
                            }`}>
                              {log.danger_type}
                            </span>
                            {!log.is_active && (
                              <span className="text-gray-600 text-[10px]">resolved</span>
                            )}
                          </div>
                          <span className="text-gray-500">
                            {new Date(log.detected_at).toLocaleTimeString('en-US', {
                              timeZone: 'America/Chicago',
                              hour: '2-digit',
                              minute: '2-digit',
                              hour12: true
                            })}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-4 text-gray-600 text-xs bg-gray-800/30 rounded">
                      <Clock className="w-4 h-4 mx-auto mb-1 opacity-40" />
                      <p>No events yet today</p>
                      <p className="text-[10px] text-gray-700 mt-1">Logs when ROC exceeds ±25%</p>
                    </div>
                  )}
                  {dangerZoneLogs.length > 5 && !dangerZonesExpanded && (
                    <button
                      onClick={() => setDangerZonesExpanded(true)}
                      className="w-full mt-2 py-1.5 text-xs text-gray-400 hover:text-white hover:bg-gray-700/50 rounded transition-colors"
                    >
                      Show {dangerZoneLogs.length - 5} more events
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Right Column - Key Levels & Context */}
          <div className="space-y-6">

            {/* Key Levels */}
            <div className="bg-gray-800/50 rounded-xl p-5">
              <h3 className="font-bold text-white flex items-center gap-2 mb-4">
                <Target className="w-5 h-5 text-purple-400" />
                Key Levels
              </h3>

              <div className="space-y-4">
                {/* Pin Strike */}
                {gammaData?.likely_pin && (
                  <div className="flex items-center justify-between p-3 bg-purple-500/10 rounded-lg border border-purple-500/30">
                    <div>
                      <div className="text-xs text-purple-400 mb-1">PIN STRIKE</div>
                      <div className="text-lg font-bold text-white">${gammaData.likely_pin}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-gray-500">Probability</div>
                      <div className="text-lg font-bold text-purple-400">{gammaData.pin_probability.toFixed(0)}%</div>
                    </div>
                  </div>
                )}

                {/* Top Magnets */}
                {gammaData?.magnets.slice(0, 3).map((m, idx) => (
                  <div key={m.strike} className="flex items-center justify-between p-3 bg-yellow-500/10 rounded-lg border border-yellow-500/30">
                    <div>
                      <div className="text-xs text-yellow-400 mb-1">MAGNET #{idx + 1}</div>
                      <div className="text-lg font-bold text-white">${m.strike}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-gray-500">Attraction</div>
                      <div className="text-lg font-bold text-yellow-400">{m.probability.toFixed(0)}%</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Bot Status - Real Data */}
            <div className="bg-gray-800/50 rounded-xl p-5">
              <h3 className="font-bold text-white flex items-center gap-2 mb-4">
                <Bot className="w-5 h-5 text-blue-400" />
                Bot Positions
                {botPositions.some(b => b.status === 'open') && (
                  <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse"></span>
                )}
              </h3>
              <div className="space-y-3">
                {botPositions.length > 0 ? botPositions.map((bot, idx) => (
                  <div
                    key={`${bot.bot}-${idx}`}
                    className={`p-3 rounded-lg ${
                      bot.status === 'open'
                        ? 'bg-emerald-500/10 border border-emerald-500/30'
                        : 'bg-gray-700/30'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div>
                        <span className="font-bold text-white">{bot.bot}</span>
                        {bot.strategy && (
                          <span className="text-xs text-gray-500 ml-2">{bot.strategy}</span>
                        )}
                      </div>
                      <span className={`text-xs px-2 py-0.5 rounded ${
                        bot.status === 'open' ? 'bg-emerald-500 text-white' :
                        bot.status === 'watching' ? 'bg-yellow-500/20 text-yellow-400' :
                        bot.status === 'closed' ? 'bg-gray-600 text-gray-300' :
                        'bg-gray-700 text-gray-500'
                      }`}>
                        {bot.status.toUpperCase()}
                      </span>
                    </div>
                    {bot.status === 'open' && (
                      <>
                        {bot.strikes && (
                          <div className="text-xs text-gray-400 mb-1">
                            Strikes: ${bot.strikes}
                          </div>
                        )}
                        {bot.direction && (
                          <div className="text-xs">
                            <span className="text-gray-500">Direction: </span>
                            <span className={bot.direction === 'BULLISH' ? 'text-emerald-400' : bot.direction === 'BEARISH' ? 'text-rose-400' : 'text-gray-400'}>
                              {bot.direction}
                            </span>
                          </div>
                        )}
                        {bot.pnl !== undefined && (
                          <div className="flex items-center justify-between mt-2 pt-2 border-t border-gray-600/50">
                            <span className="text-xs text-gray-500">P&L</span>
                            <span className={`font-mono font-bold ${bot.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                              {bot.pnl >= 0 ? '+' : ''}${bot.pnl.toFixed(2)}
                            </span>
                          </div>
                        )}
                        {bot.safe !== undefined && (
                          <div className="mt-1 text-xs">
                            <span className="text-gray-500">vs Magnets: </span>
                            <span className={bot.safe ? 'text-emerald-400' : 'text-rose-400'}>
                              {bot.safe ? 'SAFE' : 'AT RISK'}
                            </span>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )) : (
                  <div className="text-center py-4 text-gray-500">
                    <Bot className="w-6 h-6 mx-auto mb-2 opacity-30" />
                    <p className="text-sm">No active bot positions</p>
                    <p className="text-xs text-gray-600 mt-1">Positions will appear when bots are trading</p>
                  </div>
                )}
              </div>
            </div>

            {/* Gamma Walls */}
            {marketContext?.gamma_walls && (marketContext.gamma_walls.call_wall || marketContext.gamma_walls.put_wall) && (
              <div className="bg-gray-800/50 rounded-xl p-5">
                <h3 className="font-bold text-white flex items-center gap-2 mb-4">
                  <Layers className="w-5 h-5 text-cyan-400" />
                  Gamma Walls
                </h3>
                <div className="space-y-3">
                  {marketContext.gamma_walls.call_wall && (
                    <div className="flex items-center justify-between p-3 bg-emerald-500/10 rounded-lg border border-emerald-500/30">
                      <div className="flex items-center gap-2">
                        <TrendingUp className="w-4 h-4 text-emerald-400" />
                        <div>
                          <div className="text-xs text-emerald-400">CALL WALL</div>
                          <div className="font-bold text-white">${marketContext.gamma_walls.call_wall}</div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-xs text-gray-500">Distance</div>
                        <div className={`font-bold ${(marketContext.gamma_walls.call_wall_distance || 0) < 1 ? 'text-yellow-400' : 'text-emerald-400'}`}>
                          +{marketContext.gamma_walls.call_wall_distance?.toFixed(2)}%
                        </div>
                      </div>
                    </div>
                  )}
                  {marketContext.gamma_walls.put_wall && (
                    <div className="flex items-center justify-between p-3 bg-rose-500/10 rounded-lg border border-rose-500/30">
                      <div className="flex items-center gap-2">
                        <TrendingDown className="w-4 h-4 text-rose-400" />
                        <div>
                          <div className="text-xs text-rose-400">PUT WALL</div>
                          <div className="font-bold text-white">${marketContext.gamma_walls.put_wall}</div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-xs text-gray-500">Distance</div>
                        <div className={`font-bold ${Math.abs(marketContext.gamma_walls.put_wall_distance || 0) < 1 ? 'text-yellow-400' : 'text-rose-400'}`}>
                          {marketContext.gamma_walls.put_wall_distance?.toFixed(2)}%
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Psychology Traps */}
            {marketContext?.psychology_traps && (marketContext.psychology_traps.liberation_setup || marketContext.psychology_traps.false_floor || marketContext.psychology_traps.active_trap) && (
              <div className="bg-orange-500/10 border border-orange-500/30 rounded-xl p-5">
                <h3 className="font-bold text-white flex items-center gap-2 mb-4">
                  <AlertTriangle className="w-5 h-5 text-orange-400" />
                  Psychology Trap Alert
                </h3>
                <div className="space-y-3">
                  {marketContext.psychology_traps.liberation_setup && (
                    <div className="p-3 bg-emerald-500/10 rounded-lg border-l-4 border-emerald-500">
                      <div className="flex items-center gap-2 mb-1">
                        <Unlock className="w-4 h-4 text-emerald-400" />
                        <span className="font-bold text-emerald-400">Liberation Setup</span>
                      </div>
                      <p className="text-xs text-gray-400">
                        Price near gamma wall with high IV. Target: ${marketContext.psychology_traps.liberation_target || 'TBD'}
                      </p>
                    </div>
                  )}
                  {marketContext.psychology_traps.false_floor && (
                    <div className="p-3 bg-rose-500/10 rounded-lg border-l-4 border-rose-500">
                      <div className="flex items-center gap-2 mb-1">
                        <Lock className="w-4 h-4 text-rose-400" />
                        <span className="font-bold text-rose-400">False Floor Detected</span>
                      </div>
                      <p className="text-xs text-gray-400">
                        Put wall may not hold. Strike: ${marketContext.psychology_traps.false_floor_strike || 'TBD'}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* RSI Alignment */}
            {marketContext?.rsi_alignment && (marketContext.rsi_alignment.aligned_overbought || marketContext.rsi_alignment.aligned_oversold || marketContext.rsi_alignment.rsi_5m) && (
              <div className="bg-gray-800/50 rounded-xl p-5">
                <h3 className="font-bold text-white flex items-center gap-2 mb-4">
                  <Gauge className="w-5 h-5 text-indigo-400" />
                  RSI Alignment
                  {marketContext.rsi_alignment.aligned_overbought && (
                    <span className="px-2 py-0.5 bg-rose-500 text-white text-[10px] rounded font-bold">OVERBOUGHT</span>
                  )}
                  {marketContext.rsi_alignment.aligned_oversold && (
                    <span className="px-2 py-0.5 bg-emerald-500 text-white text-[10px] rounded font-bold">OVERSOLD</span>
                  )}
                </h3>
                <div className="grid grid-cols-5 gap-2">
                  {['5m', '15m', '1h', '4h', '1d'].map((tf) => {
                    const value = marketContext.rsi_alignment[`rsi_${tf}` as keyof typeof marketContext.rsi_alignment] as number | null
                    const rsiColor = value && value > 70 ? 'text-rose-400' : value && value < 30 ? 'text-emerald-400' : 'text-gray-300'
                    return (
                      <div key={tf} className="text-center p-2 bg-gray-700/30 rounded">
                        <div className="text-[10px] text-gray-500 uppercase">{tf}</div>
                        <div className={`font-bold ${rsiColor}`}>{value?.toFixed(0) || '-'}</div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Monthly Magnets */}
            {marketContext?.monthly_magnets && (marketContext.monthly_magnets.above || marketContext.monthly_magnets.below) && (
              <div className="bg-gray-800/50 rounded-xl p-5">
                <h3 className="font-bold text-white flex items-center gap-2 mb-4">
                  <Compass className="w-5 h-5 text-purple-400" />
                  Monthly Magnets
                </h3>
                <div className="space-y-2">
                  {marketContext.monthly_magnets.above && (
                    <div className="flex items-center justify-between p-2 bg-emerald-500/10 rounded">
                      <span className="text-xs text-gray-400">Above Target</span>
                      <span className="font-bold text-emerald-400">${marketContext.monthly_magnets.above}</span>
                    </div>
                  )}
                  {marketContext.monthly_magnets.below && (
                    <div className="flex items-center justify-between p-2 bg-rose-500/10 rounded">
                      <span className="text-xs text-gray-400">Below Target</span>
                      <span className="font-bold text-rose-400">${marketContext.monthly_magnets.below}</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Regime Context */}
            {marketContext?.regime?.type && (
              <div className="bg-gray-800/50 rounded-xl p-5">
                <h3 className="font-bold text-white flex items-center gap-2 mb-4">
                  <Activity className="w-5 h-5 text-blue-400" />
                  Market Regime
                </h3>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400">Type</span>
                    <span className={`font-bold ${
                      marketContext.regime.type?.includes('BULL') ? 'text-emerald-400' :
                      marketContext.regime.type?.includes('BEAR') ? 'text-rose-400' : 'text-gray-300'
                    }`}>{marketContext.regime.type}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400">Direction</span>
                    <span className={`font-bold ${
                      marketContext.regime.direction === 'BULLISH' ? 'text-emerald-400' :
                      marketContext.regime.direction === 'BEARISH' ? 'text-rose-400' : 'text-gray-300'
                    }`}>{marketContext.regime.direction || '-'}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400">Confidence</span>
                    <span className="font-bold text-blue-400">{(marketContext.regime.confidence || 0).toFixed(0)}%</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400">Risk Level</span>
                    <span className={`font-bold ${
                      marketContext.regime.risk_level === 'HIGH' ? 'text-rose-400' :
                      marketContext.regime.risk_level === 'MEDIUM' ? 'text-yellow-400' : 'text-emerald-400'
                    }`}>{marketContext.regime.risk_level || '-'}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Education */}
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4">
              <div className="flex items-start gap-3">
                <Info className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
                <div className="text-xs text-gray-400 space-y-2">
                  <p className="font-medium text-blue-400">Understanding Gamma</p>
                  <p><strong className="text-emerald-400">+Gamma:</strong> MMs sell rallies, buy dips → stabilizing effect</p>
                  <p><strong className="text-rose-400">-Gamma:</strong> MMs buy rallies, sell dips → amplifies moves</p>
                  <p><strong className="text-yellow-400">Magnets:</strong> High gamma = price attraction zones</p>
                  <p><strong className="text-purple-400">Pin:</strong> Max pain strike for options expiration</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
