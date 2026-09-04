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
import { describeLiveGate } from '@/lib/tradier'

/**
 * FLAME was invisible on the customer Live page because LIVE_BOTS was a
 * hand-written array that omitted it, and isLiveBot() re-checked membership
 * with a SECOND set of hand-written literals that drifted from the first.
 * These tests pin both: the roster contains flame, and the predicate is
 * derived from the roster rather than restated.
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
  it('declares no bot as production by default', () => {
    expect(accountMode('flame')).toBe('paper')
    // SPARK lost its production account on 2026-08-23 (the dead-keyed
    // Logan[production] row was deactivated) but stayed declared 'production'
    // here, so the customer read went to an inactive $5,000 ledger instead of
    // SPARK's real paper book. A name appearing here without a deliberate
    // change means a paper ledger just started claiming real money.
    expect(accountMode('spark')).toBe('paper')
    expect(LIVE_BOTS.filter((b: LiveBot) => accountMode(b) === 'production')).toEqual([])
  })

  it('pins the declaration against describeLiveGate so the two cannot drift', () => {
    // 🚨 THE BUG THIS FILE EXISTS TO PREVENT. describeLiveGate is the routing
    // layer's answer to "can this bot reach real money"; LIVE_BOT_MODE is the
    // display layer's. They disagreed for five days and nothing failed.
    // A bot the router calls paper-only must never be declared production.
    for (const b of LIVE_BOTS) {
      const gate = describeLiveGate(b)
      if (gate.endsWith('_is_paper_only') || gate === 'not_a_production_bot') {
        expect(accountMode(b)).toBe('paper')
      }
    }
    // Pinned explicitly too, so deleting the constant fails loudly.
    expect(describeLiveGate('spark')).toBe('spark_is_paper_only')
  })

  it('flags both bots as paper', () => {
    expect(isPaperBot('flame')).toBe(true)
    expect(isPaperBot('spark')).toBe(true)
  })

  it('keeps isPaperBot the exact complement of accountMode', () => {
    for (const b of LIVE_BOTS) {
      expect(isPaperBot(b)).toBe(accountMode(b) === 'paper')
    }
  })
})

describe('strategy accent', () => {
  it('is identity, not account mode — flame stays orange regardless', () => {
    expect(LIVE_BOT_ACCENT.flame).toBe('flame')
    expect(LIVE_BOT_ACCENT.spark).toBe('spark')
    // both bots are on paper; the accents must not track account mode at all.
    expect(accountMode('flame')).toBe('paper')
    expect(accountMode('spark')).toBe('paper')
    expect(LIVE_BOT_ACCENT.flame).not.toBe(LIVE_BOT_ACCENT.spark)
  })

  it('gives every bot a distinct pill so two rows can never read alike', () => {
    const pills = LIVE_BOTS.map((b: LiveBot) => LIVE_BOT_PILL[b])
    expect(new Set(pills).size).toBe(LIVE_BOTS.length)
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
  // flame was resolved by the `DB_PREFIX[bot] || bot` fallthrough before being
  // listed explicitly. These pin the resolved values so making the registry
  // explicit stays a no-op — a wrong prefix here would silently repoint a
  // live-money bot at another bot's tables.
  it('maps each live bot to its own table prefix', () => {
    expect(botTable('spark', 'positions')).toBe('spark_positions')
    expect(botTable('flame', 'positions')).toBe('flame_positions')
  })

  it('gives every live bot a distinct table namespace', () => {
    const prefixes = LIVE_BOTS.map((b: LiveBot) => botTable(b, 'positions'))
    expect(new Set(prefixes).size).toBe(LIVE_BOTS.length)
  })

  it('maps each live bot to its own heartbeat name', () => {
    expect(heartbeatName('spark')).toBe('SPARK')
    expect(heartbeatName('flame')).toBe('FLAME')
  })
})
