import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

/**
 * Covers the six CRM gaps from the 8/2 review. These are exactly the paths that CANNOT be
 * verified live: reactivation and membership history need real Stripe traffic (forging a webhook
 * means writing a fake membership into production and calling that evidence), and the Attio list
 * calls need a workspace key. So the assertions here are the verification.
 */

const OLD_ENV = { ...process.env }

vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: vi.fn(() => true),
  customerQuery: vi.fn(),
  customerExecute: vi.fn(),
}))

vi.mock('@/lib/billing/stripe', () => ({ verifyStripeSignature: vi.fn(() => true) }))

vi.mock('@/lib/crm/outbox', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/crm/outbox')>()
  return { ...actual, enqueueCrmEvent: vi.fn(async () => ({ enqueued: true })) }
})

vi.mock('@/lib/auth/customer-identity', () => ({
  getCustomerIdentity: vi.fn(async () => ({ customerId: 'user-1', source: 'cookie' })),
}))

import { customerQuery, customerExecute } from '@/lib/customers-db'
import { enqueueCrmEvent } from '@/lib/crm/outbox'

const mockQuery = vi.mocked(customerQuery)
const mockExecute = vi.mocked(customerExecute)
const mockEnqueue = vi.mocked(enqueueCrmEvent)

/** The single enqueued event, asserted to be the only one. */
function onlyEvent() {
  expect(mockEnqueue).toHaveBeenCalledTimes(1)
  return mockEnqueue.mock.calls[0][0]
}

beforeEach(() => {
  vi.clearAllMocks()
  process.env.ATTIO_API_KEY = 'test-attio-key'
  process.env.ATTIO_WAITLIST_LIST = 'ironforge_waitlist'
})

afterEach(() => {
  process.env = { ...OLD_ENV }
})

// ---------------------------------------------------------------------------
// Gap 1 — crm.reactivation was mapped in events.ts but nothing ever emitted it
// ---------------------------------------------------------------------------

describe('billing webhook — reactivation detection', () => {
  function stripeEvent(type: string, obj: Record<string, unknown>) {
    return new Request('http://localhost/api/billing/webhook', {
      method: 'POST',
      headers: { 'stripe-signature': 't=1,v1=sig' },
      body: JSON.stringify({ id: 'evt_1', type, created: 1767225600, data: { object: obj } }),
    })
  }

  /**
   * The webhook's queries in order: dedupe claim (execute), resolveUserId, canceledBotsFor,
   * the upsert (execute), then getUserBasic inside the emitter.
   */
  function wireQueries(priorCanceled: boolean) {
    mockExecute.mockResolvedValue(1)
    mockQuery.mockImplementation(async (sql: string) => {
      if (sql.includes('FROM users WHERE stripe_customer_id')) return [{ id: 'user-1' }] as never
      if (sql.includes("status = 'canceled'")) return (priorCanceled ? [{ bot: 'spark' }] : []) as never
      if (sql.includes('SELECT email, first_name, last_name')) {
        return [{ email: 'ada@example.com', first_name: 'Ada', last_name: 'Lovelace' }] as never
      }
      return [] as never
    })
  }

  it('emits crm.reactivation when a previously canceled bot goes active again', async () => {
    process.env.STRIPE_WEBHOOK_SECRET = 'whsec_test'
    wireQueries(true)
    const { POST } = await import('@/app/api/billing/webhook/route')
    await POST(stripeEvent('customer.subscription.created', {
      id: 'sub_new', status: 'active', customer: 'cus_1', metadata: { bot: 'spark' },
    }) as never)

    const event = onlyEvent()
    expect(event.eventType).toBe('crm.reactivation')
    // membership_id is the NEW subscription id, which is what preserves the prior
    // membership as history instead of overwriting it (AC-CRM-013).
    expect(event.payload.membershipId).toBe('sub_new')
  })

  it('emits crm.stripe_customer_created for a genuine first-time subscriber', async () => {
    process.env.STRIPE_WEBHOOK_SECRET = 'whsec_test'
    wireQueries(false)
    const { POST } = await import('@/app/api/billing/webhook/route')
    await POST(stripeEvent('customer.subscription.created', {
      id: 'sub_new', status: 'active', customer: 'cus_1', metadata: { bot: 'spark' },
    }) as never)

    expect(onlyEvent().eventType).toBe('crm.stripe_customer_created')
  })

  it('correlates on the membership, not the Stripe event id', async () => {
    process.env.STRIPE_WEBHOOK_SECRET = 'whsec_test'
    wireQueries(false)
    const { POST } = await import('@/app/api/billing/webhook/route')
    await POST(stripeEvent('customer.subscription.created', {
      id: 'sub_new', status: 'active', customer: 'cus_1', metadata: { bot: 'spark' },
    }) as never)

    const event = onlyEvent()
    expect(event.correlationId).toBe('sub_new')
    expect(event.correlationId).not.toBe(event.eventId)
  })
})

