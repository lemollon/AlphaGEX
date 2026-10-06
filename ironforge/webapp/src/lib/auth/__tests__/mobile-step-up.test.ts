import { describe, it, expect, vi, beforeEach } from 'vitest'
import { requireIdentityWithStepUp, STEP_UP_CAPABLE_HEADER } from '@/lib/auth/mobile-step-up'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { headers } from 'next/headers'

vi.mock('@/lib/auth/customer-identity', () => ({ getCustomerIdentity: vi.fn() }))
vi.mock('next/headers', () => ({ headers: vi.fn() }))

const mockedGetIdentity = vi.mocked(getCustomerIdentity)
const mockedHeaders = vi.mocked(headers)

/** A minimal Headers-like stub — only `.get(name)` is ever called here. */
function headerStore(capableValue: string | null) {
  return {
    get: (name: string) => (name === STEP_UP_CAPABLE_HEADER ? capableValue : null),
  } as unknown as ReturnType<typeof headers>
}

beforeEach(() => {
  mockedGetIdentity.mockReset()
  mockedHeaders.mockReset()
})

describe('requireIdentityWithStepUp', () => {
  it('web cookie session passes through unchanged, regardless of the header', async () => {
    mockedHeaders.mockReturnValue(headerStore(null))
    mockedGetIdentity.mockResolvedValueOnce({ customerId: 'u1', source: 'cookie' } as never)

    const res = await requireIdentityWithStepUp()

    expect(res.error).toBeNull()
    expect(res.identity?.customerId).toBe('u1')
    // Resolved on the FIRST lookup alone — a cookie session never triggers a
    // second, step-up-specific identity check.
    expect(mockedGetIdentity).toHaveBeenCalledTimes(1)
  })

  it('old client (no capability header): a plain bearer token is allowed — today\'s behavior, unchanged', async () => {
    mockedHeaders.mockReturnValue(headerStore(null))
    mockedGetIdentity.mockResolvedValueOnce({ customerId: 'u1', source: 'bearer' } as never)

    const res = await requireIdentityWithStepUp()

    expect(res.error).toBeNull()
    expect(res.identity?.customerId).toBe('u1')
    expect(mockedGetIdentity).toHaveBeenCalledTimes(1)
  })

  it('old client (no header), no session at all: unauthorized, not step_up_required', async () => {
    mockedHeaders.mockReturnValue(headerStore(null))
    mockedGetIdentity.mockResolvedValueOnce(null)

    const res = await requireIdentityWithStepUp()

    expect(res.error).toBe('unauthorized')
    expect(res.identity).toBeNull()
  })

  it('new client (header=1) with only a plain access token: step_up_required', async () => {
    mockedHeaders.mockReturnValue(headerStore('1'))
    mockedGetIdentity
      .mockResolvedValueOnce({ customerId: 'u1', source: 'bearer' } as never) // plain pass succeeds
      .mockResolvedValueOnce(null) // step-up pass: a plain 'acc' token is not type 'step'

    const res = await requireIdentityWithStepUp()

    expect(res.error).toBe('step_up_required')
    expect(res.identity).toBeNull()
    expect(mockedGetIdentity).toHaveBeenNthCalledWith(2, { requireStepUp: true })
  })

  it('new client (header=1) presenting an actual step-up token: allowed', async () => {
    mockedHeaders.mockReturnValue(headerStore('1'))
    mockedGetIdentity
      .mockResolvedValueOnce(null) // plain pass: a 'step' token fails type:'acc' verification
      .mockResolvedValueOnce({ customerId: 'u1', source: 'bearer' } as never) // step-up pass succeeds

    const res = await requireIdentityWithStepUp()

    expect(res.error).toBeNull()
    expect(res.identity?.customerId).toBe('u1')
  })

  it('new client (header=1), no token at all: unauthorized', async () => {
    mockedHeaders.mockReturnValue(headerStore('1'))
    mockedGetIdentity.mockResolvedValueOnce(null).mockResolvedValueOnce(null)

    const res = await requireIdentityWithStepUp()

    expect(res.error).toBe('unauthorized')
    expect(res.identity).toBeNull()
  })
})
