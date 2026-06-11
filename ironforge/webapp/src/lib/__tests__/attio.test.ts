import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  isAttioConfigured,
  buildPersonAssert,
  buildSignupNote,
  syncContactToAttio,
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
