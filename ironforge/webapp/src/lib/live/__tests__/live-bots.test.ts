import { describe, it, expect } from 'vitest'
import { botTable, heartbeatName } from '@/lib/db'
import {
  LIVE_BOTS,
  LIVE_BOT_MODE,
  LIVE_BOT_LABEL,
  LIVE_BOT_PILL,
  LIVE_BOT_ACCENT,
  accountMode,
  isPaperBot,
  isLiveBot,
  type LiveBot,
} from '../bots'

/**
 * FLAME was invisible on the customer Live page because LIVE_BOTS was
 * ['spark','spark2'] and isLiveBot() re-checked that with hand-written literals
 * that drifted from the array. These tests pin both.
 */

describe('live bot registry', () => {
  it('includes flame', () => {
    expect(LIVE_BOTS).toContain('flame')
  })

  it('derives isLiveBot from LIVE_BOTS rather than hardcoded literals', () => {
    for (const b of LIVE_BOTS) expect(isLiveBot(b)).toBe(true)
    for (const junk of ['inferno', 'kindle', 'blaze', '', 'FLAME', null, undefined]) {
      expect(isLiveBot(junk as string | null)).toBe(false)
    }
  })

  it('has complete metadata for every bot — no undefined labels in the UI', () => {
    for (const b of LIVE_BOTS) {
      expect(LIVE_BOT_MODE[b]).toBeDefined()
      expect(LIVE_BOT_LABEL[b]).toBeTruthy()
      expect(LIVE_BOT_PILL[b]).toBeTruthy()
      expect(LIVE_BOT_ACCENT[b]).toBeDefined()
    }
  })
})

describe('account mode', () => {
  it('declares spark as the only production account', () => {
    expect(accountMode('flame')).toBe('paper')
    expect(accountMode('spark')).toBe('production')
    expect(accountMode('spark2')).toBe('paper')
  })

  it('flags flame and spark2 as paper', () => {
    expect(isPaperBot('flame')).toBe(true)
    expect(isPaperBot('spark')).toBe(false)
    expect(isPaperBot('spark2')).toBe(true)
  })
})

describe('strategy accent', () => {
  it('is identity, not account mode — flame stays orange regardless', () => {
    expect(LIVE_BOT_ACCENT.flame).toBe('flame')
    expect(LIVE_BOT_ACCENT.spark).toBe('spark')
    expect(LIVE_BOT_ACCENT.spark2).toBe('spark')
  })

  it('both spark accounts share one accent but keep distinct pills', () => {
    expect(LIVE_BOT_ACCENT.spark).toBe(LIVE_BOT_ACCENT.spark2)
    expect(LIVE_BOT_PILL.spark).not.toBe(LIVE_BOT_PILL.spark2)
  })
})

describe('ledger partition', () => {
  // The Live page filters production rows with
  //   COALESCE(account_type,'sandbox') = 'production'
  // and paper rows with the complement. Mirrored here so the two branches are
  // proven to partition the table exactly — no row visible to both, none to
  // neither (a gap would silently blank a bot's page).
  const bucket = (accountType: string | null, mode: 'production' | 'paper') => {
    const effective = accountType ?? 'sandbox'
    return mode === 'production' ? effective === 'production' : effective !== 'production'
  }

  it('assigns every account_type value to exactly one mode', () => {
    for (const t of ['production', 'sandbox', 'paper', null]) {
      const inProd = bucket(t, 'production')
      const inPaper = bucket(t, 'paper')
      expect(inProd !== inPaper, `account_type=${t} must land in exactly one bucket`).toBe(true)
    }
  })

  it('treats NULL account_type as paper, not production', () => {
    expect(bucket(null, 'paper')).toBe(true)
    expect(bucket(null, 'production')).toBe(false)
  })
})

describe('db registry for live bots', () => {
  // spark2/flame were resolved by the `DB_PREFIX[bot] || bot` fallthrough before
  // being listed explicitly. These pin the resolved values so making the registry
  // explicit stays a no-op — a wrong prefix here would silently repoint a
  // live-money bot at another bot's tables.
  it('maps each live bot to its own table prefix', () => {
    expect(botTable('spark', 'positions')).toBe('spark_positions')
    expect(botTable('spark2', 'positions')).toBe('spark2_positions')
    expect(botTable('flame', 'positions')).toBe('flame_positions')
  })

  it('gives every live bot a distinct table namespace', () => {
    const prefixes = LIVE_BOTS.map((b: LiveBot) => botTable(b, 'positions'))
    expect(new Set(prefixes).size).toBe(LIVE_BOTS.length)
  })

  it('maps each live bot to its own heartbeat name', () => {
    expect(heartbeatName('spark')).toBe('SPARK')
    expect(heartbeatName('spark2')).toBe('SPARK2')
    expect(heartbeatName('flame')).toBe('FLAME')
  })
})
