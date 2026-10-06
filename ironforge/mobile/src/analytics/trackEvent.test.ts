import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.mock('react-native', () => ({ Platform: { OS: 'ios' } }))

const apiMock = vi.fn()
vi.mock('@/api/client', () => ({ api: apiMock }))

const store = new Map<string, string>()
vi.mock('@/api/storage', () => ({
  getItem: vi.fn(async (k: string) => store.get(k) ?? null),
  setItem: vi.fn(async (k: string, v: string) => {
    store.set(k, v)
  }),
}))

async function loadTrackEvent() {
  vi.resetModules()
  apiMock.mockReset()
  apiMock.mockResolvedValue({ ok: true, accepted: 0 })
  const mod = await import('./trackEvent')
  return mod
}

beforeEach(() => {
  vi.useFakeTimers()
  store.clear()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('trackEvent — allowlist', () => {
  it('drops an event name not on the dev-handoff allowlist', async () => {
    const { trackEvent } = await loadTrackEvent()
    trackEvent('made_up_event', { x: 1 })
    await vi.advanceTimersByTimeAsync(10_000)
    expect(apiMock).not.toHaveBeenCalled()
  })

  it('sends an allowlisted event to /api/v1/events', async () => {
    const { trackEvent } = await loadTrackEvent()
    trackEvent('tab_view', { tab: 'forge' })
    await vi.advanceTimersByTimeAsync(10_000)

    expect(apiMock).toHaveBeenCalledTimes(1)
    const [path, opts] = apiMock.mock.calls[0]
    expect(path).toBe('/api/v1/events')
    const body = opts.body as { events: Array<{ event: string; props?: unknown; surface: string }>; surface: string; anon_id?: string }
    expect(body.events).toEqual([{ event: 'tab_view', props: { tab: 'forge' }, surface: 'ios' }])
    expect(body.surface).toBe('ios')
    expect(typeof body.anon_id).toBe('string')
  })
})

describe('trackEvent — anon_id', () => {
  it('persists and reuses the same anon_id across flushes', async () => {
    const { trackEvent } = await loadTrackEvent()
    trackEvent('app_open')
    await vi.advanceTimersByTimeAsync(10_000)
    trackEvent('theme_toggle', { theme: 'dark' })
    await vi.advanceTimersByTimeAsync(10_000)

    expect(apiMock).toHaveBeenCalledTimes(2)
    const first = (apiMock.mock.calls[0][1].body as { anon_id: string }).anon_id
    const second = (apiMock.mock.calls[1][1].body as { anon_id: string }).anon_id
    expect(first).toBe(second)
  })
})

describe('trackEvent — batching', () => {
  it('flushes immediately once 20 events have queued', async () => {
    const { trackEvent } = await loadTrackEvent()
    for (let i = 0; i < 20; i++) trackEvent('chart_scrub')
    expect(apiMock).toHaveBeenCalledTimes(1)
    const body = apiMock.mock.calls[0][1].body as { events: unknown[] }
    expect(body.events).toHaveLength(20)
  })
})

describe('trackEvent — retry', () => {
  it('re-queues a failed batch once, then drops it on a second failure', async () => {
    const { trackEvent } = await loadTrackEvent()
    apiMock.mockRejectedValue(new Error('network down'))

    trackEvent('pause_all')
    await vi.advanceTimersByTimeAsync(10_000) // 1st attempt fails, re-queued
    await vi.advanceTimersByTimeAsync(10_000) // 2nd attempt fails, dropped

    expect(apiMock).toHaveBeenCalledTimes(2)

    apiMock.mockResolvedValue({ ok: true, accepted: 0 })
    await vi.advanceTimersByTimeAsync(10_000) // nothing left to send
    expect(apiMock).toHaveBeenCalledTimes(2)
  })

  it('never throws even if the network call rejects', async () => {
    const { trackEvent } = await loadTrackEvent()
    apiMock.mockRejectedValue(new Error('down'))
    expect(() => trackEvent('community_post')).not.toThrow()
  })
})
