import { describe, it, expect } from 'vitest'
import { mapBrokerageStatusToCrm } from '../brokerage-status'

describe('mapBrokerageStatusToCrm', () => {
  it('maps pending -> Pending, not reauthorization', () => {
    expect(mapBrokerageStatusToCrm('pending')).toEqual({
      connectionStatus: 'Pending',
      reauthorizationRequired: false,
    })
  })

  it('maps active -> Connected, not reauthorization', () => {
    expect(mapBrokerageStatusToCrm('active')).toEqual({
      connectionStatus: 'Connected',
      reauthorizationRequired: false,
    })
  })

  it('maps removed -> Disconnected, not reauthorization', () => {
    expect(mapBrokerageStatusToCrm('removed')).toEqual({
      connectionStatus: 'Disconnected',
      reauthorizationRequired: false,
    })
  })

  it('maps disabled -> Reauthorization Required, WITH reauthorizationRequired true', () => {
    expect(mapBrokerageStatusToCrm('disabled')).toEqual({
      connectionStatus: 'Reauthorization Required',
      reauthorizationRequired: true,
    })
  })

  it('falls back to Pending for an unrecognized status instead of throwing', () => {
    expect(mapBrokerageStatusToCrm('some_future_status')).toEqual({
      connectionStatus: 'Pending',
      reauthorizationRequired: false,
    })
  })
})
