import { describe, it, expect } from 'vitest'
import { brokerLabel, health, soleConnection } from '@/api/brokerage'
import type { BrokerageConnections } from '@/api/types'

function conn(over: Partial<BrokerageConnections['connections'][number]> = {}) {
  return {
    id: 'c1',
    provider: 'snaptrade',
    authorization_id: 'auth-1',
    broker: 'tradier',
    status: 'active',
    connected_on: '2026-08-01',
    last_synced_at: null,
    accounts: [{ id: 'a1', mask: '4821', eligibility: null, ineligible_reason: null, buying_power_cents: null }],
    ...over,
  }
}

function payload(...connections: ReturnType<typeof conn>[]): BrokerageConnections {
  return { ok: true, configured: true, connections }
}

describe('brokerLabel', () => {
  it('names the real institution, not the aggregator', () => {
    // UAT-012 was exactly this: every SnapTrade link got labelled with the aggregator.
    expect(brokerLabel('tastytrade')).toBe('Tastytrade')
    expect(brokerLabel('tradier')).toBe('Tradier')
  })

  it('title-cases an unknown slug instead of printing it raw', () => {
    expect(brokerLabel('some_new_broker')).toBe('Some New Broker')
    expect(brokerLabel('ALPACA')).toBe('Alpaca')
  })

  it('falls back to a neutral word rather than blank', () => {
    expect(brokerLabel(null)).toBe('Brokerage')
    expect(brokerLabel('')).toBe('Brokerage')
  })
})

describe('health — fails toward "look at this", never toward healthy', () => {
  it('recognises the healthy statuses', () => {
    for (const s of ['active', 'connected', 'ok', 'ACTIVE']) {
      expect(health(s).key).toBe('connected')
    }
  })

  it('maps the explicit bad states', () => {
    expect(health('disconnected').key).toBe('disconnected')
    expect(health('revoked').key).toBe('disconnected')
    expect(health('expired').key).toBe('disconnected')
    expect(health('restricted').key).toBe('restricted')
  })

  it('treats an UNKNOWN status as needing attention, not as connected', () => {
    // The point of the default. A status invented server-side later must never render
    // as a green "Connected" dot on a brokerage the bot can no longer reach.
    for (const s of ['pending', 'weird_new_state', '', undefined, null]) {
      expect(health(s as string).key).not.toBe('connected')
      expect(health(s as string).key).toBe('attention')
    }
  })
})

describe('soleConnection — never guesses which account belongs to an agent', () => {
  it('attributes the connection when there is exactly one', () => {
    const r = soleConnection(payload(conn()))
    expect(r).not.toBeNull()
    expect(r!.broker).toBe('tradier')
    expect(r!.mask).toBe('4821')
  })

  it('returns null with TWO connections rather than picking one', () => {
    // Showing the wrong account number under an agent on a trading dashboard is worse
    // than showing none.
    expect(soleConnection(payload(conn(), conn({ id: 'c2', broker: 'tastytrade' })))).toBeNull()
  })

  it('returns null with no connections and with no payload', () => {
    expect(soleConnection(payload())).toBeNull()
    expect(soleConnection(undefined)).toBeNull()
  })

  it('withholds the mask when one connection has several accounts', () => {
    const r = soleConnection(
      payload(
        conn({
          accounts: [
            { id: 'a1', mask: '4821', eligibility: null, ineligible_reason: null, buying_power_cents: null },
            { id: 'a2', mask: '7734', eligibility: null, ineligible_reason: null, buying_power_cents: null },
          ],
        }),
      ),
    )
    expect(r).not.toBeNull()
    expect(r!.mask).toBeNull()
  })
})
