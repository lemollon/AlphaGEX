import { useEffect, useState, useCallback, useRef } from 'react'
import { createWebSocket, apiClient } from '@/lib/api'
import { logger } from '@/lib/logger'

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
    const response = await apiClient.getGEX(symbol)
    if (response?.data?.success && response.data.data) {
      return {
        type: 'market_update',
        symbol: symbol,
        data: response.data.data,
        timestamp: new Date().toISOString()
      }
    }
    if (!response?.data?.success) {
      logger.warn(`GEX API returned unsuccessful response for ${symbol}:`, response?.data?.error || 'Unknown error')
    }
    return null
  } catch (err) {
    logger.error(`Failed to fetch market data for ${symbol} via REST:`, err)
    return null
  }
}

/**
 * Bug #4 Fix: Refactored useWebSocket to avoid dependency loops
 * - Uses refs to store mutable values that don't need to trigger re-renders
 * - Only symbol changes trigger reconnection
 * - Proper cleanup on unmount
 */
export function useWebSocket(symbol: string = 'SPY') {
  const [data, setData] = useState<WebSocketData | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [usingRestFallback, setUsingRestFallback] = useState(false)

  // Use refs for mutable values that don't need to trigger re-renders
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>()
  const pollingIntervalRef = useRef<NodeJS.Timeout>()
  const wsFailCountRef = useRef(0)
  const symbolRef = useRef(symbol)
  const isCleaningUpRef = useRef(false)

  // Update symbol ref when symbol changes
  symbolRef.current = symbol

  // Stop polling function (doesn't depend on anything)
  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = undefined
      setUsingRestFallback(false)
    }
  }, [])

  // Start polling function - uses symbolRef to avoid dependency on symbol
  const startPolling = useCallback(() => {
    if (pollingIntervalRef.current) return // Already polling

    const currentSymbol = symbolRef.current
    logger.info(`Starting REST API polling fallback for ${currentSymbol}...`)
    setUsingRestFallback(true)

    // Immediate fetch
    fetchMarketData(currentSymbol).then(d => {
      if (d && symbolRef.current === currentSymbol) {
        setData(d)
        setIsConnected(true)
        setError(null)
      }
    })

    // Poll every 30 seconds (matches WebSocket interval)
    pollingIntervalRef.current = setInterval(async () => {
      const currentSym = symbolRef.current
      const d = await fetchMarketData(currentSym)
      if (d && symbolRef.current === currentSym) {
        setData(d)
        setIsConnected(true)
      }
    }, 30000)
  }, [])  // No dependencies - uses refs

  // Disconnect function
  const disconnect = useCallback(() => {
    isCleaningUpRef.current = true
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = undefined
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    stopPolling()
    isCleaningUpRef.current = false
  }, [stopPolling])

  // Connect function - uses symbolRef to avoid dependency on symbol
  const connect = useCallback(() => {
    const currentSymbol = symbolRef.current

    // Close existing connection first
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    try {
      const ws = createWebSocket(currentSymbol)

      ws.onopen = () => {
        logger.info(`WebSocket connected for ${currentSymbol}`)
        setIsConnected(true)
        setError(null)
        wsFailCountRef.current = 0
        stopPolling()
      }

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          // Only update if still for the current symbol
          if (!message.symbol || message.symbol === symbolRef.current) {
            setData(message)
          }
        } catch (err) {
          logger.error('Failed to parse WebSocket message:', err)
        }
      }

      ws.onerror = (event) => {
        logger.error('WebSocket error:', event)
        wsFailCountRef.current++
        setError('WebSocket connection error')

        // After 2 failed attempts, switch to REST polling
        if (wsFailCountRef.current >= 2) {
          logger.info('WebSocket unavailable, switching to REST API fallback')
          startPolling()
        }
      }

      ws.onclose = () => {
        // Don't do anything if we're cleaning up
        if (isCleaningUpRef.current) return

        logger.info('WebSocket disconnected')
        setIsConnected(false)

        // Start REST polling immediately on close
        if (!pollingIntervalRef.current) {
          startPolling()
        }

        // Still try to reconnect WebSocket in background
        reconnectTimeoutRef.current = setTimeout(() => {
          if (!isCleaningUpRef.current) {
            logger.info('Attempting WebSocket reconnect...')
            connect()
          }
        }, 30000)
      }

      wsRef.current = ws
    } catch (err) {
      logger.error('Failed to create WebSocket:', err)
      setError('Failed to establish WebSocket connection')
      wsFailCountRef.current++

      // Fall back to REST polling
      if (wsFailCountRef.current >= 2) {
        startPolling()
      }
    }
  }, [startPolling, stopPolling])  // Only depends on stable functions

  // Bug #4 Fix: Only reconnect when symbol changes
  useEffect(() => {
    // Reset fail count when symbol changes
    wsFailCountRef.current = 0

    connect()

    return () => {
      disconnect()
    }
  }, [symbol, connect, disconnect])  // Now safe because connect/disconnect are stable

  return { data, isConnected, error, usingRestFallback, reconnect: connect }
}
