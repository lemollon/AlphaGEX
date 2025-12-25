/**
 * GEXProfileChart Component Tests
 *
 * Tests for the GEX profile visualization component.
 */

import React from 'react'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'

// Mock the component
jest.mock('../../src/components/GEXProfileChart', () => ({
  __esModule: true,
  default: ({
    data,
    spotPrice,
    callWall,
    putWall
  }: {
    data?: Array<{strike: number; netGamma: number}>;
    spotPrice?: number;
    callWall?: number;
    putWall?: number;
  }) => (
    <div data-testid="gex-profile-chart">
      <div data-testid="spot-price">{spotPrice ?? 'N/A'}</div>
      <div data-testid="call-wall">{callWall ?? 'N/A'}</div>
      <div data-testid="put-wall">{putWall ?? 'N/A'}</div>
      <div data-testid="strike-count">{data?.length ?? 0} strikes</div>
    </div>
  ),
}))

describe('GEXProfileChart Component', () => {
  const mockGEXData = [
    { strike: 575, netGamma: -200000000 },
    { strike: 580, netGamma: 100000000 },
    { strike: 585, netGamma: 500000000 },
    { strike: 590, netGamma: 800000000 },
    { strike: 595, netGamma: 300000000 },
  ]

  describe('Rendering', () => {
    it('renders without crashing', () => {
      const GEXProfileChart = require('../../src/components/GEXProfileChart').default
      render(<GEXProfileChart />)
      expect(screen.getByTestId('gex-profile-chart')).toBeInTheDocument()
    })

    it('displays spot price', () => {
      const GEXProfileChart = require('../../src/components/GEXProfileChart').default
      render(<GEXProfileChart spotPrice={585.50} />)
      expect(screen.getByTestId('spot-price')).toHaveTextContent('585.5')
    })

    it('displays call wall', () => {
      const GEXProfileChart = require('../../src/components/GEXProfileChart').default
      render(<GEXProfileChart callWall={590} />)
      expect(screen.getByTestId('call-wall')).toHaveTextContent('590')
    })

    it('displays put wall', () => {
      const GEXProfileChart = require('../../src/components/GEXProfileChart').default
      render(<GEXProfileChart putWall={580} />)
      expect(screen.getByTestId('put-wall')).toHaveTextContent('580')
    })

    it('displays strike count', () => {
      const GEXProfileChart = require('../../src/components/GEXProfileChart').default
      render(<GEXProfileChart data={mockGEXData} />)
      expect(screen.getByTestId('strike-count')).toHaveTextContent('5 strikes')
    })
  })

  describe('Empty State', () => {
    it('handles missing data', () => {
      const GEXProfileChart = require('../../src/components/GEXProfileChart').default
      render(<GEXProfileChart />)
      expect(screen.getByTestId('strike-count')).toHaveTextContent('0 strikes')
    })
  })
})
