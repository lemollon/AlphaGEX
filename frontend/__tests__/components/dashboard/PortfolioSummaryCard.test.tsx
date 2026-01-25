/**
 * PortfolioSummaryCard Component Tests
 *
 * Tests for the portfolio summary card that aggregates metrics across all trading bots.
 */

import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import { SWRConfig } from 'swr'

// Mock fetch globally
const mockFetch = jest.fn()
global.fetch = mockFetch

// Mock data for bot status responses
const mockAresStatus = {
  success: true,
  data: {
    is_active: true,
    open_positions: 2,
    today_pnl: 150,
    total_pnl: 2500,
    realized_pnl: 2500,
    unrealized_pnl: 150,
    win_rate: 65,
    total_trades: 45,
    winning_trades: 29,
  }
}

const mockTitanStatus = {
  success: true,
  data: {
    is_active: true,
    open_positions: 1,
    today_pnl: 300,
    total_pnl: 5000,
    realized_pnl: 5000,
    unrealized_pnl: 200,
    win_rate: 70,
    total_trades: 30,
    winning_trades: 21,
  }
}

const mockEmptyStatus = {
  success: true,
  data: {
    is_active: false,
    open_positions: 0,
    today_pnl: 0,
    total_pnl: 0,
  }
}

describe('PortfolioSummaryCard Component', () => {
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

  describe('Data Display', () => {
    it('renders the portfolio summary header', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockEmptyStatus),
      })

      const PortfolioSummaryCard = require('../../../src/components/dashboard/PortfolioSummaryCard').default
      renderWithSWR(<PortfolioSummaryCard />)

      expect(screen.getByText('Portfolio Summary')).toBeInTheDocument()
      expect(screen.getByText('Aggregated across all 5 bots')).toBeInTheDocument()
    })

    it('displays total equity section', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresStatus),
      })

      const PortfolioSummaryCard = require('../../../src/components/dashboard/PortfolioSummaryCard').default
      renderWithSWR(<PortfolioSummaryCard />)

      await waitFor(() => {
        expect(screen.getByText('Total Equity')).toBeInTheDocument()
      })
    })

    it('displays total P&L section', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresStatus),
      })

      const PortfolioSummaryCard = require('../../../src/components/dashboard/PortfolioSummaryCard').default
      renderWithSWR(<PortfolioSummaryCard />)

      await waitFor(() => {
        expect(screen.getByText('Total P&L')).toBeInTheDocument()
      })
    })

    it('displays win rate section', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresStatus),
      })

      const PortfolioSummaryCard = require('../../../src/components/dashboard/PortfolioSummaryCard').default
      renderWithSWR(<PortfolioSummaryCard />)

      await waitFor(() => {
        expect(screen.getByText('Win Rate')).toBeInTheDocument()
      })
    })
  })

  describe('Loading State', () => {
    it('shows loading indicator while fetching', () => {
      mockFetch.mockImplementation(() => new Promise(() => {})) // Never resolves

      const PortfolioSummaryCard = require('../../../src/components/dashboard/PortfolioSummaryCard').default
      renderWithSWR(<PortfolioSummaryCard />)

      // Component should still render header while loading
      expect(screen.getByText('Portfolio Summary')).toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('handles API errors gracefully', async () => {
      mockFetch.mockRejectedValue(new Error('API Error'))

      const PortfolioSummaryCard = require('../../../src/components/dashboard/PortfolioSummaryCard').default
      renderWithSWR(<PortfolioSummaryCard />)

      // Should still render the component structure
      await waitFor(() => {
        expect(screen.getByText('Portfolio Summary')).toBeInTheDocument()
      })
    })

    it('handles empty response', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      })

      const PortfolioSummaryCard = require('../../../src/components/dashboard/PortfolioSummaryCard').default
      renderWithSWR(<PortfolioSummaryCard />)

      await waitFor(() => {
        expect(screen.getByText('Portfolio Summary')).toBeInTheDocument()
      })
    })
  })

  describe('Active Bot Count', () => {
    it('displays active bot count', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresStatus),
      })

      const PortfolioSummaryCard = require('../../../src/components/dashboard/PortfolioSummaryCard').default
      renderWithSWR(<PortfolioSummaryCard />)

      await waitFor(() => {
        // Should show "X/5 bots active"
        expect(screen.getByText(/\/5 bots active/)).toBeInTheDocument()
      })
    })
  })

  describe('Secondary Stats', () => {
    it('displays realized P&L section', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresStatus),
      })

      const PortfolioSummaryCard = require('../../../src/components/dashboard/PortfolioSummaryCard').default
      renderWithSWR(<PortfolioSummaryCard />)

      await waitFor(() => {
        expect(screen.getByText('Realized')).toBeInTheDocument()
      })
    })

    it('displays unrealized P&L section', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresStatus),
      })

      const PortfolioSummaryCard = require('../../../src/components/dashboard/PortfolioSummaryCard').default
      renderWithSWR(<PortfolioSummaryCard />)

      await waitFor(() => {
        expect(screen.getByText('Unrealized')).toBeInTheDocument()
      })
    })

    it('displays open positions count', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresStatus),
      })

      const PortfolioSummaryCard = require('../../../src/components/dashboard/PortfolioSummaryCard').default
      renderWithSWR(<PortfolioSummaryCard />)

      await waitFor(() => {
        expect(screen.getByText('Open Positions')).toBeInTheDocument()
      })
    })
  })
})
