/**
 * Tests for the Tradier API circuit breaker.
 *
 * The circuit breaker prevents hammering Tradier when it's down:
 *   - After CIRCUIT_BREAKER_THRESHOLD consecutive failures → circuit opens
 *   - While open → tradierGet returns null immediately (no fetch)
 *   - After CIRCUIT_BREAKER_COOLDOWN_MS → half-open, one retry allowed
 *   - On success → circuit closes, counter resets
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

// Mock db module (tradier.ts imports it)
vi.mock('../db', () => ({
  query: vi.fn().mockResolvedValue([]),
  dbQuery: vi.fn().mockResolvedValue([]),
  dbExecute: vi.fn().mockResolvedValue(1),
  sharedTable: (name: string) => name,
}))

import { _testing } from '../tradier'

const {
  recordTradierSuccess,
  recordTradierFailure,
  isCircuitOpen,
  CIRCUIT_BREAKER_THRESHOLD,
  CIRCUIT_BREAKER_COOLDOWN_MS,
} = _testing

beforeEach(() => {
  // Reset circuit breaker state
  _testing._circuitOpenUntil = 0
  _testing._consecutiveFailures = 0
})

describe('Circuit breaker state', () => {
  it('starts closed', () => {
    expect(isCircuitOpen()).toBe(false)
  })

  it('stays closed after fewer than THRESHOLD failures', () => {
    for (let i = 0; i < CIRCUIT_BREAKER_THRESHOLD - 1; i++) {
      recordTradierFailure()
    }
    expect(isCircuitOpen()).toBe(false)
    expect(_testing._consecutiveFailures).toBe(CIRCUIT_BREAKER_THRESHOLD - 1)
  })

  it('opens after THRESHOLD consecutive failures', () => {
    for (let i = 0; i < CIRCUIT_BREAKER_THRESHOLD; i++) {
      recordTradierFailure()
    }
    expect(isCircuitOpen()).toBe(true)
    expect(_testing._consecutiveFailures).toBe(CIRCUIT_BREAKER_THRESHOLD)
  })

  it('resets on success', () => {
    // Trip the breaker
    for (let i = 0; i < CIRCUIT_BREAKER_THRESHOLD; i++) {
      recordTradierFailure()
    }
    expect(isCircuitOpen()).toBe(true)

    // Reset via success
    recordTradierSuccess()
    expect(isCircuitOpen()).toBe(false)
    expect(_testing._consecutiveFailures).toBe(0)
    expect(_testing._circuitOpenUntil).toBe(0)
  })

  it('half-opens after cooldown expires', () => {
    // Trip the breaker
    for (let i = 0; i < CIRCUIT_BREAKER_THRESHOLD; i++) {
      recordTradierFailure()
    }
    expect(isCircuitOpen()).toBe(true)

    // Simulate cooldown expiry by setting openUntil in the past
    _testing._circuitOpenUntil = Date.now() - 1000
    expect(isCircuitOpen()).toBe(false) // half-open: allows one retry
    // Counter should be reset after half-open
    expect(_testing._consecutiveFailures).toBe(0)
  })

  it('stays open during cooldown period', () => {
    // Trip the breaker
    for (let i = 0; i < CIRCUIT_BREAKER_THRESHOLD; i++) {
      recordTradierFailure()
    }
    // openUntil is set in the future
    expect(_testing._circuitOpenUntil).toBeGreaterThan(Date.now())
    expect(isCircuitOpen()).toBe(true)
  })

  it('THRESHOLD is 5', () => {
    expect(CIRCUIT_BREAKER_THRESHOLD).toBe(5)
  })

  it('COOLDOWN is 5 minutes', () => {
    expect(CIRCUIT_BREAKER_COOLDOWN_MS).toBe(5 * 60 * 1000)
  })
})
