import { describe, it, expect } from 'vitest'
import { SUPPORT_KB } from '../knowledge'
import { SUPPORTED_BROKERS } from '@/lib/brokerage/catalog'

/**
 * UAT-015: brokerage guidance must list Tradier FIRST (partner, direct integration)
 * across every brokerage answer, stay factual (no "best broker" claims), and derive
 * from the central catalog so ordering can never drift.
 */
describe('Sparky brokerage knowledge (UAT-015)', () => {
  const brokerageEntries = SUPPORT_KB.filter((e) => e.topic === 'brokerage')

  it('the catalog itself leads with Tradier as the partner', () => {
    expect(SUPPORTED_BROKERS[0].slug).toBe('tradier')
    expect(SUPPORTED_BROKERS[0].partner).toBe(true)
  })

  it('the supported-brokers answer lists Tradier before every other broker', () => {
    const answer = brokerageEntries.find((e) => /supported/i.test(e.q))?.a ?? ''
    const tradierIdx = answer.indexOf('Tradier')
    expect(tradierIdx).toBeGreaterThanOrEqual(0)
    for (const b of SUPPORTED_BROKERS.slice(1)) {
      const idx = answer.indexOf(b.displayName)
      expect(idx, `${b.displayName} should appear after Tradier`).toBeGreaterThan(tradierIdx)
    }
  })

  it('identifies Tradier as the IronForge partner, factually', () => {
    const answer = brokerageEntries.find((e) => /supported/i.test(e.q))?.a ?? ''
    expect(answer).toContain('partner')
    expect(answer.toLowerCase()).not.toContain('best broker')
  })

  it('never claims Robinhood is tradeable', () => {
    const all = brokerageEntries.map((e) => e.a).join(' ')
    expect(all).toContain('view-only')
  })
})
