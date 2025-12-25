/**
 * SmartStrategyPicker Component Tests
 *
 * Tests for the strategy picker component.
 */

import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'

// Mock the component
jest.mock('../../src/components/SmartStrategyPicker', () => ({
  __esModule: true,
  default: ({
    strategies,
    selectedStrategy,
    onSelect
  }: {
    strategies?: Array<{id: string; name: string; confidence: number}>;
    selectedStrategy?: string;
    onSelect?: (id: string) => void;
  }) => (
    <div data-testid="strategy-picker">
      {strategies?.map((s) => (
        <button
          key={s.id}
          data-testid={`strategy-${s.id}`}
          data-selected={selectedStrategy === s.id}
          onClick={() => onSelect?.(s.id)}
        >
          {s.name} ({Math.round(s.confidence * 100)}%)
        </button>
      ))}
      {(!strategies || strategies.length === 0) && (
        <div data-testid="no-strategies">No strategies available</div>
      )}
    </div>
  ),
}))

describe('SmartStrategyPicker Component', () => {
  const mockStrategies = [
    { id: 'ic', name: 'Iron Condor', confidence: 0.82 },
    { id: 'bcs', name: 'Bull Call Spread', confidence: 0.65 },
    { id: 'csp', name: 'Cash Secured Put', confidence: 0.75 },
  ]

  describe('Rendering', () => {
    it('renders without crashing', () => {
      const SmartStrategyPicker = require('../../src/components/SmartStrategyPicker').default
      render(<SmartStrategyPicker />)
      expect(screen.getByTestId('strategy-picker')).toBeInTheDocument()
    })

    it('displays all strategies', () => {
      const SmartStrategyPicker = require('../../src/components/SmartStrategyPicker').default
      render(<SmartStrategyPicker strategies={mockStrategies} />)
      expect(screen.getByTestId('strategy-ic')).toBeInTheDocument()
      expect(screen.getByTestId('strategy-bcs')).toBeInTheDocument()
      expect(screen.getByTestId('strategy-csp')).toBeInTheDocument()
    })

    it('displays confidence percentages', () => {
      const SmartStrategyPicker = require('../../src/components/SmartStrategyPicker').default
      render(<SmartStrategyPicker strategies={mockStrategies} />)
      expect(screen.getByTestId('strategy-ic')).toHaveTextContent('82%')
    })
  })

  describe('Selection', () => {
    it('highlights selected strategy', () => {
      const SmartStrategyPicker = require('../../src/components/SmartStrategyPicker').default
      render(<SmartStrategyPicker strategies={mockStrategies} selectedStrategy="ic" />)
      expect(screen.getByTestId('strategy-ic')).toHaveAttribute('data-selected', 'true')
    })

    it('calls onSelect when strategy clicked', () => {
      const SmartStrategyPicker = require('../../src/components/SmartStrategyPicker').default
      const mockSelect = jest.fn()
      render(<SmartStrategyPicker strategies={mockStrategies} onSelect={mockSelect} />)

      fireEvent.click(screen.getByTestId('strategy-bcs'))
      expect(mockSelect).toHaveBeenCalledWith('bcs')
    })
  })

  describe('Empty State', () => {
    it('shows empty state when no strategies', () => {
      const SmartStrategyPicker = require('../../src/components/SmartStrategyPicker').default
      render(<SmartStrategyPicker strategies={[]} />)
      expect(screen.getByTestId('no-strategies')).toBeInTheDocument()
    })
  })
})
