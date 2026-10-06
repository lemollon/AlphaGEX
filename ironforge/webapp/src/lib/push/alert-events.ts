/**
 * Copy + payload builders for the two alert-category pushes added by db-controls
 * #202 ("big moves on an open trade" and "daily summary"). Both Settings rows and
 * DB columns already existed (SettingsClient.tsx ALERT_ROWS, notification_prefs.
 * big_move/daily_summary) — this file is the missing sender half, same split as
 * trade-events.ts/dispatch.ts for trade_opened/trade_closed.
 *
 * Scoped to LiveBot ('spark' | 'flame') only, same reasoning as trade-events.ts:
 * those are the only two bots the mobile deep-link allowlist and the customer
 * Live page know how to open.
 */
import { LIVE_BOT_LABEL, type LiveBot } from '@/lib/live/bots'
import type { NotificationEvent } from '@/lib/push/types'

/**
 * Threshold for "a large swing on an open trade" (SettingsClient.tsx's own blurb
 * for `big_move`). Neither the 10.4 design docs nor the handoff give a number —
 * ironforge-dashboard.html's copy is just "Big moves on an open trade" with no
 * percentage. Assumption, stated here rather than silently guessed: 50% of the
 * position's own range, using the SAME basis the Live page already shows as
 * `unrealized_pnl_pct` (lib/live/summary.ts's `profitBasisPct` — percent of max
 * profit while winning, percent of max loss while losing). 50% is the
 * conventional "worth a look" line for a defined-risk credit spread (half its
 * own potential gain or half its own defined max loss). Revisit with Leron if a
 * different number is wanted; nothing trading-side reads this constant.
 */
export const BIG_MOVE_PNL_PCT_THRESHOLD = 50

/** Which side of the threshold `pnlPct` has crossed, or null if it hasn't. Doubles
 *  as the event's dedupe `state` so a position re-notifies only when it swings
 *  from one side to the other, never on every cycle it stays past the line. */
export function bigMoveTier(pnlPct: number): 'up' | 'down' | null {
  if (pnlPct >= BIG_MOVE_PNL_PCT_THRESHOLD) return 'up'
  if (pnlPct <= -BIG_MOVE_PNL_PCT_THRESHOLD) return 'down'
  return null
}

export interface BigMoveArgs {
  bot: LiveBot
  positionId: string
  /** Same basis as `unrealized_pnl_pct`: positive = % of max profit, negative = % of max loss. */
  pnlPct: number
  occurredAt: string
}

export function buildBigMoveEvent(args: BigMoveArgs): NotificationEvent {
  const label = LIVE_BOT_LABEL[args.bot]
  const tier = bigMoveTier(args.pnlPct) ?? (args.pnlPct >= 0 ? 'up' : 'down')
  const direction = tier === 'up' ? 'in your favor' : 'against you'
  return {
    category: 'big_move',
    // Not timestamped (types.ts's rule) — one claim row per position, re-armed
    // only by `state` flipping between 'up' and 'down'.
    eventKey: `big_move:${args.positionId}`,
    occurredAt: args.occurredAt,
    route: '/live',
    routeParams: { account: args.bot },
    title: 'Big move on an open trade',
    subtitle: `${label} is swinging ${direction}`,
    body: `${label}'s open trade has moved about ${Math.abs(args.pnlPct).toFixed(0)}% of its range. Worth a look.`,
    state: tier,
  }
}

export interface DailySummaryArgs {
  /** Sum of today_pnl across every live bot this customer owns (lib/live/summary.ts's
   *  own number — the same one the Live page's "Today's Result" tile already shows). */
  pnl: number
  /** "Monday" … "Friday" in Central time, matching ironforge-app.html's example copy
   *  ("Your agents finished Thursday at +$93.00") exactly. */
  dateLabel: string
  /** CT calendar date (YYYY-MM-DD) — the dedupe key, so this fires at most once per
   *  customer per day regardless of how many scan cycles the EOD window spans. */
  dateKey: string
  occurredAt: string
}

export function buildDailySummaryEvent(args: DailySummaryArgs): NotificationEvent {
  const sign = args.pnl >= 0 ? '+' : '-'
  const amount = `${sign}$${Math.abs(args.pnl).toFixed(2)}`
  return {
    category: 'daily_summary',
    eventKey: `daily_summary:${args.dateKey}`,
    occurredAt: args.occurredAt,
    route: '/home',
    title: 'Daily summary',
    subtitle: `Your agents finished ${args.dateLabel} at ${amount}`,
    body: 'Tap to see today’s results.',
    amount: args.pnl,
  }
}

/**
 * Percent of the position's own range, same formula as lib/live/summary.ts's
 * private `profitBasisPct` (gain vs max profit / loss vs max loss) — duplicated
 * rather than imported because scanner.ts (the only caller) must never pull in
 * summary.ts's Tradier-heavy, request-scoped module graph for a one-line check.
 * Keep in sync with summary.ts if that formula ever changes.
 */
export function positionRangePct(pnl: number, maxProfitDollars: number, maxLossDollars: number): number | null {
  const basis = pnl >= 0 ? maxProfitDollars : maxLossDollars
  if (!(basis > 0)) return null
  return Math.round((pnl / basis) * 10000) / 100
}
