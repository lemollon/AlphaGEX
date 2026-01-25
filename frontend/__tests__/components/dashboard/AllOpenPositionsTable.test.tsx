/**
 * AllOpenPositionsTable Component Tests
 *
 * Tests for the consolidated open positions table across all trading bots.
 */

import React from 'react'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import { SWRConfig } from 'swr'

// Mock fetch globally
const mockFetch = jest.fn()
global.fetch = mockFetch

// Mock position data
const mockAresPositions = {
  success: true,
  data: [
    {
      position_id: 'ARES-001',
      spread_type: 'IRON_CONDOR',
      ticker: 'SPY',
      short_call_strike: 590,
      short_put_strike: 580,
      contracts: 1,
      entry_credit: 1.25,
      unrealized_pnl: 50,
      return_pct: 40,
      status: 'open',
      open_time: '2025-01-25T09:30:00',
      underlying_at_entry: 585,
    }
  ]
}

const mockTitanPositions = {
  success: true,
  data: {
    open_positions: [
      {
        position_id: 'TITAN-001',
        spread_type: 'IRON_CONDOR',
        ticker: 'SPX',
        short_call_strike: 5900,
        short_put_strike: 5800,
        contracts: 2,
        entry_credit: 5.50,
        unrealized_pnl: -100,
        return_pct: -18,
        status: 'open',
        open_time: '2025-01-25T10:15:00',
        underlying_at_entry: 5850,
      }
    ],
    closed_positions: []
  }
}

const mockEmptyPositions = {
  success: true,
  data: []
}

describe('AllOpenPositionsTable Component', () => {
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
    it('renders the table header', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockEmptyPositions),
      })

      const AllOpenPositionsTable = require('../../../src/components/dashboard/AllOpenPositionsTable').default
      renderWithSWR(<AllOpenPositionsTable />)

      expect(screen.getByText('All Open Positions')).toBeInTheDocument()
    })

    it('shows position count in subtitle', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresPositions),
      })

      const AllOpenPositionsTable = require('../../../src/components/dashboard/AllOpenPositionsTable').default
      renderWithSWR(<AllOpenPositionsTable />)

      await waitFor(() => {
        expect(screen.getByText(/positions across all bots/)).toBeInTheDocument()
      })
    })
  })

  describe('Empty State', () => {
    it('displays empty state message when no positions', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockEmptyPositions),
      })

      const AllOpenPositionsTable = require('../../../src/components/dashboard/AllOpenPositionsTable').default
      renderWithSWR(<AllOpenPositionsTable />)

      await waitFor(() => {
        expect(screen.getByText('No open positions')).toBeInTheDocument()
      })
    })

    it('shows helpful hint in empty state', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockEmptyPositions),
      })

      const AllOpenPositionsTable = require('../../../src/components/dashboard/AllOpenPositionsTable').default
      renderWithSWR(<AllOpenPositionsTable />)

      await waitFor(() => {
        expect(screen.getByText(/Positions will appear here when bots enter trades/)).toBeInTheDocument()
      })
    })
  })

  describe('Table Columns', () => {
    it('displays Bot column header', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresPositions),
      })

      const AllOpenPositionsTable = require('../../../src/components/dashboard/AllOpenPositionsTable').default
      renderWithSWR(<AllOpenPositionsTable />)

      await waitFor(() => {
        expect(screen.getByText('Bot')).toBeInTheDocument()
      })
    })

    it('displays Position column header', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresPositions),
      })

      const AllOpenPositionsTable = require('../../../src/components/dashboard/AllOpenPositionsTable').default
      renderWithSWR(<AllOpenPositionsTable />)

      await waitFor(() => {
        expect(screen.getByText('Position')).toBeInTheDocument()
      })
    })

    it('displays P&L column header', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresPositions),
      })

      const AllOpenPositionsTable = require('../../../src/components/dashboard/AllOpenPositionsTable').default
      renderWithSWR(<AllOpenPositionsTable />)

      await waitFor(() => {
        expect(screen.getByText('P&L')).toBeInTheDocument()
      })
    })

    it('displays Entry column header', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresPositions),
      })

      const AllOpenPositionsTable = require('../../../src/components/dashboard/AllOpenPositionsTable').default
      renderWithSWR(<AllOpenPositionsTable />)

      await waitFor(() => {
        expect(screen.getByText('Entry')).toBeInTheDocument()
      })
    })

    it('displays Opened column header', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresPositions),
      })

      const AllOpenPositionsTable = require('../../../src/components/dashboard/AllOpenPositionsTable').default
      renderWithSWR(<AllOpenPositionsTable />)

      await waitFor(() => {
        expect(screen.getByText('Opened')).toBeInTheDocument()
      })
    })
  })

  describe('Sorting', () => {
    it('allows clicking Bot column to sort', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresPositions),
      })

      const AllOpenPositionsTable = require('../../../src/components/dashboard/AllOpenPositionsTable').default
      renderWithSWR(<AllOpenPositionsTable />)

      await waitFor(() => {
        const botHeader = screen.getByText('Bot')
        expect(botHeader).toBeInTheDocument()
        fireEvent.click(botHeader)
      })
    })

    it('allows clicking P&L column to sort', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresPositions),
      })

      const AllOpenPositionsTable = require('../../../src/components/dashboard/AllOpenPositionsTable').default
      renderWithSWR(<AllOpenPositionsTable />)

      await waitFor(() => {
        const pnlHeader = screen.getByText('P&L')
        expect(pnlHeader).toBeInTheDocument()
        fireEvent.click(pnlHeader)
      })
    })
  })

  describe('Error Handling', () => {
    it('handles API errors gracefully', async () => {
      mockFetch.mockRejectedValue(new Error('API Error'))

      const AllOpenPositionsTable = require('../../../src/components/dashboard/AllOpenPositionsTable').default
      renderWithSWR(<AllOpenPositionsTable />)

      await waitFor(() => {
        expect(screen.getByText('All Open Positions')).toBeInTheDocument()
      })
    })
  })

  describe('Position Display', () => {
    it('displays ticker symbol in position row', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresPositions),
      })

      const AllOpenPositionsTable = require('../../../src/components/dashboard/AllOpenPositionsTable').default
      renderWithSWR(<AllOpenPositionsTable />)

      await waitFor(() => {
        // Use getAllByText since SPY appears in multiple places (position ticker + strikes)
        const spyElements = screen.getAllByText(/SPY/)
        expect(spyElements.length).toBeGreaterThan(0)
      })
    })
  })
})
