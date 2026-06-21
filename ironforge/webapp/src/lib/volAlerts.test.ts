import { describe, it, expect } from 'vitest'
import {
  diffVolAlerts,
  botVolMessage,
  isAlertingKey,
  classifySignalState,
  notifyDecision,
  WATCH_PROXIMITY,
  type VolAlert,
  type VolBot,
  type LadderTransition,
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

describe('classifySignalState', () => {
  it('confirmed wins even if a single read goes inactive (resolve-debounce window)', () => {
    expect(classifySignalState({ active: false, confirmed: true, proximity: 0.1 })).toBe('confirmed')
    expect(classifySignalState({ active: true, confirmed: true, proximity: 1 })).toBe('confirmed')
  })
  it('tripped when active but not yet confirmed', () => {
    expect(classifySignalState({ active: true, confirmed: false, proximity: 0.2 })).toBe('tripped')
  })
  it('watch when inactive but proximity at/above the watch threshold', () => {
    expect(classifySignalState({ active: false, confirmed: false, proximity: WATCH_PROXIMITY })).toBe('watch')
    expect(classifySignalState({ active: false, confirmed: false, proximity: 0.95 })).toBe('watch')
  })
  it('idle when inactive and below the watch threshold (incl. null proximity)', () => {
    expect(classifySignalState({ active: false, confirmed: false, proximity: 0.5 })).toBe('idle')
    expect(classifySignalState({ active: false, confirmed: false, proximity: null })).toBe('idle')
    expect(classifySignalState({ active: false, confirmed: false, proximity: undefined })).toBe('idle')
  })
})

describe('notifyDecision', () => {
  const mk = (over: Partial<LadderTransition>): LadderTransition => ({
    signalKey: 'backwardation',
    direction: 'bullish',
    from: 'idle',
    to: 'idle',
    ...over,
  })

  it('notifies HIGH on any →confirmed transition', () => {
    const v = notifyDecision(mk({ from: 'tripped', to: 'confirmed' }))
    expect(v).toMatchObject({ notify: true, priority: 'high', reason: 'confirmed' })
  })
  it('notifies HIGH on ts_flattening →tripped (asymmetric early warning, default on)', () => {
    const v = notifyDecision(mk({ signalKey: 'ts_flattening', direction: 'bearish', from: 'watch', to: 'tripped' }))
    expect(v).toMatchObject({ notify: true, priority: 'high', reason: 'early-warning' })
  })
  it('does NOT early-warn other signals on →tripped', () => {
    expect(notifyDecision(mk({ signalKey: 'backwardation', to: 'tripped' })).notify).toBe(false)
    expect(notifyDecision(mk({ signalKey: 'exhaustion', to: 'tripped' })).notify).toBe(false)
  })
  it('suppresses ts_flattening early warning when disabled', () => {
    const v = notifyDecision(mk({ signalKey: 'ts_flattening', to: 'tripped' }), { earlyWarnTsFlattening: false })
    expect(v.notify).toBe(false)
  })
  it('never pings on resolution (confirmed→watch/idle) — UI only', () => {
    expect(notifyDecision(mk({ from: 'confirmed', to: 'watch' }))).toMatchObject({ notify: false, reason: 'resolved' })
    expect(notifyDecision(mk({ from: 'confirmed', to: 'idle' })).notify).toBe(false)
    // even ts_flattening leaving confirmed must not re-fire an early warning
    expect(notifyDecision(mk({ signalKey: 'ts_flattening', from: 'confirmed', to: 'tripped' })).notify).toBe(false)
  })
  it('is silent on benign transitions (idle↔watch)', () => {
    expect(notifyDecision(mk({ from: 'idle', to: 'watch' })).notify).toBe(false)
    expect(notifyDecision(mk({ from: 'watch', to: 'idle' })).notify).toBe(false)
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
