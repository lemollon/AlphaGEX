/**
 * enroll_step_view / enroll_step_complete pairing (en-events).
 *
 * `ms_on_step` needs a start time to subtract from. EnrollShell fires the
 * view the moment a step mounts and stamps sessionStorage; whichever client
 * component owns that step's "Continue" action calls trackEnrollStepComplete
 * when the step actually finishes, which reads the stamp back out. Session
 * storage (not a React ref) because the view and the complete call live in
 * two different component trees that don't share state otherwise.
 */
import { track } from './track'

const KEY_PREFIX = 'if_step_view_'

export function trackEnrollStepView(step: string): void {
  if (typeof window !== 'undefined') {
    try {
      window.sessionStorage.setItem(`${KEY_PREFIX}${step}`, String(Date.now()))
    } catch {
      // Storage unavailable — the view still fires; ms_on_step just won't resolve.
    }
  }
  track('enroll_step_view', { step })
}

export function trackEnrollStepComplete(step: string): void {
  let msOnStep: number | null = null
  if (typeof window !== 'undefined') {
    try {
      const key = `${KEY_PREFIX}${step}`
      const started = window.sessionStorage.getItem(key)
      if (started) msOnStep = Date.now() - Number(started)
      window.sessionStorage.removeItem(key)
    } catch {
      // Fall through with no duration rather than block the completion event.
    }
  }
  track('enroll_step_complete', msOnStep != null ? { step, ms_on_step: msOnStep } : { step })
}
