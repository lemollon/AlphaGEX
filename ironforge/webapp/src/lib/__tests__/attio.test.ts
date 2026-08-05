import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  isAttioConfigured,
  buildPersonAssert,
  buildSignupNote,
  syncContactToAttio,
  upsertWaitlistToAttio,
  isPhoneValidationError,
  withoutPhone,
} from '@/lib/attio'

const OLD = { ...process.env }

const CONTACT = {
  firstName: 'Ada',
  lastName: 'Lovelace',
  email: 'ada@example.com',
  phone: '+15551234567',
  state: 'CA',
  referralCode: 'FOUNDER',
}

beforeEach(() => {
  vi.restoreAllMocks()
  process.env.ATTIO_API_KEY = 'test-attio-key'
})
afterEach(() => {
  process.env = { ...OLD }
})

describe('isAttioConfigured', () => {
  it('is true only when ATTIO_API_KEY is set', () => {
    expect(isAttioConfigured()).toBe(true)
    delete process.env.ATTIO_API_KEY
    expect(isAttioConfigured()).toBe(false)
  })
})

describe('buildPersonAssert', () => {
  it('maps signup fields to standard People attributes', () => {
    const body = buildPersonAssert(CONTACT) as any
    const values = body.data.values
    expect(values.name[0]).toEqual({
      first_name: 'Ada',
      last_name: 'Lovelace',
      full_name: 'Ada Lovelace',
    })
    expect(values.email_addresses).toEqual([{ email_address: 'ada@example.com' }])
    expect(values.phone_numbers).toEqual([{ original_phone_number: '+15551234567' }])
  })

  it('omits phone_numbers when phone is blank', () => {
    const body = buildPersonAssert({ ...CONTACT, phone: '' }) as any
    expect(body.data.values.phone_numbers).toBeUndefined()
  })
})

describe('buildSignupNote', () => {
  it('targets the people record and carries state + referral', () => {
    const note = buildSignupNote('rec_123', CONTACT) as any
    expect(note.data.parent_object).toBe('people')
    expect(note.data.parent_record_id).toBe('rec_123')
    expect(note.data.content).toContain('CA')
    expect(note.data.content).toContain('FOUNDER')
  })
})

describe('syncContactToAttio', () => {
  it('skips (no fetch) when ATTIO_API_KEY is unset', async () => {
    delete process.env.ATTIO_API_KEY
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const res = await syncContactToAttio(CONTACT)
    expect(res.skipped).toBe(true)
    expect(res.synced).toBe(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('asserts a Person by email and returns the record id on success', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).includes('/objects/people/records')) {
        return new Response(JSON.stringify({ data: { id: { record_id: 'rec_abc' } } }), { status: 200 })
      }
      return new Response('{}', { status: 200 }) // note attach
    })
    vi.stubGlobal('fetch', fetchMock)

    const res = await syncContactToAttio(CONTACT)
    expect(res.synced).toBe(true)
    expect(res.recordId).toBe('rec_abc')

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/objects/people/records?matching_attribute=email_addresses')
    expect((init as any).method).toBe('PUT')
    expect((init as any).headers.Authorization).toBe('Bearer test-attio-key')
    // best-effort note posted as a second call
    expect(fetchMock.mock.calls.length).toBe(2)
    expect(String(fetchMock.mock.calls[1][0])).toContain('/notes')
  })

  it('returns synced=false with an error on a non-2xx assert', async () => {
    const fetchMock = vi.fn(async () => new Response('bad request', { status: 400 }))
    vi.stubGlobal('fetch', fetchMock)
    const res = await syncContactToAttio(CONTACT)
    expect(res.synced).toBe(false)
    expect(res.error).toContain('Attio 400')
  })

  it('does not fail the sync when the note attach throws', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).includes('/objects/people/records')) {
        return new Response(JSON.stringify({ data: { id: { record_id: 'rec_x' } } }), { status: 200 })
      }
      throw new Error('note service down')
    })
    vi.stubGlobal('fetch', fetchMock)
    const res = await syncContactToAttio(CONTACT)
    expect(res.synced).toBe(true)
    expect(res.recordId).toBe('rec_x')
  })
})

/**
 * 8/3 production incident: a waitlist submission 400'd on `phone_numbers` ("Invalid phone number,
 * possibly due to missing country information") and then dead-lettered out of the CRM outbox, so
 * the lead lived in Postgres and nowhere else. Attio validates against the real numbering plan;
 * normalizePhone only counts digits. Losing the phone must never cost us the person.
 */
const PHONE_400 = JSON.stringify({
  status_code: 400,
  type: 'invalid_request_error',
  code: 'validation_type',
  message: 'An invalid value was passed to attribute with slug "phone_numbers".',
  validation_errors: [{ code: 'invalid', path: ['original_phone_number'], message: 'Invalid phone number' }],
})

const WAITLIST_CONTACT = {
  firstName: 'Ada',
  lastName: 'Lovelace',
  email: 'ada@example.com',
  phone: '+11234567890',
  city: 'Austin',
  state: 'TX',
  tradingCapitalRange: '$10,000 - $24,999',
  consentVersion: 'v1',
  submissionId: 'sub_1',
}

describe('isPhoneValidationError / withoutPhone', () => {
  it('recognises the Attio phone rejection and nothing else', () => {
    expect(isPhoneValidationError(PHONE_400)).toBe(true)
    expect(isPhoneValidationError('Attio 400: unknown attribute "trading_volume"')).toBe(false)
    expect(isPhoneValidationError(undefined)).toBe(false)
  })

  it('drops only phone_numbers', () => {
    const out = withoutPhone({ email_addresses: [1], phone_numbers: [2], name: [3] })
    expect(out).toEqual({ email_addresses: [1], name: [3] })
  })
})

