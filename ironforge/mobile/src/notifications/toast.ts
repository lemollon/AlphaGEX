/**
 * The floating bottom snackbar (10.4 design `.toast` / `toast()`) — "Spark paused",
 * "Trade added", quick confirmation of something the customer just tapped.
 *
 * A plain pub/sub bus, not a Context, on purpose: `showToast()` is called from deep
 * inside action handlers (agent pause/resume, Ember trade ack, community report/block)
 * that have no reason to otherwise touch React state, and a Context would mean every
 * one of those screens importing a hook and wiring a provider prop just to call one
 * function. `ToastHost` (components/ToastHost.tsx) is the one subscriber, mounted once
 * in app/_layout.tsx — same shape as notifications/bell.ts's permission state, kept
 * pure and testable here rather than tangled into the render layer.
 *
 * Matches the prototype's own timing: `setTimeout(()=>t.hidden=true,2200)` — a new
 * toast while one is showing replaces it outright rather than queuing, so a flurry of
 * taps never leaves a backlog of stale confirmations to read through.
 */
export const TOAST_DURATION_MS = 2200

export interface ToastEvent {
  id: number
  message: string
}

type Listener = (event: ToastEvent | null) => void

let nextId = 1
let listeners: Listener[] = []

export function showToast(message: string): void {
  const event: ToastEvent = { id: nextId++, message }
  listeners.forEach((l) => l(event))
}

export function clearToast(): void {
  listeners.forEach((l) => l(null))
}

export function subscribeToast(listener: Listener): () => void {
  listeners.push(listener)
  return () => {
    listeners = listeners.filter((l) => l !== listener)
  }
}
