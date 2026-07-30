'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { PAGE_RANK, routeForNextStep, type EnrollPageStep } from './steps'

/**
 * Shared client plumbing for the /enroll/* screens (ported from the retired
 * single-page EnrollClient).
 *
 * The SERVER owns funnel position: every screen resumes on mount
 * (POST /api/v1/enrollments) and, if the server says the customer has not yet earned
 * this page, replaces the URL with the canonical one. Going BACKWARD deliberately is
 * allowed — re-entering an earlier page re-reads server state (accepted documents stay
 * accepted, the chosen plan stays chosen), which is what the doc's "back navigation
 * preserves entered values" means when every step is persisted the moment it happens.
 *
 * Errors come back in the shared envelope, so `message` is always safe to show a
 * customer — provider text never reaches here.
 */

export interface EnrollmentSummary {
  id: string
  selected_plan: string | null
  status: string
}

export function useEnrollment(current: EnrollPageStep) {
  const router = useRouter()
  const [enrollment, setEnrollment] = useState<EnrollmentSummary | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const alive = useRef(true)

  /** Every call funnels through here so the error envelope is handled in ONE place. */
  const call = useCallback(async (url: string, init?: RequestInit) => {
    const res = await fetch(url, init)
    const body = await res.json().catch(() => null)
    if (!res.ok) {
      throw new Error(body?.message || 'Something went wrong. Please try again.')
    }
    return body
  }, [])

  /**
   * Create or RESUME, then guard: redirect only when the server's canonical position
   * is EARLIER than this page — the customer hasn't completed the gates to be here.
   * Returns the enrollment (or null after a redirect/failure) so submit handlers can
   * re-resume after external round-trips (Stripe return) and follow next_step forward.
   */
  const resume = useCallback(async (): Promise<{ enrollment: EnrollmentSummary; next_step: string } | null> => {
    try {
      const d = await call('/api/v1/enrollments', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ source: 'enroll_page' }),
      })
      if (!alive.current) return null
      const summary: EnrollmentSummary = d.enrollment
      const canonical = routeForNextStep(d.next_step, summary.selected_plan)
      if (PAGE_RANK[current] > canonical.rank) {
        router.replace(canonical.route)
        return null
      }
      setEnrollment(summary)
      return { enrollment: summary, next_step: d.next_step }
    } catch (e) {
      if (alive.current) setError(e instanceof Error ? e.message : 'Could not start setup.')
      return null
    }
  }, [call, current, router])

  useEffect(() => {
    alive.current = true
    resume()
    return () => {
      alive.current = false
    }
  }, [resume])

  return { enrollment, busy, setBusy, error, setError, call, resume, router }
}
