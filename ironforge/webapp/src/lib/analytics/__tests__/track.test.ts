// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('track (web)', () => {
  const originalSendBeacon = (globalThis as any).navigator?.sendBeacon
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.resetModules()
    window.localStorage.clear()
    fetchMock = vi.fn().mockResolvedValue({ ok: true })
    ;(globalThis as any).fetch = fetchMock
    // sendBeacon is preferred when present — remove it so these tests exercise
    // the fetch fallback deterministically across environments.
    if ((globalThis as any).navigator) (globalThis as any).navigator.sendBeacon = undefined
  })

  afterEach(() => {
    if ((globalThis as any).navigator) (globalThis as any).navigator.sendBeacon = originalSendBeacon
  })

  it('posts to /api/v1/events with a generated anon_id', async () => {
    const { track } = await import('../track')
    track('cta_click', { cta: 'create_account', placement: 'hero' })
    await Promise.resolve()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, opts] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/events')
    const body = JSON.parse(opts.body as string)
    expect(body.event).toBe('cta_click')
    expect(body.props).toEqual({ cta: 'create_account', placement: 'hero' })
    expect(body.surface).toBe('web')
    expect(typeof body.anon_id).toBe('string')
    expect(body.anon_id.length).toBeGreaterThan(0)
  })

  it('reuses the same anon_id across calls', async () => {
    const { track } = await import('../track')
    track('cta_click', { cta: 'create_account', placement: 'hero' })
    track('agent_filter', { filter: 'morning' })
    await Promise.resolve()

    const first = JSON.parse(fetchMock.mock.calls[0][1].body as string).anon_id
    const second = JSON.parse(fetchMock.mock.calls[1][1].body as string).anon_id
    expect(first).toBe(second)
  })

  it('never throws even if fetch rejects', async () => {
    fetchMock.mockRejectedValue(new Error('network down'))
    const { track } = await import('../track')
    expect(() => track('enroll_sso', { provider: 'google' })).not.toThrow()
  })

  it('uses sendBeacon when available, with no anon_id for a signed-in caller handled server-side', async () => {
    const beacon = vi.fn().mockReturnValue(true)
    ;(globalThis as any).navigator.sendBeacon = beacon
    const { track } = await import('../track')
    track('enroll_complete', { agent: 'spark' })

    expect(beacon).toHaveBeenCalledTimes(1)
    expect(fetchMock).not.toHaveBeenCalled()
    const [url] = beacon.mock.calls[0]
    expect(url).toBe('/api/v1/events')
  })
})
