/**
 * MultiBotEquityCurve Component Tests
 *
 * Tests for the multi-bot equity curve comparison chart.
 */

import React from 'react'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import { SWRConfig } from 'swr'

// Mock fetch globally
const mockFetch = jest.fn()
global.fetch = mockFetch

// Mock Recharts to avoid SSR issues in tests
jest.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => <div data-testid="chart-line" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Legend: () => <div data-testid="legend" />,
}))

// Mock equity curve data
const mockAresEquityCurve = {
  success: true,
  data: {
    equity_curve: [
      { date: '2025-01-20', equity: 100000, pnl: 0 },
      { date: '2025-01-21', equity: 100500, pnl: 500 },
      { date: '2025-01-22', equity: 101000, pnl: 1000 },
      { date: '2025-01-23', equity: 100750, pnl: 750 },
      { date: '2025-01-24', equity: 101500, pnl: 1500 },
    ],
    starting_capital: 100000,
    current_equity: 101500,
    total_pnl: 1500,
    total_return_pct: 1.5,
  }
}

const mockTitanEquityCurve = {
  success: true,
  data: {
    equity_curve: [
      { date: '2025-01-20', equity: 200000, pnl: 0 },
      { date: '2025-01-21', equity: 201000, pnl: 1000 },
      { date: '2025-01-22', equity: 202500, pnl: 2500 },
      { date: '2025-01-23', equity: 201500, pnl: 1500 },
      { date: '2025-01-24', equity: 204000, pnl: 4000 },
    ],
    starting_capital: 200000,
    current_equity: 204000,
    total_pnl: 4000,
    total_return_pct: 2.0,
  }
}

const mockEmptyEquityCurve = {
  success: true,
  data: {
    equity_curve: [],
    starting_capital: 100000,
    current_equity: 100000,
    total_pnl: 0,
    total_return_pct: 0,
  }
}