describe('phone fallback — a bad phone must not cost us the record', () => {
  it('retries the waitlist person WITHOUT the phone and still captures the lead', async () => {
    const bodies: any[] = []
    const fetchMock = vi.fn(async (url: string, init: any) => {
      if (String(url).includes('/objects/people/records')) {
        const body = JSON.parse(init.body)
        bodies.push(body)
        if (body.data.values.phone_numbers) return new Response(PHONE_400, { status: 400 })
        return new Response(JSON.stringify({ data: { id: { record_id: 'rec_ok' } } }), { status: 200 })
      }
      return new Response('{}', { status: 200 }) // note / list entry
    })
    vi.stubGlobal('fetch', fetchMock)

    const res = await upsertWaitlistToAttio(WAITLIST_CONTACT)
    expect(res.synced).toBe(true)
    expect(res.recordId).toBe('rec_ok')
    expect(bodies.length).toBe(2)
    expect(bodies[1].data.values.phone_numbers).toBeUndefined()
    // the rest of the record survives the retry
    expect(bodies[1].data.values.email_addresses).toEqual([{ email_address: 'ada@example.com' }])
    expect(bodies[1].data.values.primary_location[0].region).toBe('TX')
    // the rejected number is preserved as a note rather than silently dropped
    const noteCall = fetchMock.mock.calls.find((c) => String(c[0]).includes('/notes'))
    expect(noteCall).toBeDefined()
    expect(JSON.parse((noteCall![1] as any).body).data.content).toContain('+11234567890')
  })

  it('does NOT retry when the 400 is about something else', async () => {
    const fetchMock = vi.fn(async () => new Response('{"message":"unknown attribute"}', { status: 400 }))
    vi.stubGlobal('fetch', fetchMock)
    const res = await upsertWaitlistToAttio(WAITLIST_CONTACT)
    expect(res.synced).toBe(false)
    expect(fetchMock.mock.calls.length).toBe(1)
  })

  it('applies the same fallback to signup contacts', async () => {
    const fetchMock = vi.fn(async (url: string, init: any) => {
      if (String(url).includes('/objects/people/records')) {
        return JSON.parse(init.body).data.values.phone_numbers
          ? new Response(PHONE_400, { status: 400 })
          : new Response(JSON.stringify({ data: { id: { record_id: 'rec_s' } } }), { status: 200 })
      }
      return new Response('{}', { status: 200 })
    })
    vi.stubGlobal('fetch', fetchMock)
    const res = await syncContactToAttio(CONTACT)
    expect(res.synced).toBe(true)
    expect(res.recordId).toBe('rec_s')
  })
})

describe('inline waitlist list entry — upsert, never duplicate', () => {
  const LIST = 'ironforge_waitlist'

  function mock(list: (url: string, init: any) => Response) {
    const calls: Array<{ url: string; method: string; body: any }> = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: any) => {
      calls.push({ url: String(url), method: init.method, body: init.body ? JSON.parse(init.body) : undefined })
      if (String(url).includes('/objects/people/records')) {
        return new Response(JSON.stringify({ data: { id: { record_id: 'rec_p' } } }), { status: 200 })
      }
      return list(String(url), init)
    }))
    return calls
  }

  it('PATCHes the existing entry instead of adding a second one', async () => {
    process.env.ATTIO_WAITLIST_LIST = LIST
    const calls = mock((url) =>
      url.endsWith('/entries/query')
        ? new Response(JSON.stringify({ data: [{ id: { entry_id: 'ent_1' } }] }), { status: 200 })
        : new Response('{}', { status: 200 }))

    const res = await upsertWaitlistToAttio({ ...WAITLIST_CONTACT, phone: '+15551234567' })
    expect(res.synced).toBe(true)

    const query = calls.find((c) => c.url.endsWith('/entries/query'))
    expect(query!.body.filter.path).toEqual([[LIST, 'parent_record'], ['people', 'record_id']])
    expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/entries'))).toBe(false)
    const patch = calls.find((c) => c.method === 'PATCH')
    expect(patch!.url).toContain('/entries/ent_1')
    // 'Pending' is stamped on CREATE only — a resubmit must not erase a sent confirmation.
    expect(patch!.body.data.entry_values.confirmation_email_status).toBeUndefined()
  })

  it('creates the entry when the person has none', async () => {
    process.env.ATTIO_WAITLIST_LIST = LIST
    const calls = mock((url) =>
      url.endsWith('/entries/query')
        ? new Response(JSON.stringify({ data: [] }), { status: 200 })
        : new Response('{}', { status: 200 }))

    await upsertWaitlistToAttio({ ...WAITLIST_CONTACT, phone: '+15551234567' })
    const create = calls.find((c) => c.method === 'POST' && c.url.endsWith('/entries'))
    expect(create!.body.data.entry_values.confirmation_email_status).toBe('Pending')
    expect(create!.body.data.entry_values.submission_id).toBe('sub_1')
  })

  it('keeps the person when the lookup fails, and writes no entry', async () => {
    process.env.ATTIO_WAITLIST_LIST = LIST
    const calls = mock(() => new Response('{"code":"unknown_filter_attribute_slug"}', { status: 400 }))
    const res = await upsertWaitlistToAttio({ ...WAITLIST_CONTACT, phone: '+15551234567' })
    expect(res.synced).toBe(true) // person captured — the list add is best-effort
    expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/entries'))).toBe(false)
    expect(calls.some((c) => c.method === 'PATCH')).toBe(false)
  })
})
