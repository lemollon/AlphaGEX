import { describe, expect, it } from 'vitest'

import { nextSearch, parseBotFilter, parsePeriod } from '../params'

describe('parsePeriod', () => {
  it('accepts the two supported values', () => {
    expect(parsePeriod('7d')).toBe('7d')
    expect(parsePeriod('30d')).toBe('30d')
  })

  it('falls back to 30d for anything else', () => {
    expect(parsePeriod(undefined)).toBe('30d')
    expect(parsePeriod('')).toBe('30d')
    expect(parsePeriod('90d')).toBe('30d')
    expect(parsePeriod('7D')).toBe('30d') // case-sensitive by design
    expect(parsePeriod('../etc/passwd')).toBe('30d')
  })

  it('takes the first value when Next hands back a repeated param', () => {
    expect(parsePeriod(['7d', '30d'])).toBe('7d')
  })
})

describe('parseBotFilter', () => {
  it('accepts the three supported values', () => {
    expect(parseBotFilter('all')).toBe('all')
    expect(parseBotFilter('spark')).toBe('spark')
    expect(parseBotFilter('flame')).toBe('flame')
  })

  it('falls back to all for anything else', () => {
    expect(parseBotFilter(undefined)).toBe('all')
    expect(parseBotFilter('inferno')).toBe('all')
    expect(parseBotFilter(['flame', 'spark'])).toBe('flame')
  })
})

describe('nextSearch — the control-independence guarantee', () => {
  it('changing the period preserves the bot filter', () => {
    expect(nextSearch('?bot=flame', { period: '7d' })).toBe('?bot=flame&period=7d')
  })

  it('changing the bot filter preserves the period', () => {
    expect(nextSearch('?period=7d', { bot: 'spark' })).toBe('?period=7d&bot=spark')
  })

  it('returning a control to its default drops only that key', () => {
    expect(nextSearch('?period=7d&bot=flame', { period: '30d' })).toBe('?bot=flame')
    expect(nextSearch('?period=7d&bot=flame', { bot: 'all' })).toBe('?period=7d')
  })

  it('preserves unrelated params such as campaign tags', () => {
    const out = nextSearch('?utm_source=x&period=7d', { bot: 'flame' })
    expect(out).toContain('utm_source=x')
    expect(out).toContain('period=7d')
    expect(out).toContain('bot=flame')
  })

  it('omits defaults so shared links stay clean', () => {
    expect(nextSearch('', { period: '30d' })).toBe('')
    expect(nextSearch('', { bot: 'all' })).toBe('')
    expect(nextSearch('?period=7d', { period: '30d' })).toBe('')
  })

  it('never touches the key it was not given', () => {
    // The whole point: the period control passes only { period }, so it is
    // structurally incapable of clobbering `bot`.
    expect(nextSearch('?bot=spark', { period: '7d' })).toContain('bot=spark')
    expect(nextSearch('?period=7d', { bot: 'flame' })).toContain('period=7d')
  })
})
