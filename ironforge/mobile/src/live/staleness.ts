/**
 * "Updated x seconds ago" (mobile fidelity #268 / dev-handoff §"Loading / stale
 * data": 'show "Updated x seconds ago" if stale over 30 seconds'). Pure helpers so
 * the 30s threshold and the wording are tested directly, not just eyeballed on a
 * screen — the screen (Forge tab) only supplies `now` and `lastUpdatedAt`.
 */
export const STALE_THRESHOLD_MS = 30_000

export function isStale(lastUpdatedAt: number | null, now: number = Date.now()): boolean {
  if (lastUpdatedAt == null) return false
  return now - lastUpdatedAt > STALE_THRESHOLD_MS
}

/** "Updated 42 seconds ago" / "Updated 3 minutes ago" — never shown below the 30s
 *  threshold (isStale gates whether the caller renders this at all). */
export function staleLabel(lastUpdatedAt: number, now: number = Date.now()): string {
  const secs = Math.max(0, Math.round((now - lastUpdatedAt) / 1000))
  if (secs < 60) return `Updated ${secs} second${secs === 1 ? '' : 's'} ago`
  const mins = Math.round(secs / 60)
  return `Updated ${mins} minute${mins === 1 ? '' : 's'} ago`
}
