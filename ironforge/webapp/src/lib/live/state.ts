import { getCTNow, isMarketOpen } from '@/lib/pt-tiers'
import { isMarketHoliday, isEarlyClose } from '@/lib/market-calendar'
import type { CustomerState, MarketSession } from './types'

/**
 * The single home of the customer-facing state model. Maps raw operator
 * signals (heartbeat bot_state, production pause, open positions) onto the
 * seven plain-English states the Live page shows. All customer copy lives
 * here — no options jargon (strikes, legs, greeks) is allowed in any string.
 */

export interface StateInput {
  /** bot_state as derived by /api/[bot]/status: scanning | monitoring |
   *  awaiting_fill | pending_fill | traded | market_closed | error | idle | unknown */
  botState: string
  /** heartbeat details.reason, e.g. "skip:vix_too_high(34.2>32)" */
  lastScanReason: string | null
  /** production-pause flag (ironforge_production_pause) */
  paused: boolean
  /** paper_account.is_active — operator-level bot toggle */
  isActive: boolean
  openPositions: number
  todayTradesClosed: number
  sessionOpen: boolean
  /** minutes since last heartbeat; null when no heartbeat row exists */
  heartbeatAgeMin: number | null
}

const STALE_HEARTBEAT_MIN = 15

/** Scan-skip reasons that mean "conditions failed the strategy's protection
 *  rules today" — the calm BLOCKED state, not an error. */
const BLOCKED_REASON_PREFIXES = ['skip:vix_too_high', 'skip:event_blackout']

export function deriveCustomerState(input: StateInput): CustomerState {
  const {
    botState, lastScanReason, paused, isActive,
    openPositions, todayTradesClosed, sessionOpen, heartbeatAgeMin,
  } = input

  if (paused) {
    return {
      key: 'PAUSED',
      headline: 'Spark is Paused',
      subtitle: 'You paused trading. Open positions are still being managed safely.',
      check_line: null,
      dot: 'amber',
      timeline_step: null,
      paused: true,
      can_resume: true,
    }
  }

  if (!isActive) {
    return {
      key: 'PAUSED',
      headline: 'Spark is Paused',
      subtitle: 'Trading is temporarily disabled. Open positions are still being managed safely.',
      check_line: null,
      dot: 'amber',
      timeline_step: null,
      paused: true,
      // Operator-level toggle — the customer Resume button can't clear it.
      can_resume: false,
    }
  }

  const heartbeatStale =
    sessionOpen && heartbeatAgeMin != null && heartbeatAgeMin > STALE_HEARTBEAT_MIN
  if (botState === 'error' || heartbeatStale) {
    return {
      key: 'ACTION_REQUIRED',
      headline: 'Spark Needs Attention',
      subtitle: 'We hit a technical issue and are looking into it. Your account is protected by defined-risk positions.',
      check_line: null,
      dot: 'red',
      timeline_step: null,
      paused: false,
      can_resume: false,
    }
  }

  if (openPositions > 0 && (botState === 'awaiting_fill' || botState === 'pending_fill')) {
    return {
      key: 'TRADE_ACTIVE',
      headline: 'Spark Found a Trade',
      subtitle: 'Opening a position now.',
      check_line: null,
      dot: 'blue',
      timeline_step: 1,
      paused: false,
      can_resume: false,
    }
  }

  if (openPositions > 0) {
    return {
      key: 'MONITORING_POSITION',
      headline: 'Spark is Working',
      subtitle: 'Monitoring markets and protecting your account.',
      check_line: 'No action required.',
      dot: 'green',
      timeline_step: 2,
      paused: false,
      can_resume: false,
    }
  }

  if (todayTradesClosed > 0) {
    return {
      key: 'TRADE_COMPLETE',
      headline: 'Done for Today',
      subtitle: "Today's trade is complete. See the result below.",
      check_line: 'No action required.',
      dot: 'green',
      timeline_step: 4,
      paused: false,
      can_resume: false,
    }
  }

  if (lastScanReason && BLOCKED_REASON_PREFIXES.some((p) => lastScanReason.startsWith(p))) {
    return {
      key: 'BLOCKED',
      headline: 'No Trading Today',
      subtitle: "Market conditions aren't right, so Spark is sitting this one out. That's the strategy working.",
      check_line: null,
      dot: 'gray',
      timeline_step: null,
      paused: false,
      can_resume: false,
    }
  }

  if (sessionOpen) {
    return {
      key: 'WORKING_WAITING',
      headline: 'Looking for an Opportunity',
      subtitle: 'Spark is scanning the market for a high-quality setup.',
      check_line: 'No action required.',
      dot: 'blue',
      timeline_step: 0,
      paused: false,
      can_resume: false,
    }
  }

  return {
    key: 'WORKING_WAITING',
    headline: 'Spark is Standing By',
    subtitle: 'Markets are closed. Spark resumes at the next market open.',
    check_line: 'No action required.',
    dot: 'gray',
    timeline_step: null,
    paused: false,
    can_resume: false,
  }
}

function isTradingDay(d: Date): boolean {
  return d.getDay() !== 0 && d.getDay() !== 6 && !isMarketHoliday(d)
}

const OPEN_MIN = 510 // 8:30 AM CT

export function getMarketSession(ct: Date = getCTNow()): MarketSession {
  const open = isMarketOpen(ct)
  if (open) {
    return {
      open: true,
      label: 'Market Open',
      closes_at_min: isEarlyClose(ct) ? 720 : 900,
      next_open_label: null,
    }
  }

  const label = isMarketHoliday(ct) ? 'Market Holiday' : 'Market Closed'

  // Next open: today if we're pre-open on a trading day, else walk forward.
  const mins = ct.getHours() * 60 + ct.getMinutes()
  const d = new Date(ct)
  if (!(isTradingDay(ct) && mins < OPEN_MIN)) {
    do { d.setDate(d.getDate() + 1) } while (!isTradingDay(d))
  }
  const sameDay = d.toDateString() === ct.toDateString()
  const dayName = d.toLocaleDateString('en-US', { weekday: 'long' })
  return {
    open: false,
    label,
    closes_at_min: null,
    next_open_label: `Opens ${sameDay ? 'today' : dayName} 8:30 AM CT`,
  }
}
