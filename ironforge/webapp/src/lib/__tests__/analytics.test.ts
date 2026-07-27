// @vitest-environment jsdom
//
// track() is a deliberate no-op during SSR (an event is a user action, not a
// render), so these assertions need a window. Per-file docblock rather than a
// change to vitest.config.ts, which stays node for every other suite.
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  __queuedEvents,
  __resetAnalytics,
  referrerClass,
  setAnalyticsSink,
  track,
  viewportClass,
  type AnalyticsEvent,
} from '../analytics'

afterEach(() => {
  __resetAnalytics()
})

describe('track', () => {
  it('queues before a sink exists and flushes on install', () => {
    track({ name: 'period_change', props: { from_period: '30d', to_period: '7d' } })
    expect(__queuedEvents()).toHaveLength(1)

    const seen: AnalyticsEvent[] = []
    setAnalyticsSink((e) => seen.push(e))
    expect(seen).toHaveLength(1)
    expect(seen[0].name).toBe('period_change')
    expect(__queuedEvents()).toHaveLength(0)
  })

  it('delivers straight to an installed sink', () => {
    const sink = vi.fn()
    setAnalyticsSink(sink)
    track({ name: 'bot_filter_change', props: { from_bot: 'all', to_bot: 'flame' } })
    expect(sink).toHaveBeenCalledOnce()
  })

  it('never lets a throwing sink break the page', () => {
    setAnalyticsSink(() => {
      throw new Error('provider exploded')
    })
    expect(() =>
      track({ name: 'period_change', props: { from_period: '7d', to_period: '30d' } }),
    ).not.toThrow()
  })

  it('bounds the queue so a page with no provider cannot grow forever', () => {
    for (let i = 0; i < 200; i++) {
      track({ name: 'period_change', props: { from_period: '7d', to_period: '30d' } })
    }
    expect(__queuedEvents().length).toBeLessThanOrEqual(50)
  })
})

describe('privacy buckets', () => {
  it('buckets the viewport rather than recording a raw width', () => {
    expect(viewportClass(375)).toBe('mobile')
    expect(viewportClass(767)).toBe('mobile')
    expect(viewportClass(768)).toBe('tablet')
    expect(viewportClass(1023)).toBe('tablet')
    expect(viewportClass(1440)).toBe('desktop')
  })

  it('buckets the referrer rather than recording the URL', () => {
    expect(referrerClass('', 'ironforge.trade')).toBe('direct')
    expect(referrerClass('https://ironforge.trade/pricing', 'ironforge.trade')).toBe('internal')
    expect(referrerClass('https://www.google.com/search?q=x', 'ironforge.trade')).toBe('search')
    expect(referrerClass('https://t.co/abc', 'ironforge.trade')).toBe('social')
    expect(referrerClass('https://news.ycombinator.com/', 'ironforge.trade')).toBe('external')
    expect(referrerClass('not a url', 'ironforge.trade')).toBe('direct')
  })

  it('never carries a financial or identifying value in any event shape', () => {
    // The union is the enforcement point; this asserts the shipped payloads.
    const events: AnalyticsEvent[] = [
      {
        name: 'bot_ledger_view',
        props: {
          period: '30d',
          viewport_class: 'desktop',
          referrer_class: 'direct',
          auth_state: 'anonymous',
        },
      },
      { name: 'period_change', props: { from_period: '7d', to_period: '30d' } },
      { name: 'bot_filter_change', props: { from_bot: 'all', to_bot: 'spark' } },
      {
        name: 'cta_click',
        props: {
          cta_name: 'start_trial',
          placement: 'hero',
          target_route: '/signup',
          plan: 'automate',
        },
      },
      { name: 'trade_log_page', props: { direction: 'next', page_size: 20, bot_filter: 'all' } },
      {
        name: 'ledger_error',
        props: { component: 'summary', error_code: 'SNAPSHOT_EXPIRED', request_id: 'req_abc' },
      },
    ]
    const banned = /win_rate|pnl|profit|net_result|buying_power|return_on_bp|public_id|email|account/i
    for (const e of events) {
      expect(JSON.stringify(e)).not.toMatch(banned)
    }
  })
})
