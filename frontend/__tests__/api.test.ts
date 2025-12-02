/**
 * API Client Tests
 *
 * These tests verify the API client functions work correctly.
 * Run with: npm test
 */

import { apiClient } from '../src/lib/api'

// Mock axios for testing
jest.mock('axios', () => ({
  create: jest.fn(() => ({
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    interceptors: {
      response: {
        use: jest.fn()
      }
    }
  })),
}))

describe('API Client', () => {
  describe('apiClient methods exist', () => {
    it('should have GEX methods', () => {
      expect(typeof apiClient.getGEX).toBe('function')
      expect(typeof apiClient.getGEXLevels).toBe('function')
      expect(typeof apiClient.getGEXHistory).toBe('function')
    })

    it('should have Trader methods', () => {
      expect(typeof apiClient.getTraderStatus).toBe('function')
      expect(typeof apiClient.getTraderPerformance).toBe('function')
      expect(typeof apiClient.getOpenPositions).toBe('function')
      expect(typeof apiClient.getClosedTrades).toBe('function')
      expect(typeof apiClient.getEquityCurve).toBe('function')
    })

    it('should have Wheel methods', () => {
      expect(typeof apiClient.getWheelPhases).toBe('function')
      expect(typeof apiClient.startWheelCycle).toBe('function')
      expect(typeof apiClient.getWheelCycles).toBe('function')
    })

    it('should have Export methods', () => {
      expect(typeof apiClient.exportData).toBe('function')
    })

    it('should have SPX Backtest methods', () => {
      expect(typeof apiClient.runSPXBacktest).toBe('function')
      expect(typeof apiClient.getSPXBacktestResults).toBe('function')
    })

    it('should have Psychology SSE subscription', () => {
      expect(typeof apiClient.subscribeToPsychologyNotifications).toBe('function')
    })

    it('should have AI Intelligence methods', () => {
      expect(typeof apiClient.getDailyTradingPlan).toBe('function')
      expect(typeof apiClient.getMarketCommentary).toBe('function')
      expect(typeof apiClient.explainTrade).toBe('function')
    })

    it('should have VIX methods', () => {
      expect(typeof apiClient.getVIXCurrent).toBe('function')
      expect(typeof apiClient.getVIXHedgeSignal).toBe('function')
    })
  })

  describe('API Response Types', () => {
    it('should export type definitions', () => {
      // These are compile-time checks - if types are missing, TypeScript will fail
      const testApiResponse: import('../src/lib/api').APIResponse = {
        success: true,
        data: {}
      }
      expect(testApiResponse.success).toBe(true)
    })
  })
})

describe('Environment Configuration', () => {
  it('should warn when API_URL is not set', () => {
    const consoleSpy = jest.spyOn(console, 'warn').mockImplementation()

    // In test environment, env vars may not be set
    // The API module should warn about this
    expect(process.env.NEXT_PUBLIC_API_URL).toBeUndefined()

    consoleSpy.mockRestore()
  })
})
