import { describe, it, expect, vi } from 'vitest'
import { showToast, subscribeToast } from '@/notifications/toast'

describe('toast bus', () => {
  it('delivers a shown message to every subscriber, with a unique id', () => {
    const received: Array<{ id: number; message: string } | null> = []
    const unsub = subscribeToast((e) => received.push(e))
    showToast('Spark paused')
    expect(received).toHaveLength(1)
    expect(received[0]?.message).toBe('Spark paused')
    unsub()
  })

  it('a later subscriber never replays an earlier message — it is a bus, not a store', () => {
    const cb = vi.fn()
    showToast('first (before subscribing)')
    const unsub = subscribeToast(cb)
    expect(cb).not.toHaveBeenCalled()
    unsub()
  })

  it('unsubscribing stops delivery', () => {
    const cb = vi.fn()
    const unsub = subscribeToast(cb)
    unsub()
    showToast('after unsubscribe')
    expect(cb).not.toHaveBeenCalled()
  })

  it('each call gets a distinct id, even for the same message', () => {
    const ids: number[] = []
    const unsub = subscribeToast((e) => e && ids.push(e.id))
    showToast('same message')
    showToast('same message')
    expect(ids[0]).not.toBe(ids[1])
    unsub()
  })
})
