/**
 * Shared client plumbing for the /enroll/* screens — mirrors
 * webapp/src/app/enroll/useEnrollment.ts so the mobile funnel cannot disagree with the
 * web one about where a customer resumes.
 *
 * The SERVER owns funnel position: every screen resumes on mount
 * (POST /api/v1/enrollments) and, if the server says this customer has not yet earned
 * this screen, replaces the route with the canonical one. Errors come back through
 * ApiError.humanMessage, which is always safe to show — provider text never reaches here.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'expo-router'
import { ApiError } from '@/api/client'
import { resumeEnrollment } from './api'
import { routeForNextStep, PAGE_RANK, type EnrollPageStep } from './steps'
import type { EnrollmentSummary, EnrollmentNextStep } from './types'

export function useEnrollment(current: EnrollPageStep) {
  const router = useRouter()
  const [enrollment, setEnrollment] = useState<EnrollmentSummary | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const alive = useRef(true)

  /**
   * Create or RESUME, then guard: redirect only when the server's canonical position
   * is EARLIER than this screen. Returns the enrollment (or null after a
   * redirect/failure) so submit handlers can re-resume after an external round trip
   * (Tradier auth session) and follow next_step forward.
   */
  const resume = useCallback(async (): Promise<{ enrollment: EnrollmentSummary; next_step: EnrollmentNextStep } | null> => {
    try {
      const d = await resumeEnrollment()
      if (!alive.current) return null
      const canonical = routeForNextStep(d.next_step, d.enrollment.selected_plan)
      if (PAGE_RANK[current] > canonical.rank) {
        router.replace(canonical.route as never)
        return null
      }
      setEnrollment(d.enrollment)
      return d
    } catch (e) {
      if (alive.current) setError(e instanceof ApiError ? e.humanMessage : (e as Error).message)
      return null
    }
  }, [current, router])

  useEffect(() => {
    alive.current = true
    resume()
    return () => {
      alive.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { enrollment, busy, setBusy, error, setError, resume, router }
}
