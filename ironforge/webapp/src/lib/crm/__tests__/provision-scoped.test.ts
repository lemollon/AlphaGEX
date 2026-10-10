import { describe, it, expect, vi, beforeEach } from 'vitest'

const client = vi.hoisted(() => ({
  isAttioConfigured: vi.fn(() => true),
  listAttributes: vi.fn(),
  createAttribute: vi.fn(),
  listSelectOptions: vi.fn(),
  listStatuses: vi.fn(),
}))

vi.mock('@/lib/crm/client', () => ({
  ...client,
  assertRecord: vi.fn(),
  createList: vi.fn(),
  createListAttribute: vi.fn(),
  createObject: vi.fn(),
  createSelectOption: vi.fn(),
  createStatus: vi.fn(),
  listListAttributes: vi.fn(),
  listLists: vi.fn(),
  listObjects: vi.fn(),
}))

import { provisionObjectAttributes } from '../provision'

const SLUGS = ['waitlist_email_stage', 'waitlist_last_email_at']

beforeEach(() => {
  vi.clearAllMocks()
  client.isAttioConfigured.mockReturnValue(true)
})

describe('provisionObjectAttributes (scoped, boot-time)', () => {
  it('creates only the two missing waitlist attributes on people', async () => {
    client.listAttributes.mockResolvedValue({ ok: true, data: { data: [{ api_slug: 'lead_priority' }] } })
    client.createAttribute.mockResolvedValue({ ok: true })
    const r = await provisionObjectAttributes('people', SLUGS)
    expect(r).toMatchObject({ configured: true, created: 2, existing: 0, errors: 0 })
    expect(client.createAttribute).toHaveBeenCalledTimes(2)
    expect(client.createAttribute.mock.calls.map((c) => c[1].apiSlug)).toEqual(SLUGS)
    expect(client.createAttribute.mock.calls.every((c) => c[0] === 'people')).toBe(true)
  })

  it('is idempotent: when both exist nothing is created', async () => {
    client.listAttributes.mockResolvedValue({ ok: true, data: { data: SLUGS.map((s) => ({ api_slug: s })) } })
    const r = await provisionObjectAttributes('people', SLUGS)
    expect(r).toMatchObject({ created: 0, existing: 2, errors: 0 })
    expect(client.createAttribute).not.toHaveBeenCalled()
  })

  it('reports an API failure as an error instead of throwing', async () => {
    client.listAttributes.mockResolvedValue({ ok: false, error: '403 object_configuration scope missing' })
    const r = await provisionObjectAttributes('people', SLUGS)
    expect(r.errors).toBe(1)
    expect(r.items[0].error).toContain('403')
    expect(client.createAttribute).not.toHaveBeenCalled()
  })

  it('unconfigured Attio → configured:false and no calls', async () => {
    client.isAttioConfigured.mockReturnValue(false)
    const r = await provisionObjectAttributes('people', SLUGS)
    expect(r.configured).toBe(false)
    expect(client.listAttributes).not.toHaveBeenCalled()
  })

  it('an unknown slug is an error, never a guess', async () => {
    client.listAttributes.mockResolvedValue({ ok: true, data: { data: [] } })
    client.createAttribute.mockResolvedValue({ ok: true })
    const r = await provisionObjectAttributes('people', ['waitlist_email_stage', 'made_up'])
    expect(r.errors).toBe(1)
    expect(r.created).toBe(1)
  })
})
