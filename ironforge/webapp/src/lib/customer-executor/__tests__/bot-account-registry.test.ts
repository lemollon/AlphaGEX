import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { getKnownBotTradedTradierAccountNumbers } from '../bot-account-registry'

const ENV_KEYS = [
  'TRADIER_FLAME_ACCOUNT_ID',
  'TRADIER_KINDLE_ACCOUNT_ID',
  'TRADIER_PROD_ACCOUNT_ID',
  'TRADIER_SANDBOX_ACCOUNT_ID',
  'BOT_TRADED_TRADIER_ACCOUNT_IDS',
] as const

const saved: Record<string, string | undefined> = {}

beforeEach(() => {
  for (const k of ENV_KEYS) {
    saved[k] = process.env[k]
    delete process.env[k]
  }
})

afterEach(() => {
  for (const k of ENV_KEYS) {
    if (saved[k] === undefined) delete process.env[k]
    else process.env[k] = saved[k]
  }
})

describe('getKnownBotTradedTradierAccountNumbers', () => {
  it('returns empty when nothing is configured', () => {
    expect(getKnownBotTradedTradierAccountNumbers()).toEqual([])
  })

  it('includes FLAME (which is also SPARK\'s shared 6YB71371 account)', () => {
    process.env.TRADIER_FLAME_ACCOUNT_ID = '6YB71371'
    expect(getKnownBotTradedTradierAccountNumbers()).toEqual(['6YB71371'])
  })

  it('collects every known production/legacy env var', () => {
    process.env.TRADIER_FLAME_ACCOUNT_ID = 'AAA1111'
    process.env.TRADIER_KINDLE_ACCOUNT_ID = 'BBB2222'
    process.env.TRADIER_PROD_ACCOUNT_ID = 'CCC3333'
    process.env.TRADIER_SANDBOX_ACCOUNT_ID = 'DDD4444'
    expect(getKnownBotTradedTradierAccountNumbers()).toEqual(['AAA1111', 'BBB2222', 'CCC3333', 'DDD4444'])
  })

  it('parses the comma-separated escape hatch and trims whitespace', () => {
    process.env.BOT_TRADED_TRADIER_ACCOUNT_IDS = ' EEE5555 , FFF6666,GGG7777 '
    expect(getKnownBotTradedTradierAccountNumbers()).toEqual(['EEE5555', 'FFF6666', 'GGG7777'])
  })

  it('drops empty entries from unset vars and stray commas', () => {
    process.env.TRADIER_FLAME_ACCOUNT_ID = 'AAA1111'
    process.env.BOT_TRADED_TRADIER_ACCOUNT_IDS = ',,'
    expect(getKnownBotTradedTradierAccountNumbers()).toEqual(['AAA1111'])
  })
})
