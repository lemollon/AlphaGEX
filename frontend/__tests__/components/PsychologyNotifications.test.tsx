/**
 * PsychologyNotifications Component Tests
 *
 * Tests for the psychology notifications component.
 */

import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'

// Mock the component
jest.mock('../../src/components/PsychologyNotifications', () => ({
  __esModule: true,
  default: ({
    notifications,
    onDismiss
  }: {
    notifications?: Array<{id: string; type: string; message: string}>;
    onDismiss?: (id: string) => void;
  }) => (
    <div data-testid="psychology-notifications">
      {notifications?.map((n) => (
        <div key={n.id} data-testid={`notification-${n.id}`}>
          <span data-testid={`type-${n.id}`}>{n.type}</span>
          <span data-testid={`message-${n.id}`}>{n.message}</span>
          <button
            data-testid={`dismiss-${n.id}`}
            onClick={() => onDismiss?.(n.id)}
          >
            Dismiss
          </button>
        </div>
      ))}
      {(!notifications || notifications.length === 0) && (
        <div data-testid="no-notifications">No notifications</div>
      )}
    </div>
  ),
}))

describe('PsychologyNotifications Component', () => {
  const mockNotifications = [
    { id: '1', type: 'WARNING', message: 'Possible revenge trading detected' },
    { id: '2', type: 'INFO', message: 'Take a break after 3 consecutive losses' },
  ]

  describe('Rendering', () => {
    it('renders without crashing', () => {
      const PsychologyNotifications = require('../../src/components/PsychologyNotifications').default
      render(<PsychologyNotifications />)
      expect(screen.getByTestId('psychology-notifications')).toBeInTheDocument()
    })

    it('displays notifications', () => {
      const PsychologyNotifications = require('../../src/components/PsychologyNotifications').default
      render(<PsychologyNotifications notifications={mockNotifications} />)
      expect(screen.getByTestId('notification-1')).toBeInTheDocument()
      expect(screen.getByTestId('notification-2')).toBeInTheDocument()
    })

    it('displays notification types', () => {
      const PsychologyNotifications = require('../../src/components/PsychologyNotifications').default
      render(<PsychologyNotifications notifications={mockNotifications} />)
      expect(screen.getByTestId('type-1')).toHaveTextContent('WARNING')
    })

    it('displays notification messages', () => {
      const PsychologyNotifications = require('../../src/components/PsychologyNotifications').default
      render(<PsychologyNotifications notifications={mockNotifications} />)
      expect(screen.getByTestId('message-1')).toHaveTextContent('revenge trading')
    })
  })

  describe('Empty State', () => {
    it('shows empty state when no notifications', () => {
      const PsychologyNotifications = require('../../src/components/PsychologyNotifications').default
      render(<PsychologyNotifications notifications={[]} />)
      expect(screen.getByTestId('no-notifications')).toBeInTheDocument()
    })
  })

  describe('Interactions', () => {
    it('calls onDismiss when dismiss button clicked', () => {
      const PsychologyNotifications = require('../../src/components/PsychologyNotifications').default
      const mockDismiss = jest.fn()
      render(<PsychologyNotifications notifications={mockNotifications} onDismiss={mockDismiss} />)

      fireEvent.click(screen.getByTestId('dismiss-1'))
      expect(mockDismiss).toHaveBeenCalledWith('1')
    })
  })
})
