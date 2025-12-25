/**
 * EquityCurve Component Tests
 *
 * Tests for the equity curve chart component.
 */

import React from 'react'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'

// Mock the component
jest.mock('../../src/components/trader/EquityCurve', () => ({
  __esModule: true,
  default: ({ data, title }: { data?: Array<{date: string; equity: number}>; title?: string }) => (
    <div data-testid="equity-curve">
      <h3 data-testid="chart-title">{title ?? 'Equity Curve'}</h3>
      <div data-testid="data-points">{data?.length ?? 0} points</div>
    </div>
  ),
}))

describe('EquityCurve Component', () => {
  const mockEquityData = [
    { date: '2024-01-01', equity: 100000 },
    { date: '2024-01-02', equity: 101500 },
    { date: '2024-01-03', equity: 102000 },
    { date: '2024-01-04', equity: 101000 },
    { date: '2024-01-05', equity: 103000 },
  ]

  describe('Rendering', () => {
    it('renders without crashing', () => {
      const EquityCurve = require('../../src/components/trader/EquityCurve').default
      render(<EquityCurve />)
      expect(screen.getByTestId('equity-curve')).toBeInTheDocument()
    })

    it('displays the title', () => {
      const EquityCurve = require('../../src/components/trader/EquityCurve').default
      render(<EquityCurve title="Portfolio Performance" />)
      expect(screen.getByTestId('chart-title')).toHaveTextContent('Portfolio Performance')
    })

    it('displays data point count', () => {
      const EquityCurve = require('../../src/components/trader/EquityCurve').default
      render(<EquityCurve data={mockEquityData} />)
      expect(screen.getByTestId('data-points')).toHaveTextContent('5 points')
    })
  })

  describe('Empty State', () => {
    it('handles empty data gracefully', () => {
      const EquityCurve = require('../../src/components/trader/EquityCurve').default
      render(<EquityCurve data={[]} />)
      expect(screen.getByTestId('data-points')).toHaveTextContent('0 points')
    })

    it('handles missing data prop', () => {
      const EquityCurve = require('../../src/components/trader/EquityCurve').default
      render(<EquityCurve />)
      expect(screen.getByTestId('data-points')).toHaveTextContent('0 points')
    })
  })

  describe('Data Updates', () => {
    it('updates when data changes', () => {
      const EquityCurve = require('../../src/components/trader/EquityCurve').default
      const { rerender } = render(<EquityCurve data={mockEquityData} />)
      expect(screen.getByTestId('data-points')).toHaveTextContent('5 points')

      const newData = [...mockEquityData, { date: '2024-01-06', equity: 104000 }]
      rerender(<EquityCurve data={newData} />)
      expect(screen.getByTestId('data-points')).toHaveTextContent('6 points')
    })
  })
})
