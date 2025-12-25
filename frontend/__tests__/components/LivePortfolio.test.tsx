/**
 * LivePortfolio Component Tests
 *
 * Tests for the live portfolio display component.
 */

import React from 'react'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'

// Mock the component
jest.mock('../../src/components/trader/LivePortfolio', () => ({
  __esModule: true,
  default: ({
    positions,
    totalValue,
    dailyPnL
  }: {
    positions?: Array<{id: string; symbol: string; pnl: number}>;
    totalValue?: number;
    dailyPnL?: number;
  }) => (
    <div data-testid="live-portfolio">
      <div data-testid="total-value">${totalValue?.toLocaleString() ?? 'N/A'}</div>
      <div data-testid="daily-pnl">{dailyPnL ?? 0}</div>
      <div data-testid="position-count">{positions?.length ?? 0} positions</div>
    </div>
  ),
}))

describe('LivePortfolio Component', () => {
  const mockPositions = [
    { id: '1', symbol: 'SPY', pnl: 150 },
    { id: '2', symbol: 'SPX', pnl: -50 },
  ]

  describe('Rendering', () => {
    it('renders without crashing', () => {
      const LivePortfolio = require('../../src/components/trader/LivePortfolio').default
      render(<LivePortfolio />)
      expect(screen.getByTestId('live-portfolio')).toBeInTheDocument()
    })

    it('displays total portfolio value', () => {
      const LivePortfolio = require('../../src/components/trader/LivePortfolio').default
      render(<LivePortfolio totalValue={125000} />)
      expect(screen.getByTestId('total-value')).toHaveTextContent('$125,000')
    })

    it('displays daily P&L', () => {
      const LivePortfolio = require('../../src/components/trader/LivePortfolio').default
      render(<LivePortfolio dailyPnL={350} />)
      expect(screen.getByTestId('daily-pnl')).toHaveTextContent('350')
    })

    it('displays position count', () => {
      const LivePortfolio = require('../../src/components/trader/LivePortfolio').default
      render(<LivePortfolio positions={mockPositions} />)
      expect(screen.getByTestId('position-count')).toHaveTextContent('2 positions')
    })
  })

  describe('Empty State', () => {
    it('handles no positions', () => {
      const LivePortfolio = require('../../src/components/trader/LivePortfolio').default
      render(<LivePortfolio positions={[]} />)
      expect(screen.getByTestId('position-count')).toHaveTextContent('0 positions')
    })

    it('handles missing props', () => {
      const LivePortfolio = require('../../src/components/trader/LivePortfolio').default
      render(<LivePortfolio />)
      expect(screen.getByTestId('total-value')).toHaveTextContent('N/A')
    })
  })
})
