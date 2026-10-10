import { describe, it, expect, beforeEach, vi } from 'vitest'
import { buildTradeOpenedEvent, buildTradeClosedEvent } from '@/lib/push/trade-events'

/**
 * In-memory stand-ins for the tables dispatch touches — same pattern as
 * dispatch.test.ts. Declared (and mocked) at module scope, not inside a
 * describe block: vi.mock factories are hoisted above the rest of the file,
 * so a factory closing over a variable declared inside a describe callback
 * throws "state is not defined" at import time.
 */
const state = {
  prefs: new Map<string, Record<string, boolean>>(),
  devices: new Map<string, Array<{ id: string; expo_push_token: string }>>(),
  claimed: new Map<string, string | null>(),
}
const sent: Array<{ to: string; title: string; subtitle?: string }> = []

vi.mock('@/lib/push/transport', () => ({
  isPushConfigured: () => true,
  isExpoPushToken: (t: string) => t.startsWith('ExponentPushToken['),
  isDeviceGone: () => false,
  sendExpoPush: async (msgs: Array<{ to: string; title: string; subtitle?: string }>) => {
    sent.push(...msgs)
    return msgs.map(() => ({ status: 'ok' as const, id: 'ticket' }))
  },
}))

vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: () => true,
  customerExecute: async () => 0,
  customerQuery: async (sql: string, params: unknown[] = []) => {
    if (sql.includes('FROM notification_prefs')) {
      const p = state.prefs.get(params[0] as string)
      return p ? [p] : []
    }
    if (sql.includes('FROM push_devices')) {
      return state.devices.get(params[0] as string) ?? []
    }
    if (sql.includes('INSERT INTO notification_events')) {
      const [eventKey, userId] = params as [string, string]
      const k = `${eventKey}|${userId}`
      if (state.claimed.has(k)) return []
      state.claimed.set(k, null)
      return [{ event_key: eventKey }]
    }
    return []
  },
}))

const { dispatchToCustomers } = await import('@/lib/push/dispatch')

describe('buildTradeOpenedEvent — copy (UAT #7)', () => {
  it('matches the approved copy exactly', () => {
    const evt = buildTradeOpenedEvent({
      bot: 'flame',
      positionId: 'FLAME-SPY-20260904-ABC123',
      occurredAt: '2026-09-04T14:00:00.000Z',
    })
    expect(evt.title).toBe('Trade Opened')
    expect(evt.subtitle).toBe('🔥 Flame entered a new position')
    expect(evt.body).toBe("Trade is live. We'll handle it from here.")
  })

  it('carries the right mascot and label per agent', () => {
    const spark = buildTradeOpenedEvent({
      bot: 'spark',
      positionId: 'SPARK-SPY-20260904-XYZ789',
      occurredAt: '2026-09-04T14:00:00.000Z',
    })
    expect(spark.subtitle).toBe('⚡ Spark entered a new position')
  })

  it('deep-links to the agent page, never the (not-yet-closed) trade detail page', () => {
    const evt = buildTradeOpenedEvent({
      bot: 'flame',
      positionId: 'FLAME-SPY-20260904-ABC123',
      occurredAt: '2026-09-04T14:00:00.000Z',
    })
    expect(evt.route).toBe('/live')
    expect(evt.routeParams).toEqual({ account: 'flame' })
    // No tradeId: /api/live/trades/{id} only ever serves CLOSED trades — a tradeId
    // here would 404 on tap before the position closes.
    expect(evt.routeParams?.tradeId).toBeUndefined()
  })

  it('derives the dedupe key from the position id alone, not a timestamp', () => {
    const a = buildTradeOpenedEvent({
      bot: 'flame',
      positionId: 'FLAME-SPY-20260904-ABC123',
      occurredAt: '2026-09-04T14:00:00.000Z',
    })
    const b = buildTradeOpenedEvent({
      bot: 'flame',
      positionId: 'FLAME-SPY-20260904-ABC123',
      occurredAt: '2026-09-04T14:05:00.000Z', // a retry, five minutes later
    })
    expect(a.eventKey).toBe(b.eventKey)
    expect(a.eventKey).toBe('trade_opened:FLAME-SPY-20260904-ABC123')
  })
})

