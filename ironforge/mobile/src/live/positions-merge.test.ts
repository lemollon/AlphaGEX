import { describe, it, expect } from 'vitest'
import { mergeAgentsTrade } from './positions-merge'
import type { LiveAgent } from '@/api/types'

function agent(bot: string, overrides: Partial<LiveAgent> = {}): LiveAgent {
  return {
    bot,
    label: bot,
    paper: false,
    state: null,
    account: null,
    trade: null,
    stats: null,
    error: null,
    ...overrides,
  }
}

describe('mergeAgentsTrade', () => {
  it('replaces only the trade field for a bot the push mentions', () => {
    const current = [agent('spark', { label: 'Spark' })]
    const pushedTrade = { active: true } as unknown as LiveAgent['trade']
    const result = mergeAgentsTrade(current, [{ bot: 'spark', trade: pushedTrade }])
    expect(result[0].trade).toBe(pushedTrade)
    expect(result[0].label).toBe('Spark') // untouched
  })

  it('leaves an agent untouched when the push does not mention its bot', () => {
    const existingTrade = { active: false } as unknown as LiveAgent['trade']
    const current = [agent('spark', { trade: existingTrade }), agent('flame')]
    const result = mergeAgentsTrade(current, [{ bot: 'spark', trade: null }])
    expect(result[1]).toBe(current[1]) // flame reference unchanged
  })

  it('returns the same array reference when the push is empty', () => {
    const current = [agent('spark')]
    expect(mergeAgentsTrade(current, [])).toBe(current)
  })

  it('never drops an agent tile the push did not mention', () => {
    const current = [agent('spark'), agent('flame')]
    const result = mergeAgentsTrade(current, [{ bot: 'spark', trade: null }])
    expect(result.map((a) => a.bot)).toEqual(['spark', 'flame'])
  })
})
