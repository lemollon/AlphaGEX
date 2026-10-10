/**
 * In-memory concurrency cap for long-lived SSE connections, keyed by viewer
 * identity (see api/v1/stream/positions).
 *
 * Render runs `ironforge-customer` as a SINGLE web service (ironforge/CLAUDE.md:
 * "Frontend + API + Scanner | Next.js 14 on Render (single web service)"), so a
 * process-local Map is a real cap on this deployment, not a per-instance
 * approximation that silently under-enforces behind a load balancer. A restart
 * clears it, which only ever makes the cap MORE permissive for a moment — never
 * a way to leak past it.
 */

const counts = new Map<string, number>()

/** Attempts to reserve one stream slot for `key`. Returns false at `max`. */
export function acquireStreamSlot(key: string, max: number): boolean {
  const current = counts.get(key) ?? 0
  if (current >= max) return false
  counts.set(key, current + 1)
  return true
}

/** Releases one previously-acquired slot. Safe to call more than once. */
export function releaseStreamSlot(key: string): void {
  const current = counts.get(key) ?? 0
  if (current <= 1) counts.delete(key)
  else counts.set(key, current - 1)
}

export function currentStreamCount(key: string): number {
  return counts.get(key) ?? 0
}

/** Test-only: wipes all state between test cases. */
export function _resetStreamRegistryForTest(): void {
  counts.clear()
}
