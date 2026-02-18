/**
 * useChartWebSocket - Real-time chart data streaming hook
 *
 * Manages a WebSocket connection to /ws/live-chart for streaming
 * price quotes, candle updates, and GEX level changes.
 *
 * Features:
 * - Auto-reconnect with exponential backoff (resets on success)
 * - Fallback to short-interval HTTP polling (2s) when WS unavailable
 * - Mutual exclusion: polling stops when WS connects, WS stops when polling
 * - Animation-friendly throttled updates (capped at ~30fps)
 * - Connection status tracking (connected/reconnecting/disconnected/polling)
 * - Session data deduplication on reconnect (Section 2)
 * - Forming candle merges with last REST bar to avoid duplicates (Section 4)
 * - Proper cleanup on unmount (no memory leaks) (Section 5)
 */

import { useEffect, useState, useCallback, useRef } from 'react'
import { apiClient } from '@/lib/api'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ── Types ────────────────────────────────────────────────────────

export interface CandleData {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface GexLevels {
  flip_point: number | null
  call_wall: number | null
  put_wall: number | null
  expected_move: number | null
  upper_1sd: number | null
  lower_1sd: number | null
  vix: number | null
  net_gamma: number | null
  gamma_regime: string | null
}

export interface GexTick {
  time: string
  spot_price: number | null
  net_gamma: number | null
  vix: number | null
  expected_move: number | null
  gamma_regime: string | null
  flip_point: number | null
  call_wall: number | null
  put_wall: number | null
}

export interface QuoteData {
  price: number
  bid: number | null
  ask: number | null
  timestamp: string
}

export type ConnectionStatus = 'connected' | 'reconnecting' | 'disconnected' | 'polling'

export interface SessionData {
  bars: CandleData[]
  gex_levels: GexLevels
  gex_ticks: GexTick[]
  session_date: string | null
  available_dates: string[]
  market_open: boolean
}

export interface ChartWebSocketState {
  bars: CandleData[]
  formingCandle: CandleData | null
  quote: QuoteData | null
  gexLevels: GexLevels
  gexTicks: GexTick[]
  sessionDate: string | null
  availableDates: string[]
  marketOpen: boolean
  connectionStatus: ConnectionStatus
  error: string | null
}

// ── Hook ─────────────────────────────────────────────────────────

export function useChartWebSocket(symbol: string): ChartWebSocketState {
  const [bars, setBars] = useState<CandleData[]>([])
  const [formingCandle, setFormingCandle] = useState<CandleData | null>(null)
  const [quote, setQuote] = useState<QuoteData | null>(null)
  const [gexLevels, setGexLevels] = useState<GexLevels>({
    flip_point: null, call_wall: null, put_wall: null,
    expected_move: null, upper_1sd: null, lower_1sd: null,
    vix: null, net_gamma: null, gamma_regime: null,
  })
  const [gexTicks, setGexTicks] = useState<GexTick[]>([])
  const [sessionDate, setSessionDate] = useState<string | null>(null)
  const [availableDates, setAvailableDates] = useState<string[]>([])
  const [marketOpen, setMarketOpen] = useState(false)
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected')
  const [error, setError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout>>()
  const pollingTimerRef = useRef<ReturnType<typeof setInterval>>()
  const mountedRef = useRef(true)
  const reconnectAttemptRef = useRef(0)
  const maxReconnectAttempts = 5
  const symbolRef = useRef(symbol)
  symbolRef.current = symbol

  // Throttle candle updates to ~30fps max
  const lastUpdateRef = useRef(0)
  const pendingCandleRef = useRef<CandleData | null>(null)
  const rafRef = useRef<number>()

  const flushCandleUpdate = useCallback(() => {
    if (pendingCandleRef.current && mountedRef.current) {
      setFormingCandle({ ...pendingCandleRef.current })
      pendingCandleRef.current = null
    }
    rafRef.current = undefined
  }, [])

  const throttledSetFormingCandle = useCallback((candle: CandleData) => {
    const now = performance.now()
    pendingCandleRef.current = candle
    if (now - lastUpdateRef.current >= 33) {
      lastUpdateRef.current = now
      flushCandleUpdate()
    } else if (!rafRef.current) {
      rafRef.current = requestAnimationFrame(flushCandleUpdate)
    }
  }, [flushCandleUpdate])

  // ── Load session data via REST (instant render) ─────────────────
  const loadSessionData = useCallback(async (sym: string) => {
    try {
      const res = await apiClient.getWatchtowerSessionData(sym)
      const d = res.data?.data
      if (!d || !mountedRef.current) return

      if (d.bars?.length > 0) setBars(d.bars)
      if (d.gex_levels) setGexLevels(prev => ({ ...prev, ...d.gex_levels }))
      if (d.gex_ticks?.length > 0) setGexTicks(d.gex_ticks)
      if (d.session_date) setSessionDate(d.session_date)
      if (d.available_dates) setAvailableDates(d.available_dates)
      setMarketOpen(d.market_open ?? false)
    } catch (err) {
      console.error('Failed to load session data:', err)
    }
  }, [])

  // ── Polling fallback (2s interval) ──────────────────────────────
  const startPolling = useCallback(() => {
    // Section 2: guard against starting polling after unmount
    if (!mountedRef.current) return
    if (pollingTimerRef.current) return // already polling
    setConnectionStatus('polling')

    const poll = async () => {
      if (!mountedRef.current) return
      try {
        const [barsRes, ticksRes] = await Promise.all([
          apiClient.getWatchtowerIntradayBars(symbolRef.current, '5min'),
          apiClient.getWatchtowerIntradayTicks(symbolRef.current, 5),
        ])

        if (barsRes.data?.success && barsRes.data?.data?.bars) {
          setBars(barsRes.data.data.bars)
        }
        if (ticksRes.data?.success && ticksRes.data?.data?.ticks) {
          setGexTicks(ticksRes.data.data.ticks)
          const ticks = ticksRes.data.data.ticks
          if (ticks.length > 0) {
            const last = ticks[ticks.length - 1]
            setGexLevels(prev => ({
              ...prev,
              flip_point: last.flip_point ?? prev.flip_point,
              call_wall: last.call_wall ?? prev.call_wall,
              put_wall: last.put_wall ?? prev.put_wall,
            }))
          }
        }
        setError(null)
      } catch {
        // Silent - don't disrupt chart on poll failure
      }
    }

    poll()
    pollingTimerRef.current = setInterval(poll, 2000)
  }, [])

  const stopPolling = useCallback(() => {
    if (pollingTimerRef.current) {
      clearInterval(pollingTimerRef.current)
      pollingTimerRef.current = undefined
    }
  }, [])

  // ── WebSocket connection ────────────────────────────────────────
  const connect = useCallback(() => {
    if (!mountedRef.current) return
    // Section 2: close any existing socket before creating a new one
    if (wsRef.current) {
      if (wsRef.current.readyState === WebSocket.OPEN ||
          wsRef.current.readyState === WebSocket.CONNECTING) {
        return // already connected / connecting
      }
      wsRef.current = null
    }

    try {
      const wsUrl = API_BASE.replace('http://', 'ws://').replace('https://', 'wss://')
      const ws = new WebSocket(`${wsUrl}/ws/live-chart?symbol=${symbolRef.current}`)

      ws.onopen = () => {
        if (!mountedRef.current) return
        setConnectionStatus('connected')
        setError(null)
        // Section 2: reset backoff counter on successful connect
        reconnectAttemptRef.current = 0
        // Section 2: stop polling — mutual exclusion
        stopPolling()
      }

      ws.onmessage = (event) => {
        if (!mountedRef.current) return
        try {
          const msg = JSON.parse(event.data)

          switch (msg.type) {
            case 'session_data':
              // Section 2: on reconnect, WS sends session data again.
              // Replace bars only if WS actually sent bars (don't clear with empty).
              if (msg.bars?.length > 0) setBars(msg.bars)
              if (msg.gex_levels) setGexLevels(prev => ({ ...prev, ...msg.gex_levels }))
              if (msg.gex_ticks?.length > 0) setGexTicks(msg.gex_ticks)
              if (msg.session_date) setSessionDate(msg.session_date)
              if (msg.available_dates) setAvailableDates(msg.available_dates)
              setMarketOpen(msg.market_open ?? false)
              break

            case 'candle_update':
              if (msg.candle) {
                throttledSetFormingCandle(msg.candle)
              }
              if (msg.price) {
                setQuote({
                  price: msg.price,
                  bid: msg.bid,
                  ask: msg.ask,
                  timestamp: msg.timestamp,
                })
              }
              // Section 4: receiving candle_update means market is open —
              // this drives the LIVE badge without requiring a clock check.
              setMarketOpen(true)
              break

            case 'completed_candle':
              // Section 2+4: merge completed candle into bars, replacing any
              // existing bar at the same timestamp (handles REST→WS overlap).
              if (msg.candle) {
                setBars(prev => {
                  const idx = prev.findIndex(b => b.time === msg.candle.time)
                  if (idx >= 0) {
                    // Update in place (REST bar → verified WS bar)
                    const updated = [...prev]
                    updated[idx] = msg.candle
                    return updated
                  }
                  return [...prev, msg.candle]
                })
              }
              break

            case 'gex_levels':
              setGexLevels(prev => ({ ...prev, ...msg }))
              break

            case 'keepalive':
              setMarketOpen(msg.market_open ?? false)
              break
          }
        } catch (err) {
          console.error('Failed to parse chart WS message:', err)
        }
      }

      ws.onerror = () => {
        if (!mountedRef.current) return
        setError('WebSocket connection error')
        // Don't increment here — onclose always fires after onerror and handles retry
      }

      ws.onclose = () => {
        if (!mountedRef.current) return

        // Section 2: only reconnect / poll if still mounted
        reconnectAttemptRef.current++
        setConnectionStatus('reconnecting')

        // Start polling as immediate fallback
        startPolling()

        // Schedule WS reconnect with exponential backoff
        if (reconnectAttemptRef.current < maxReconnectAttempts) {
          const delay = Math.min(1000 * Math.pow(2, reconnectAttemptRef.current), 30000)
          reconnectTimerRef.current = setTimeout(() => {
            if (mountedRef.current) connect()
          }, delay)
        }
      }

      wsRef.current = ws
    } catch {
      console.error('Failed to create chart WebSocket')
      startPolling()
    }
  }, [stopPolling, startPolling, throttledSetFormingCandle])

  // ── Lifecycle ───────────────────────────────────────────────────

  useEffect(() => {
    mountedRef.current = true

    // 1. Load cached session data instantly via REST
    loadSessionData(symbol)

    // 2. Attempt WebSocket connection for live streaming
    connect()

    return () => {
      // Section 5: set mounted false FIRST to prevent callbacks from firing
      mountedRef.current = false

      // Cancel pending reconnect
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = undefined
      }

      // Stop polling
      stopPolling()

      // Close WebSocket
      if (wsRef.current) {
        wsRef.current.onclose = null // prevent onclose from triggering reconnect
        wsRef.current.onerror = null
        wsRef.current.onmessage = null
        wsRef.current.close()
        wsRef.current = null
      }

      // Cancel any pending animation frame
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = undefined
      }
    }
  }, [symbol]) // eslint-disable-line react-hooks/exhaustive-deps

  return {
    bars,
    formingCandle,
    quote,
    gexLevels,
    gexTicks,
    sessionDate,
    availableDates,
    marketOpen,
    connectionStatus,
    error,
  }
}
