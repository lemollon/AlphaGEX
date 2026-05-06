import { describe, it, expect } from 'vitest'
import { getEventStrategy, getPlaybook } from '../playbook'

describe('getEventStrategy', () => {
  it('classifies a 13:00 CT FOMC release as mid-day with +30 min resume', () => {
    const s = getEventStrategy('FOMC', '13:00', true, 30)
    expect(s.kind).toBe('mid_day')
    expect(s.label).toMatch(/Mid-day/i)
    expect(s.detail).toContain('1:00 PM CT')
    expect(s.detail).toContain('1:30 PM CT')
    expect(s.detail).toContain('30 min')
  })

  it('classifies a 07:30 CT CPI release as pre-market', () => {
    const s = getEventStrategy('CPI', '07:30', true, 30)
    expect(s.kind).toBe('pre_market')
    expect(s.label).toMatch(/Pre-market/i)
    expect(s.detail).toContain('8:30 AM CT')
  })

  it('classifies an 07:30 CT NFP release as pre-market regardless of offset', () => {
    const s = getEventStrategy('NFP', '07:30', true, 60)
    expect(s.kind).toBe('pre_market')
    // Pre-market always resumes at the bell, never at release+offset
    expect(s.detail).toContain('8:30 AM CT')
  })

  it('returns no_halt when haltsBots is false', () => {
    const s = getEventStrategy('PCE', '07:30', false)
    expect(s.kind).toBe('no_halt')
    expect(s.label).toBe('No halt')
  })

  it('treats 08:29 CT as pre-market (boundary just before open)', () => {
    const s = getEventStrategy('CPI', '08:29', true, 30)
    expect(s.kind).toBe('pre_market')
  })

  it('treats 08:30 CT exactly as mid-day (boundary at market open)', () => {
    const s = getEventStrategy('CPI', '08:30', true, 30)
    expect(s.kind).toBe('mid_day')
  })
})

describe('getPlaybook', () => {
  it('returns the FOMC playbook for "FOMC"', () => {
    expect(getPlaybook('FOMC').display_name).toBe('FOMC Rate Decision')
  })

  it('returns UNKNOWN_PLAYBOOK for unknown event type', () => {
    expect(getPlaybook('NOT_A_REAL_EVENT').tier).toBe('tier3')
  })
})
