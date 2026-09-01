import { PROTECTIVE_REASON_PREFIXES, isProtectiveSkip } from './riskProtection'
import { formatCTClock } from '@/lib/pt-tiers'

/**
 * "Live gate/health activity feed" — turns today's SCAN log rows (the same
 * `{bot}_logs` rows already wired up for BLOCKED_REASON_PREFIXES in state.ts
 * and PROTECTIVE_REASON_PREFIXES in riskProtection.ts) into a short, plain-
 * English list so the Live page feels alive even on a 0-trade day.
 *
 * Compliance rule: the raw internal `reason` string (e.g.
 * "skip:vix_elevated(0.904>0.90)") must NEVER reach a FeedEntry.label — only
 * the curated labels below. No options jargon, no raw gate math, ever.
 *
 * De-dup is the whole point: the scanner writes a SCAN row roughly once a
 * minute, so an unbroken 15-minute VIX-gate hold must collapse into ONE feed
 * entry, not fifteen. buildActivityFeed does that by bucketing consecutive
 * rows that classify to the same bucketKey into one segment.
 */

export type FeedKind = 'gate' | 'lifecycle' | 'neutral'

/** Exact label per protective-gate reason prefix. Prefixes are reused
 *  verbatim from riskProtection.ts's PROTECTIVE_REASON_PREFIXES — never
 *  duplicate that list, only add the customer-facing copy here. */
export const PROTECTIVE_GATE_LABELS: Record<string, string> = {
  'skip:vix_elevated': 'VIX volatility gate held',
  'skip:vix_bad_window': 'Waiting for enough VIX history to confirm conditions',
  'skip:vix_too_high': 'VIX too high, held for safety',
  'skip:event_blackout': 'Paused for a scheduled market event',
  'skip:cooldown_after_first_loss': 'Cooling down after a recent loss',
  'skip:standdown': 'Cooling down after a recent loss',
  'skip:standdown_after_loss': 'Cooling down after a recent loss',
  'skip:credit_too_low': 'Premium too thin to be worth the risk',
  'skip:credit_pct_too_low': 'Premium too thin to be worth the risk',
  'skip:neg_gamma_env': 'Market regime not favorable right now',
}

export interface FeedEntry {
  label: string
  kind: FeedKind
  timeLabel: string
  isOngoing: boolean
}

/**
 * Classify one already-parsed scan row. Exhaustive over every `action`
 * scanner.ts's scanBot() can log for a SCAN row, per the reverse-engineered
 * state machine — anything unrecognized (including the fallback 'scan'
 * value) falls through to the same calm generic label, never a guessed one.
 *
 * `bucketKey` is what buildActivityFeed collapses consecutive rows on: for
 * `no_trade` it is the matched protective-gate prefix (or 'other' for a
 * non-protective/infra reason) so two DIFFERENT gates never collapse into
 * one segment, while the SAME gate repeated minute after minute does.
 */
