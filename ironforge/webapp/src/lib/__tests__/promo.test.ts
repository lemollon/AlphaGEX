import { describe, it, expect } from 'vitest'
import { lookupPromo, isValidPromo, normalizePromo } from '../promo'

describe('promo', () => {
  it('recognises FORGE50 case-insensitively and trims', () => {
    for (const raw of ['FORGE50', 'forge50', '  Forge50 ']) {
      const p = lookupPromo(raw)
      expect(p).not.toBeNull()
      expect(p!.code).toBe('FORGE50')
      expect(p!.bots).toBe(2)
      expect(p!.price).toBe(50)
    }
  })

  it('rejects unknown / empty codes', () => {
    for (const raw of ['', '   ', 'NOPE', null, undefined]) {
      expect(lookupPromo(raw)).toBeNull()
      expect(isValidPromo(raw)).toBe(false)
    }
  })

  it('normalizes to upper-trimmed', () => {
    expect(normalizePromo('  forge50 ')).toBe('FORGE50')
    expect(normalizePromo(null)).toBe('')
  })
})
