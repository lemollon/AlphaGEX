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
  error?: string
}

export function useTraderWebSocket() {
  const [data, setData] = useState<TraderUpdate | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>()

  const connect = useCallback(() => {
    try {
      const wsUrl = API_BASE.replace('http://', 'ws://').replace('https://', 'wss://')
      const ws = new WebSocket(`${wsUrl}/ws/trader`)

      ws.onopen = () => {
        console.log('Trader WebSocket connected')
        setIsConnected(true)
        setError(null)
      }

      ws.onmessage = (event) => {
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
        console.error('WebSocket error:', event)
        setError('WebSocket connection error')
      }

      ws.onclose = () => {
        console.log('Trader WebSocket disconnected')
        setIsConnected(false)

        // Attempt to reconnect after 5 seconds
        reconnectTimeoutRef.current = setTimeout(() => {
          console.log('Attempting to reconnect...')
          connect()
        }, 5000)
      }

      wsRef.current = ws
    } catch (err) {
      console.error('Failed to create WebSocket:', err)
      setError('Failed to establish WebSocket connection')
    }
  }, [])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }, [])

  const subscribe = useCallback((symbols: string[]) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'subscribe',
        symbols
      }))
    }
  }, [])

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [connect, disconnect])

  return {
    data,
    isConnected,
    error,
    reconnect: connect,
    subscribe
  }
}
