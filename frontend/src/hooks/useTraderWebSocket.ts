import { useEffect, useState, useCallback, useRef } from 'react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface TraderUpdate {
  type: string
  timestamp: string
  market_open: boolean
  config?: Record<string, string>
  status?: {
    status: string
    current_action: string
    market_analysis: string
    last_decision: string
    last_updated: string
    next_check_time?: string
  }
  positions?: Array<{
    id: number
    symbol: string
    strategy: string
    action: string
    strike: number
    option_type: string
    expiration_date: string
    contracts: number
    entry_price: number
    current_price: number
    unrealized_pnl: number
    unrealized_pnl_pct: number
    confidence: number
  }>
  recent_trades?: Array<{
    id: number
    symbol: string
    strategy: string
    action: string
    strike: number
    option_type: string
    entry_date: string
    exit_date: string
    entry_price: number
    exit_price: number
    realized_pnl: number
    realized_pnl_pct: number
    exit_reason: string
  }>
  performance?: {
    starting_capital: number
    current_equity: number
    total_realized_pnl: number
    total_unrealized_pnl: number
    net_pnl: number
    return_pct: number
    total_trades: number
    winning_trades: number
    losing_trades: number
    win_rate: number
    open_positions: number
  }
  alerts?: Array<{
    level: 'info' | 'warning' | 'critical'
    message: string
  }>
  market?: {
    symbol: string
    spot_price: number
    net_gex: number
    flip_point: number
    call_wall: number
    put_wall: number
  }
  ai_logs?: Array<{
    id: number
    timestamp: string
    log_type: string
    symbol: string
    pattern_detected: string
    confidence_score: number
    trade_direction: string
    ai_thought_process: string
    action_taken: string
    reasoning_summary: string
  }>
  error?: string
}

// Fetch data from REST API as fallback
async function fetchTraderData(): Promise<TraderUpdate | null> {
  try {
    const [statusRes, perfRes, positionsRes, tradesRes, logsRes, gexRes] = await Promise.all([
      fetch(`${API_BASE}/api/trader/status`).then(r => r.json()).catch(() => null),
      fetch(`${API_BASE}/api/trader/performance`).then(r => r.json()).catch(() => null),
      fetch(`${API_BASE}/api/trader/positions`).then(r => r.json()).catch(() => null),
      fetch(`${API_BASE}/api/trader/closed-trades`).then(r => r.json()).catch(() => null),
      fetch(`${API_BASE}/api/autonomous/logs?limit=20`).then(r => r.json()).catch(() => null),
      fetch(`${API_BASE}/api/gex/SPY`).then(r => r.json()).catch(() => null)
    ])

    const statusData = statusRes?.data || statusRes
    const perfData = perfRes?.data || perfRes
    const positionsData = positionsRes?.data || []
    const tradesData = tradesRes?.data || []
    const logsData = logsRes?.data || []
    const gexData = gexRes?.data || gexRes

    return {
      type: 'rest_update',
      timestamp: new Date().toISOString(),
      market_open: statusData?.is_active || false,
      status: statusData ? {
        status: statusData.status || 'UNKNOWN',
        current_action: statusData.current_action || '',
        market_analysis: statusData.market_analysis || '',
        last_decision: statusData.last_decision || '',
        last_updated: statusData.last_check || new Date().toISOString(),
        next_check_time: statusData.next_check
      } : undefined,
      positions: positionsData,
      recent_trades: tradesData,
      performance: perfData ? {
        starting_capital: perfData.starting_capital || 10000,
        current_equity: perfData.current_value || perfData.starting_capital || 10000,
        total_realized_pnl: perfData.realized_pnl || perfData.total_pnl || 0,
        total_unrealized_pnl: perfData.unrealized_pnl || 0,
        net_pnl: perfData.total_pnl || 0,
        return_pct: perfData.return_pct || 0,
        total_trades: perfData.total_trades || 0,
        winning_trades: perfData.winning_trades || 0,
        losing_trades: perfData.losing_trades || 0,
        win_rate: perfData.win_rate || 0,
        open_positions: perfData.open_positions || 0
      } : undefined,
      market: gexData ? {
        symbol: gexData.symbol || 'SPY',
        spot_price: gexData.spot_price || 0,
        net_gex: gexData.net_gex || 0,
        flip_point: gexData.flip_point || 0,
        call_wall: gexData.call_wall || 0,
        put_wall: gexData.put_wall || 0
      } : undefined,
      ai_logs: logsData
    }
  } catch (err) {
    console.error('Failed to fetch trader data via REST:', err)
    return null
  }
}

