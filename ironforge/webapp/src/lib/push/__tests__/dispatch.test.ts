import { describe, it, expect, beforeEach, vi } from 'vitest'
import type { NotificationEvent } from '@/lib/push/types'

/** In-memory stand-ins for the three tables dispatch touches. */
const state = {
  prefs: new Map<string, Record<string, boolean>>(),
  devices: new Map<string, Array<{ id: string; expo_push_token: string }>>(),
  claimed: new Map<string, string | null>(), // `${eventKey}|${userId}` -> state
  approvalStatus: 'pending' as string,
  approvalExpired: false,
  connectionStatus: 'disconnected' as string,
}

const sent: Array<{ to: string; title: string; body: string }> = []

vi.mock('@/lib/push/transport', () => ({
  isPushConfigured: () => true,
  isExpoPushToken: (t: string) => t.startsWith('ExponentPushToken['),
  isDeviceGone: () => false,
  sendExpoPush: async (msgs: Array<{ to: string; title: string; body: string }>) => {
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
    if (sql.includes('FROM trade_approvals')) {
      return [{ status: state.approvalStatus, expired: state.approvalExpired }]
    }
    if (sql.includes('FROM brokerage_connections')) {
      return [{ status: state.connectionStatus }]
    }
    if (sql.includes('INSERT INTO notification_events')) {
      const [eventKey, userId, , newState] = params as [string, string, string, string | null]
      const k = `${eventKey}|${userId}`
      const had = state.claimed.has(k)
      const prev = state.claimed.get(k) ?? null
      if (!had) {
        state.claimed.set(k, newState ?? null)
        return [{ event_key: eventKey }]
      }
      // Conflict. State-carrying rows notify only on an actual change.
      if (newState != null && prev !== newState) {
        state.claimed.set(k, newState)
        return [{ event_key: eventKey }]
      }
      return []
    }
    return []
  },
}))

const { dispatchToCustomers } = await import('@/lib/push/dispatch')

const USER = 'user-1'
const NOW = Date.parse('2026-08-02T18:00:00.000Z')

function evt(over: Partial<NotificationEvent> = {}): NotificationEvent {
  return {
    category: 'trade_closed',
    eventKey: 'trade_close:spark:1DTE:POS-1',
    occurredAt: new Date(NOW).toISOString(),
    route: '/live',
    title: 'Spark closed a trade',
    body: 'Open IronForge to see the result.',
    amount: 100,
    ...over,
  }
}

beforeEach(() => {
  state.prefs.clear()
  state.devices.clear()
  state.claimed.clear()
  state.approvalStatus = 'pending'
  state.approvalExpired = false
  state.connectionStatus = 'disconnected'
  sent.length = 0
  state.devices.set(USER, [{ id: 'dev-1', expo_push_token: 'ExponentPushToken[abc]' }])
})

describe('dedupe — once per eligible event (APP-033)', () => {
  it('sends the first time and skips every repeat', async () => {
    const a = await dispatchToCustomers(evt(), [USER], NOW)
    expect(a.sent).toBe(1)

    const b = await dispatchToCustomers(evt(), [USER], NOW)
    expect(b.sent).toBe(0)
    expect(b.reasons).toContain('duplicate')
    expect(sent).toHaveLength(1)
  })
})

describe('staleness — no alert long after the fact (APP-034)', () => {
  it('drops an event older than its category allows', async () => {
    // trade_closed tolerates 900s; this is 20 minutes late, the "dispatch retried
    // much later" case a transition check alone cannot catch.
    const late = NOW + 1200 * 1000
    const r = await dispatchToCustomers(evt(), [USER], late)
    expect(r.sent).toBe(0)
    expect(r.reasons).toContain('stale')
    expect(sent).toHaveLength(0)
  })

  it('holds approvals to the tighter 5-minute window', async () => {
    const r = await dispatchToCustomers(
      evt({ category: 'trade_approval', eventKey: 'trade_approval:a1' }),
      [USER],
      NOW + 400 * 1000,
    )
    expect(r.sent).toBe(0)
    expect(r.reasons).toContain('stale')
  })
})

describe('re-read at SEND time — no alert after recovery (APP-035)', () => {
  it('drops a brokerage alert when the connection is healthy again', async () => {
    state.connectionStatus = 'active'
    const r = await dispatchToCustomers(
      evt({
        category: 'brokerage_health',
        eventKey: 'brokerage_health:conn-1',
        routeParams: { connectionId: 'conn-1' },
        state: 'degraded',
      }),
      [USER],
      NOW,
    )
    expect(r.sent).toBe(0)
    expect(r.reasons).toContain('condition_resolved')
  })

  it('drops an approval push once the approval is no longer pending', async () => {
    state.approvalStatus = 'approved'
    const r = await dispatchToCustomers(
      evt({
        category: 'trade_approval',
        eventKey: 'trade_approval:a2',
        routeParams: { approvalId: 'a2' },
      }),
      [USER],
      NOW,
    )
    expect(r.sent).toBe(0)
    expect(r.reasons).toContain('condition_resolved')
  })
})

describe('state transitions', () => {
  it('notifies on ok -> degraded but stays silent on degraded -> degraded', async () => {
    const base = {
      category: 'brokerage_health' as const,
      eventKey: 'brokerage_health:conn-9',
      routeParams: { connectionId: 'conn-9' },
    }
    const first = await dispatchToCustomers(evt({ ...base, state: 'degraded' }), [USER], NOW)
    expect(first.sent).toBe(1)

    const repeat = await dispatchToCustomers(evt({ ...base, state: 'degraded' }), [USER], NOW)
    expect(repeat.sent).toBe(0)
    expect(repeat.reasons).toContain('duplicate')
  })
})

describe('preferences and devices', () => {
  it('respects a category the customer switched off', async () => {
    state.prefs.set(USER, {
      trade_opened: true,
      trade_closed: false,
      trade_approval: true,
      brokerage_health: true,
      billing: true,
      community: false,
      show_amounts_on_lockscreen: false,
    })
    const r = await dispatchToCustomers(evt(), [USER], NOW)
    expect(r.sent).toBe(0)
    expect(r.reasons).toContain('pref_off')
  })

  it('redacts money by default and reveals it only on opt-in', async () => {
    await dispatchToCustomers(evt(), [USER], NOW)
    expect(sent[0].body).not.toMatch(/\$/)

    state.prefs.set(USER, {
      trade_opened: true,
      trade_closed: true,
      trade_approval: true,
      brokerage_health: true,
      billing: true,
      community: false,
      show_amounts_on_lockscreen: true,
    })
    await dispatchToCustomers(evt({ eventKey: 'trade_close:other' }), [USER], NOW)
    expect(sent[1].body).toContain('$100.00')
  })

  it('never touches another customer\'s devices', async () => {
    state.devices.set('user-2', [{ id: 'dev-2', expo_push_token: 'ExponentPushToken[zzz]' }])
    await dispatchToCustomers(evt(), [USER], NOW)
    expect(sent.map((m) => m.to)).toEqual(['ExponentPushToken[abc]'])
  })

  it('skips cleanly when the customer has no registered device', async () => {
    state.devices.set(USER, [])
    const r = await dispatchToCustomers(evt(), [USER], NOW)
    expect(r.sent).toBe(0)
    expect(r.reasons).toContain('no_device')
  })
})