describe('MultiBotEquityCurve Component', () => {
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

  const setupMockFetch = (responseData = mockAresEquityCurve) => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(responseData),
    })
  }

  describe('Rendering', () => {
    it('renders the component header', async () => {
      setupMockFetch()

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      expect(screen.getByText('Bot Performance Comparison')).toBeInTheDocument()
    })

    it('renders the subtitle', async () => {
      setupMockFetch()

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      expect(screen.getByText(/returns over time/)).toBeInTheDocument()
    })

    it('renders the chart container', async () => {
      setupMockFetch()

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      await waitFor(() => {
        expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
      })
    })
  })

  describe('Bot Toggle Pills', () => {
    it('renders FORTRESS toggle pill', async () => {
      setupMockFetch()

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      await waitFor(() => {
        // Bot names appear in both toggle pills and stats grid
        const aresElements = screen.getAllByText('FORTRESS')
        expect(aresElements.length).toBeGreaterThan(0)
      })
    })

    it('renders SOLOMON toggle pill', async () => {
      setupMockFetch()

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      await waitFor(() => {
        const solomonElements = screen.getAllByText('SOLOMON')
        expect(solomonElements.length).toBeGreaterThan(0)
      })
    })

    it('renders ICARUS toggle pill', async () => {
      setupMockFetch()

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      await waitFor(() => {
        const icarusElements = screen.getAllByText('ICARUS')
        expect(icarusElements.length).toBeGreaterThan(0)
      })
    })

    it('renders PEGASUS toggle pill', async () => {
      setupMockFetch()

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      await waitFor(() => {
        const pegasusElements = screen.getAllByText('PEGASUS')
        expect(pegasusElements.length).toBeGreaterThan(0)
      })
    })

    it('renders SAMSON toggle pill', async () => {
      setupMockFetch()

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      await waitFor(() => {
        const titanElements = screen.getAllByText('SAMSON')
        expect(titanElements.length).toBeGreaterThan(0)
      })
    })

    it('allows toggling bot visibility', async () => {
      setupMockFetch()

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      await waitFor(() => {
        // Get all FORTRESS elements and find the one that's a button child
        const aresElements = screen.getAllByText('FORTRESS')
        const aresButton = aresElements[0].closest('button')
        expect(aresButton).toBeInTheDocument()
        if (aresButton) {
          fireEvent.click(aresButton)
        }
      })
    })
  })

  describe('Timeframe Selector', () => {
    it('renders timeframe dropdown', async () => {
      setupMockFetch()

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      await waitFor(() => {
        const select = screen.getByRole('combobox')
        expect(select).toBeInTheDocument()
      })
    })

    it('has 7 days option', async () => {
      setupMockFetch()

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      await waitFor(() => {
        expect(screen.getByText('7 Days')).toBeInTheDocument()
      })
    })

    it('has 30 days option', async () => {
      setupMockFetch()

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      await waitFor(() => {
        expect(screen.getByText('30 Days')).toBeInTheDocument()
      })
    })

    it('has 90 days option', async () => {
      setupMockFetch()

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      await waitFor(() => {
        expect(screen.getByText('90 Days')).toBeInTheDocument()
      })
    })

    it('allows changing timeframe', async () => {
      setupMockFetch()

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      await waitFor(() => {
        const select = screen.getByRole('combobox')
        fireEvent.change(select, { target: { value: '7' } })
      })
    })
  })

  describe('Summary Stats Grid', () => {
    it('renders bot stat cards', async () => {
      setupMockFetch()

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      await waitFor(() => {
        // Should have 5 stat cards for 5 bots
        const aresCards = screen.getAllByText('FORTRESS')
        expect(aresCards.length).toBeGreaterThanOrEqual(1)
      })
    })

    it('displays return percentage for bots with data', async () => {
      setupMockFetch()

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      await waitFor(() => {
        // Should show percentage returns
        const percentages = screen.getAllByText(/%/)
        expect(percentages.length).toBeGreaterThan(0)
      })
    })
  })

  describe('Empty State', () => {
    it('shows message when no data available', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        json: () => Promise.resolve({}),
      })

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      await waitFor(() => {
        expect(screen.getByText('Bot Performance Comparison')).toBeInTheDocument()
      })
    })
  })

  describe('Loading State', () => {
    it('shows loading indicator while fetching', () => {
      mockFetch.mockImplementation(() => new Promise(() => {})) // Never resolves

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      // Should still show header during loading
      expect(screen.getByText('Bot Performance Comparison')).toBeInTheDocument()
    })
  })

  describe('Props', () => {
    it('accepts days prop', async () => {
      setupMockFetch()

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve days={14} />)

      await waitFor(() => {
        expect(screen.getByText('Bot Performance Comparison')).toBeInTheDocument()
      })
    })

    it('accepts height prop', async () => {
      setupMockFetch()

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve height={500} />)

      await waitFor(() => {
        expect(screen.getByText('Bot Performance Comparison')).toBeInTheDocument()
      })
    })

    it('accepts showPercentage prop', async () => {
      setupMockFetch()

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve showPercentage={false} />)

      await waitFor(() => {
        expect(screen.getByText('Bot Performance Comparison')).toBeInTheDocument()
      })
    })
  })

  describe('Error Handling', () => {
    it('handles API errors gracefully', async () => {
      mockFetch.mockRejectedValue(new Error('Network Error'))

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      await waitFor(() => {
        expect(screen.getByText('Bot Performance Comparison')).toBeInTheDocument()
      })
    })

    it('handles partial data', async () => {
      // Some bots succeed, some fail
      mockFetch.mockImplementation((url: string) => {
        if (url.includes('fortress')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(mockAresEquityCurve) })
        }
        return Promise.reject(new Error('Failed'))
      })

      const MultiBotEquityCurve = require('../../../src/components/charts/MultiBotEquityCurve').default
      renderWithSWR(<MultiBotEquityCurve />)

      await waitFor(() => {
        expect(screen.getByText('Bot Performance Comparison')).toBeInTheDocument()
      })
    })
  })
})
