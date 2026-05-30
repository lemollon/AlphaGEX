import { describe, it, expect } from 'vitest'
import {
  diffVolAlerts,
  botVolMessage,
  isAlertingKey,
  type VolAlert,
  type VolBot,
} from './volAlerts'

/** Minimal alert factory. */
function mkAlert(over: Partial<VolAlert> = {}): VolAlert {
  return {
    id: 1,
    signal_key: 'backwardation',
    direction: 'bullish',
    status: 'active',
    headline: 'h',
    message: 'm',
    regime_label: 'backwardation_stressed',
    vix: 20,
    vvix: 100,
    fired_at: '2026-05-30T12:00:00Z',
    resolved_at: null,
    ...over,
  }
}

describe('isAlertingKey', () => {
  it('includes the three directional high-confidence signals', () => {
    expect(isAlertingKey('backwardation')).toBe(true)
    expect(isAlertingKey('exhaustion')).toBe(true)
    expect(isAlertingKey('ts_flattening')).toBe(true)
  })
  it('excludes divergence (low-confidence) and double_floor (neutral)', () => {
    expect(isAlertingKey('divergence')).toBe(false)
    expect(isAlertingKey('double_floor')).toBe(false)
    expect(isAlertingKey('nonsense')).toBe(false)
  })
})

describe('diffVolAlerts', () => {
  it('opens newly-active keys not already open', () => {
    const { toOpen, toResolve } = diffVolAlerts(['backwardation', 'ts_flattening'], [])
    expect(toOpen).toEqual(['backwardation', 'ts_flattening'])
    expect(toResolve).toEqual([])
  })

  it('resolves open keys that are no longer active', () => {
    const { toOpen, toResolve } = diffVolAlerts([], ['backwardation'])
    expect(toOpen).toEqual([])
    expect(toResolve).toEqual(['backwardation'])
  })

  it('is a no-op when active == open', () => {
    const { toOpen, toResolve } = diffVolAlerts(['exhaustion'], ['exhaustion'])
    expect(toOpen).toEqual([])
    expect(toResolve).toEqual([])
  })

  it('handles simultaneous open + resolve', () => {
    const { toOpen, toResolve } = diffVolAlerts(
      ['backwardation', 'exhaustion'],
      ['ts_flattening', 'exhaustion'],
    )
    expect(toOpen).toEqual(['backwardation'])
    expect(toResolve).toEqual(['ts_flattening'])
  })

  it('de-dupes doubled keys so no double-insert', () => {
    const { toOpen } = diffVolAlerts(['backwardation', 'backwardation'], [])
    expect(toOpen).toEqual(['backwardation'])
  })
})

describe('botVolMessage — sellers (spark/flame/inferno)', () => {
  const sellers: VolBot[] = ['spark', 'flame', 'inferno']

  for (const bot of sellers) {
    it(`${bot}: backwardation → warn`, () => {
      const msg = botVolMessage(bot, [mkAlert({ signal_key: 'backwardation' })])
      expect(msg?.tone).toBe('warn')
      expect(msg?.text).toMatch(/tail risk/i)
    })

    it(`${bot}: ts_flattening → warn`, () => {
      const msg = botVolMessage(bot, [mkAlert({ signal_key: 'ts_flattening', direction: 'bearish' })])
      expect(msg?.tone).toBe('warn')
    })

    it(`${bot}: exhaustion only → info`, () => {
      const msg = botVolMessage(bot, [mkAlert({ signal_key: 'exhaustion' })])
      expect(msg?.tone).toBe('info')
      expect(msg?.text).toMatch(/bounce/i)
    })
  }

  it('seller priority: backwardation outranks exhaustion (warn wins)', () => {
    const msg = botVolMessage('spark', [
      mkAlert({ signal_key: 'exhaustion' }),
      mkAlert({ signal_key: 'backwardation' }),
    ])
    expect(msg?.tone).toBe('warn')
  })

  it('seller priority: ts_flattening outranks exhaustion (warn wins)', () => {
    const msg = botVolMessage('flame', [
      mkAlert({ signal_key: 'exhaustion' }),
      mkAlert({ signal_key: 'ts_flattening', direction: 'bearish' }),
    ])
    expect(msg?.tone).toBe('warn')
  })
})

describe('botVolMessage — directional (blaze/flare)', () => {
  const directional: VolBot[] = ['blaze', 'flare']

  for (const bot of directional) {
    it(`${bot}: exhaustion → bull`, () => {
      const msg = botVolMessage(bot, [mkAlert({ signal_key: 'exhaustion' })])
      expect(msg?.tone).toBe('bull')
      expect(msg?.text).toMatch(/lean long/i)
    })

    it(`${bot}: backwardation → bull`, () => {
      const msg = botVolMessage(bot, [mkAlert({ signal_key: 'backwardation' })])
      expect(msg?.tone).toBe('bull')
    })

    it(`${bot}: ts_flattening → bear`, () => {
      const msg = botVolMessage(bot, [mkAlert({ signal_key: 'ts_flattening', direction: 'bearish' })])
      expect(msg?.tone).toBe('bear')
      expect(msg?.text).toMatch(/lean puts/i)
    })
  }

  it('directional priority: backwardation/exhaustion outranks ts_flattening (bull wins)', () => {
    const msg = botVolMessage('blaze', [
      mkAlert({ signal_key: 'ts_flattening', direction: 'bearish' }),
      mkAlert({ signal_key: 'exhaustion' }),
    ])
    expect(msg?.tone).toBe('bull')
  })
})

describe('botVolMessage — null cases', () => {
  it('returns null when no alerts', () => {
    expect(botVolMessage('spark', [])).toBeNull()
    expect(botVolMessage('spark', null)).toBeNull()
    expect(botVolMessage('spark', undefined)).toBeNull()
  })

  it('ignores resolved alerts', () => {
    expect(botVolMessage('spark', [mkAlert({ status: 'resolved' })])).toBeNull()
  })

  it('ignores non-alerting keys (divergence/double_floor)', () => {
    expect(
      botVolMessage('spark', [
        mkAlert({ signal_key: 'divergence', direction: 'bearish' }),
        mkAlert({ signal_key: 'double_floor', direction: 'neutral' }),
      ]),
    ).toBeNull()
  })
})
