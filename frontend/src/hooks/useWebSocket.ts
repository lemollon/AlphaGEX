import { useEffect, useState, useCallback, useRef } from 'react'
import { createWebSocket, apiClient } from '@/lib/api'

interface WebSocketData {
  type: string
  symbol?: string
  data?: any
  message?: string
  timestamp?: string
}

// REST fallback to fetch GEX data when WebSocket is unavailable
async function fetchMarketData(symbol: string): Promise<WebSocketData | null> {
  try {
    const response = await apiClient.getGEX(symbol).catch(() => null)
    if (response?.data?.success && response.data.data) {
      return {
        type: 'market_update',
        symbol: symbol,
        data: response.data.data,
        timestamp: new Date().toISOString()
      }
    }
    return null
  } catch (err) {
    console.error('Failed to fetch market data via REST:', err)
    return null
  }
}

export function useWebSocket(symbol: string = 'SPY') {
  const [data, setData] = useState<WebSocketData | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [usingRestFallback, setUsingRestFallback] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>()
  const pollingIntervalRef = useRef<NodeJS.Timeout>()
  const wsFailCountRef = useRef(0)

  // REST API polling fallback
  const startPolling = useCallback(() => {
    if (pollingIntervalRef.current) return // Already polling

    console.log('Starting REST API polling fallback for market data...')
    setUsingRestFallback(true)

    // Immediate fetch
    fetchMarketData(symbol).then(d => {
      if (d) {
        setData(d)
        setIsConnected(true)
        setError(null)
      }
    })

    // Poll every 30 seconds (matches WebSocket interval)
    pollingIntervalRef.current = setInterval(async () => {
      const d = await fetchMarketData(symbol)
      if (d) {
        setData(d)
        setIsConnected(true)
      }
    }, 30000)
  }, [symbol])

  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = undefined
      setUsingRestFallback(false)
    }
  }, [])

  const connect = useCallback(() => {
    try {
      const ws = createWebSocket(symbol)

      ws.onopen = () => {
        console.log('WebSocket connected')
        setIsConnected(true)
        setError(null)
        wsFailCountRef.current = 0
        stopPolling() // Stop REST polling if WS connects
      }

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          setData(message)
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err)
        }
      }

      ws.onerror = (event) => {
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
        console.log('WebSocket disconnected')
        setIsConnected(false)

        // Start REST polling immediately on close
        if (!pollingIntervalRef.current) {
          startPolling()
        }

        // Still try to reconnect WebSocket in background
        reconnectTimeoutRef.current = setTimeout(() => {
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
  }, [symbol, startPolling, stopPolling])

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

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [connect, disconnect])

  return { data, isConnected, error, usingRestFallback, reconnect: connect }
}
