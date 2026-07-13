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
export type VolBot = 'flame' | 'spark' | 'inferno' | 'blaze' | 'flare' | 'kindle' | 'spark2'

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
const SELLER_BOTS: ReadonlySet<VolBot> = new Set<VolBot>(['spark', 'flame', 'inferno', 'kindle'])
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

/* ------------------------------------------------------------------ */
/*  Daily hedge trigger (pure, unit-tested) — the STABLE per-day read  */
/* ------------------------------------------------------------------ */

export interface RegimeSnapshot {
  regimeLabel?: string | null
  /** Alerting keys active this read (e.g. ['ts_flattening']). */
  activeSignals: string[]
  vix?: number | null
  vix3m?: number | null
  vvix?: number | null
}

export interface HedgeDecision {
  flagged: boolean
  reasons: string[]
}

/** Regimes that, on their own, warrant an IC hedge for the day. */
const HEDGE_REGIMES: ReadonlySet<string> = new Set(['backwardation_stressed', 'contango_flattening'])
/** VVIX (vol-of-vol) stress threshold. */
export const VVIX_STRESS = 115

/**
 * The stable daily hedge trigger: flagged=true (with reasons) when the regime /
 * term structure signals elevated short-premium tail risk — the days we want an
 * IC hedge on. Pure + total. The scanner LATCHES this per CT day (sticky) so a
 * transient intraday trip still marks the day "hedge", killing the flap problem.
 * Calm contango with VIX<VIX3M and benign VVIX → not flagged (don't hedge).
 */
export function hedgeFlagged(s: RegimeSnapshot): HedgeDecision {
  const reasons: string[] = []
  if (s.regimeLabel && HEDGE_REGIMES.has(s.regimeLabel)) reasons.push(`regime ${s.regimeLabel}`)
  if (s.activeSignals?.includes('ts_flattening')) reasons.push('ts_flattening')
  if (s.activeSignals?.includes('backwardation')) reasons.push('backwardation')
  if (typeof s.vix === 'number' && typeof s.vix3m === 'number' && s.vix > s.vix3m) {
    reasons.push(`VIX ${s.vix.toFixed(1)} > VIX3M ${s.vix3m.toFixed(1)}`)
  }
  if (typeof s.vvix === 'number' && s.vvix >= VVIX_STRESS) {
    reasons.push(`VVIX ${s.vvix.toFixed(0)} ≥ ${VVIX_STRESS}`)
  }
  return { flagged: reasons.length > 0, reasons }
}

/* ------------------------------------------------------------------ */
/*  Alert debounce / hysteresis (pure, unit-tested) — kills the flap   */
/* ------------------------------------------------------------------ */

export interface SignalStreak {
  active: number
  inactive: number
}

/** Consecutive active reads required before OPENING an alert (~10 min @ 5-min cadence). */
export const DEBOUNCE_OPEN_AFTER = 2
/** Consecutive inactive reads required before RESOLVING an open alert (~15 min). */
export const DEBOUNCE_RESOLVE_AFTER = 3

/**
 * Advance per-signal active/inactive streaks by one cycle (pure → new map).
 * `instActive` = keys active THIS read; `keys` = the universe to track.
 */
export function stepStreaks(
  prev: Record<string, SignalStreak>,
  instActive: string[],
  keys: readonly string[],
): Record<string, SignalStreak> {
  const active = new Set(instActive)
  const next: Record<string, SignalStreak> = {}
  for (const k of keys) {
    const p = prev[k] ?? { active: 0, inactive: 0 }
    next[k] = active.has(k)
      ? { active: p.active + 1, inactive: 0 }
      : { active: 0, inactive: p.inactive + 1 }
  }
  return next
}

/**
 * Debounced open/resolve decision from streaks + currently-open keys. Open once a
 * key's active streak ≥ openAfter; resolve an open key once its inactive streak ≥
 * resolveAfter. This replaces the per-cycle diff so a 5-min blip can't flap an alert.
 */
