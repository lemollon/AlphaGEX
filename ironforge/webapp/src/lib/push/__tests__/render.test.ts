import { describe, it, expect } from 'vitest'
import { renderNotification, CURRENCY_RE, formatAmount } from '@/lib/push/render'
import type { NotificationEvent, NotificationCategory } from '@/lib/push/types'

const CATEGORIES: NotificationCategory[] = [
  'trade_opened',
  'trade_closed',
  'trade_approval',
  'brokerage_health',
  'billing',
  'community',
]

function evt(over: Partial<NotificationEvent> = {}): NotificationEvent {
  return {
    category: 'trade_closed',
    eventKey: 'trade_close:spark:1DTE:POS-1',
    occurredAt: '2026-08-02T18:00:00.000Z',
    route: '/live',
    routeParams: { account: 'spark' },
    title: 'Spark closed today\'s trade',
    body: 'Open IronForge to see the result.',
    amount: 142.15,
    ...over,
  }
}

describe('lock-screen redaction (APP-035)', () => {
  // Asserted with a regex rather than a snapshot on purpose: a snapshot gets blessed
  // away the first time someone rewords the copy, and the property we care about
  // ("no money on a locked phone") would silently stop being checked.
  it.each(CATEGORIES)(
    'never puts currency in title/body for %s when the customer has not opted in',
    (category) => {
      const msg = renderNotification(evt({ category, amount: -1234.56 }), {
        showAmountsOnLockscreen: false,
      })
      expect(msg.title).not.toMatch(CURRENCY_RE)
      expect(msg.body).not.toMatch(CURRENCY_RE)
    },
  )

  it('shows the amount only when the customer explicitly opted in', () => {
    const msg = renderNotification(evt({ amount: 142.15 }), { showAmountsOnLockscreen: true })
    expect(msg.body).toContain('+$142.15')
  })

  it('still carries the amount in data, so the app can show it after unlock', () => {
    const msg = renderNotification(evt({ amount: 142.15 }), { showAmountsOnLockscreen: false })
    expect(msg.data.amount).toBe(142.15)
  })

  it('formats sign and cents consistently', () => {
    expect(formatAmount(142.1)).toBe('+$142.10')
    expect(formatAmount(-18.2)).toBe('-$18.20')
    expect(formatAmount(0)).toBe('+$0.00')
  })
})

describe('deep-link payload', () => {
  it('derives the url server-side from an allowlisted route', () => {
    const msg = renderNotification(evt(), { showAmountsOnLockscreen: false })
    expect(msg.data.route).toBe('/live')
    expect(msg.data.url).toBe('ironforge://live?account=spark')
  })

  it('clamps a route the producer should not be able to choose', () => {
    // A compromised event producer must not be able to aim a tap anywhere it likes.
    const msg = renderNotification(
      evt({ route: '/ops/impersonate' as unknown as NotificationEvent['route'] }),
      { showAmountsOnLockscreen: false },
    )
    expect(msg.data.route).toBe('/live')
    expect(msg.data.url).not.toContain('ops')
  })

  it('gives approvals high priority and a short ttl', () => {
    const msg = renderNotification(evt({ category: 'trade_approval' }), {
      showAmountsOnLockscreen: false,
    })
    expect(msg.priority).toBe('high')
    // Matches APP-041's 5-minute approval window — a push that outlives the decision
    // is noise.
    expect(msg.ttl).toBe(300)
    expect(msg.channelId).toBe('approvals')
  })

  it('carries the event key so delivery can be correlated', () => {
    const msg = renderNotification(evt(), { showAmountsOnLockscreen: false })
    expect(msg.data.eventKey).toBe('trade_close:spark:1DTE:POS-1')
  })
})