export function useTraderWebSocket() {
  const [data, setData] = useState<TraderUpdate | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [usingRestFallback, setUsingRestFallback] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>()
  const pollingIntervalRef = useRef<NodeJS.Timeout>()
  const wsFailCountRef = useRef(0)
  const mountedRef = useRef(true) // Track if component is mounted to prevent state updates after unmount
  const fetchInProgressRef = useRef(false) // Prevent request stacking

  // REST API polling fallback
  const startPolling = useCallback(() => {
    if (pollingIntervalRef.current) return // Already polling
    if (!mountedRef.current) return // Don't start if unmounted

    console.log('Starting REST API polling fallback...')
    setUsingRestFallback(true)

    // Immediate fetch
    if (!fetchInProgressRef.current) {
      fetchInProgressRef.current = true
      fetchTraderData().then(d => {
        fetchInProgressRef.current = false
        if (d && mountedRef.current) {
          setData(d)
          setIsConnected(true)
          setError(null)
        }
      }).catch(() => {
        fetchInProgressRef.current = false
      })
    }

    // Poll every 10 seconds with request deduplication
    pollingIntervalRef.current = setInterval(async () => {
      if (!mountedRef.current) return
      // Skip if a fetch is already in progress (prevents request stacking)
      if (fetchInProgressRef.current) {
        console.log('Skipping poll - previous request still in progress')
        return
      }
      fetchInProgressRef.current = true
      try {
        const d = await fetchTraderData()
        if (d && mountedRef.current) {
          setData(d)
          setIsConnected(true)
        }
      } finally {
        fetchInProgressRef.current = false
      }
    }, 10000)
  }, [])

  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = undefined
      setUsingRestFallback(false)
    }
  }, [])

  const connect = useCallback(() => {
    try {
      const wsUrl = API_BASE.replace('http://', 'ws://').replace('https://', 'wss://')
      const ws = new WebSocket(`${wsUrl}/ws/trader`)

      ws.onopen = () => {
        if (!mountedRef.current) return
        console.log('Trader WebSocket connected')
        setIsConnected(true)
        setError(null)
        wsFailCountRef.current = 0
        stopPolling() // Stop REST polling if WS connects
      }

      ws.onmessage = (event) => {
        if (!mountedRef.current) return
        try {
          const message = JSON.parse(event.data)
          if (message.type === 'trader_update' || message.type === 'connected') {
            setData(message)
          }
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err)
        }
      }

      ws.onerror = (event) => {
        if (!mountedRef.current) return
        console.error('WebSocket error:', event)
        wsFailCountRef.current++
        setError('WebSocket connection error')

        // After 2 failed attempts, switch to REST polling
        if (wsFailCountRef.current >= 2) {
          console.log('WebSocket unavailable, switching to REST API fallback')
          startPolling()
        }
      }

      ws.onclose = () => {
        if (!mountedRef.current) return
        console.log('Trader WebSocket disconnected')
        setIsConnected(false)

        // Start REST polling immediately on close
        if (!pollingIntervalRef.current) {
          startPolling()
        }

        // Still try to reconnect WebSocket in background
        reconnectTimeoutRef.current = setTimeout(() => {
          if (!mountedRef.current) return
          console.log('Attempting WebSocket reconnect...')
          connect()
        }, 30000) // Try WS reconnect every 30s
      }

      wsRef.current = ws
    } catch (err) {
      console.error('Failed to create WebSocket:', err)
      setError('Failed to establish WebSocket connection')
      wsFailCountRef.current++

      // Fall back to REST polling
      if (wsFailCountRef.current >= 2) {
        startPolling()
      }
    }
  }, [startPolling, stopPolling])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    stopPolling()
  }, [stopPolling])

  const subscribe = useCallback((symbols: string[]) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'subscribe',
        symbols
      }))
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      disconnect()
    }
  }, [connect, disconnect])

  return {
    data,
    isConnected,
    error,
    usingRestFallback,
    reconnect: connect,
    subscribe
  }
}
