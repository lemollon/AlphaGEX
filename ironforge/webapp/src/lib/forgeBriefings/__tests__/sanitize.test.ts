import { describe, it, expect } from 'vitest'
import { stripDecorativeUnicode } from '../sanitize'

describe('stripDecorativeUnicode', () => {
  it('removes face emoji', () => {
    expect(stripDecorativeUnicode('Bot is hot 🔥 today')).toBe('Bot is hot today')
  })

  it('removes a run of multiple emojis', () => {
    expect(stripDecorativeUnicode('🚀📈💰 win streak')).toBe('win streak')
  })

  it('removes dingbat / symbol icons (✓ ✗ ⚠ ★)', () => {
    expect(stripDecorativeUnicode('✓ ok ✗ fail ⚠ careful ★ great')).toBe('ok fail careful great')
  })

  it('removes color variation selectors', () => {
    // ⚠️ is U+26A0 + U+FE0F. After strip, both gone.
    expect(stripDecorativeUnicode('warning ⚠️ here')).toBe('warning here')
  })

  it('preserves dashes, middle dot, curly quotes', () => {
    const s = 'FLAME — measured · "patient" – never glib'
    expect(stripDecorativeUnicode(s)).toBe(s)
  })

  it('preserves accented Latin and currency / math symbols', () => {
    expect(stripDecorativeUnicode('±$1,200 résumé ÷')).toBe('±$1,200 résumé ÷')
  })

  it('handles null / empty', () => {
    expect(stripDecorativeUnicode(null)).toBe('')
    expect(stripDecorativeUnicode(undefined)).toBe('')
    expect(stripDecorativeUnicode('')).toBe('')
  })

  it('collapses double spaces left behind by stripped emojis', () => {
    expect(stripDecorativeUnicode('FLAME  🔥  measured')).toBe('FLAME measured')
  })
})
