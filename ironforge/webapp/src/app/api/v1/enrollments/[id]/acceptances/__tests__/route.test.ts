import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

/**
 * E-signature must case-insensitively match the account's name on file (design spec
 * §5 step 2; gap audit "Web enrollment — E-signature match" PARTIAL/S, previously
 * length-only). Covers the three distinct server messages: too short, single word,
 * and a real mismatch — plus the happy path (exact match, case/whitespace-insensitive).
 */

const ENROLLMENT_ID = '55555555-5555-5555-5555-555555555555'
const USER_ID = '66666666-6666-6666-6666-666666666666'

vi.mock('@/lib/enrollment-mode', () => ({
  isEnrollmentClosed: () => false,
  enrollmentClosedResponse: () => new Response('closed', { status: 503 }),
}))

vi.mock('@/lib/auth/customer-identity', () => ({
  getCustomerIdentity: vi.fn(async () => ({ customerId: USER_ID })),
}))

vi.mock('@/lib/enrollment/service', () => ({
  getEnrollmentForUser: vi.fn(async (id: string, userId: string) =>
    id === ENROLLMENT_ID && userId === USER_ID ? { id: ENROLLMENT_ID, user_id: USER_ID, selected_plan: 'spark' } : null,
  ),
  recordAcceptances: vi.fn(async () => ({ ok: true })),
  ensureLegalDocumentsSeeded: vi.fn(async () => undefined),
}))

vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: () => true,
  customerQuery: vi.fn(async (sql: string) => {
    if (sql.includes('FROM users')) return [{ first_name: 'Jane', last_name: 'Doe' }]
    return []
  }),
}))

const { POST } = await import('../route')

function postAcceptances(body: Record<string, unknown>) {
  return POST(
    new NextRequest(`https://app.test/api/v1/enrollments/${ENROLLMENT_ID}/acceptances`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
    { params: { id: ENROLLMENT_ID } },
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('POST /api/v1/enrollments/[id]/acceptances — signature must match the account name', () => {
  it('rejects a signature under 2 characters', async () => {
    const res = await postAcceptances({ accepted: ['TERMS'], signature_name: 'J' })
    expect(res.status).toBeGreaterThanOrEqual(400)
    const body = await res.json()
    expect(body.message).toMatch(/full legal name/i)
  })

  it('rejects a single-word signature ("Type your first and last name.")', async () => {
    const res = await postAcceptances({ accepted: ['TERMS'], signature_name: 'Jane' })
    expect(res.status).toBeGreaterThanOrEqual(400)
    const body = await res.json()
    expect(body.message).toBe('Type your first and last name.')
  })

  it('rejects a two-word signature that does not match the account name', async () => {
    const res = await postAcceptances({ accepted: ['TERMS'], signature_name: 'John Smith' })
    expect(res.status).toBeGreaterThanOrEqual(400)
    const body = await res.json()
    expect(body.message).toBe('Type your name exactly as Jane Doe.')
  })

  it('accepts an exact match, case- and whitespace-insensitive', async () => {
    const res = await postAcceptances({ accepted: ['TERMS'], signature_name: '  jane   doe  ' })
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.ok).toBe(true)
  })
})
