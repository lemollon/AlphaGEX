import { describe, it, expect } from 'vitest'
import { routeFor } from '@/notifications/route-for'

const hrefs = {
  tradeDetailHref: (id: string) => `/trade/${id}`,
  agentDetailHref: (bot: 'spark' | 'flame') => `/agents/${bot}`,
}

describe('routeFor', () => {
  it('routes a trade payload to the trade detail screen', () => {
    expect(routeFor({ trade_id: 'POS-1' }, hrefs)).toBe('/trade/POS-1')
  })

  it('routes an agent payload to the agent detail screen', () => {
    expect(routeFor({ agent: 'spark' }, hrefs)).toBe('/agents/spark')
    expect(routeFor({ agent: 'flame' }, hrefs)).toBe('/agents/flame')
  })

  it('routes brokerage and billing kinds to the account tab', () => {
    expect(routeFor({ kind: 'brokerage' }, hrefs)).toBe('/account')
    expect(routeFor({ kind: 'billing' }, hrefs)).toBe('/account')
  })

  it('prefers trade_id over agent when a payload carries both', () => {
    expect(routeFor({ trade_id: 'POS-9', agent: 'flame' }, hrefs)).toBe('/trade/POS-9')
  })

  it('prefers agent over kind when a payload carries both', () => {
    expect(routeFor({ agent: 'spark', kind: 'billing' }, hrefs)).toBe('/agents/spark')
  })

  it('returns null for an unrecognized or empty payload', () => {
    expect(routeFor(null, hrefs)).toBeNull()
    expect(routeFor(undefined, hrefs)).toBeNull()
    expect(routeFor({}, hrefs)).toBeNull()
    expect(routeFor({ kind: 'community' }, hrefs)).toBeNull()
  })

  it('ignores a malformed trade_id or agent rather than throwing', () => {
    expect(routeFor({ trade_id: 42 }, hrefs)).toBeNull()
    expect(routeFor({ trade_id: '' }, hrefs)).toBeNull()
    expect(routeFor({ agent: 'ares' }, hrefs)).toBeNull()
  })
})
