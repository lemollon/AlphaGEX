/**
 * Offline handling (mobile fidelity #294 / dev-handoff §"Offline and flaky network":
 * "cached data shows with a stale notice; actions queue or fail with clear copy").
 *
 * @react-native-community/netinfo is NOT an installed dependency (no new native
 * deps for this pass — see package.json), so this infers connectivity from the
 * app's own request traffic instead of a dedicated OS reachability check: every
 * call through api/client.ts's `api()` reports success or failure here, and a run
 * of consecutive failures with no success in between is read as "offline".
 *
 * The "cached data" half of the design requirement needs no code here — SWR
 * already keeps the last good `data` for a key on a failed revalidation (that is
 * the whole point of stale-while-revalidate); this module only adds the banner
 * that tells the customer WHY the numbers on screen stopped moving.
 *
 * A single failure is not "offline" — a one-off 5xx or a dropped packet happens on
 * a perfectly fine connection. CONSECUTIVE_FAILURE_THRESHOLD requires a short run
 * of them before declaring offline, and ANY success immediately clears it.
 */
const CONSECUTIVE_FAILURE_THRESHOLD = 2

let consecutiveFailures = 0
let offline = false

type Listener = (offline: boolean) => void
let listeners: Listener[] = []

function setOffline(next: boolean) {
  if (next === offline) return
  offline = next
  listeners.forEach((l) => l(offline))
}

export function reportNetworkSuccess(): void {
  consecutiveFailures = 0
  setOffline(false)
}

/** Call ONLY for a network-layer failure (fetch itself rejecting) — never for an
 *  ordinary HTTP error status, which proves the connection is actually working. */
export function reportNetworkFailure(): void {
  consecutiveFailures += 1
  if (consecutiveFailures >= CONSECUTIVE_FAILURE_THRESHOLD) setOffline(true)
}

export function isOffline(): boolean {
  return offline
}

export function subscribeConnectivity(listener: Listener): () => void {
  listeners.push(listener)
  return () => {
    listeners = listeners.filter((l) => l !== listener)
  }
}

/** Test-only: resets module state between vitest runs. */
export function __resetConnectivityForTest(): void {
  consecutiveFailures = 0
  offline = false
  listeners = []
}
