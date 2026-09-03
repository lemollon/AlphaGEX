import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

/**
 * track.ts keeps its batch queue in module state, so every test re-imports it fresh
 * (vi.resetModules) rather than sharing one import across the file — otherwise events
 * from one test would leak into the next test's batch.
 */
vi.mock('react-native', () => ({ Platform: { OS: 'ios' } }))
vi.mock('expo-constants', () => ({
  default: { expoConfig: { version: '1.0.0', extra: { apiBase: 'https://example.test' } } },
}))

const apiMock = vi.fn()
vi.mock('@/api/client', () => ({ api: apiMock }))

const captureApiErrorMock = vi.fn()
vi.mock('@/monitoring/sentry', () => ({ captureApiError: captureApiErrorMock }))

async function loadTrack() {
  vi.resetModules()
  apiMock.mockReset()
  captureApiErrorMock.mockReset()
  apiMock.mockResolvedValue({ ok: true, accepted: 0 })
  const mod = await import('@/analytics/track')
  return mod.track
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('track — key redaction', () => {
  it('drops any prop key matching /account|token|password|secret/i', async () => {
    const track = await loadTrack()
    track('sign_in_attempted', {
      accountId: 'acct_1',
      authToken: 'tok_1',
      userPassword: 'hunter2',
      apiSecret: 'shh',
      screen: 'sign-in',
      attempt: 1,
    })
    await vi.advanceTimersByTimeAsync(10_000)

    expect(apiMock).toHaveBeenCalledTimes(1)
    const [, opts] = apiMock.mock.calls[0]
    const events = (opts.body as { events: Array<{ props?: Record<string, unknown> }> }).events
    expect(events).toHaveLength(1)
    expect(events[0].props).toEqual({ screen: 'sign-in', attempt: 1 })
  })

  it('sends an event with no props at all as undefined, not an empty leaked object', async () => {
    const track = await loadTrack()
    track('app_opened')
    await vi.advanceTimersByTimeAsync(10_000)

    const [, opts] = apiMock.mock.calls[0]
    const events = (opts.body as { events: Array<{ props?: unknown }> }).events
    expect(events[0].props).toBeUndefined()
  })
})

describe('track — batching', () => {
  it('flushes on a 10s timer when the batch never fills', async () => {
    const track = await loadTrack()
    track('screen_view', { path: '/live' })
    expect(apiMock).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(9_999)
    expect(apiMock).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1)
    expect(apiMock).toHaveBeenCalledTimes(1)
  })

  it('flushes immediately once 20 events have queued, without waiting for the timer', async () => {
    const track = await loadTrack()
    for (let i = 0; i < 20; i++) track('screen_view', { i })

    expect(apiMock).toHaveBeenCalledTimes(1)
    const [, opts] = apiMock.mock.calls[0]
    const events = (opts.body as { events: unknown[] }).events
    expect(events).toHaveLength(20)
  })

  it('starts a fresh batch after a flush rather than re-sending old events', async () => {
    const track = await loadTrack()
    track('screen_view', { path: '/live' })
    await vi.advanceTimersByTimeAsync(10_000)
    expect(apiMock).toHaveBeenCalledTimes(1)

    track('screen_view', { path: '/community' })
    await vi.advanceTimersByTimeAsync(10_000)
    expect(apiMock).toHaveBeenCalledTimes(2)

    const [, secondOpts] = apiMock.mock.calls[1]
    const events = (secondOpts.body as { events: Array<{ props?: Record<string, unknown> }> }).events
    expect(events).toHaveLength(1)
    expect(events[0].props).toEqual({ path: '/community' })
  })
})

describe('track — never throws', () => {
  it('swallows a network failure rather than rejecting or throwing', async () => {
    const track = await loadTrack()
    apiMock.mockRejectedValue(new Error('network down'))

    expect(() => track('screen_view', { path: '/live' })).not.toThrow()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(apiMock).toHaveBeenCalledTimes(1)
  })

  it('reports a status >= 500 api_error event to Sentry via captureApiError', async () => {
    const track = await loadTrack()
    track('api_error', { status: 502, path: '/api/live/summary' })
    expect(captureApiErrorMock).toHaveBeenCalledTimes(1)
    const err = captureApiErrorMock.mock.calls[0][0] as { status: number; message: string }
    expect(err.status).toBe(502)
    expect(err.message).toContain('/api/live/summary')
  })

  it('does not report a client error (4xx) to Sentry', async () => {
    const track = await loadTrack()
    track('api_error', { status: 404, path: '/api/live/summary' })
    expect(captureApiErrorMock).not.toHaveBeenCalled()
  })
})
