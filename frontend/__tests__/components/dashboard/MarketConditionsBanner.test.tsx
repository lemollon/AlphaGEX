/**
 * MarketConditionsBanner Component Tests
 *
 * Tests for the market conditions banner displaying VIX, GEX, and Oracle status.
 */

import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import { SWRConfig } from 'swr'

// Mock fetch globally
const mockFetch = jest.fn()
global.fetch = mockFetch

// Mock GEX data
const mockGEXData = {
  success: true,
  data: {
    spot_price: 585.25,
    net_gex: 2500000,
    flip_point: 583.50,
    call_wall: 590,
    put_wall: 580,
    regime: 'POSITIVE',
    mm_state: 'BULLISH',
  }
}

// Mock VIX data - various regimes
const mockVIXLow = {
  success: true,
  data: { vix_spot: 12.5 }
}

const mockVIXNormal = {
  success: true,
  data: { vix_spot: 18.0 }
}

const mockVIXElevated = {
  success: true,
  data: { vix_spot: 25.0 }
}

const mockVIXHigh = {
  success: true,
  data: { vix_spot: 32.0 }
}

const mockVIXExtreme = {
  success: true,
  data: { vix_spot: 40.0 }
}

// Mock Oracle data
const mockOracleData = {
  success: true,
  status: 'healthy',
  is_trained: true,
  recommendation: 'IRON_CONDOR',
  confidence: 0.75,
}

