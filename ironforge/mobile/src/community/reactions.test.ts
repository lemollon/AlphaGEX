import { describe, it, expect } from 'vitest'
import { applyFlame, FLAME } from '@/community/reactions'
import type { CommunityFeed, CommunityMessage } from '@/api/types'

function msg(over: Partial<CommunityMessage> = {}): CommunityMessage {
  return {
    id: 'm1',
    sender_name: 'Jordan M.',
    sender_type: 'USER',
    message: 'hello',
    created_at: '2026-08-20T14:00:00Z',
    reactions: [],
    ...over,
  }
}

function feed(...messages: CommunityMessage[]): CommunityFeed {
  return { channels: [], messages, online_count: 0, members: [] }
}

const flameOn = (f: CommunityFeed | undefined, id = 'm1') =>
  f?.messages.find((m) => m.id === id)?.reactions.find((r) => r.emoji === FLAME)

describe('applyFlame', () => {
  it('adds my flame from nothing', () => {
    const r = flameOn(applyFlame(feed(msg()), 'm1'))
    expect(r).toEqual({ emoji: FLAME, count: 1, mine: true })
  })

  it('joins an existing count', () => {
    const r = flameOn(applyFlame(feed(msg({ reactions: [{ emoji: FLAME, count: 11, mine: false }] })), 'm1'))
    expect(r).toEqual({ emoji: FLAME, count: 12, mine: true })
  })

  it('removes mine and drops the entry at zero', () => {
    // A leftover {count:0} entry would still render the row as reacted.
    const r = flameOn(applyFlame(feed(msg({ reactions: [{ emoji: FLAME, count: 1, mine: true }] })), 'm1'))
    expect(r).toBeUndefined()
  })

  it('removes mine but keeps other people’s flames', () => {
    const r = flameOn(applyFlame(feed(msg({ reactions: [{ emoji: FLAME, count: 9, mine: true }] })), 'm1'))
    expect(r).toEqual({ emoji: FLAME, count: 8, mine: false })
  })

  it('never produces a negative count even from inconsistent server state', () => {
    const r = flameOn(applyFlame(feed(msg({ reactions: [{ emoji: FLAME, count: 0, mine: true }] })), 'm1'))
    // count would be -1; it is floored and, being zero with mine=false, the entry goes.
    expect(r).toBeUndefined()
  })

  it('round-trips: two taps return to the original state', () => {
    const start = feed(msg({ reactions: [{ emoji: FLAME, count: 4, mine: false }] }))
    const twice = applyFlame(applyFlame(start, 'm1'), 'm1')
    expect(flameOn(twice)).toEqual({ emoji: FLAME, count: 4, mine: false })
  })

  it('preserves reactions that are not the flame', () => {
    const other = { emoji: '🎯', count: 3, mine: false }
    const out = applyFlame(feed(msg({ reactions: [other] })), 'm1')
    expect(out!.messages[0].reactions).toContainEqual(other)
    expect(flameOn(out)!.count).toBe(1)
  })

  it('touches only the targeted message', () => {
    const out = applyFlame(feed(msg({ id: 'm1' }), msg({ id: 'm2' })), 'm2')
    expect(flameOn(out, 'm1')).toBeUndefined()
    expect(flameOn(out, 'm2')!.mine).toBe(true)
  })

  it('is a no-op on undefined and on an unknown id', () => {
    expect(applyFlame(undefined, 'm1')).toBeUndefined()
    const out = applyFlame(feed(msg()), 'nope')
    expect(flameOn(out)).toBeUndefined()
  })

  it('sends the flame, never a heart — the server would reject one', () => {
    expect(FLAME).toBe('🔥')
  })
})
