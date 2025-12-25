/**
 * useDataCache Hook Tests
 *
 * Tests for the data caching hook.
 */

import { renderHook, act } from '@testing-library/react'

// Mock the hook
const mockCache = new Map<string, { data: unknown; timestamp: number }>()

const useDataCache = (key: string, fetchFn: () => Promise<unknown>, ttl: number = 60000) => {
  const getCached = () => {
    const cached = mockCache.get(key)
    if (cached && Date.now() - cached.timestamp < ttl) {
      return cached.data
    }
    return null
  }

  const setCache = (data: unknown) => {
    mockCache.set(key, { data, timestamp: Date.now() })
  }

  const invalidate = () => {
    mockCache.delete(key)
  }

  const refresh = async () => {
    const data = await fetchFn()
    setCache(data)
    return data
  }

  return {
    data: getCached(),
    setCache,
    invalidate,
    refresh,
    isCached: getCached() !== null,
  }
}

describe('useDataCache Hook', () => {
  beforeEach(() => {
    mockCache.clear()
  })

  describe('Initialization', () => {
    it('returns null data initially', () => {
      const { result } = renderHook(() =>
        useDataCache('test-key', () => Promise.resolve({ value: 'test' }))
      )

      expect(result.current.data).toBeNull()
      expect(result.current.isCached).toBe(false)
    })
  })

  describe('Caching', () => {
    it('caches data after setting', () => {
      const { result } = renderHook(() =>
        useDataCache('test-key', () => Promise.resolve({ value: 'test' }))
      )

      act(() => {
        result.current.setCache({ value: 'cached' })
      })

      expect(result.current.isCached).toBe(true)
    })

    it('returns cached data when available', () => {
      mockCache.set('existing-key', { data: { value: 'existing' }, timestamp: Date.now() })

      const { result } = renderHook(() =>
        useDataCache('existing-key', () => Promise.resolve({ value: 'new' }))
      )

      expect(result.current.data).toEqual({ value: 'existing' })
    })
  })

  describe('Invalidation', () => {
    it('clears cache on invalidate', () => {
      mockCache.set('test-key', { data: { value: 'cached' }, timestamp: Date.now() })

      const { result } = renderHook(() =>
        useDataCache('test-key', () => Promise.resolve({ value: 'test' }))
      )

      act(() => {
        result.current.invalidate()
      })

      expect(result.current.isCached).toBe(false)
    })
  })

  describe('Refresh', () => {
    it('refreshes data from fetch function', async () => {
      const { result } = renderHook(() =>
        useDataCache('test-key', () => Promise.resolve({ value: 'refreshed' }))
      )

      let refreshedData: unknown
      await act(async () => {
        refreshedData = await result.current.refresh()
      })

      expect(refreshedData).toEqual({ value: 'refreshed' })
    })
  })

  describe('TTL', () => {
    it('returns null for expired cache', () => {
      // Set cache with old timestamp
      mockCache.set('expired-key', {
        data: { value: 'old' },
        timestamp: Date.now() - 120000  // 2 minutes ago
      })

      const { result } = renderHook(() =>
        useDataCache('expired-key', () => Promise.resolve({ value: 'new' }), 60000)
      )

      expect(result.current.data).toBeNull()
      expect(result.current.isCached).toBe(false)
    })
  })
})