export function debouncedTransitions(
  streaks: Record<string, SignalStreak>,
  openKeys: string[],
  opts: { openAfter: number; resolveAfter: number } = {
    openAfter: DEBOUNCE_OPEN_AFTER,
    resolveAfter: DEBOUNCE_RESOLVE_AFTER,
  },
): VolAlertDiff {
  const open = new Set(openKeys)
  const toOpen: string[] = []
  for (const [k, s] of Object.entries(streaks)) {
    if (!open.has(k) && s.active >= opts.openAfter) toOpen.push(k)
  }
  const toResolve: string[] = []
  for (const k of openKeys) {
    const s = streaks[k]
    if (s && s.inactive >= opts.resolveAfter) toResolve.push(k)
  }
  return { toOpen, toResolve }
}

/* ------------------------------------------------------------------ */
/*  Signal escalation ladder (pure, unit-tested) — NEVER drops a read  */
/* ------------------------------------------------------------------ */

/**
 * Instantaneous escalation state of a directional signal on a single read.
 *
 *   idle      → not active and not near its trigger
 *   watch     → not active but proximity ≥ WATCH_PROXIMITY (approaching)
 *   tripped   → crossed its trigger this read but not yet debounce-CONFIRMED
 *   confirmed → has a sustained, debounce-confirmed open alert (`vol_alerts`)
 *
 * The `vol_alerts` table holds only the CONFIRMED (actionable, debounced) layer.
 * This ladder is the observation layer underneath it: a `tripped` read that never
 * confirms still becomes a permanent event row, so a real market sign can never be
 * silently dropped by the debounce. `resolved` is not a state — it's the EVENT of
 * leaving `confirmed` (a confirmed→{idle,watch} transition).
 */
export type SignalState = 'idle' | 'watch' | 'tripped' | 'confirmed'

/** Proximity (0..1, from the advisor) at/above which an inactive signal is WATCH. */
export const WATCH_PROXIMITY = 0.9

/**
 * Classify one signal's instantaneous ladder state. `confirmed` wins (the open
 * alert persists through the resolve-debounce window even when a single read goes
 * inactive); else `tripped` when active; else `watch` near the trigger; else idle.
 * Pure + total.
 */
export function classifySignalState(args: {
  active: boolean
  confirmed: boolean
  proximity: number | null | undefined
}): SignalState {
  if (args.confirmed) return 'confirmed'
  if (args.active) return 'tripped'
  const p = typeof args.proximity === 'number' && Number.isFinite(args.proximity) ? args.proximity : 0
  return p >= WATCH_PROXIMITY ? 'watch' : 'idle'
}

/** A single ladder state change for one signal (the unit the event log records). */
export interface LadderTransition {
  signalKey: string
  direction: string | null
  from: SignalState
  to: SignalState
}

/** Notification verdict for a ladder transition. */
export interface NotifyVerdict {
  notify: boolean
  priority: 'high' | 'info'
  /** Short machine reason, e.g. 'confirmed' | 'early-warning' | 'resolved' | 'none'. */
  reason: string
}

/**
 * Escalation + asymmetry policy for a ladder transition (pure):
 *   • →confirmed (any signal)                  → notify HIGH ('confirmed')
 *   • →tripped for the bearish vol-expansion
 *     signal (ts_flattening), if early-warning
 *     is enabled                               → notify HIGH ('early-warning')
 *   • confirmed→{idle,watch,tripped}           → no ping ('resolved'; UI only)
 *   • everything else                          → no ping ('none')
 *
 * The ts_flattening asymmetry exists because vol-expansion is the ruin scenario for
 * the short-premium books — we accept an extra heads-up on the dangerous signal
 * before it fully confirms. Flap is tamed by a per-signal notify cooldown at the
 * call site, not here. Pure + total.
 */
export function notifyDecision(
  t: LadderTransition,
  opts: { earlyWarnTsFlattening?: boolean } = {},
): NotifyVerdict {
  const earlyWarn = opts.earlyWarnTsFlattening !== false // default ON
  if (t.to === 'confirmed') {
    return { notify: true, priority: 'high', reason: 'confirmed' }
  }
  if (t.from === 'confirmed') {
    return { notify: false, priority: 'info', reason: 'resolved' }
  }
  if (t.to === 'tripped' && t.signalKey === 'ts_flattening' && earlyWarn) {
    return { notify: true, priority: 'high', reason: 'early-warning' }
  }
  return { notify: false, priority: 'info', reason: 'none' }
}