describe('buildTradeClosedEvent — copy and sign (UAT #7)', () => {
  it('matches the approved copy exactly for a winner', () => {
    const evt = buildTradeClosedEvent({
      bot: 'flame',
      positionId: 'FLAME-SPY-20260904-ABC123',
      realizedPnl: 36,
      occurredAt: '2026-09-04T20:00:00.000Z',
    })
    expect(evt.title).toBe('Trade Closed')
    expect(evt.subtitle).toBe('✅ Flame closed +$36.00')
    expect(evt.body).toBe('Position exited successfully and added to your Ledger.')
    expect(evt.amount).toBe(36)
  })

  it('uses the typographic minus (U+2212), not the ASCII hyphen, for a loser', () => {
    const evt = buildTradeClosedEvent({
      bot: 'flame',
      positionId: 'FLAME-SPY-20260904-ABC123',
      realizedPnl: -42.5,
      occurredAt: '2026-09-04T20:00:00.000Z',
    })
    expect(evt.subtitle).toBe('✅ Flame closed −$42.50')
    expect(evt.subtitle).not.toContain('-$42.50')
  })

  it('deep-links to the trade ledger detail, since this trade is now closed', () => {
    const evt = buildTradeClosedEvent({
      bot: 'spark',
      positionId: 'SPARK-SPY-20260904-XYZ789',
      realizedPnl: 12,
      occurredAt: '2026-09-04T20:00:00.000Z',
    })
    expect(evt.route).toBe('/live')
    expect(evt.routeParams).toEqual({ account: 'spark', tradeId: 'SPARK-SPY-20260904-XYZ789' })
  })

  it('derives the dedupe key from the position id alone, not a timestamp', () => {
    const a = buildTradeClosedEvent({
      bot: 'flame',
      positionId: 'FLAME-SPY-20260904-ABC123',
      realizedPnl: 36,
      occurredAt: '2026-09-04T20:00:00.000Z',
    })
    const b = buildTradeClosedEvent({
      bot: 'flame',
      positionId: 'FLAME-SPY-20260904-ABC123',
      realizedPnl: 36,
      occurredAt: '2026-09-04T20:03:00.000Z', // a retry
    })
    expect(a.eventKey).toBe(b.eventKey)
    expect(a.eventKey).toBe('trade_closed:FLAME-SPY-20260904-ABC123')
  })
})

/**
 * End-to-end through the real dispatch/dedupe path (not just the eventKey in
 * isolation): a scanner retry on the SAME closed position must still deliver
 * exactly one push.
 */
describe('close fires exactly one trade_closed per trade (dedupe)', () => {
  beforeEach(() => {
    state.prefs.clear()
    state.devices.clear()
    state.claimed.clear()
    sent.length = 0
    state.devices.set('user-1', [{ id: 'dev-1', expo_push_token: 'ExponentPushToken[abc]' }])
  })

  it('a retried close dispatch for the same position sends only once', async () => {
    const args = {
      bot: 'flame' as const,
      positionId: 'FLAME-SPY-20260904-ABC123',
      realizedPnl: 36,
      occurredAt: '2026-09-04T20:00:00.000Z',
    }
    const NOW = Date.parse(args.occurredAt)

    const first = await dispatchToCustomers(buildTradeClosedEvent(args), ['user-1'], NOW)
    expect(first.sent).toBe(1)

    // Scanner retry: same position, a few seconds later — same eventKey.
    const retry = await dispatchToCustomers(
      buildTradeClosedEvent({ ...args, occurredAt: '2026-09-04T20:00:05.000Z' }),
      ['user-1'],
      NOW + 5000,
    )
    expect(retry.sent).toBe(0)
    expect(retry.reasons).toContain('duplicate')
    expect(sent).toHaveLength(1)
    expect(sent[0].subtitle).toBe('✅ Flame closed +$36.00')
  })
})
