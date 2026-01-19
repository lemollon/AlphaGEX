/**
 * Custom debounce hooks for ARGUS and HYPERION
 *
 * Provides debounced values and callbacks to reduce UI reactivity
 * and prevent excessive re-renders during rapid data updates.
 */

import { useState, useEffect, useCallback, useRef } from 'react'

/**
 * Debounce a value - returns the value only after it hasn't changed for `delay` ms
 *
 * @param value The value to debounce
 * @param delay Delay in milliseconds (default: 150ms)
 * @returns The debounced value
 *
 * @example
 * const debouncedSearchTerm = useDebounce(searchTerm, 300)
 */
export function useDebounce<T>(value: T, delay: number = 150): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)

    return () => {
      clearTimeout(timer)
    }
  }, [value, delay])

  return debouncedValue
}

/**
 * Debounce a callback function
 *
 * @param callback The callback to debounce
 * @param delay Delay in milliseconds (default: 150ms)
 * @returns A debounced version of the callback
 *
 * @example
 * const debouncedSave = useDebouncedCallback(() => saveData(), 500)
 */
export function useDebouncedCallback<T extends (...args: any[]) => any>(
  callback: T,
  delay: number = 150
): T {
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)
  const callbackRef = useRef(callback)

  // Keep callback ref up to date
  useEffect(() => {
    callbackRef.current = callback
  }, [callback])

  const debouncedCallback = useCallback(
    (...args: Parameters<T>) => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }

      timeoutRef.current = setTimeout(() => {
        callbackRef.current(...args)
      }, delay)
    },
    [delay]
  ) as T

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [])

  return debouncedCallback
}

/**
 * Throttle a callback - ensures it's called at most once per `delay` ms
 *
 * @param callback The callback to throttle
 * @param delay Delay in milliseconds (default: 100ms)
 * @returns A throttled version of the callback
 *
 * @example
 * const throttledScroll = useThrottledCallback(handleScroll, 100)
 */
export function useThrottledCallback<T extends (...args: any[]) => any>(
  callback: T,
  delay: number = 100
): T {
  const lastCallRef = useRef<number>(0)
  const callbackRef = useRef(callback)

  // Keep callback ref up to date
  useEffect(() => {
    callbackRef.current = callback
  }, [callback])

  const throttledCallback = useCallback(
    (...args: Parameters<T>) => {
      const now = Date.now()
      if (now - lastCallRef.current >= delay) {
        lastCallRef.current = now
        callbackRef.current(...args)
      }
    },
    [delay]
  ) as T

  return throttledCallback
}

/**
 * Stable state setter that batches rapid updates
 *
 * Updates are collected and applied in a single batch after `delay` ms of inactivity.
 * Useful for preventing UI flicker during rapid data polling.
 *
 * @param initialValue Initial state value
 * @param delay Delay in milliseconds (default: 100ms)
 * @returns [value, setValue, forceUpdate] - forceUpdate bypasses debouncing
 *
 * @example
 * const [data, setData, forceSetData] = useStableState(null, 100)
 */
export function useStableState<T>(
  initialValue: T,
  delay: number = 100
): [T, (value: T | ((prev: T) => T)) => void, (value: T) => void] {
  const [value, setValue] = useState<T>(initialValue)
  const pendingValueRef = useRef<T | null>(null)
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)

  const debouncedSetValue = useCallback(
    (newValue: T | ((prev: T) => T)) => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }

      // Store pending value
      if (typeof newValue === 'function') {
        const fn = newValue as (prev: T) => T
        pendingValueRef.current = fn(pendingValueRef.current ?? value)
      } else {
        pendingValueRef.current = newValue
      }

      timeoutRef.current = setTimeout(() => {
        if (pendingValueRef.current !== null) {
          setValue(pendingValueRef.current)
          pendingValueRef.current = null
        }
      }, delay)
    },
    [delay, value]
  )

  const forceSetValue = useCallback((newValue: T) => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
    }
    pendingValueRef.current = null
    setValue(newValue)
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [])

  return [value, debouncedSetValue, forceSetValue]
}

export default useDebounce
