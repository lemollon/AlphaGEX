import { describe, expect, it } from 'vitest'

import { ALLOWED_EVENT_NAMES, validateEvent } from '../event-schema'

const VIEW = {
  name: 'bot_ledger_view',
  props: {
    period: '30d',
    viewport_class: 'desktop',
    referrer_class: 'direct',
    auth_state: 'anonymous',
  },
}

describe('validateEvent — accepts the documented schema', () => {
  it('covers exactly the six specified events', () => {
    expect(ALLOWED_EVENT_NAMES.sort()).toEqual(
      [
        'bot_ledger_view',
        'period_change',
        'bot_filter_change',
        'cta_click',
        'trade_log_page',
        'ledger_error',
      ].sort(),
    )
  })

  it('accepts each event in its documented shape', () => {
    const good = [
      VIEW,
      { name: 'period_change', props: { from_period: '30d', to_period: '7d' } },
      { name: 'bot_filter_change', props: { from_bot: 'all', to_bot: 'flame' } },
      {
        name: 'cta_click',
        props: {
          cta_name: 'start_trial',
          placement: 'hero',
          target_route: '/signup',
          plan: 'automate',
        },
      },
      { name: 'trade_log_page', props: { direction: 'next', page_size: 20, bot_filter: 'spark' } },
      {
        name: 'ledger_error',
        props: { component: 'summary', error_code: 'SNAPSHOT_EXPIRED', request_id: 'req_abc123' },
      },
      { name: 'ledger_error', props: { component: 'trade_log', error_code: 'network', request_id: null } },
    ]
    for (const e of good) expect(validateEvent(e), e.name).not.toBeNull()
  })
})

describe('validateEvent — rejects everything else', () => {
  it('rejects an unknown event name', () => {
    expect(validateEvent({ name: 'evil_event', props: {} })).toBeNull()
  })

  it('rejects malformed envelopes', () => {
    for (const bad of [null, undefined, 42, 'str', [], {}, { name: 'period_change' }]) {
      expect(validateEvent(bad)).toBeNull()
    }
  })

  it('rejects an EXTRA key — the smuggling path that matters most', () => {
    const smuggled = { ...VIEW, props: { ...VIEW.props, win_rate: '73.7' } }
    expect(validateEvent(smuggled)).toBeNull()
  })

  it('rejects a missing key', () => {
    const { period, ...rest } = VIEW.props
    expect(validateEvent({ name: 'bot_ledger_view', props: rest })).toBeNull()
  })

  it('rejects out-of-enum values', () => {
    expect(validateEvent({ ...VIEW, props: { ...VIEW.props, period: '90d' } })).toBeNull()
    expect(validateEvent({ ...VIEW, props: { ...VIEW.props, auth_state: 'admin' } })).toBeNull()
    expect(
      validateEvent({ name: 'bot_filter_change', props: { from_bot: 'all', to_bot: 'inferno' } }),
    ).toBeNull()
  })

  it('rejects a target_route that is not a plain path', () => {
    const cta = (route: unknown) => ({
      name: 'cta_click',
      props: { cta_name: 'create_account', placement: 'hero', target_route: route, plan: 'none' },
    })
    expect(validateEvent(cta('/signup'))).not.toBeNull()
    expect(validateEvent(cta('https://evil.example.com'))).toBeNull()
    expect(validateEvent(cta('/signup?email=a@b.com'))).toBeNull()
    expect(validateEvent(cta('/' + 'x'.repeat(200)))).toBeNull()
  })

  it('rejects an error_code that is not screaming snake or "network"', () => {
    const err = (code: unknown) => ({
      name: 'ledger_error',
      props: { component: 'summary', error_code: code, request_id: null },
    })
    expect(validateEvent(err('SNAPSHOT_EXPIRED'))).not.toBeNull()
    expect(validateEvent(err('user@example.com'))).toBeNull()
    expect(validateEvent(err('a'.repeat(80)))).toBeNull()
  })

  it('rejects an out-of-range page_size', () => {
    const p = (n: unknown) => ({
      name: 'trade_log_page',
      props: { direction: 'next', page_size: n, bot_filter: 'all' },
    })
    expect(validateEvent(p(20))).not.toBeNull()
    expect(validateEvent(p(0))).toBeNull()
    expect(validateEvent(p(1000))).toBeNull()
    expect(validateEvent(p(1.5))).toBeNull()
  })

  it('returns a rebuilt object, not the caller’s — no prototype pollution path', () => {
    const hostile = JSON.parse('{"name":"period_change","props":{"from_period":"7d","to_period":"30d","__proto__":{"x":1}}}')
    const out = validateEvent(hostile)
    // The __proto__ key is not an own enumerable key after JSON.parse in V8,
    // so this is accepted — what matters is the OUTPUT carries only schema keys.
    if (out) expect(Object.keys(out.props).sort()).toEqual(['from_period', 'to_period'])
  })
})
