/**
 * Open-position lifecycle line (Forge tab, UAT round two mock #1 — "Open-position
 * lifecycle with the real open time").
 *
 * Four nodes on one track: Opened -> Monitoring -> Target / Stop -> Auto Close.
 * Extracted from the screen so the state derivation and every caption can be
 * TESTED rather than trusted — same pattern as period-stats.ts / capital.ts.
 */

export const LIFECYCLE_LABELS = ['Opened', 'Monitoring', 'Target / Stop', 'Auto Close'] as const

/**
 * FLAME and SPARK are EBB settle-at-expiry bots — see isSettleAtExpiryBot below.
 * They never stop out and never auto-close early, so "Target / Stop" and "Auto
 * Close" describe outcomes that cannot happen for them: a short holds to the
 * close and a guard only steps in during the final three minutes before it.
 * Showing the generic labels (and, downstream, "by 2:45 PM") on these bots is
 * what the customer actually traded against, not what the lifecycle line said.
 */
export const SETTLE_AT_EXPIRY_LIFECYCLE_LABELS = [
  'Opened',
  'Monitoring',
  'Hold to Close',
  'Settles at Close',
] as const

export type LifecycleNodeStatus = 'done' | 'current' | 'future'

export interface LifecycleNode {
  label: string
  status: LifecycleNodeStatus
}

/**
 * FLAME/SPARK (EBB) hold every position to expiry/settlement instead of being
 * stopped out or force-closed early — mirrors webapp lib/db.ts isSettleAtExpiryBot.
 * Duplicated rather than imported: the mobile app is a separate package with its
 * own bundler root and does not import webapp source (same pattern as
 * theme/tokens.ts's agentAccent).
 */
export function isSettleAtExpiryBot(bot: string): boolean {
  return bot === 'flame' || bot === 'spark'
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
 * back to its existing closed-state rendering. `bot` selects the settle-at-
 * expiry label set for FLAME/SPARK; omitted or any other bot keeps the
 * original four labels.
 */
export function deriveLifecycleNodes(closed: boolean, bot?: string | null): LifecycleNode[] {
  const labels = bot && isSettleAtExpiryBot(bot) ? SETTLE_AT_EXPIRY_LIFECYCLE_LABELS : LIFECYCLE_LABELS
  return labels.map((label, i) => ({
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

/** Minutes remaining until `autoCloseAt`, clamped to zero — `null` when there is
 *  no real scheduled close to count down to (a swung leg, or a bot that never
 *  reports one). Feeds the Live-now card's "{left} left" caption (10.4 design
 *  `.life-row`'s right-hand span) alongside `minutesSince`'s "Open {elapsed}". */
export function minutesUntil(autoCloseAt: string | null | undefined, nowMs: number = Date.now()): number | null {
  if (!autoCloseAt) return null
  const close = new Date(autoCloseAt).getTime()
  if (Number.isNaN(close)) return null
  return Math.max(0, (close - nowMs) / 60_000)
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

/**
 * Elapsed-time progress fraction (0..1) for the Live-now card's bar (10.4 design
 * `.bar i` — "the open trade's elapsed time, as a fraction of its own expected
 * session"). `null` when there is no real auto-close instant to measure against
 * (a swung leg, or a bot that never reports one) — the caller renders no bar
 * rather than a fabricated one, same honesty rule as every other "—" in this file.
 * Clamped to [0, 1]: a device clock a few seconds ahead of the close instant, or
 * a position still open past its expected close, must not overflow the bar.
 */
export function liveProgressFraction(
  openedAt: string | null,
  autoCloseAt: string | null | undefined,
  nowMs: number = Date.now(),
): number | null {
  if (!openedAt || !autoCloseAt) return null
  const opened = new Date(openedAt).getTime()
  const close = new Date(autoCloseAt).getTime()
  if (Number.isNaN(opened) || Number.isNaN(close) || close <= opened) return null
  return Math.max(0, Math.min(1, (nowMs - opened) / (close - opened)))
}

/**
 * The Live-now card's 3-stage footer (10.4 design `.stages`: Opened / Monitoring /
 * Auto close) — a coarser read than the 4-node LifecycleLine elsewhere on the same
 * tile, mirroring the prototype's own `liveCard()` stage math exactly: the first 20
 * minutes read as "just opened", the last 15 minutes before auto-close read as
 * "closing soon", everything between is "being monitored". Returns 0/1/2 — the
 * caller's own stage label array indexes into this directly.
 */
export function liveCardStage(
  openedAt: string | null,
  autoCloseAt: string | null | undefined,
  nowMs: number = Date.now(),
): 0 | 1 | 2 {
  const elapsed = openedAt ? minutesSince(openedAt, nowMs) : 0
  const closeAt = autoCloseAt ? new Date(autoCloseAt).getTime() : null
  const leftMin = closeAt != null && !Number.isNaN(closeAt) ? Math.max(0, (closeAt - nowMs) / 60_000) : null
  if (elapsed < 20) return 0
  if (leftMin != null && leftMin < 15) return 2
  return 1
}

/**
 * The settle-at-close caption for FLAME/SPARK — "Settles at close (3:00 PM CT)".
 * Always CT, never the viewer's local time: "at close" means the CT session
 * close (noon CT on an early-close half-day), and showing it converted to the
 * viewer's own zone would read as a different, invented cutoff. Falls back to
 * the bare label when no same-day instant is known (a swung leg), same honesty
 * rule as formatAutoCloseCaption's "at close".
 */
export function formatSettleAtCloseCaption(autoCloseAt: string | null | undefined): string {
  if (!autoCloseAt) return 'Settles at close'
  const d = new Date(autoCloseAt)
  if (Number.isNaN(d.getTime())) return 'Settles at close'
  const ct = d.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    timeZone: 'America/Chicago',
  })
  return `Settles at close (${ct} CT)`
}