// ---------------------------------------------------------------------------
// Gap 2 — the 'Paused' lifecycle had no emitter at all
// ---------------------------------------------------------------------------

describe('automation pause — CRM mirror', () => {
  function pauseRequest(paused: boolean) {
    return new Request('http://localhost/api/v1/automation/pause', {
      method: 'POST',
      body: JSON.stringify({ paused }),
    })
  }

  function wire(subStatus: string | null) {
    mockExecute.mockResolvedValue(1) // the UPDATE reports a real transition
    mockQuery.mockImplementation(async (sql: string) => {
      if (sql.includes('SELECT email, first_name, last_name')) {
        return [{ email: 'ada@example.com', first_name: 'Ada', last_name: 'Lovelace' }] as never
      }
      if (sql.includes('FROM customer_bot_subscriptions')) {
        return (subStatus ? [{ stripe_subscription_id: 'sub_1', status: subStatus }] : []) as never
      }
      return [] as never // liveActivations
    })
  }

  it('publishes Paused on pause', async () => {
    wire('active')
    const { POST } = await import('@/app/api/v1/automation/pause/route')
    await POST(pauseRequest(true) as never)

    const event = onlyEvent()
    expect(event.eventType).toBe('crm.membership_paused')
    expect(event.payload.membershipStatus).toBe('Paused')
    expect(event.payload.lifecycle).toBe('Paused')
  })

  it('resumes to Active when the subscription is genuinely active', async () => {
    wire('active')
    const { POST } = await import('@/app/api/v1/automation/pause/route')
    await POST(pauseRequest(false) as never)

    const event = onlyEvent()
    expect(event.payload.membershipStatus).toBe('Active')
    expect(event.payload.lifecycle).toBe('Active')
  })

  it('resumes a past_due customer as Past Due, never Active', async () => {
    wire('past_due')
    const { POST } = await import('@/app/api/v1/automation/pause/route')
    await POST(pauseRequest(false) as never)

    const event = onlyEvent()
    expect(event.payload.membershipStatus).toBe('Past Due')
    // No lifecycle at all — a failed card is not "in good standing".
    expect(event.payload.lifecycle).toBeUndefined()
  })

  it('emits nothing when there is no membership to mark', async () => {
    wire(null)
    const { POST } = await import('@/app/api/v1/automation/pause/route')
    await POST(pauseRequest(true) as never)

    // Inventing a membershipId would create a stray Attio record nothing reconciles.
    expect(mockEnqueue).not.toHaveBeenCalled()
  })

  it('never lets a CRM failure break the pause itself', async () => {
    wire('active')
    mockEnqueue.mockRejectedValueOnce(new Error('outbox down'))
    const { POST } = await import('@/app/api/v1/automation/pause/route')
    const res = await POST(pauseRequest(true) as never)

    // Pausing is a risk control: it must return 200 even when the CRM is on fire.
    expect(res.status).toBe(200)
  })
})

// ---------------------------------------------------------------------------
// Gaps 4 + 6 — waitlist list entries and the structured signup fields
// ---------------------------------------------------------------------------

