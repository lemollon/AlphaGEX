/**
 * `paused_at` from POST /api/v1/automation/pause is a plain ISO timestamp with no
 * timezone opinion of its own. Every timestamp shown to a customer carries a
 * timezone label (SPEC.md) — the rest of the product's timestamps are Central Time,
 * so this one is too, converted rather than left in whatever zone the device is in.
 */
export function formatPausedAt(iso: string | null | undefined): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const formatted = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Chicago',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(d)
  return `${formatted} CT`
}
