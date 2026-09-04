import { describe, it, expect } from 'vitest'
import { pickBanner, bannerActionHref, type BannerInput } from '@/alerts/banner'
import type { LiveAgent } from '@/api/types'

function agent(bot: string, overrides: Partial<LiveAgent> = {}): LiveAgent {
  return {
    bot,
    label: bot === 'spark' ? 'Spark' : 'Flame',
    paper: false,
    state: null,
    account: null,
    trade: null,
    stats: null,
    error: null,
    ...overrides,
  }
}

const base: BannerInput = {
  connections: { ok: true, connections: [] },
  agents: [],
  membershipBadge: undefined,
  marketCondition: 'good',
  conditionLine: '',
}

describe('pickBanner', () => {
  it('returns null when everything is fine', () => {
    expect(pickBanner(base)).toBeNull()
  })

  it('brokerage disconnected beats everything else', () => {
    const r = pickBanner({
      ...base,
      connections: {
        ok: true,
        connections: [
          {
            id: '1',
            provider: 'snaptrade',
            authorization_id: 'a1',
            broker: 'Tastytrade',
            status: 'disconnected',
            connected_on: '2026-01-01',
            last_synced_at: null,
            accounts: [],
          },
        ],
      },
      agents: [agent('spark', { state: { key: 'BLOCKED' } as any })],
      membershipBadge: 'Payment due',
      marketCondition: 'no_trading',
    })
    expect(r?.severity).toBe('brokerage')
    expect(r?.dismissible).toBe(false)
  })

  it('BLOCKED beats ACTION_REQUIRED, payment, paused and market condition', () => {
    const r = pickBanner({
      ...base,
      agents: [
        agent('spark', { state: { key: 'BLOCKED', check_line: 'Account restricted.' } as any }),
        agent('flame', { state: { key: 'ACTION_REQUIRED' } as any }),
      ],
      membershipBadge: 'Payment due',
      marketCondition: 'no_trading',
    })
    expect(r?.severity).toBe('blocked')
    expect(r?.text).toBe('Account restricted.')
    expect(r?.action).toEqual({ label: 'View', target: 'agent', bot: 'spark' })
  })

  it('ACTION_REQUIRED beats payment, paused and market condition', () => {
    const r = pickBanner({
      ...base,
      agents: [agent('flame', { state: { key: 'ACTION_REQUIRED' } as any })],
      membershipBadge: 'Payment due',
      marketCondition: 'caution',
    })
    expect(r?.severity).toBe('action_required')
  })

  it('payment due beats paused and market condition', () => {
    const r = pickBanner({
      ...base,
      agents: [agent('spark', { state: { key: 'PAUSED' } as any })],
      membershipBadge: 'Payment due',
      marketCondition: 'caution',
    })
    expect(r?.severity).toBe('payment')
    expect(r?.action).toEqual({ label: 'Manage Billing', target: 'billing' })
  })

  it('paused beats market condition', () => {
    const r = pickBanner({
      ...base,
      agents: [agent('flame', { state: { key: 'PAUSED', check_line: 'Flame is paused.' } as any })],
      marketCondition: 'no_trading',
    })
    expect(r?.severity).toBe('paused')
    expect(r?.text).toBe('Flame is paused.')
  })

  it('no_trading beats caution', () => {
    const r = pickBanner({ ...base, marketCondition: 'no_trading', conditionLine: 'Market halted.' })
    expect(r?.severity).toBe('no_trading')
    expect(r?.dismissible).toBe(false)
  })

  it('caution is the lowest severity and is dismissible', () => {
    const r = pickBanner({ ...base, marketCondition: 'caution', conditionLine: 'Elevated volatility.' })
    expect(r?.severity).toBe('caution')
    expect(r?.dismissible).toBe(true)
  })
})

describe('bannerActionHref', () => {
  it('routes brokerage and billing actions to the Account tab', () => {
    expect(bannerActionHref({ label: '', target: 'brokerage' })).toBe('/account')
    expect(bannerActionHref({ label: '', target: 'billing' })).toBe('/account')
  })

  it('routes an agent action to that agent detail screen', () => {
    expect(bannerActionHref({ label: '', target: 'agent', bot: 'flame' })).toBe('/agents/flame')
  })
})
