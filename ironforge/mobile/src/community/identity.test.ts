import { describe, it, expect } from 'vitest'
import { initials, channelAccent, bubbleTint, NEUTRAL_ACCENT } from './identity'

describe('initials', () => {
  it('takes first and last initial, as UX-005 shows', () => {
    expect(initials('Jordan M.')).toBe('JM')
    expect(initials('Alex R.')).toBe('AR')
  })

  it('uses a single letter for a mononym rather than doubling it', () => {
    expect(initials('Forge')).toBe('F')
  })

  it('ignores middle names instead of returning three letters', () => {
    expect(initials('Leron Anthony Mollon')).toBe('LM')
  })

  it('survives extra whitespace', () => {
    expect(initials('  Jordan   M.  ')).toBe('JM')
  })

  it('does not split a surrogate pair in half', () => {
    // charAt(0) would return half of the code point and render as a replacement glyph.
    expect(initials('𝒥ordan Mollon')).toBe('𝒥M')
  })

  it('degrades to a placeholder rather than an empty bubble', () => {
    expect(initials('')).toBe('?')
    expect(initials('   ')).toBe('?')
  })
})

describe('channelAccent', () => {
  it('colours the categories UX-005 shows', () => {
    expect(channelAccent('market-talk')).toBe('#EE5A24')
    expect(channelAccent('trade-ideas')).toBe('#3B82F6')
  })

  it('falls back to neutral for a channel added later', () => {
    // A new channel should get a plain chip, never no chip and never a wrong colour.
    expect(channelAccent('brand-new-room')).toBe(NEUTRAL_ACCENT)
  })

  it('is neutral when the server sends no channel at all', () => {
    // An older API that predates the per-post channel must not crash the card.
    expect(channelAccent(undefined)).toBe(NEUTRAL_ACCENT)
  })
})

describe('bubbleTint', () => {
  it('is stable for the same name across reorders', () => {
    // The bug this prevents: index-based colour, so a member changes colour on every
    // poll and reads as a different person.
    expect(bubbleTint('Jordan M.')).toBe(bubbleTint('Jordan M.'))
  })

  it('distinguishes different members', () => {
    expect(bubbleTint('Jordan M.')).not.toBe(bubbleTint('Alex R.'))
  })

  it('does not throw on an empty name', () => {
    expect(typeof bubbleTint('')).toBe('string')
  })
})
