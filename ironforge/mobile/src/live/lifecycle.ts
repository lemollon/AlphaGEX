/**
 * Open-position lifecycle line (Forge tab, UAT round two mock #1 — "Open-position
 * lifecycle with the real open time").
 *
 * Four nodes on one track: Opened -> Monitoring -> Target / Stop -> Auto Close.
 * Extracted from the screen so the state derivation and every caption can be
 * TESTED rather than trusted — same pattern as period-stats.ts / capital.ts.
 */

export const LIFECYCLE_LABELS = ['Opened', 'Monitoring', 'Target / Stop', 'Auto Close'] as const

export type LifecycleNodeStatus = 'done' | 'current' | 'future'

export interface LifecycleNode {
  label: (typeof LIFECYCLE_LABELS)[number]
  status: LifecycleNodeStatus
}

/**
 * While a position is open, the API only ever reports two moments — the order
 * being placed and the position being monitored — and both mean the fill is
 * already recorded (there is a real `opened_at` to show). So for an open
 * position, Opened is always done and Monitoring is always the current node;
 * Target/Stop and Auto Close describe FUTURE outcomes the backend does not
 * detect live, and only become real once the position actually closes.
 *
 * `closed` marks every node done — the moment a lifecycle line would read as
 * fully complete (Auto Close gets the real close time) before the card falls
 * back to its existing closed-state rendering.
 */
export function deriveLifecycleNodes(closed: boolean): LifecycleNode[] {
  return LIFECYCLE_LABELS.map((label, i) => ({
    label,
    status: closed ? 'done' : i === 0 ? 'done' : i === 1 ? 'current' : 'future',
  }))
}

/**
 * Fraction (0..1) of the track — between the first and last node's centers —
 * that should render filled. Four evenly spaced nodes sit at 0, 1/3, 2/3 and 1
 * along that span, so the fill ends at the last non-future node's own stop.
 */
export function lifecycleFillFraction(nodes: LifecycleNode[]): number {
  let lastReached = -1
  nodes.forEach((n, i) => {
    if (n.status !== 'future') lastReached = i
  })
  if (lastReached <= 0) return 0
  return lastReached / (nodes.length - 1)
}

/** `null`/`undefined`/invalid means "unknown" — the caller shows "—", never a fabricated time. */
export function formatLocalClock(iso: string | null | undefined): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}

/** Minutes elapsed since `openedAt`, clamped to zero — never negative from a
 *  device clock a few seconds behind the server's open timestamp. */
export function minutesSince(openedAt: string, nowMs: number = Date.now()): number {
  const opened = new Date(openedAt).getTime()
  if (Number.isNaN(opened)) return 0
  return Math.max(0, (nowMs - opened) / 60_000)
}

/** "37 min" under an hour, "1 h 12 min" at or beyond one — the Monitoring caption. */
export function formatElapsedMinutes(minutes: number): string {
  const m = Math.max(0, Math.round(minutes))
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  const rem = m % 60
  return `${h} h ${rem} min`
}

/**
 * The Target/Stop caption. `stopDollars` null means the strategy holds to
 * settlement instead of stopping out — "hold to close", never a fabricated
 * $0 stop. `targetDollars` null with a real stop is the one case honest data
 * cannot fill in, so it reads as "—" rather than guessing a number.
 */
export function formatTargetStopCaption(
  targetDollars: number | null | undefined,
  stopDollars: number | null | undefined,
): string {
  if (targetDollars == null && stopDollars == null) return '—'
  if (stopDollars == null) return 'hold to close'
  const target = targetDollars != null
    ? `$${Math.round(Math.abs(targetDollars)).toLocaleString('en-US')}`
    : '—'
  const stop = `−$${Math.round(Math.abs(stopDollars)).toLocaleString('en-US')}` // real minus, not a hyphen
  return `${target} / ${stop}`
}

/** The Auto Close caption — "by 3:00 PM" in the viewer's local time, or the
 *  honest fallback when no same-day scheduled instant is known (a swung leg). */
export function formatAutoCloseCaption(autoCloseAt: string | null | undefined): string {
  const clock = formatLocalClock(autoCloseAt)
  return clock ? `by ${clock}` : 'at close'
}
