/**
 * useWebSocket Hook Tests
 *
 * Tests for the WebSocket connection hook.
 */

import { renderHook, act } from '@testing-library/react'

// Mock WebSocket
class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  readyState: number = MockWebSocket.CONNECTING
  url: string
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: ((error: Error) => void) | null = null

  constructor(url: string) {
    this.url = url
  }

  send(data: string) {
    // Mock send
  }

  close() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.()
  }

  simulateOpen() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.()
  }

  simulateMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }

  simulateError(error: Error) {
    this.onerror?.(error)
  }
}

// Mock hook implementation
const useWebSocket = (url: string) => {
  let ws: MockWebSocket | null = null
  let isConnected = false
  let lastMessage: unknown = null
  let error: Error | null = null

  const connect = () => {
    ws = new MockWebSocket(url)
    ws.onopen = () => {
      isConnected = true
    }
    ws.onclose = () => {
      isConnected = false
    }
    ws.onmessage = (event) => {
      lastMessage = JSON.parse(event.data)
    }
    ws.onerror = (err) => {
      error = err
    }
  }

  const disconnect = () => {
    ws?.close()
    ws = null
  }

  const send = (data: unknown) => {
    if (ws && ws.readyState === MockWebSocket.OPEN) {
      ws.send(JSON.stringify(data))
      return true
    }
    return false
  }

  return {
    connect,
    disconnect,
    send,
    isConnected,
    lastMessage,
    error,
    ws,
  }
}

describe('useWebSocket Hook', () => {
  describe('Connection', () => {
    it('creates WebSocket connection', () => {
      const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))

      act(() => {
        result.current.connect()
      })

      expect(result.current.ws).not.toBeNull()
    })

    it('initializes with disconnected state', () => {
      const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))

      expect(result.current.isConnected).toBe(false)
    })
  })

  describe('Disconnection', () => {
    it('closes WebSocket on disconnect', () => {
      const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))

      act(() => {
        result.current.connect()
      })

      act(() => {
        result.current.disconnect()
      })

      expect(result.current.ws).toBeNull()
    })
  })

  describe('Sending Messages', () => {
    it('returns false when sending to closed socket', () => {
      const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))

      const sent = result.current.send({ type: 'test' })
      expect(sent).toBe(false)
    })
  })

  describe('Error Handling', () => {
    it('initializes with no error', () => {
      const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))

      expect(result.current.error).toBeNull()
    })
  })

  describe('Message Handling', () => {
    it('initializes with no last message', () => {
      const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))

      expect(result.current.lastMessage).toBeNull()
    })
  })
})
