import { describe, it, expect } from 'vitest'
import { agentAction } from '@/agents/eligibility'

describe('agentAction', () => {
  it('is Active when an unpaused activation exists', () => {
    const r = agentAction({
      bot: 'spark',
      entitlements: ['spark'],
      activations: [{ agent: 'spark', paused: false }],
      eligibleAccountCount: 1,
    })
    expect(r.kind).toBe('active')
  })

  it('is Paused when the activation is paused', () => {
    const r = agentAction({
      bot: 'spark',
      entitlements: ['spark'],
      activations: [{ agent: 'spark', paused: true }],
      eligibleAccountCount: 1,
    })
    expect(r.kind).toBe('paused')
  })

  it('is Setup Required when nothing eligible is connected, even with an entitlement', () => {
    const r = agentAction({
      bot: 'spark',
      entitlements: ['spark'],
      activations: [],
      eligibleAccountCount: 0,
    })
    expect(r.kind).toBe('setup_required')
  })

  it('is Switch when the other agent already owns the only eligible account', () => {
    const r = agentAction({
      bot: 'flame',
      entitlements: ['flame'],
      activations: [{ agent: 'spark', paused: false }],
      eligibleAccountCount: 1,
    })
    expect(r.kind).toBe('switch')
  })

  it('is NOT Switch when the other agent is only paused, not active', () => {
    const r = agentAction({
      bot: 'flame',
      entitlements: ['flame'],
      activations: [{ agent: 'spark', paused: true }],
      eligibleAccountCount: 1,
    })
    expect(r.kind).toBe('add')
  })

  it('is NOT Switch when there is a second eligible account free', () => {
    const r = agentAction({
      bot: 'flame',
      entitlements: ['flame'],
      activations: [{ agent: 'spark', paused: false }],
      eligibleAccountCount: 2,
    })
    expect(r.kind).toBe('add')
  })

  it('is Add when eligible and unowned, with no other agent in the way', () => {
    const r = agentAction({
      bot: 'spark',
      entitlements: ['spark'],
      activations: [],
      eligibleAccountCount: 1,
    })
    expect(r.kind).toBe('add')
  })

  it('is Add (not blocked client-side) when there is no entitlement yet — billing is the server blocker', () => {
    const r = agentAction({
      bot: 'spark',
      entitlements: [],
      activations: [],
      eligibleAccountCount: 1,
    })
    expect(r.kind).toBe('add')
  })

  it('Setup Required takes priority over Switch when nothing is eligible at all', () => {
    const r = agentAction({
      bot: 'flame',
      entitlements: ['flame'],
      activations: [{ agent: 'spark', paused: false }],
      eligibleAccountCount: 0,
    })
    expect(r.kind).toBe('setup_required')
  })
})
