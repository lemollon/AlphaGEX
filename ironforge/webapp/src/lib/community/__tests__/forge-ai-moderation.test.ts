import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { moderateMessage } from '../forge-ai'

/**
 * db-community "Moderation: ... block personal financial advice, promotions and
 * account details" (gap audit #196) — the three categories the AI scorer's schema
 * didn't have at all. Tested here via the deterministic local pattern layer (same
 * zero-latency pre-filter as the existing profanity WORDLIST), so this suite needs no
 * Claude API key and never makes a network call.
 */

const ORIGINAL_CLAUDE_KEY = process.env.CLAUDE_API_KEY
const ORIGINAL_ANTHROPIC_KEY = process.env.ANTHROPIC_API_KEY

beforeEach(() => {
  delete process.env.CLAUDE_API_KEY
  delete process.env.ANTHROPIC_API_KEY
})

afterEach(() => {
  process.env.CLAUDE_API_KEY = ORIGINAL_CLAUDE_KEY
  process.env.ANTHROPIC_API_KEY = ORIGINAL_ANTHROPIC_KEY
})

describe('moderateMessage — financial advice directed at another member', () => {
  it('blocks "you should buy ..."', async () => {
    const v = await moderateMessage('You should buy SPY calls right now, trust me.')
    expect(v.ok).toBe(false)
    expect(v.category).toBe('FINANCIAL_ADVICE_DETECTED')
  })

  it('blocks "I recommend you sell everything"', async () => {
    const v = await moderateMessage('I recommend you sell everything before Friday.')
    expect(v.ok).toBe(false)
    expect(v.category).toBe('FINANCIAL_ADVICE_DETECTED')
  })

  it('blocks "put your money into ..."', async () => {
    const v = await moderateMessage('Put your money into TSLA, it only goes up.')
    expect(v.ok).toBe(false)
    expect(v.category).toBe('FINANCIAL_ADVICE_DETECTED')
  })

  it('allows a general market opinion — not advice directed at a member', async () => {
    const v = await moderateMessage('I think SPY grinds up into the close today.')
    expect(v.ok).toBe(true)
  })

  it('allows plain disagreement about strategy', async () => {
    const v = await moderateMessage('Flame has been choppy this week, not loving the entries.')
    expect(v.ok).toBe(true)
  })
})

describe('moderateMessage — promotions', () => {
  it('blocks a referral/discount code pitch', async () => {
    const v = await moderateMessage('Use my referral code FORGE10 for a discount!')
    expect(v.ok).toBe(false)
    expect(v.category).toBe('PROMOTION_DETECTED')
  })

  it('blocks a paid-signals DM solicitation', async () => {
    const v = await moderateMessage('DM me for signals, $50/month, limited spots.')
    expect(v.ok).toBe(false)
    expect(v.category).toBe('PROMOTION_DETECTED')
  })

  it('blocks "join my channel" solicitation', async () => {
    const v = await moderateMessage('Join my Telegram channel for daily picks.')
    expect(v.ok).toBe(false)
    expect(v.category).toBe('PROMOTION_DETECTED')
  })

  it('allows a member thanking the community (no solicitation)', async () => {
    const v = await moderateMessage('Thanks everyone, this channel has been super helpful.')
    expect(v.ok).toBe(true)
  })
})

describe('moderateMessage — account details', () => {
  it('blocks a shared account number', async () => {
    const v = await moderateMessage('My account number is 48213099, can someone check this trade?')
    expect(v.ok).toBe(false)
    expect(v.category).toBe('ACCOUNT_DETAILS_DETECTED')
  })

  it('blocks a routing number mention', async () => {
    const v = await moderateMessage('Here is my routing number for the wire: 021000021')
    expect(v.ok).toBe(false)
    expect(v.category).toBe('ACCOUNT_DETAILS_DETECTED')
  })

  it('blocks a request implying shared brokerage login', async () => {
    const v = await moderateMessage('Can I just give you my Tradier account password so you can check?')
    expect(v.ok).toBe(false)
    expect(v.category).toBe('ACCOUNT_DETAILS_DETECTED')
  })

  it('allows discussing account VALUE without an identifier', async () => {
    const v = await moderateMessage('My account is up 12% this month, feeling good about Spark.')
    expect(v.ok).toBe(true)
  })
})

describe('moderateMessage — existing profanity path is unaffected', () => {
  it('still blocks the profanity wordlist first', async () => {
    const v = await moderateMessage('this is such bullshit holy fuck')
    expect(v.ok).toBe(false)
    expect(v.category).toBe('PROFANITY_DETECTED')
  })
})

/**
 * #218: moderation fails CLOSED, not open. A post that trips none of the local
 * patterns (above) and reaches the AI scorer must be HELD, not auto-approved,
 * if that scorer is unreachable or returns something unusable — the opposite
 * of the old behaviour, which published anyway on any scorer failure.
 */
describe('moderateMessage — fails closed when the scorer errors (#218)', () => {
  const originalFetch = global.fetch

  beforeEach(() => {
    // Only the "configured" branch reaches the network — these tests need a key.
    process.env.CLAUDE_API_KEY = 'test-key'
  })

  afterEach(() => {
    global.fetch = originalFetch
  })

  it('holds the post as pending, not approved, when the API call throws', async () => {
    global.fetch = (async () => {
      throw new Error('network down')
    }) as typeof fetch
    const v = await moderateMessage('A perfectly normal message about today\'s range.')
    expect(v.ok).toBe(false)
    expect(v.pending).toBe(true)
    expect(v.category).toBe('MODERATION_UNAVAILABLE')
  })

  it('holds the post as pending, not approved, when the API returns a non-2xx', async () => {
    global.fetch = (async () =>
      new Response('rate limited', { status: 429 })) as typeof fetch
    const v = await moderateMessage('A perfectly normal message about today\'s range.')
    expect(v.ok).toBe(false)
    expect(v.pending).toBe(true)
  })

  it('holds the post as pending, not approved, when the response has no parseable JSON', async () => {
    global.fetch = (async () =>
      new Response(JSON.stringify({ content: [{ type: 'text', text: 'not json at all' }] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })) as typeof fetch
    const v = await moderateMessage('A perfectly normal message about today\'s range.')
    expect(v.ok).toBe(false)
    expect(v.pending).toBe(true)
    expect(v.category).toBe('MODERATION_UNAVAILABLE')
  })

  it('still approves normally when the scorer responds cleanly', async () => {
    global.fetch = (async () =>
      new Response(
        JSON.stringify({
          content: [
            {
              type: 'text',
              text: '{"profanity":0,"threat":0,"harassment":0,"personal_attack":0,"spam":0,"financial_advice":0,"promotion":0,"account_details":0}',
            },
          ],
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      )) as typeof fetch
    const v = await moderateMessage('A perfectly normal message about today\'s range.')
    expect(v.ok).toBe(true)
    expect(v.pending).toBeUndefined()
  })
})