describe('MarketConditionsBanner Component', () => {
  beforeEach(() => {
    mockFetch.mockClear()
  })

  const renderWithSWR = (component: React.ReactElement) => {
    return render(
      <SWRConfig value={{ dedupingInterval: 0, provider: () => new Map() }}>
        {component}
      </SWRConfig>
    )
  }

  const setupMockFetch = (gex = mockGEXData, vix = mockVIXNormal, oracle = mockOracleData) => {
    mockFetch.mockImplementation((url: string) => {
      if (url.includes('/api/gex/')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(gex) })
      }
      if (url.includes('/api/vix/')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(vix) })
      }
      if (url.includes('/api/oracle/')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(oracle) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
  }

  describe('VIX Regime Display', () => {
    it('displays VIX Regime label', async () => {
      setupMockFetch()

      const MarketConditionsBanner = require('../../../src/components/dashboard/MarketConditionsBanner').default
      renderWithSWR(<MarketConditionsBanner />)

      await waitFor(() => {
        expect(screen.getByText('VIX Regime')).toBeInTheDocument()
      })
    })

    it('displays LOW regime for VIX < 15', async () => {
      setupMockFetch(mockGEXData, mockVIXLow, mockOracleData)

      const MarketConditionsBanner = require('../../../src/components/dashboard/MarketConditionsBanner').default
      renderWithSWR(<MarketConditionsBanner />)

      await waitFor(() => {
        expect(screen.getByText('LOW')).toBeInTheDocument()
      })
    })

    it('displays NORMAL regime for VIX 15-22', async () => {
      setupMockFetch(mockGEXData, mockVIXNormal, mockOracleData)

      const MarketConditionsBanner = require('../../../src/components/dashboard/MarketConditionsBanner').default
      renderWithSWR(<MarketConditionsBanner />)

      await waitFor(() => {
        expect(screen.getByText('NORMAL')).toBeInTheDocument()
      })
    })

    it('displays ELEVATED regime for VIX 22-28', async () => {
      setupMockFetch(mockGEXData, mockVIXElevated, mockOracleData)

      const MarketConditionsBanner = require('../../../src/components/dashboard/MarketConditionsBanner').default
      renderWithSWR(<MarketConditionsBanner />)

      await waitFor(() => {
        expect(screen.getByText('ELEVATED')).toBeInTheDocument()
      })
    })

    it('displays HIGH regime for VIX 28-35', async () => {
      setupMockFetch(mockGEXData, mockVIXHigh, mockOracleData)

      const MarketConditionsBanner = require('../../../src/components/dashboard/MarketConditionsBanner').default
      renderWithSWR(<MarketConditionsBanner />)

      await waitFor(() => {
        expect(screen.getByText('HIGH')).toBeInTheDocument()
      })
    })

    it('displays EXTREME regime for VIX > 35', async () => {
      setupMockFetch(mockGEXData, mockVIXExtreme, mockOracleData)

      const MarketConditionsBanner = require('../../../src/components/dashboard/MarketConditionsBanner').default
      renderWithSWR(<MarketConditionsBanner />)

      await waitFor(() => {
        expect(screen.getByText('EXTREME')).toBeInTheDocument()
      })
    })
  })

  describe('GEX Regime Display', () => {
    it('displays GEX Regime label', async () => {
      setupMockFetch()

      const MarketConditionsBanner = require('../../../src/components/dashboard/MarketConditionsBanner').default
      renderWithSWR(<MarketConditionsBanner />)

      await waitFor(() => {
        expect(screen.getByText('GEX Regime')).toBeInTheDocument()
      })
    })

    it('displays POSITIVE regime with description', async () => {
      setupMockFetch()

      const MarketConditionsBanner = require('../../../src/components/dashboard/MarketConditionsBanner').default
      renderWithSWR(<MarketConditionsBanner />)

      await waitFor(() => {
        expect(screen.getByText('POSITIVE')).toBeInTheDocument()
        expect(screen.getByText('Mean reversion likely')).toBeInTheDocument()
      })
    })

    it('displays NEGATIVE regime with description', async () => {
      const negativeGEX = { ...mockGEXData, data: { ...mockGEXData.data, regime: 'NEGATIVE' } }
      setupMockFetch(negativeGEX, mockVIXNormal, mockOracleData)

      const MarketConditionsBanner = require('../../../src/components/dashboard/MarketConditionsBanner').default
      renderWithSWR(<MarketConditionsBanner />)

      await waitFor(() => {
        expect(screen.getByText('NEGATIVE')).toBeInTheDocument()
        expect(screen.getByText('Trend continuation likely')).toBeInTheDocument()
      })
    })
  })

  describe('Oracle Recommendation Display', () => {
    it('displays Oracle Says label', async () => {
      setupMockFetch()

      const MarketConditionsBanner = require('../../../src/components/dashboard/MarketConditionsBanner').default
      renderWithSWR(<MarketConditionsBanner />)

      await waitFor(() => {
        expect(screen.getByText('Oracle Says')).toBeInTheDocument()
      })
    })

    it('displays IRON CONDOR recommendation', async () => {
      setupMockFetch()

      const MarketConditionsBanner = require('../../../src/components/dashboard/MarketConditionsBanner').default
      renderWithSWR(<MarketConditionsBanner />)

      await waitFor(() => {
        expect(screen.getByText('IRON CONDOR')).toBeInTheDocument()
      })
    })

    it('displays confidence percentage', async () => {
      setupMockFetch()

      const MarketConditionsBanner = require('../../../src/components/dashboard/MarketConditionsBanner').default
      renderWithSWR(<MarketConditionsBanner />)

      await waitFor(() => {
        expect(screen.getByText('75% confidence')).toBeInTheDocument()
      })
    })
  })

  describe('Key Levels Display', () => {
    it('displays Flip Point', async () => {
      setupMockFetch()

      const MarketConditionsBanner = require('../../../src/components/dashboard/MarketConditionsBanner').default
      renderWithSWR(<MarketConditionsBanner />)

      await waitFor(() => {
        expect(screen.getByText('Flip Point')).toBeInTheDocument()
      })
    })

    it('displays Call Wall', async () => {
      setupMockFetch()

      const MarketConditionsBanner = require('../../../src/components/dashboard/MarketConditionsBanner').default
      renderWithSWR(<MarketConditionsBanner />)

      await waitFor(() => {
        expect(screen.getByText('Call Wall')).toBeInTheDocument()
      })
    })

    it('displays Put Wall', async () => {
      setupMockFetch()

      const MarketConditionsBanner = require('../../../src/components/dashboard/MarketConditionsBanner').default
      renderWithSWR(<MarketConditionsBanner />)

      await waitFor(() => {
        expect(screen.getByText('Put Wall')).toBeInTheDocument()
      })
    })
  })

  describe('Error Handling', () => {
    it('handles missing GEX data gracefully', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      })

      const MarketConditionsBanner = require('../../../src/components/dashboard/MarketConditionsBanner').default
      renderWithSWR(<MarketConditionsBanner />)

      await waitFor(() => {
        expect(screen.getByText('VIX Regime')).toBeInTheDocument()
      })
    })

    it('handles API errors gracefully', async () => {
      mockFetch.mockRejectedValue(new Error('API Error'))

      const MarketConditionsBanner = require('../../../src/components/dashboard/MarketConditionsBanner').default
      renderWithSWR(<MarketConditionsBanner />)

      // Should still render structure
      await waitFor(() => {
        expect(screen.getByText('VIX Regime')).toBeInTheDocument()
      })
    })
  })
})