describe('waitlist list entries', () => {
  const CONTACT = {
    firstName: 'Ada', lastName: 'Lovelace', email: 'ada@example.com', phone: '+15551234567',
    city: 'Austin', state: 'TX', tradingCapitalRange: '50000_plus',
    consentVersion: 'waitlist-v1', submissionId: 'wl_1',
  }

  function jsonResponse(body: unknown) {
    return { ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) } as Response
  }

  it('PATCHes the existing entry on a resubmit instead of creating a duplicate', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (String(url).includes('/objects/people/records')) {
        return jsonResponse({ data: { id: { record_id: 'rec_1' } } })
      }
      if (String(url).endsWith('/entries/query')) {
        return jsonResponse({ data: [{ id: { entry_id: 'entry_1' } }] })
      }
      return jsonResponse({ data: {} })
    })
    vi.stubGlobal('fetch', fetchMock)

    const { upsertWaitlistToAttio } = await import('@/lib/attio')
    await upsertWaitlistToAttio(CONTACT)

    const entryCalls = fetchMock.mock.calls.filter(
      ([url]) => String(url).includes('/entries') && !String(url).endsWith('/query'),
    )
    expect(entryCalls).toHaveLength(1)
    expect(entryCalls[0][1]?.method).toBe('PATCH')
    expect(String(entryCalls[0][0])).toContain('entry_1')
  })

  it('creates the entry when the person has none yet', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).includes('/objects/people/records')) {
        return jsonResponse({ data: { id: { record_id: 'rec_1' } } })
      }
      if (String(url).endsWith('/entries/query')) return jsonResponse({ data: [] })
      return jsonResponse({ data: {} })
    })
    vi.stubGlobal('fetch', fetchMock)

    const { upsertWaitlistToAttio } = await import('@/lib/attio')
    await upsertWaitlistToAttio(CONTACT)

    const create = fetchMock.mock.calls.find(
      ([url, init]) => String(url).endsWith('/entries') && (init as RequestInit)?.method === 'POST',
    )
    expect(create).toBeDefined()
    const body = JSON.parse(String((create![1] as RequestInit).body))
    expect(body.data.entry_values.confirmation_email_status).toBe('Pending')
  })

  it('moves confirmation_email_status off Pending once the email resolves', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).endsWith('/entries/query')) {
        return jsonResponse({ data: [{ id: { entry_id: 'entry_1' } }] })
      }
      return jsonResponse({ data: {} })
    })
    vi.stubGlobal('fetch', fetchMock)

    const { setWaitlistConfirmationStatus } = await import('@/lib/attio')
    await setWaitlistConfirmationStatus('rec_1', 'failed')

    const patch = fetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'PATCH')
    expect(patch).toBeDefined()
    const body = JSON.parse(String((patch![1] as RequestInit).body))
    expect(body.data.entry_values.confirmation_email_status).toBe('failed')
  })
})

describe('person upsert — structured fields that replaced the legacy signup Note', () => {
  it('writes state as primary_location and lead_source when the event carries them', async () => {
    const fetchMock = vi.fn(async () =>
      ({ ok: true, status: 200, json: async () => ({ data: { id: { record_id: 'rec_1' } } }), text: async () => '' }) as Response,
    )
    vi.stubGlobal('fetch', fetchMock)

    const { deliverCrmEvent } = await import('@/lib/crm/events')
    await deliverCrmEvent('crm.account_created', {
      email: 'ada@example.com', firstName: 'Ada', lastName: 'Lovelace',
      state: 'TX', ironforgeUserId: 'user-1', leadSource: 'Referral',
    })

    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body))
    expect(body.data.values.primary_location[0].region).toBe('TX')
    expect(body.data.values.lead_source).toBe('Referral')
    expect(body.data.values.customer_lifecycle).toBe('Enrollment Started')
  })

  it('omits lead_source entirely when the emitter does not know it', async () => {
    const fetchMock = vi.fn(async () =>
      ({ ok: true, status: 200, json: async () => ({ data: { id: { record_id: 'rec_1' } } }), text: async () => '' }) as Response,
    )
    vi.stubGlobal('fetch', fetchMock)

    const { deliverCrmEvent } = await import('@/lib/crm/events')
    await deliverCrmEvent('crm.account_created', {
      email: 'ada@example.com', firstName: 'Ada', ironforgeUserId: 'user-1',
    })

    // A defaulted 'Organic' here would overwrite a waitlist lead's real attribution
    // the moment they created an account — the bug already fixed once in the waitlist route.
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body))
    expect(body.data.values.lead_source).toBeUndefined()
  })
})
