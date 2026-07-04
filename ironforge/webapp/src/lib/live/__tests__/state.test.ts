import { describe, it, expect } from 'vitest'
import { deriveCustomerState, getMarketSession, StateInput } from '../state'

const base: StateInput = {
  botState: 'scanning',
  lastScanReason: null,
  paused: false,
  isActive: true,
  openPositions: 0,
  todayTradesClosed: 0,
  sessionOpen: true,
  heartbeatAgeMin: 1,
}

describe('deriveCustomerState priority order', () => {
  it('customer pause wins over everything and offers Resume', () => {
    const s = deriveCustomerState({ ...base, paused: true, openPositions: 1, botState: 'error' })
    expect(s.key).toBe('PAUSED')
    expect(s.can_resume).toBe(true)
  })

  it('operator toggle-off is PAUSED without a Resume CTA', () => {
    const s = deriveCustomerState({ ...base, isActive: false, openPositions: 1 })
    expect(s.key).toBe('PAUSED')
    expect(s.can_resume).toBe(false)
  })

  it('error bot_state is ACTION_REQUIRED', () => {
    expect(deriveCustomerState({ ...base, botState: 'error' }).key).toBe('ACTION_REQUIRED')
  })

  it('stale heartbeat during open session is ACTION_REQUIRED', () => {
    expect(deriveCustomerState({ ...base, heartbeatAgeMin: 30 }).key).toBe('ACTION_REQUIRED')
  })

  it('stale heartbeat while market is closed is NOT an error (off-hours idle)', () => {
    const s = deriveCustomerState({ ...base, sessionOpen: false, heartbeatAgeMin: 600 })
    expect(s.key).toBe('WORKING_WAITING')
    expect(s.dot).toBe('gray')
  })

  it('open position awaiting fill is TRADE_ACTIVE at timeline step 1', () => {
    const s = deriveCustomerState({ ...base, openPositions: 1, botState: 'awaiting_fill' })
    expect(s.key).toBe('TRADE_ACTIVE')
    expect(s.timeline_step).toBe(1)
  })

  it('open position monitoring is MONITORING_POSITION at step 2', () => {
    const s = deriveCustomerState({ ...base, openPositions: 1, botState: 'monitoring' })
    expect(s.key).toBe('MONITORING_POSITION')
    expect(s.timeline_step).toBe(2)
    expect(s.check_line).toBe('No action required.')
  })

  it('no open position but trades closed today is TRADE_COMPLETE at step 4', () => {
    const s = deriveCustomerState({ ...base, todayTradesClosed: 1, botState: 'traded' })
    expect(s.key).toBe('TRADE_COMPLETE')
    expect(s.timeline_step).toBe(4)
  })

  it('vix skip reason is BLOCKED', () => {
    const s = deriveCustomerState({ ...base, lastScanReason: 'skip:vix_too_high(41.2>40)' })
    expect(s.key).toBe('BLOCKED')
    expect(s.headline).toBe('No Trading Today')
  })

  it('open-session scanning with nothing else is WORKING_WAITING', () => {
    const s = deriveCustomerState(base)
    expect(s.key).toBe('WORKING_WAITING')
    expect(s.headline).toBe('Looking for an Opportunity')
    expect(s.timeline_step).toBe(0)
  })

  it('closed-session default is the standing-by variant', () => {
    const s = deriveCustomerState({ ...base, sessionOpen: false, botState: 'idle', heartbeatAgeMin: null })
    expect(s.key).toBe('WORKING_WAITING')
    expect(s.headline).toBe('Spark is Standing By')
    expect(s.timeline_step).toBeNull()
  })

  it('an open position outranks a blocked scan reason (manage what exists)', () => {
    const s = deriveCustomerState({
      ...base, openPositions: 1, botState: 'monitoring',
      lastScanReason: 'skip:vix_too_high(41.2>40)',
    })
    expect(s.key).toBe('MONITORING_POSITION')
  })

  it('no copy string contains options jargon', () => {
    const jargon = /strike|leg|greek|delta|gamma|theta|vega|condor|spread/i
    const variants: StateInput[] = [
      base,
      { ...base, paused: true },
      { ...base, isActive: false },
      { ...base, botState: 'error' },
      { ...base, openPositions: 1, botState: 'awaiting_fill' },
      { ...base, openPositions: 1, botState: 'monitoring' },
      { ...base, todayTradesClosed: 1 },
      { ...base, lastScanReason: 'skip:event_blackout' },
      { ...base, sessionOpen: false },
    ]
    for (const v of variants) {
      const s = deriveCustomerState(v)
      expect(`${s.headline} ${s.subtitle} ${s.check_line ?? ''}`).not.toMatch(jargon)
    }
  })
})

describe('getMarketSession', () => {
  it('weekday mid-session is open with a 3:00 PM CT close', () => {
    // Wed 2026-07-08 11:00 CT
    const s = getMarketSession(new Date(2026, 6, 8, 11, 0))
    expect(s.open).toBe(true)
    expect(s.closes_at_min).toBe(900)
    expect(s.next_open_label).toBeNull()
  })

  it('Saturday is closed and next open is Monday', () => {
    const s = getMarketSession(new Date(2026, 6, 4, 12, 0)) // Sat 2026-07-04
    expect(s.open).toBe(false)
    expect(s.label).toBe('Market Closed')
    expect(s.next_open_label).toBe('Opens Monday 8:30 AM CT')
  })

  it('full-closure holiday reads as Market Holiday', () => {
    const s = getMarketSession(new Date(2026, 6, 3, 12, 0)) // Fri 2026-07-03 closure
    expect(s.open).toBe(false)
    expect(s.label).toBe('Market Holiday')
    expect(s.next_open_label).toBe('Opens Monday 8:30 AM CT')
  })

  it('pre-open on a trading day points at today', () => {
    const s = getMarketSession(new Date(2026, 6, 8, 7, 0)) // Wed 07:00 CT
    expect(s.open).toBe(false)
    expect(s.next_open_label).toBe('Opens today 8:30 AM CT')
  })

  it('early-close day closes at 12:00 PM CT', () => {
    const s = getMarketSession(new Date(2026, 10, 27, 10, 0)) // Fri 2026-11-27 half-day
    expect(s.open).toBe(true)
    expect(s.closes_at_min).toBe(720)
  })
})
