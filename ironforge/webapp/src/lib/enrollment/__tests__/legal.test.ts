import { describe, it, expect } from 'vitest'
import { requiredDocumentsFor, staleDocumentCodes, LEGAL_DOCUMENTS } from '../legal'
import { nextStepFor } from '../service'
import { CUSTOMER_API_PREFIXES } from '@/lib/surface'
import { isPublicPath } from '@/lib/auth/access'

describe('required documents by plan (§3 LEGAL-01)', () => {
  it('Community gets CORE only — never a trading authorization it cannot use', () => {
    const codes = requiredDocumentsFor('community').map((d) => d.code)
    expect(codes).toEqual(['TERMS', 'RISK'])
    expect(codes).not.toContain('TRADING_AUTH')
    expect(codes).not.toContain('ELECTRONIC_CONSENT')
  })

  it('Automate plans add electronic consent + trading authorization (mandatory)', () => {
    for (const plan of ['spark', 'flame', 'both']) {
      const codes = requiredDocumentsFor(plan).map((d) => d.code)
      expect(codes).toContain('TRADING_AUTH')
      expect(codes).toContain('ELECTRONIC_CONSENT')
      expect(codes).toContain('TERMS')
      expect(codes).toContain('RISK')
    }
  })

  it('an unknown/absent plan falls back to CORE, never to the automate set', () => {
    expect(requiredDocumentsFor(null).map((d) => d.code)).toEqual(['TERMS', 'RISK'])
    expect(requiredDocumentsFor('nonsense').map((d) => d.code)).toEqual(['TERMS', 'RISK'])
  })

  it('every document carries a version and a content URI', () => {
    for (const d of LEGAL_DOCUMENTS) {
      expect(d.version).toMatch(/^\d+\.\d+$/)
      expect(d.contentUri.startsWith('/')).toBe(true)
    }
  })
})

describe('acceptance staleness (§11 "return to affected document only")', () => {
  const all = (plan: string) => requiredDocumentsFor(plan).map((d) => ({ code: d.code, version: d.version }))

  it('fully accepted current versions leave nothing outstanding', () => {
    expect(staleDocumentCodes('spark', all('spark'))).toEqual([])
  })

  it('an OLD version does not satisfy the requirement', () => {
    const accepted = all('spark').map((a) => (a.code === 'TERMS' ? { ...a, version: '0.9' } : a))
    expect(staleDocumentCodes('spark', accepted)).toEqual(['TERMS'])
  })

  it('a bump to ONE document does not invalidate the others', () => {
    const accepted = all('spark').map((a) => (a.code === 'RISK' ? { ...a, version: '0.1' } : a))
    const stale = staleDocumentCodes('spark', accepted)
    expect(stale).toEqual(['RISK'])
    expect(stale).not.toContain('TERMS')
    expect(stale).not.toContain('TRADING_AUTH')
  })

  it('switching Community → Automate reopens ONLY the newly required documents (§12)', () => {
    const asCommunity = all('community')          // TERMS + RISK accepted
    expect(staleDocumentCodes('community', asCommunity)).toEqual([])
    // Same acceptances, now on an automate plan:
    expect(staleDocumentCodes('spark', asCommunity)).toEqual(['ELECTRONIC_CONSENT', 'TRADING_AUTH'])
  })

  it('switching Automate → Community does not re-ask for anything', () => {
    expect(staleDocumentCodes('community', all('spark'))).toEqual([])
  })

  it('accepting nothing leaves every required document outstanding', () => {
    expect(staleDocumentCodes('spark', [])).toHaveLength(4)
  })
})

describe('resumable next step (§3 DONE-01)', () => {
  it.each([
    ['draft', 'plan'],
    ['legal_pending', 'legal'],
    ['billing_pending', 'billing'],
    ['setup_required', 'setup'],
    ['complete', 'done'],
  ])('%s → %s', (status, expected) => {
    expect(nextStepFor({ status: status as never, selected_plan: 'spark' })).toBe(expected)
  })
})

describe('route wiring', () => {
  it('/api/v1/ is served on the customer surface', () => {
    expect(CUSTOMER_API_PREFIXES).toContain('/api/v1/')
  })

  it('and is NOT public — every enrollment route needs a session', () => {
    expect(isPublicPath('/api/v1/enrollments')).toBe(false)
    expect(isPublicPath('/api/v1/enrollments/abc/legal')).toBe(false)
  })
})
