/**
 * TodaysActivityFeed Component Tests
 *
 * Tests for the today's trading activity feed component.
 */

import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import { SWRConfig } from 'swr'

// Mock fetch globally
const mockFetch = jest.fn()
global.fetch = mockFetch

// Get today's date in the format the component expects
const getTodayISO = () => {
  const now = new Date()
  return now.toISOString().split('T')[0]
}

const today = getTodayISO()

// Mock positions with today's activity
const mockPositionsWithTodayActivity = {
  success: true,
  data: [
    {
      position_id: 'FORTRESS-TODAY-001',
      spread_type: 'IRON_CONDOR',
      ticker: 'SPY',
      contracts: 1,
      realized_pnl: 125,
      return_pct: 50,
      status: 'closed',
      open_time: `${today}T09:30:00`,
      close_time: `${today}T14:30:00`,
      close_reason: 'PROFIT_TARGET',
    },
    {
      position_id: 'FORTRESS-TODAY-002',
      spread_type: 'IRON_CONDOR',
      ticker: 'SPY',
      contracts: 1,
      status: 'open',
      open_time: `${today}T10:00:00`,
    }
  ]
}

// Mock positions with no today activity
const mockPositionsNoTodayActivity = {
  success: true,
  data: [
    {
      position_id: 'FORTRESS-OLD-001',
      spread_type: 'IRON_CONDOR',
      ticker: 'SPY',
      status: 'closed',
      open_time: '2025-01-20T09:30:00',
      close_time: '2025-01-20T14:30:00',
    }
  ]
}

const mockEmptyPositions = {
  success: true,
  data: []
}

describe('TodaysActivityFeed Component', () => {
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

  describe('Rendering', () => {
    it('renders the activity feed header', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockEmptyPositions),
      })

      const TodaysActivityFeed = require('../../../src/components/dashboard/TodaysActivityFeed').default
      renderWithSWR(<TodaysActivityFeed />)

      expect(screen.getByText("Today's Trading Activity")).toBeInTheDocument()
    })

    it('shows entry and exit count in subtitle', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockPositionsWithTodayActivity),
      })

      const TodaysActivityFeed = require('../../../src/components/dashboard/TodaysActivityFeed').default
      renderWithSWR(<TodaysActivityFeed />)

      await waitFor(() => {
        expect(screen.getByText(/entries/)).toBeInTheDocument()
        expect(screen.getByText(/exits/)).toBeInTheDocument()
      })
    })
  })

  describe('Empty State', () => {
    it('displays empty state when no activity today', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockEmptyPositions),
      })

      const TodaysActivityFeed = require('../../../src/components/dashboard/TodaysActivityFeed').default
      renderWithSWR(<TodaysActivityFeed />)

      await waitFor(() => {
        expect(screen.getByText('No trading activity today')).toBeInTheDocument()
      })
    })

    it('shows helpful hint in empty state', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockEmptyPositions),
      })

      const TodaysActivityFeed = require('../../../src/components/dashboard/TodaysActivityFeed').default
      renderWithSWR(<TodaysActivityFeed />)

      await waitFor(() => {
        expect(screen.getByText(/Trades will appear here as bots enter\/exit positions/)).toBeInTheDocument()
      })
    })

    it('shows empty state for old positions only', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockPositionsNoTodayActivity),
      })

      const TodaysActivityFeed = require('../../../src/components/dashboard/TodaysActivityFeed').default
      renderWithSWR(<TodaysActivityFeed />)

      await waitFor(() => {
        expect(screen.getByText('No trading activity today')).toBeInTheDocument()
      })
    })
  })

  describe('Activity Display', () => {
    it('displays ticker symbol in activity item', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockPositionsWithTodayActivity),
      })

      const TodaysActivityFeed = require('../../../src/components/dashboard/TodaysActivityFeed').default
      renderWithSWR(<TodaysActivityFeed />)

      await waitFor(() => {
        expect(screen.getAllByText(/SPY/).length).toBeGreaterThan(0)
      })
    })
  })

  describe('Summary Stats', () => {
    it('displays total P&L for exits', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockPositionsWithTodayActivity),
      })

      const TodaysActivityFeed = require('../../../src/components/dashboard/TodaysActivityFeed').default
      renderWithSWR(<TodaysActivityFeed />)

      await waitFor(() => {
        // Should show P&L summary in subtitle
        expect(screen.getByText(/P&L/)).toBeInTheDocument()
      })
    })
  })

  describe('Error Handling', () => {
    it('handles API errors gracefully', async () => {
      mockFetch.mockRejectedValue(new Error('API Error'))

      const TodaysActivityFeed = require('../../../src/components/dashboard/TodaysActivityFeed').default
      renderWithSWR(<TodaysActivityFeed />)

      await waitFor(() => {
        expect(screen.getByText("Today's Trading Activity")).toBeInTheDocument()
      })
    })

    it('handles malformed response', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: false }),
      })

      const TodaysActivityFeed = require('../../../src/components/dashboard/TodaysActivityFeed').default
      renderWithSWR(<TodaysActivityFeed />)

      await waitFor(() => {
        expect(screen.getByText("Today's Trading Activity")).toBeInTheDocument()
      })
    })
  })

  describe('Time Display', () => {
    it('displays time in Central Time', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockPositionsWithTodayActivity),
      })

      const TodaysActivityFeed = require('../../../src/components/dashboard/TodaysActivityFeed').default
      renderWithSWR(<TodaysActivityFeed />)

      await waitFor(() => {
        // Should show CT indicator
        expect(screen.getAllByText('CT').length).toBeGreaterThan(0)
      })
    })
  })
})
