import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

/**
 * Regression test for the TestFlight build 23 bug: "choose a plan, continue, go
 * back, choose a DIFFERENT plan does nothing." The fix lived entirely in the
 * mobile/web client (a `busy` flag that never reset after a successful choice —
 * see app/enroll/plan.tsx and enroll/plan/PlanClient.tsx), but this pins the
 * server contract those clients depend on: PUT .../plan must accept a new
 * selection even after the funnel has advanced past 'draft' (legal_pending,
 * billing_pending), including an Ember <-> Spark switch, which also has to add
 * or remove the billing step correctly. A completed/abandoned enrollment is
 * deliberately NOT covered — changing plan after activation stays out of scope.
 */

const ENROLLMENT_ID = '11111111-1111-1111-1111-111111111111'
const USER_ID = '22222222-2222-2222-2222-222222222222'

const enrollment = {
  id: ENROLLMENT_ID,
  user_id: USER_ID,
  selected_plan: null as string | null,
  status: 'draft' as string,
  current_step: 'plan' as string | null,
}

vi.mock('@/lib/auth/customer-identity', () => ({
  getCustomerIdentity: vi.fn(async () => ({ customerId: USER_ID })),
}))

vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: () => true,
  customerQuery: vi.fn(async (sql: string) => {
    if (sql.includes('FROM enrollments')) return [{ ...enrollment }]
    if (sql.includes('FROM legal_acceptances')) return []
    return []
  }),
  customerExecute: vi.fn(async (sql: string, params: unknown[]) => {
    // Mirrors setEnrollmentPlan's real WHERE clause: a complete/abandoned
    // enrollment can never be driven backward by a plan re-choose.
    if (sql.includes('UPDATE enrollments') && sql.includes('SET selected_plan')) {
      if (enrollment.status === 'complete' || enrollment.status === 'abandoned') return 0
      enrollment.selected_plan = params[2] as string
      enrollment.status = 'legal_pending'
      enrollment.current_step = 'legal'
      return 1
    }
    if (sql.includes('INSERT INTO legal_documents')) return 0
    return 0
  }),
}))

const { PUT } = await import('../route')

function putPlan(plan: string) {
  return PUT(
    new NextRequest(`https://app.test/api/v1/enrollments/${ENROLLMENT_ID}/plan`, {
      method: 'PUT',
      body: JSON.stringify({ plan }),
    }),
    { params: { id: ENROLLMENT_ID } },
  )
}

beforeEach(() => {
  enrollment.selected_plan = null
  enrollment.status = 'draft'
  enrollment.current_step = 'plan'
})

describe('PUT /api/v1/enrollments/[id]/plan — choose A, back, choose B', () => {
  it('accepts a second plan choice after the funnel already advanced past draft', async () => {
    const first = await putPlan('spark')
    expect(first.status).toBe(200)
    expect((await first.json()).selected_plan).toBe('spark')
    expect(enrollment.status).toBe('legal_pending')

    // The customer continued forward (billing_pending) before hitting back.
    enrollment.status = 'billing_pending'
    enrollment.current_step = 'billing'

    const second = await putPlan('flame')
    expect(second.status).toBe(200)
    const body2 = await second.json()
    expect(body2).toMatchObject({ ok: true, selected_plan: 'flame', next_step: 'legal' })
    expect(enrollment.selected_plan).toBe('flame')
    expect(enrollment.status).toBe('legal_pending')
  })

  it('switches Ember -> Spark and Spark -> Ember, correctly re-adding the billing step', async () => {
    const toEmber = await putPlan('ember')
    expect(toEmber.status).toBe(200)
    expect(enrollment.selected_plan).toBe('ember')
    expect(enrollment.status).toBe('legal_pending')

    // Ember's own legal acceptance skips billing entirely (setup_required direct).
    enrollment.status = 'setup_required'
    enrollment.current_step = 'setup'

    const toSpark = await putPlan('spark')
    expect(toSpark.status).toBe(200)
    expect((await toSpark.json()).selected_plan).toBe('spark')
    // Rewound to legal_pending — Spark's billing step is required again, which is
    // exactly the "add the billing step back" half of the bug report.
    expect(enrollment.status).toBe('legal_pending')

    enrollment.status = 'billing_pending'
    enrollment.current_step = 'billing'

    const backToEmber = await putPlan('ember')
    expect(backToEmber.status).toBe(200)
    expect((await backToEmber.json()).selected_plan).toBe('ember')
    expect(enrollment.status).toBe('legal_pending')
  })

  it('rejects an unknown plan without touching the stored selection', async () => {
    const res = await putPlan('not_a_real_plan')
    expect(res.status).toBeGreaterThanOrEqual(400)
    expect(res.status).toBeLessThan(500)
    expect(enrollment.selected_plan).toBeNull()
  })
})
