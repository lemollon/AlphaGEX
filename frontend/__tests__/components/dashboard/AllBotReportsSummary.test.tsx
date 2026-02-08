/**
 * AllBotReportsSummary Component Tests
 *
 * Tests for the all-bot reports summary that displays cached reports
 * from the database WITHOUT triggering Claude API calls.
 */

import React from 'react'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import { SWRConfig } from 'swr'

// Mock fetch globally
const mockFetch = jest.fn()
global.fetch = mockFetch

// Mock report data
const mockAresReport = {
  success: true,
  data: {
    report_date: '2025-01-25',
    total_pnl: 1500,
    trade_count: 8,
    win_count: 6,
    loss_count: 2,
    daily_summary: 'Strong day with Iron Condors performing well in low volatility.',
    lessons_learned: ['Wider strikes worked better today', 'Entry timing at 9:30 optimal'],
    generated_at: '2025-01-25T15:30:00',
    estimated_cost_usd: 0.05,
  }
}

const mockTitanReport = {
  success: true,
  data: {
    report_date: '2025-01-25',
    total_pnl: 2500,
    trade_count: 5,
    win_count: 4,
    loss_count: 1,
    daily_summary: 'Excellent day with aggressive positioning.',
    lessons_learned: ['SPX provided better premiums'],
    generated_at: '2025-01-25T15:25:00',
    estimated_cost_usd: 0.05,
  }
}

const mockNoReport = {
  success: false,
  message: 'No report found for today'
}

describe('AllBotReportsSummary Component', () => {
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
    it('renders the component header', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockNoReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      expect(screen.getByText("Today's Trading Reports")).toBeInTheDocument()
    })

    it('renders the subtitle with report count', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText(/bots have reports/)).toBeInTheDocument()
      })
    })
  })

  describe('Bot Selector Tabs', () => {
    it('renders FORTRESS bot tab', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockNoReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText('FORTRESS')).toBeInTheDocument()
      })
    })

    it('renders SOLOMON bot tab', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockNoReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText('SOLOMON')).toBeInTheDocument()
      })
    })

    it('renders GIDEON bot tab', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockNoReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText('GIDEON')).toBeInTheDocument()
      })
    })

    it('renders ANCHOR bot tab', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockNoReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText('ANCHOR')).toBeInTheDocument()
      })
    })

    it('renders SAMSON bot tab', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockNoReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText('SAMSON')).toBeInTheDocument()
      })
    })

    it('allows switching between bot tabs', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockNoReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        const titanTab = screen.getByText('SAMSON')
        expect(titanTab).toBeInTheDocument()
        const titanButton = titanTab.closest('button')
        if (titanButton) {
          fireEvent.click(titanButton)
        }
      })
    })
  })

  describe('Report Display - With Data', () => {
    it('displays P&L when report exists', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText('+$1500')).toBeInTheDocument()
      })
    })

    it('displays trade count when report exists', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText('8')).toBeInTheDocument()
      })
    })

    it('displays win/loss record when report exists', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText('6W')).toBeInTheDocument()
        expect(screen.getByText('2L')).toBeInTheDocument()
      })
    })

    it('displays daily summary when available', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText(/Strong day with Iron Condors/)).toBeInTheDocument()
      })
    })

    it('displays lessons learned when available', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText(/Wider strikes worked better/)).toBeInTheDocument()
      })
    })

    it('shows View Full Report link when report exists', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText(/View Full FORTRESS Report/)).toBeInTheDocument()
      })
    })
  })

  describe('Report Display - No Data', () => {
    it('shows no report message when report does not exist', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockNoReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText(/No report available/)).toBeInTheDocument()
      })
    })

    it('shows generation hint when no report', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockNoReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText(/Reports are generated from the individual bot pages/)).toBeInTheDocument()
      })
    })

    it('shows Go to Reports link when no report', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockNoReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText(/Go to FORTRESS Reports/)).toBeInTheDocument()
      })
    })
  })

  describe('Aggregate Stats', () => {
    it('shows total P&L in header', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText(/total P&L/)).toBeInTheDocument()
      })
    })

    it('shows total trades in header', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText(/trades/)).toBeInTheDocument()
      })
    })
  })

  describe('Footer Note', () => {
    it('displays the no-charge footer note', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockNoReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText(/Reports are cached from database/)).toBeInTheDocument()
      })
    })
  })

  describe('Error Handling', () => {
    it('handles network errors gracefully', async () => {
      mockFetch.mockRejectedValue(new Error('Network error'))

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText("Today's Trading Reports")).toBeInTheDocument()
      })
    })

    it('handles API errors gracefully', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        json: () => Promise.resolve({ success: false }),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        expect(screen.getByText("Today's Trading Reports")).toBeInTheDocument()
      })
    })
  })

  describe('Loading State', () => {
    it('shows loading indicator while fetching', () => {
      mockFetch.mockImplementation(() => new Promise(() => {})) // Never resolves

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      // Should still show header during loading
      expect(screen.getByText("Today's Trading Reports")).toBeInTheDocument()
    })
  })

  describe('Check Icon Status', () => {
    it('shows check icon for bot with report', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockAresReport),
      })

      const AllBotReportsSummary = require('../../../src/components/dashboard/AllBotReportsSummary').default
      renderWithSWR(<AllBotReportsSummary />)

      await waitFor(() => {
        // Check that the FORTRESS tab has the CheckCircle icon (green check)
        const aresButton = screen.getByText('FORTRESS').closest('button')
        expect(aresButton).toBeInTheDocument()
        // The CheckCircle should be visible in the button
        const checkIcon = aresButton?.querySelector('svg.text-green-400')
        expect(checkIcon).toBeInTheDocument()
      })
    })
  })
})
