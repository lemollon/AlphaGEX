import { describe, it, expect, vi, beforeEach } from 'vitest'

/**
 * The 10/5 reorder's dual-order contract (lib/enrollment/service.ts).
 *
 * The WEB funnel now runs account -> legal -> plan (Choose agent) -> broker -> billing
 * -> review. The APP (mobile) funnel keeps plan -> legal -> billing -> broker -> agent
 * -> review, over the SAME five `enrollments.status` values and the SAME
 * recordAcceptances()/setEnrollmentPlan() writes — only resolveNextStepWeb() (web) vs
 * nextStepFor() (app, UNTOUCHED by this reorder) read them differently.
 *
 * Covers:
 *  1. recordAcceptances() with plan=null (the web's normal pre-plan Agreements submit)
 *     — requires the full automate-family document set, leaves status untouched, and
 *     reports the customer should go choose a plan next.
 *  2. recordAcceptances() with a REAL plan (exactly how the app always calls it, since
 *     the app chooses its plan before touching legal) — byte-for-byte the SAME
 *     transition as before this reorder. This is the "app keeps its order" pin.
 *  3. resolveNextStepWeb() for every status, including the MIGRATION case: a
 *     pre-reorder in-flight row sitting at legal_pending that never actually did
 *     legal (old order: plan chosen -> legal_pending -> do legal) must still be sent
 *     to do legal, not fast-forwarded past it.
 */

let acceptedVersions: Array<{ code: string; version: string }> = []
const executed: Array<{ sql: string; params: unknown[] }> = []

vi.mock('@/lib/customers-db', () => ({
  customerQuery: vi.fn(async (sql: string) => {
    if (sql.includes('FROM legal_acceptances')) return acceptedVersions
    if (sql.includes('INSERT INTO legal_acceptances')) return 1
    return []
  }),
  customerExecute: vi.fn(async (sql: string, params: unknown[]) => {
    executed.push({ sql, params })
    return 1
  }),
}))

const { recordAcceptances, resolveNextStepWeb } = await import('../service')
const { requiredDocumentsFor } = await import('../legal')

const USER_ID = '77777777-7777-7777-7777-777777777777'
const ENROLLMENT_ID = '88888888-8888-8888-8888-888888888888'

const ALL_SEVEN = requiredDocumentsFor('automate').map((d) => d.code)

beforeEach(() => {
  acceptedVersions = []
  executed.length = 0
  vi.clearAllMocks()
})

describe('recordAcceptances — plan unknown yet (web, normal order)', () => {
  it('requires the full automate-family set, not core-only', async () => {
    const res = await recordAcceptances({
      userId: USER_ID,
      enrollmentId: ENROLLMENT_ID,
      plan: null,
      submittedCodes: ['TERMS', 'PRIVACY', 'REFUND'], // core only — not enough
      ip: null,
      userAgent: null,
    })
    expect(res.ok).toBe(false)
    if (!res.ok) expect(res.missing.sort()).toEqual(['ADVICE_DISCLAIMER', 'ELECTRONIC_CONSENT', 'RISK', 'TRADING_AUTH'].sort())
  })

  it('accepting the full set succeeds, touches NO status, and points at plan next', async () => {
    const res = await recordAcceptances({
      userId: USER_ID,
      enrollmentId: ENROLLMENT_ID,
      plan: null,
      submittedCodes: ALL_SEVEN,
      ip: null,
      userAgent: null,
    })
    expect(res).toEqual({ ok: true, nextStep: 'plan' })
    expect(executed.some((e) => e.sql.includes('UPDATE enrollments'))).toBe(false)
  })
})

describe('recordAcceptances — plan already known (app order, UNCHANGED)', () => {
  it('spark -> billing_pending / billing, exactly as before this reorder', async () => {
    const res = await recordAcceptances({
      userId: USER_ID,
      enrollmentId: ENROLLMENT_ID,
      plan: 'spark',
      submittedCodes: ALL_SEVEN,
      ip: null,
      userAgent: null,
    })
    expect(res).toEqual({ ok: true, nextStep: 'billing' })
    const upd = executed.find((e) => e.sql.includes('UPDATE enrollments'))
    expect(upd?.params).toEqual([ENROLLMENT_ID, USER_ID, 'billing_pending', 'billing'])
  })

  it('ember -> setup_required / setup direct, skipping billing', async () => {
    const res = await recordAcceptances({
      userId: USER_ID,
      enrollmentId: ENROLLMENT_ID,
      plan: 'ember',
      submittedCodes: ALL_SEVEN,
      ip: null,
      userAgent: null,
    })
    expect(res).toEqual({ ok: true, nextStep: 'setup' })
    const upd = executed.find((e) => e.sql.includes('UPDATE enrollments'))
    expect(upd?.params).toEqual([ENROLLMENT_ID, USER_ID, 'setup_required', 'setup'])
  })
})

describe('resolveNextStepWeb', () => {
  it('complete -> done', async () => {
    expect(await resolveNextStepWeb({ status: 'complete', selected_plan: 'spark' }, USER_ID)).toBe('done')
  })

  it('draft, nothing accepted -> legal', async () => {
    acceptedVersions = []
    expect(await resolveNextStepWeb({ status: 'draft', selected_plan: null }, USER_ID)).toBe('legal')
  })

  it('draft, full set already accepted -> plan (choose agent)', async () => {
    acceptedVersions = requiredDocumentsFor('automate').map((d) => ({ code: d.code, version: d.version }))
    expect(await resolveNextStepWeb({ status: 'draft', selected_plan: null }, USER_ID)).toBe('plan')
  })

  it('legal_pending, plan chosen, legal already done (normal web order) -> broker', async () => {
    acceptedVersions = requiredDocumentsFor('automate').map((d) => ({ code: d.code, version: d.version }))
    expect(await resolveNextStepWeb({ status: 'legal_pending', selected_plan: 'spark' }, USER_ID)).toBe('broker')
  })

  it('MIGRATION: legal_pending, plan chosen under the OLD order, legal NOT done -> legal (not broker)', async () => {
    acceptedVersions = []
    expect(await resolveNextStepWeb({ status: 'legal_pending', selected_plan: 'spark' }, USER_ID)).toBe('legal')
  })

  it('billing_pending -> billing (broker is already done by the time status reaches here)', async () => {
    expect(await resolveNextStepWeb({ status: 'billing_pending', selected_plan: 'flame' }, USER_ID)).toBe('billing')
  })

  it('setup_required -> setup (review)', async () => {
    expect(await resolveNextStepWeb({ status: 'setup_required', selected_plan: 'ember' }, USER_ID)).toBe('setup')
  })

  it('Community past draft always resolves to billing (the free-join screen), regardless of status', async () => {
    expect(await resolveNextStepWeb({ status: 'legal_pending', selected_plan: 'community' }, USER_ID)).toBe('billing')
    expect(await resolveNextStepWeb({ status: 'billing_pending', selected_plan: 'community' }, USER_ID)).toBe('billing')
  })
})
