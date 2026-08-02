import { describe, it, expect, vi, beforeEach } from 'vitest'

/**
 * The `client` field decides where a completed OAuth round-trip sends the customer.
 * It is stored server-side with the state precisely so a caller cannot pick its own
 * return surface — these pin the defaulting, which must never fail OPEN to 'mobile'
 * (that would strand a web customer on a bridge page their browser cannot act on).
 */
const rows: Array<Record<string, unknown>> = []
const inserts: unknown[][] = []

vi.mock('@/lib/customers-db', () => ({
  customerExecute: async (_sql: string, params: unknown[]) => {
    inserts.push(params)
    return 1
  },
  customerQuery: async () => rows.splice(0, rows.length),
}))

const { asClient, createOAuthState, consumeOAuthState } = await import(
  '@/lib/enrollment/oauth-state'
)

beforeEach(() => {
  inserts.length = 0
  rows.length = 0
})

describe('asClient', () => {
  it('recognises mobile', () => {
    expect(asClient('mobile')).toBe('mobile')
  })

  // Fail toward WEB. A wrong 'web' just sends a mobile user to a web page they can
  // still read; a wrong 'mobile' hands a desktop browser an ironforge:// URL it
  // cannot open, which is a dead end.
  it.each(['web', '', null, undefined, 'MOBILE', 'ios', 42, {}])(
    'defaults %o to web',
    (v) => {
      expect(asClient(v)).toBe('web')
    },
  )
})

describe('createOAuthState', () => {
  it('persists the client alongside the state', async () => {
    await createOAuthState({ userId: 'u1', brokerCode: 'snaptrade', pkce: false, client: 'mobile' })
    expect(inserts[0]).toContain('mobile')
  })

  it('defaults to web when the caller does not say', async () => {
    await createOAuthState({ userId: 'u1', brokerCode: 'snaptrade', pkce: false })
    expect(inserts[0]).toContain('web')
  })

  it('never returns the PKCE verifier to the caller', async () => {
    // The verifier must stay server-side; handing it back would defeat PKCE entirely.
    const out = await createOAuthState({ userId: 'u1', brokerCode: 'tradier', pkce: true })
    expect(out).toHaveProperty('codeChallenge')
    expect(JSON.stringify(out)).not.toContain('codeVerifier')
  })
})

describe('consumeOAuthState', () => {
  it('reads the client back off the record', async () => {
    rows.push({
      state: 's1',
      user_id: 'u1',
      broker_code: 'snaptrade',
      code_verifier: null,
      return_to: 'enroll',
      client: 'mobile',
    })
    const rec = await consumeOAuthState('s1')
    expect(rec?.client).toBe('mobile')
    expect(rec?.userId).toBe('u1')
  })

  it('treats a legacy row with no client as web', async () => {
    // Rows written before the column existed have client = NULL. They must keep
    // working as web rather than becoming undefined.
    rows.push({
      state: 's2',
      user_id: 'u2',
      broker_code: 'tradier',
      code_verifier: null,
      return_to: null,
      client: null,
    })
    expect((await consumeOAuthState('s2'))?.client).toBe('web')
  })

  it('returns null for a missing/replayed/expired state without saying which', async () => {
    expect(await consumeOAuthState('nope')).toBeNull()
    expect(await consumeOAuthState(null)).toBeNull()
    expect(await consumeOAuthState('')).toBeNull()
  })
})
