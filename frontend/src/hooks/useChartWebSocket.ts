/**
 * useChartWebSocket - Real-time chart data streaming hook
 *
 * Manages a WebSocket connection to /ws/live-chart for streaming
 * price quotes, candle updates, and GEX level changes.
 *
 * Features:
 * - Auto-reconnect with exponential backoff
 * - Fallback to short-interval HTTP polling (2s) when WS unavailable
 * - Animation-friendly throttled updates (capped at ~30fps)
 * - Connection status tracking (connected/reconnecting/disconnected)
 * - Proper cleanup on unmount (no memory leaks)
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
  /** Session bars (historical + live) */
  bars: CandleData[]
  /** Current forming candle (updates in real-time) */
  formingCandle: CandleData | null
  /** Latest price quote */
  quote: QuoteData | null
  /** GEX overlay levels */
  gexLevels: GexLevels
  /** GEX ticks (intraday time series) */
  gexTicks: GexTick[]
  /** Session date being displayed */
  sessionDate: string | null
  /** Available historical session dates */
  availableDates: string[]
  /** Whether market is currently open */
  marketOpen: boolean
  /** WebSocket / polling connection status */
  connectionStatus: ConnectionStatus
  /** Error message if any */
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
    // Cap at ~30fps (33ms between frames)
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
    if (pollingTimerRef.current) return
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
          // Update GEX levels from latest tick
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
      } catch (err) {
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
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return

    try {
      const wsUrl = API_BASE.replace('http://', 'ws://').replace('https://', 'wss://')
      const ws = new WebSocket(`${wsUrl}/ws/live-chart?symbol=${symbolRef.current}`)

      ws.onopen = () => {
        if (!mountedRef.current) return
        setConnectionStatus('connected')
        setError(null)
        reconnectAttemptRef.current = 0
        stopPolling()
      }

      ws.onmessage = (event) => {
        if (!mountedRef.current) return
        try {
          const msg = JSON.parse(event.data)

          switch (msg.type) {
            case 'session_data':
              // Initial session data from WebSocket
              if (msg.bars?.length > 0) setBars(msg.bars)
              if (msg.gex_levels) setGexLevels(prev => ({ ...prev, ...msg.gex_levels }))
              if (msg.gex_ticks?.length > 0) setGexTicks(msg.gex_ticks)
              if (msg.session_date) setSessionDate(msg.session_date)
              if (msg.available_dates) setAvailableDates(msg.available_dates)
              setMarketOpen(msg.market_open ?? false)
              break

            case 'candle_update':
              // Real-time forming candle update (throttled)
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
              setMarketOpen(true)
              break

            case 'completed_candle':
              // A 5-min candle closed — append to bars
              if (msg.candle) {
                setBars(prev => {
                  // Avoid duplicates
                  const existing = prev.find(b => b.time === msg.candle.time)
                  if (existing) return prev
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
        reconnectAttemptRef.current++
        setError('WebSocket connection error')

        // After max attempts, fall back to polling
        if (reconnectAttemptRef.current >= maxReconnectAttempts) {
          startPolling()
        }
      }

      ws.onclose = () => {
        if (!mountedRef.current) return
        setConnectionStatus('reconnecting')

        // Start polling immediately as fallback
        startPolling()

        // Schedule reconnect with exponential backoff
        const delay = Math.min(
          1000 * Math.pow(2, reconnectAttemptRef.current),
          30000
        )
        reconnectTimerRef.current = setTimeout(() => {
          if (mountedRef.current && reconnectAttemptRef.current < maxReconnectAttempts) {
            connect()
          }
        }, delay)
      }

      wsRef.current = ws
    } catch (err) {
      console.error('Failed to create chart WebSocket:', err)
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
      mountedRef.current = false
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
      }
      stopPolling()
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
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
