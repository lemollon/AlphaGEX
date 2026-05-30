/**
 * Volatility Regime Alerts — shared types, pure reconcile logic, the
 * bot-page message tailoring helper, and the `vol_alerts` table bootstrap.
 *
 * Everything here is PURE (no I/O, no `pg`/DB import) so it is safe to import
 * from client components. The DB-bound `ensureVolAlertsTable()` lives in the
 * server-only sibling `volAlerts.server.ts`.
 *
 * The pure helpers (`diffVolAlerts`, `botVolMessage`) carry NO I/O and are
 * unit-tested under vitest's `node` env.
 *
 * Data source: AlphaGEX `/api/vix/regime-advisor`. Directional signals are
 * those whose `direction` is 'bullish' or 'bearish'. We alert ONLY on the
 * high-confidence directional set and EXCLUDE `divergence` (low-confidence)
 * and `double_floor` (neutral).
 */

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export type VolAlertStatus = 'active' | 'resolved'

/** One row of the `vol_alerts` table, as returned by the API (timestamps
 *  stringified). All nullable fields may come back null. */
export interface VolAlert {
  id: number
  signal_key: string
  direction: string | null
  status: VolAlertStatus
  headline: string | null
  message: string | null
  regime_label: string | null
  vix: number | null
  vvix: number | null
  fired_at: string | null
  resolved_at: string | null
}

/** The bot kinds that render a tailored volatility banner. */
export type VolBot = 'flame' | 'spark' | 'inferno' | 'blaze' | 'flare'

/** Tone → color mapping handled by the banner component. */
export type VolTone = 'warn' | 'bull' | 'bear' | 'info'

/** Tailored bot-page message, or null when nothing relevant is active. */
export interface BotVolMessage {
  tone: VolTone
  text: string
}

/* ------------------------------------------------------------------ */
/*  Alerting signal set                                                */
/* ------------------------------------------------------------------ */

/**
 * Signal keys we alert on (directional + high-confidence). `divergence`
 * (bearish but low-confidence) and `double_floor` (neutral) are excluded.
 */
export const ALERTING_SIGNAL_KEYS = [
  'backwardation', // bullish
  'exhaustion',    // bullish
  'ts_flattening', // bearish
] as const

export type AlertingSignalKey = (typeof ALERTING_SIGNAL_KEYS)[number]

const ALERTING_SET: ReadonlySet<string> = new Set(ALERTING_SIGNAL_KEYS)

/** True when a signal key is one we open alerts for. */
export function isAlertingKey(key: string): boolean {
  return ALERTING_SET.has(key)
}

/* ------------------------------------------------------------------ */
/*  Pure reconcile logic (unit-tested, no I/O)                         */
/* ------------------------------------------------------------------ */

export interface VolAlertDiff {
  /** Keys newly active that have no open alert → INSERT a new row. */
  toOpen: string[]
  /** Open-alert keys no longer active → mark resolved. */
  toResolve: string[]
}

/**
 * Reconcile the set of currently-active directional signal keys against the
 * set of keys that already have an OPEN alert.
 *
 *   toOpen    = activeKeys not already open  (inactive→active edge)
 *   toResolve = openKeys no longer active    (active→inactive edge)
 *
 * Pure + total. De-dupes inputs so a doubled key never produces a double
 * insert. Order of `toOpen`/`toResolve` follows first-seen order of the
 * respective input arrays.
 */
export function diffVolAlerts(activeKeys: string[], openKeys: string[]): VolAlertDiff {
  const active = new Set(activeKeys)
  const open = new Set(openKeys)

  const toOpen: string[] = []
  for (const k of activeKeys) {
    if (!open.has(k) && !toOpen.includes(k)) toOpen.push(k)
  }

  const toResolve: string[] = []
  for (const k of openKeys) {
    if (!active.has(k) && !toResolve.includes(k)) toResolve.push(k)
  }

  return { toOpen, toResolve }
}

/* ------------------------------------------------------------------ */
/*  Bot-page message tailoring (unit-tested, no I/O)                   */
/* ------------------------------------------------------------------ */

/** Iron-condor / short-premium sellers. */
const SELLER_BOTS: ReadonlySet<VolBot> = new Set<VolBot>(['spark', 'flame', 'inferno'])
/** Debit-spread / 0DTE directional bots. */
const DIRECTIONAL_BOTS: ReadonlySet<VolBot> = new Set<VolBot>(['blaze', 'flare'])

/** Priority order for SELLER bots (first match wins). */
const SELLER_PRIORITY: AlertingSignalKey[] = ['backwardation', 'ts_flattening', 'exhaustion']
/** Priority order for DIRECTIONAL bots (backwardation/exhaustion tie → list order). */
const DIRECTIONAL_PRIORITY: AlertingSignalKey[] = ['backwardation', 'exhaustion', 'ts_flattening']

/**
 * Compute the tailored banner message for a bot, given the currently-active
 * alerts. Returns null when nothing relevant is active (banner renders nothing).
 *
 * Sellers (spark/flame/inferno):
 *   - backwardation OR ts_flattening → WARN (tail-risk for short premium)
 *   - exhaustion only                → INFO (bounce likely; ICs OK, mind reversal)
 * Directional (blaze/flare):
 *   - exhaustion OR backwardation    → BULL (buy-the-bounce; lean long)
 *   - ts_flattening                  → BEAR (rising-vol; lean puts/downside)
 *
 * When several relevant signals are active, the highest-priority one for that
 * bot kind decides the message. Pure + total; never throws.
 */
export function botVolMessage(bot: VolBot, alerts: VolAlert[] | null | undefined): BotVolMessage | null {
  if (!alerts || alerts.length === 0) return null

  // Active alerting keys present right now.
  const activeKeys = new Set<string>()
  for (const a of alerts) {
    if (a && a.status === 'active' && isAlertingKey(a.signal_key)) {
      activeKeys.add(a.signal_key)
    }
  }
  if (activeKeys.size === 0) return null

  if (SELLER_BOTS.has(bot)) {
    const top = SELLER_PRIORITY.find((k) => activeKeys.has(k))
    if (!top) return null
    if (top === 'backwardation' || top === 'ts_flattening') {
      return {
        tone: 'warn',
        text:
          'Backwardation/flattening active — historically ~4× next-day tail risk for short premium. ' +
          'Consider halting new ICs or widening wings.',
      }
    }
    // exhaustion only
    return {
      tone: 'info',
      text: 'Vol exhausting — a bounce is likely; ICs OK but mind a sharp reversal.',
    }
  }

  if (DIRECTIONAL_BOTS.has(bot)) {
    const top = DIRECTIONAL_PRIORITY.find((k) => activeKeys.has(k))
    if (!top) return null
    if (top === 'backwardation' || top === 'exhaustion') {
      return {
        tone: 'bull',
        text: 'Exhaustion/backwardation — buy-the-bounce setup; lean long (calls / call debit spread).',
      }
    }
    // ts_flattening
    return {
      tone: 'bear',
      text: 'Flattening — rising-vol warning; lean puts / downside.',
    }
  }

  return null
}
