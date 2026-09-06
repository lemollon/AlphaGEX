import { describe, it, expect } from 'vitest'
import { color as darkTokens } from './tokens'
import { dark, light, getPalette, resolveScheme, resolveTone, type ColorTokens } from './palette'

const TOKEN_KEYS: (keyof ColorTokens)[] = [
  'bg',
  'card',
  'surface',
  'surfaceRaised',
  'border',
  'muted',
  'textMuted',
  'wordmark',
  'accent',
  'spark',
  'flame',
  'pos',
  'positive',
  'neg',
  'negative',
  'warn',
  'warning',
  'text',
  'textDim',
  'tabBar',
]

describe('dark palette', () => {
  it('is pixel-identical to theme/tokens.ts color — the brand default must not move', () => {
    expect(dark.bg).toBe(darkTokens.bg)
    expect(dark.card).toBe(darkTokens.card)
    expect(dark.border).toBe(darkTokens.border)
    expect(dark.muted).toBe(darkTokens.muted)
    expect(dark.wordmark).toBe(darkTokens.wordmark)
    expect(dark.accent).toBe(darkTokens.accent)
    expect(dark.spark).toBe(darkTokens.spark)
    expect(dark.flame).toBe(darkTokens.flame)
    expect(dark.pos).toBe(darkTokens.pos)
    expect(dark.neg).toBe(darkTokens.neg)
    expect(dark.warn).toBe(darkTokens.warn)
    expect(dark.text).toBe(darkTokens.text)
    expect(dark.textDim).toBe(darkTokens.textDim)
  })

  it('defines every token', () => {
    for (const key of TOKEN_KEYS) {
      expect(dark[key], `dark.${key}`).toBeTruthy()
      expect(dark[key]).toMatch(/^#[0-9A-Fa-f]{6}$/)
    }
  })
})

describe('light palette', () => {
  it('defines every token', () => {
    for (const key of TOKEN_KEYS) {
      expect(light[key], `light.${key}`).toBeTruthy()
      expect(light[key]).toMatch(/^#[0-9A-Fa-f]{6}$/)
    }
  })

  it('keeps the wordmark and accent orange unchanged from dark', () => {
    expect(light.wordmark).toBe(dark.wordmark)
    expect(light.accent).toBe(dark.accent)
  })

  it('has near-white backgrounds and near-black text', () => {
    expect(light.bg.toUpperCase()).not.toBe(dark.bg.toUpperCase())
    expect(light.card.toUpperCase()).toBe('#FFFFFF')
    expect(light.text.toUpperCase()).not.toBe('#FFFFFF')
  })

  it('is a genuinely different palette from dark, not a relabeled copy', () => {
    expect(light.pos).not.toBe(dark.pos)
    expect(light.neg).not.toBe(dark.neg)
    expect(light.text).not.toBe(dark.text)
  })
})

/** WCAG 2 relative luminance / contrast ratio, straight from the spec. */
function luminance(hex: string): number {
  const n = hex.replace('#', '')
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(n.slice(i, i + 2), 16) / 255)
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}

function contrastRatio(hex1: string, hex2: string): number {
  const l1 = luminance(hex1)
  const l2 = luminance(hex2)
  const lighter = Math.max(l1, l2)
  const darker = Math.min(l1, l2)
  return (lighter + 0.05) / (darker + 0.05)
}

describe('light palette WCAG AA text contrast (>= 4.5:1 on white card)', () => {
  const white = '#FFFFFF'
  it.each([
    ['text', light.text],
    ['textDim', light.textDim],
    ['muted', light.muted],
    ['pos', light.pos],
    ['neg', light.neg],
    ['warn', light.warn],
    ['spark', light.spark],
    ['flame', light.flame],
  ])('%s clears 4.5:1 against a white card', (_name, hex) => {
    expect(contrastRatio(hex, white)).toBeGreaterThanOrEqual(4.5)
  })
})

describe('getPalette', () => {
  it('returns dark for scheme "dark"', () => {
    expect(getPalette('dark')).toBe(dark)
  })
  it('returns light for scheme "light"', () => {
    expect(getPalette('light')).toBe(light)
  })
})

describe('resolveScheme — preference x system scheme -> palette', () => {
  it('an explicit "dark" preference always resolves to dark, regardless of system', () => {
    expect(resolveScheme('dark', 'light')).toBe('dark')
    expect(resolveScheme('dark', 'dark')).toBe('dark')
    expect(resolveScheme('dark', null)).toBe('dark')
  })

  it('an explicit "light" preference always resolves to light, regardless of system', () => {
    expect(resolveScheme('light', 'dark')).toBe('light')
    expect(resolveScheme('light', 'light')).toBe('light')
    expect(resolveScheme('light', null)).toBe('light')
  })

  it('"system" follows the OS scheme', () => {
    expect(resolveScheme('system', 'light')).toBe('light')
    expect(resolveScheme('system', 'dark')).toBe('dark')
  })

  it('"system" with an unknown OS scheme falls back to dark, never light', () => {
    expect(resolveScheme('system', null)).toBe('dark')
    expect(resolveScheme('system', undefined)).toBe('dark')
  })
})

describe('resolveTone', () => {
  it('is the identity function in dark scheme', () => {
    expect(resolveTone(dark.pos, 'dark')).toBe(dark.pos)
    expect(resolveTone('#000000', 'dark')).toBe('#000000')
  })

  it('translates a dark-canonical hex to its light equivalent', () => {
    expect(resolveTone(dark.pos, 'light')).toBe(light.pos)
    expect(resolveTone(dark.neg, 'light')).toBe(light.neg)
    expect(resolveTone(dark.warn, 'light')).toBe(light.warn)
    expect(resolveTone(dark.text, 'light')).toBe(light.text)
    expect(resolveTone(dark.textDim, 'light')).toBe(light.textDim)
  })

  it('passes an unrecognized hex through unchanged in light scheme', () => {
    expect(resolveTone('#123456', 'light')).toBe('#123456')
  })

  it('accent and wordmark are unchanged either way (same value in both palettes)', () => {
    expect(resolveTone(dark.accent, 'light')).toBe(light.accent)
    expect(resolveTone(dark.wordmark, 'light')).toBe(light.wordmark)
  })
})
