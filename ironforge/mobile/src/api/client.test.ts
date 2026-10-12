import { describe, it, expect, vi, beforeEach } from 'vitest'

/**
 * The sign-in loop (see onSessionChange in api/client).
 *
 * client.ts reaches expo-constants directly and react-native + expo-secure-store
 * through api/storage. None of that exists in the node test environment and none of it
 * is the subject here: what is under test is whether the two functions that own the
 * tokens announce that the session changed. Mock the edges, keep client.ts real.
 */
vi.mock('expo-constants', () => ({
  default: { expoConfig: { extra: { apiBase: 'https://example.test' } } },
}))

const store = new Map<string, string>()

vi.mock('@/api/storage', () => ({
  setItem: async (k: string, v: string) => {
    store.set(k, v)
  },
  getItem: async (k: string) => store.get(k) ?? null,
  deleteItem: async (k: string) => {
    store.delete(k)
  },
  AFTER_FIRST_UNLOCK: 'AFTER_FIRST_UNLOCK',
}))

const swrMutateMock = vi.fn(async (_key?: unknown, _data?: unknown, _opts?: unknown) => undefined)
vi.mock('swr', () => ({ mutate: swrMutateMock }))

const { saveTokens, clearTokens, onSessionChange, hasSession, refreshAccessToken } = await import(
  '@/api/client'
)

const PAIR = { accessToken: 'access-1', refreshToken: 'refresh-1' }

beforeEach(() => {
  store.clear()
  swrMutateMock.mockClear()
})

describe('onSessionChange', () => {
  it('announces a sign-in, so the auth gate is not frozen at its cold-start value', async () => {
    // This is the shipped bug reproduced at the layer that caused it. The root layout
    // reads hasSession() once at mount; on a fresh install that is false. A successful
    // login then saved the tokens and navigated to '/', but the gate still held false
    // and replaced straight back to /sign-in — "Signing in…", then a blank form, on a
    // loop, with no error to explain it. Nothing about it was iOS-specific.
    let gateBelievesSignedIn = await hasSession()
    expect(gateBelievesSignedIn).toBe(false)

    onSessionChange((v) => {
      gateBelievesSignedIn = v
    })

    await saveTokens(PAIR)

    expect(gateBelievesSignedIn).toBe(true)
    expect(await hasSession()).toBe(true)
  })

  it('announces a sign-out, so a signed-out app is not bounced back into the tabs', async () => {
    // The mirror failure, and the reason this lives in clearTokens rather than in the
    // account screen: doSignOut() replaced to /sign-in while the gate still held true,
    // and the gate sent them right back in.
    await saveTokens(PAIR)

    let gateBelievesSignedIn = true
    onSessionChange((v) => {
      gateBelievesSignedIn = v
    })

    await clearTokens()

    expect(gateBelievesSignedIn).toBe(false)
    expect(await hasSession()).toBe(false)
  })

  it('stops delivering after unsubscribe', async () => {
    const seen: boolean[] = []
    const off = onSessionChange((v) => seen.push(v))

    await saveTokens(PAIR)
    off()
    await clearTokens()

    expect(seen).toEqual([true])
  })

  it('delivers to every subscriber', async () => {
    const a: boolean[] = []
    const b: boolean[] = []
    onSessionChange((v) => a.push(v))
    onSessionChange((v) => b.push(v))

    await saveTokens(PAIR)

    expect(a).toEqual([true])
    expect(b).toEqual([true])
  })

  it('survives a listener that unsubscribes itself mid-notify', async () => {
    // Iterating the live Set would skip the next listener here. React cleanups run at
    // arbitrary times, so this is not hypothetical.
    const seen: boolean[] = []
    const off = onSessionChange(() => off())
    onSessionChange((v) => seen.push(v))

    await expect(saveTokens(PAIR)).resolves.toBeUndefined()
    expect(seen).toEqual([true])
  })
})

describe('clearTokens cache hygiene', () => {
  it('clears the global SWR cache on sign-out, so a different account on the same device never sees the prior one\'s data', async () => {
    await saveTokens(PAIR)
    await clearTokens()
    expect(swrMutateMock).toHaveBeenCalledTimes(1)
    // No key filter is passed as the data — every cached key gets cleared, not just a
    // named subset the author remembered to list.
    const [, data, opts] = swrMutateMock.mock.calls[0]
    expect(data).toBeUndefined()
    expect(opts).toMatchObject({ revalidate: false })
  })

  it('a failure clearing the SWR cache still completes sign-out (tokens gone, listeners notified)', async () => {
    swrMutateMock.mockRejectedValueOnce(new Error('cache blip'))
    await saveTokens(PAIR)

    let gateBelievesSignedIn = true
    onSessionChange((v) => {
      gateBelievesSignedIn = v
    })

    await expect(clearTokens()).resolves.toBeUndefined()
    expect(gateBelievesSignedIn).toBe(false)
    expect(await hasSession()).toBe(false)
  })
})

describe('refreshAccessToken timeout', () => {
  it('gives up on a hung refresh request instead of blocking every caller forever', async () => {
    await saveTokens(PAIR)
    vi.useFakeTimers()
    const abortedSignals: AbortSignal[] = []
    const originalFetch = global.fetch
    // Never resolves on its own — only an abort() on the passed signal ends it, exactly
    // the hang this fix exists to bound.
    global.fetch = vi.fn((_url: string, init?: RequestInit) => {
      const signal = init?.signal as AbortSignal
      abortedSignals.push(signal)
      return new Promise((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(new Error('aborted')))
      })
    }) as typeof fetch

    try {
      const pending = refreshAccessToken()
      await vi.advanceTimersByTimeAsync(15_000)
      const result = await pending
      expect(result).toBeNull()
      expect(abortedSignals[0]?.aborted).toBe(true)
    } finally {
      global.fetch = originalFetch
      vi.useRealTimers()
    }
  })
})
