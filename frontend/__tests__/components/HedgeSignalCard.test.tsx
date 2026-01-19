/**
 * HedgeSignalCard Component Tests
 *
 * Tests for the VIX hedge signal display component.
 */

import React from 'react'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'

// Mock the useVIXHedgeSignal hook
const mockUseVIXHedgeSignal = jest.fn()

jest.mock('../../src/lib/hooks/useMarketData', () => ({
  useVIXHedgeSignal: () => mockUseVIXHedgeSignal(),
}))

// Import after mocking
import HedgeSignalCard from '../../src/components/trader/HedgeSignalCard'

describe('HedgeSignalCard Component', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Loading State', () => {
    it('renders loading state correctly', () => {
      mockUseVIXHedgeSignal.mockReturnValue({
        data: null,
        isLoading: true,
        error: null,
      })

      render(<HedgeSignalCard />)

      expect(screen.getByText('Current Hedge Signal')).toBeInTheDocument()
      // Loading skeleton should have animate-pulse class
      const loadingElement = document.querySelector('.animate-pulse')
      expect(loadingElement).toBeInTheDocument()
    })
  })

  describe('Error State', () => {
    it('renders error state when API fails', () => {
      mockUseVIXHedgeSignal.mockReturnValue({
        data: null,
        isLoading: false,
        error: new Error('API error'),
      })

      render(<HedgeSignalCard />)

      expect(screen.getByText('Current Hedge Signal')).toBeInTheDocument()
      expect(screen.getByText('No hedge signal available')).toBeInTheDocument()
    })

    it('renders error state when data is null', () => {
      mockUseVIXHedgeSignal.mockReturnValue({
        data: null,
        isLoading: false,
        error: null,
      })

      render(<HedgeSignalCard />)

      expect(screen.getByText('No hedge signal available')).toBeInTheDocument()
    })
  })

  describe('Signal Types', () => {
    it('renders NO_ACTION signal with green styling', () => {
      mockUseVIXHedgeSignal.mockReturnValue({
        data: {
          data: {
            signal_type: 'no_action',
            confidence: 85,
            vol_regime: 'low',
            reasoning: 'VIX is within normal range',
            recommended_action: 'Continue normal trading',
            timestamp: '2025-01-19T10:00:00Z',
            metrics: { vix_spot: 15.5, vix_source: 'tradier' },
          },
        },
        isLoading: false,
        error: null,
      })

      render(<HedgeSignalCard />)

      expect(screen.getByText('NO ACTION')).toBeInTheDocument()
      expect(screen.getByText('85% confidence')).toBeInTheDocument()
      expect(screen.getByText('VIX is within normal range')).toBeInTheDocument()
      expect(screen.getByText('Continue normal trading')).toBeInTheDocument()
      expect(screen.getByText('VIX: 15.50')).toBeInTheDocument()

      // Check for green color class on the signal container
      const signalContainer = document.querySelector('.bg-green-500\\/20')
      expect(signalContainer).toBeInTheDocument()
    })

    it('renders MONITOR_CLOSELY signal with yellow styling', () => {
      mockUseVIXHedgeSignal.mockReturnValue({
        data: {
          data: {
            signal_type: 'monitor_closely',
            confidence: 65,
            vol_regime: 'elevated',
            reasoning: 'VIX is elevated, watch for spikes',
            recommended_action: 'Reduce position sizes',
            timestamp: '2025-01-19T10:00:00Z',
            metrics: { vix_spot: 24.5, vix_source: 'tradier' },
          },
        },
        isLoading: false,
        error: null,
      })

      render(<HedgeSignalCard />)

      expect(screen.getByText('MONITOR CLOSELY')).toBeInTheDocument()
      expect(screen.getByText('65% confidence')).toBeInTheDocument()

      // Check for yellow color class on the signal container
      const signalContainer = document.querySelector('.bg-yellow-500\\/20')
      expect(signalContainer).toBeInTheDocument()
    })

    it('renders HEDGE_RECOMMENDED signal with red styling', () => {
      mockUseVIXHedgeSignal.mockReturnValue({
        data: {
          data: {
            signal_type: 'hedge_recommended',
            confidence: 90,
            vol_regime: 'high',
            reasoning: 'VIX spike detected, high volatility environment',
            recommended_action: 'Consider hedging positions or reducing exposure',
            risk_warning: 'Market conditions unfavorable for premium selling',
            timestamp: '2025-01-19T10:00:00Z',
            metrics: { vix_spot: 35.0, vix_source: 'tradier' },
          },
        },
        isLoading: false,
        error: null,
      })

      render(<HedgeSignalCard />)

      expect(screen.getByText('HEDGE RECOMMENDED')).toBeInTheDocument()
      expect(screen.getByText('90% confidence')).toBeInTheDocument()
      expect(screen.getByText('Risk Warning')).toBeInTheDocument()
      expect(screen.getByText('Market conditions unfavorable for premium selling')).toBeInTheDocument()

      // Check for red color class on the signal container
      const signalContainer = document.querySelector('.bg-red-500\\/20')
      expect(signalContainer).toBeInTheDocument()
    })
  })

  describe('Compact Mode', () => {
    it('renders compact version correctly', () => {
      mockUseVIXHedgeSignal.mockReturnValue({
        data: {
          data: {
            signal_type: 'no_action',
            confidence: 80,
            vol_regime: 'low',
            reasoning: 'Normal conditions',
            recommended_action: 'Continue trading',
            timestamp: '2025-01-19T10:00:00Z',
            metrics: { vix_spot: 16.0, vix_source: 'tradier' },
          },
        },
        isLoading: false,
        error: null,
      })

      render(<HedgeSignalCard compact={true} />)

      // Compact mode should show "Hedge Signal" instead of "Current Hedge Signal"
      expect(screen.getByText('Hedge Signal')).toBeInTheDocument()
      expect(screen.getByText('NO ACTION')).toBeInTheDocument()
      expect(screen.getByText(/VIX: 16.00/)).toBeInTheDocument()
      expect(screen.getByText(/80% confidence/)).toBeInTheDocument()

      // Compact mode should NOT show recommended action or full reasoning
      expect(screen.queryByText('RECOMMENDED ACTION')).not.toBeInTheDocument()
    })
  })

  describe('Risk Warning Display', () => {
    it('shows risk warning when present', () => {
      mockUseVIXHedgeSignal.mockReturnValue({
        data: {
          data: {
            signal_type: 'hedge_recommended',
            confidence: 85,
            vol_regime: 'high',
            reasoning: 'High VIX',
            recommended_action: 'Hedge now',
            risk_warning: 'Critical volatility level reached',
            timestamp: '2025-01-19T10:00:00Z',
          },
        },
        isLoading: false,
        error: null,
      })

      render(<HedgeSignalCard />)

      expect(screen.getByText('Risk Warning')).toBeInTheDocument()
      expect(screen.getByText('Critical volatility level reached')).toBeInTheDocument()
    })

    it('hides risk warning when set to "None"', () => {
      mockUseVIXHedgeSignal.mockReturnValue({
        data: {
          data: {
            signal_type: 'no_action',
            confidence: 75,
            vol_regime: 'low',
            reasoning: 'Normal',
            recommended_action: 'Continue',
            risk_warning: 'None',
            timestamp: '2025-01-19T10:00:00Z',
          },
        },
        isLoading: false,
        error: null,
      })

      render(<HedgeSignalCard />)

      expect(screen.queryByText('Risk Warning')).not.toBeInTheDocument()
    })
  })

  describe('Fallback Mode', () => {
    it('shows fallback mode indicator when using basic analysis', () => {
      mockUseVIXHedgeSignal.mockReturnValue({
        data: {
          data: {
            signal_type: 'no_action',
            confidence: 60,
            vol_regime: 'low',
            reasoning: 'Basic VIX analysis',
            recommended_action: 'Continue',
            fallback_mode: true,
            timestamp: '2025-01-19T10:00:00Z',
          },
        },
        isLoading: false,
        error: null,
      })

      render(<HedgeSignalCard />)

      expect(screen.getByText('Using basic VIX-level analysis')).toBeInTheDocument()
    })
  })

  describe('Data Structure Handling', () => {
    it('handles nested data.data structure', () => {
      mockUseVIXHedgeSignal.mockReturnValue({
        data: {
          data: {
            signal_type: 'no_action',
            confidence: 70,
            vol_regime: 'low',
            reasoning: 'Test',
            recommended_action: 'Test action',
            timestamp: '2025-01-19T10:00:00Z',
          },
        },
        isLoading: false,
        error: null,
      })

      render(<HedgeSignalCard />)

      expect(screen.getByText('NO ACTION')).toBeInTheDocument()
    })

    it('handles flat data structure', () => {
      mockUseVIXHedgeSignal.mockReturnValue({
        data: {
          signal_type: 'no_action',
          confidence: 70,
          vol_regime: 'low',
          reasoning: 'Test',
          recommended_action: 'Test action',
          timestamp: '2025-01-19T10:00:00Z',
        },
        isLoading: false,
        error: null,
      })

      render(<HedgeSignalCard />)

      expect(screen.getByText('NO ACTION')).toBeInTheDocument()
    })
  })

  describe('VIX Metrics Display', () => {
    it('displays VIX spot value when available', () => {
      mockUseVIXHedgeSignal.mockReturnValue({
        data: {
          data: {
            signal_type: 'no_action',
            confidence: 75,
            vol_regime: 'low',
            reasoning: 'Normal',
            recommended_action: 'Continue',
            timestamp: '2025-01-19T10:00:00Z',
            metrics: { vix_spot: 18.75, vix_source: 'tradier' },
          },
        },
        isLoading: false,
        error: null,
      })

      render(<HedgeSignalCard />)

      expect(screen.getByText('VIX: 18.75')).toBeInTheDocument()
    })

    it('handles missing metrics gracefully', () => {
      mockUseVIXHedgeSignal.mockReturnValue({
        data: {
          data: {
            signal_type: 'no_action',
            confidence: 75,
            vol_regime: 'low',
            reasoning: 'Normal',
            recommended_action: 'Continue',
            timestamp: '2025-01-19T10:00:00Z',
          },
        },
        isLoading: false,
        error: null,
      })

      render(<HedgeSignalCard />)

      // Should still render without VIX display
      expect(screen.getByText('NO ACTION')).toBeInTheDocument()
      expect(screen.queryByText(/VIX:/)).not.toBeInTheDocument()
    })
  })
})
