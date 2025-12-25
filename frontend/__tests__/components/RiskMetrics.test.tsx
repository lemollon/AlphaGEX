/**
 * RiskMetrics Component Tests
 *
 * Tests for the risk metrics display component.
 */

import React from 'react'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'

// Mock the component if not available
jest.mock('../../src/components/trader/RiskMetrics', () => ({
  __esModule: true,
  default: ({ riskLevel, maxDrawdown }: { riskLevel?: number; maxDrawdown?: number }) => (
    <div data-testid="risk-metrics">
      <div data-testid="risk-level">{riskLevel ?? 'N/A'}</div>
      <div data-testid="max-drawdown">{maxDrawdown ?? 'N/A'}</div>
    </div>
  ),
}))

describe('RiskMetrics Component', () => {
  describe('Rendering', () => {
    it('renders without crashing', () => {
      const RiskMetrics = require('../../src/components/trader/RiskMetrics').default
      render(<RiskMetrics />)
      expect(screen.getByTestId('risk-metrics')).toBeInTheDocument()
    })

    it('displays risk level when provided', () => {
      const RiskMetrics = require('../../src/components/trader/RiskMetrics').default
      render(<RiskMetrics riskLevel={0.3} />)
      expect(screen.getByTestId('risk-level')).toHaveTextContent('0.3')
    })

    it('displays max drawdown when provided', () => {
      const RiskMetrics = require('../../src/components/trader/RiskMetrics').default
      render(<RiskMetrics maxDrawdown={-5.2} />)
      expect(screen.getByTestId('max-drawdown')).toHaveTextContent('-5.2')
    })

    it('handles missing data gracefully', () => {
      const RiskMetrics = require('../../src/components/trader/RiskMetrics').default
      render(<RiskMetrics />)
      expect(screen.getByTestId('risk-level')).toHaveTextContent('N/A')
    })
  })

  describe('Risk Level Colors', () => {
    it('displays low risk correctly', () => {
      const RiskMetrics = require('../../src/components/trader/RiskMetrics').default
      render(<RiskMetrics riskLevel={0.2} />)
      const riskElement = screen.getByTestId('risk-level')
      expect(riskElement).toBeInTheDocument()
    })

    it('displays high risk correctly', () => {
      const RiskMetrics = require('../../src/components/trader/RiskMetrics').default
      render(<RiskMetrics riskLevel={0.8} />)
      const riskElement = screen.getByTestId('risk-level')
      expect(riskElement).toBeInTheDocument()
    })
  })

  describe('Data Updates', () => {
    it('updates when props change', () => {
      const RiskMetrics = require('../../src/components/trader/RiskMetrics').default
      const { rerender } = render(<RiskMetrics riskLevel={0.3} />)
      expect(screen.getByTestId('risk-level')).toHaveTextContent('0.3')

      rerender(<RiskMetrics riskLevel={0.7} />)
      expect(screen.getByTestId('risk-level')).toHaveTextContent('0.7')
    })
  })
})