export function classifyScanRow(row: { action: string; reason: string | null }): {
  bucketKey: string
  label: string
  kind: FeedKind
} {
  const { action, reason } = row

  switch (action) {
    case 'traded':
      return { bucketKey: 'traded', label: 'Opened a new trade', kind: 'lifecycle' }

    case 'outside_window':
      return { bucketKey: 'outside_window', label: 'Outside market hours', kind: 'neutral' }

    case 'outside_entry_window':
      return {
        bucketKey: 'outside_entry_window',
        label: "Outside today's entry window",
        kind: 'neutral',
      }

    case 'no_trade': {
      if (isProtectiveSkip(reason)) {
        const prefix = PROTECTIVE_REASON_PREFIXES.find((p) => (reason as string).startsWith(p))
        const label = (prefix && PROTECTIVE_GATE_LABELS[prefix]) || 'Checking market conditions'
        return { bucketKey: `no_trade:${prefix ?? 'other'}`, label, kind: 'gate' }
      }
      // already_traded_today, max_trades_reached, low_bp, no_paper_balance,
      // any production_* string, insufficient_bp, bad_collateral, etc. — an
      // operational/infra non-event. Never surface the raw reason.
      return { bucketKey: 'no_trade:other', label: 'Checking market conditions', kind: 'neutral' }
    }

    case 'skip':
      // reason is tradier_not_configured or no_spy_quote — same calm label
      // either way, never the raw reason string.
      return { bucketKey: 'skip', label: 'Checking market data', kind: 'neutral' }

    case 'error':
      return { bucketKey: 'error', label: 'Checking system health', kind: 'neutral' }

    case 'scan':
    default:
      // 'scan' is the fallback/default value scanner.ts assigns before a scan
      // decides anything — should rarely if ever be the final logged value.
      // Any other unrecognized action (defensive — see the module's report
      // to the requester about 'monitoring'/'closed', which are NOT in the
      // reverse-engineered table this function implements) falls through
      // here too, rather than guessing a new label.
      return { bucketKey: 'scan', label: 'Scanning the market', kind: 'neutral' }
  }
}

/** Wall-clock minutes-since-midnight in America/Chicago for an arbitrary
 *  Date — NOT the getCTNow "now only" trick in pt-tiers.ts, which only works
 *  for the current instant. This works for any historical log_time. */
function ctMinutesOfDay(d: Date): number {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Chicago',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(d)
  const hour = Number(parts.find((p) => p.type === 'hour')?.value ?? '0')
  const minute = Number(parts.find((p) => p.type === 'minute')?.value ?? '0')
  return hour * 60 + minute
}

function formatSegmentTime(start: Date, end: Date): string {
  const startMin = ctMinutesOfDay(start)
  const endMin = ctMinutesOfDay(end)
  const startLabel = formatCTClock(startMin)
  if (startMin === endMin) return startLabel
  return `${startLabel}–${formatCTClock(endMin)} CT`
}

interface Segment {
  bucketKey: string
  label: string
  kind: FeedKind
  start: Date
  end: Date
}

/**
 * Build the customer-facing feed from already-parsed scan rows (JSON parsing
 * of the raw `details` column happens in the caller — summary.ts — one
 * malformed row there must not break the others; this function never
 * throws on its own account either).
 *
 * Returns newest-first, capped to `opts.max` (default 8) AFTER reversing so
 * the cap keeps the most RECENT entries.
 */
export function buildActivityFeed(
  rows: Array<{ logTime: string | Date; action: string; reason: string | null }>,
  opts?: { max?: number },
): FeedEntry[] {
  if (!rows || rows.length === 0) return []
  const max = opts?.max ?? 8

  const timed = rows
    .map((r) => ({ ...r, time: r.logTime instanceof Date ? r.logTime : new Date(r.logTime) }))
    .filter((r) => !isNaN(r.time.getTime()))
    .sort((a, b) => a.time.getTime() - b.time.getTime())

  if (timed.length === 0) return []

  const segments: Segment[] = []
  for (const row of timed) {
    let classified: { bucketKey: string; label: string; kind: FeedKind }
    try {
      classified = classifyScanRow(row)
    } catch {
      // Defensive only — classifyScanRow does not throw on typed input, but
      // a single bad row must never take the rest of the feed down with it.
      classified = { bucketKey: 'scan', label: 'Scanning the market', kind: 'neutral' }
    }
    const last = segments[segments.length - 1]
    if (last && last.bucketKey === classified.bucketKey) {
      last.end = row.time
    } else {
      segments.push({ ...classified, start: row.time, end: row.time })
    }
  }

  const entries: FeedEntry[] = segments.map((seg, i) => ({
    label: seg.label,
    kind: seg.kind,
    timeLabel: formatSegmentTime(seg.start, seg.end),
    isOngoing: i === segments.length - 1,
  }))

  return entries.reverse().slice(0, max)
}
