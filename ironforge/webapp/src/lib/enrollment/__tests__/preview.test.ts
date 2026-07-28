import { describe, it, expect } from 'vitest'
import { previewHash, isPreviewFresh, PREVIEW_TTL_MS, type ActivationSnapshot } from '../preview'

const SNAP: ActivationSnapshot = {
  userId: 'u1',
  brokerAccountId: 'ba1',
  accountMask: '••••6411',
  agentCode: 'spark',
  ruleVersion: '1.0',
  maxDeploymentCents: 500000,
  buyingPowerCents: 1200000,
  legalVersions: ['TERMS@1.0', 'RISK@1.0', 'TRADING_AUTH@1.0', 'ELECTRONIC_CONSENT@1.0'],
}

describe('activation preview hash (§3 ACT-01, §4)', () => {
  it('is stable for identical snapshots', () => {
    expect(previewHash(SNAP)).toBe(previewHash({ ...SNAP }))
  })

  it('does NOT depend on legal version ORDER — only on the set', () => {
    const shuffled = { ...SNAP, legalVersions: [...SNAP.legalVersions].reverse() }
    expect(previewHash(shuffled)).toBe(previewHash(SNAP))
  })

  it.each([
    ['a different account', { brokerAccountId: 'ba2' }],
    ['a different agent', { agentCode: 'flame' }],
    ['a bumped rule version', { ruleVersion: '1.1' }],
    ['a changed capital limit', { maxDeploymentCents: 600000 }],
    ['MOVED BUYING POWER', { buyingPowerCents: 900000 }],
    ['a re-accepted legal version', { legalVersions: [...SNAP.legalVersions.slice(1), 'TERMS@1.1'] }],
  ])('changes when %s', (_label, patch) => {
    expect(previewHash({ ...SNAP, ...patch })).not.toBe(previewHash(SNAP))
  })

  it('buying power in the hash is what makes §4 "requires a fresh confirmation" automatic', () => {
    // The customer consented to a snapshot that said $12,000 of buying power. If it
    // moved before they hit Activate, the hash no longer matches and the predicate
    // reports PREVIEW_STALE rather than activating against different numbers.
    const before = previewHash(SNAP)
    const after = previewHash({ ...SNAP, buyingPowerCents: 300000 })
    expect(after).not.toBe(before)
  })

  it('never contains a full account number — only the mask goes in', () => {
    const h = previewHash(SNAP)
    expect(h).not.toContain('6411')
    expect(h).toMatch(/^[0-9a-f]{32}$/)
  })
})

describe('preview freshness', () => {
  it('is 10 minutes', () => {
    expect(PREVIEW_TTL_MS).toBe(10 * 60 * 1000)
  })

  it('accepts a just-issued preview and rejects an aged one', () => {
    const now = 1_000_000_000
    expect(isPreviewFresh(now, now)).toBe(true)
    expect(isPreviewFresh(now - PREVIEW_TTL_MS + 1, now)).toBe(true)
    expect(isPreviewFresh(now - PREVIEW_TTL_MS - 1, now)).toBe(false)
  })
})
