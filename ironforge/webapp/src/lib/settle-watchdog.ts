/**
 * THE EXPIRED-POSITION WATCHDOG — decision logic.
 *
 * An option that has expired is not "waiting". It is over. A row that still says
 * `status = 'open'` after its expiration date has passed is ALWAYS wrong, whatever
 * the cause — a rejected broker order, a bad date parse, a 0-row UPDATE, or the next
 * failure mode nobody has invented yet. With max 1 concurrent position, one such row
 * blocks every future entry, silently, for as long as nobody looks at the page.
 *
 * SPARK's 8/21, 8/24 and 8/25 positions sat exactly like that for three trading days
 * while the log printed `SETTLED ... pnl=$35.00` once a minute. The fix for the cause
 * shipped in PR #2911. THIS is the fix for the DETECTION failure, and it is a
 * WATCHDOG, not an alarm: an alarm turns a silent failure into a notification someone
 * still has to act on, which loses the same three days if nobody is looking. This one
 * repairs the book and then reports what it did.
 *
 * ── The two guards are the whole design ────────────────────────────────────────
 *
 * 1. NEVER INVENT A PRICE. The settlement value comes from the daily bar's close for
 *    the expiration date or the watchdog does NOTHING and escalates. No $0 mark, no
 *    live quote on a dead contract, no estimate. A fixer that guesses turns a
 *    bookkeeping problem into a real loss: `max(0.0, val)` once booked MAX PROFIT on
 *    ITM credit expiries, and a $0 force-close mark did the same thing a second time.
 *    Those are precisely what a careless version of this file looks like.
 *
 * 2. CIRCUIT BREAKER. The bug this replaces WAS an infinite retry loop — three
 *    rejected multileg orders a minute for three days. If the watchdog force-settles
 *    the same `position_id` and that position is still open on a later cycle, the
 *    fixer itself is broken. It stops, escalates once, and never touches that row
 *    again. Bounded retry is not optional here.
 *
 * Everything in this file is pure: no DB, no network, no clock. The scanner owns the
 * IO and hands the facts in, which is what makes the guards testable.
 */

/**
 * Cycles a past-expiry open position must survive before the watchdog acts.
 *
 * 2, not 1: the FIRST cycle is the normal settle path's turn. `settleExpiredPositions`
 * runs immediately before the watchdog in the same tick, so a position that the normal
 * path can handle is already closed by the time the watchdog's query runs. Acting on
 * the first sighting would race the thing it is backstopping.
 */
export const WATCHDOG_CYCLES_BEFORE_ACT = 2

/**
 * Force-settles allowed per position, ever. One.
 *
 * A second attempt is not a retry — it is proof the first `UPDATE` did not stick, and
 * re-running a fixer that does not fix is how the original bug burned three days.
 */
export const WATCHDOG_MAX_ATTEMPTS = 1

/** `close_reason` written by the normal held-to-expiry settle path. */
export const SETTLE_AT_EXPIRY_REASON = 'settled_at_expiry'

/** `close_reason` written by the watchdog, so a force-settle is auditable forever. */
export const WATCHDOG_SETTLE_REASON = 'watchdog_force_settle'

/** Log `level` for a watchdog repair. Distinct from TRADE_CLOSE so it is greppable. */
export const WATCHDOG_LOG_LEVEL = 'WATCHDOG'

/** Log `level` for the case the watchdog tried and could not. This one is loud. */
export const WATCHDOG_ESCALATION_LEVEL = 'CRITICAL'

/**
 * A close that must be booked WITHOUT touching the broker.
 *
 * An expired contract has no market, so a close order against it can never produce a
 * fill price — Tradier answers "There is no price. Security symbol: SPY260824P00762000"
 * — and closePosition's DEFER branches then wait forever for a fill that cannot come.
 * closePosition also derives this from the expiration date; naming the reasons as well
 * means a same-day settle (where the date comparison is false) is still book-only.
 */
export function isBookOnlyCloseReason(reason: string): boolean {
  return reason === SETTLE_AT_EXPIRY_REASON || reason === WATCHDOG_SETTLE_REASON
}

/**
 * Read a `DATE` column as YYYY-MM-DD.
 *
 * node-postgres hands back a JS Date, and `String(new Date('2026-08-17')).slice(0,10)`
 * is "Sun Aug 16" — the LOCALE rendering, a day early, and never equal to a daily
 * bar's `date`. That single conversion is why settleExpiredPositions matched nothing
 * for its entire first ten days alive.
 */
export function normalizeExpiration(expiration: unknown): string {
  const d = expiration as { toISOString?: () => string } | null | undefined
  return d?.toISOString?.()?.slice(0, 10) || String(expiration).slice(0, 10)
}

/**
 * STRICTLY past expiry. Expiry day itself is not the watchdog's business — the
 * position is still live until the close, and the normal settle path owns it.
 */
export function isPastExpiry(expiration: unknown, todayCT: string): boolean {
  const exp = normalizeExpiration(expiration)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(exp)) return false
  return exp < todayCT
}

export type SpreadLegs = {
  putShort: number
  putLong: number
  /** 0 for a put credit spread — every FLAME/SPARK position since the Apr 2026 migration. */
  callShort: number
  callLong: number
}

/**
 * Intrinsic value of the structure at the official close, clamped to the wings.
 *
 * 🚨 GUARD 1 LIVES HERE. Returns `null` — never 0 — when there is no usable close or
 * the row's strikes are malformed. `null` means "do not settle, escalate". Returning
 * 0 would book MAX PROFIT on a position that may have expired deep ITM, which is
 * exactly the loss two prior incidents booked for real.
 */
export function settlementValue(legs: SpreadLegs, settleClose: number): number | null {
  if (!Number.isFinite(settleClose) || settleClose <= 0) return null

  let value = 0

  if (legs.putShort > 0) {
    const putWidth = legs.putShort - legs.putLong
    if (!(putWidth > 0)) return null // malformed row — refuse rather than guess
    value += Math.min(Math.max(legs.putShort - settleClose, 0), putWidth)
  }

  if (legs.callShort > 0) {
    const callWidth = legs.callLong - legs.callShort
    if (!(callWidth > 0)) return null
    value += Math.min(Math.max(settleClose - legs.callShort, 0), callWidth)
  }

  if (legs.putShort <= 0 && legs.callShort <= 0) return null // nothing to settle

  return Math.round(value * 10000) / 10000
}

/** Realized P&L of a credit spread settled at `value`. Credit and value are per-contract. */
export function settlementPnl(credit: number, value: number, contracts: number): number {
  return Math.round((credit - value) * 100 * contracts * 100) / 100
}

export type WatchdogEscalation =
  /** No daily bar for the expiration date. Guard 1: refuse rather than invent one. */
  | 'no_settle_price'
  /** Already force-settled once and still open. Guard 2: the fixer is broken. */
  | 'circuit_breaker'

export type WatchdogDecision =
  /** Seen, but the normal settle path still owns it this cycle. */
  | { action: 'wait'; cyclesSeen: number }
  /** Already escalated. Stay quiet — an alert repeated every 60s is an alert nobody reads. */
  | { action: 'silent' }
  /** Book it at `value`. */
  | { action: 'settle'; value: number; settleClose: number }
  /** Tried, or refused to try. Say so loudly, once. */
  | { action: 'escalate'; cause: WatchdogEscalation; detail: string }

export type WatchdogInput = {
  /** Consecutive scan cycles this position has been seen open-and-past-expiry. */
  cyclesSeen: number
  /** Force-settles already attempted against this position, memory OR database. */
  attempts: number
  /** Whether this position has already been escalated. */
  tripped: boolean
  /** Official close for the expiration date, or null if no daily bar was found. */
  settleClose: number | null
  legs: SpreadLegs
}

/**
 * The whole decision, in evaluation order. Both guards sit ahead of every path that
 * can write to the database, which is the only ordering that makes them guards.
 */
export function decideWatchdog(input: WatchdogInput): WatchdogDecision {
  // Already escalated: never speak twice about the same row.
  if (input.tripped) return { action: 'silent' }

  // 🚨 GUARD 2 — before anything else that could act.
  if (input.attempts >= WATCHDOG_MAX_ATTEMPTS) {
    return {
      action: 'escalate',
      cause: 'circuit_breaker',
      detail:
        `force-settled ${input.attempts}x and still open — the watchdog is not fixing it. ` +
        `Refusing to loop; fix this by hand.`,
    }
  }

  // The normal settle path gets its turn first.
  if (input.cyclesSeen < WATCHDOG_CYCLES_BEFORE_ACT) {
    return { action: 'wait', cyclesSeen: input.cyclesSeen }
  }

  // 🚨 GUARD 1 — no close, no settle. Not a $0 mark, not a live quote, not an estimate.
  const value = input.settleClose == null ? null : settlementValue(input.legs, input.settleClose)
  if (value == null) {
    return {
      action: 'escalate',
      cause: 'no_settle_price',
      detail:
        input.settleClose == null
          ? 'no daily bar for the expiration date — refusing to invent a settlement price'
          : `close ${input.settleClose} cannot be settled against these strikes ` +
            `(${input.legs.putLong}/${input.legs.putShort}P ${input.legs.callShort}/${input.legs.callLong}C)`,
    }
  }

  return { action: 'settle', value, settleClose: input.settleClose as number }
}

/**
 * Consecutive-cycle and attempt bookkeeping.
 *
 * `observe()` is called once per scan cycle with the FULL set of currently
 * offending position ids. Anything absent is forgotten — a position the normal path
 * settled must not carry a stale count into a future incident, and a count that only
 * ever grows is not a CONSECUTIVE count.
 *
 * Process memory is the fast path, not the authority: the durable attempt count comes
 * from the bot's own log table, so a redeploy cannot reset the circuit breaker.
 */
export class WatchdogLedger {
  private seen = new Map<string, number>()
  private attempts = new Map<string, number>()
  private tripped = new Set<string>()

  observe(ids: readonly string[]): void {
    const live = new Set(ids)
    // Array.from, never a spread: this repo's build target cannot iterate a Map/Set
    // iterator directly, and a spread here is a compile error, not a style choice.
    Array.from(this.seen.keys()).forEach((id) => {
      if (!live.has(id)) this.forget(id)
    })
    Array.from(live).forEach((id) => {
      this.seen.set(id, (this.seen.get(id) ?? 0) + 1)
    })
  }

  cyclesSeen(id: string): number {
    return this.seen.get(id) ?? 0
  }

  attemptsFor(id: string): number {
    return this.attempts.get(id) ?? 0
  }

  recordAttempt(id: string): void {
    this.attempts.set(id, this.attemptsFor(id) + 1)
  }

  isTripped(id: string): boolean {
    return this.tripped.has(id)
  }

  trip(id: string): void {
    this.tripped.add(id)
  }

  /** Drop all state for a position — it is closed, or it never was our problem. */
  forget(id: string): void {
    this.seen.delete(id)
    this.attempts.delete(id)
    this.tripped.delete(id)
  }
}

export type WatchdogRepair = { positionId: string; value: number; pnl: number }

/**
 * Why a position is still open after the watchdog looked at it. The two escalation
 * causes are DECISIONS (the watchdog refused to act); `close_declined` is an OUTCOME
 * (it acted and the write did not land), which is the case the circuit breaker exists
 * to stop from repeating.
 */
export type WatchdogFailureCause = WatchdogEscalation | 'close_declined'

export type WatchdogFailure = { positionId: string; cause: WatchdogFailureCause; detail: string }

/**
 * The message a human reads. Repairs are an FYI; failures are the loud case.
 *
 * Returns null when nothing happened, so the caller never posts an empty heartbeat —
 * a channel that pings every minute is a channel nobody reads, which is where this
 * whole incident started.
 */
export function summarizeWatchdogRun(
  botName: string,
  repaired: readonly WatchdogRepair[],
  failed: readonly WatchdogFailure[],
): { text: string; severity: 'info' | 'critical' } | null {
  if (repaired.length === 0 && failed.length === 0) return null
  const name = botName.toUpperCase()

  if (failed.length > 0) {
    const lines = failed.map(f => `${f.positionId}: ${f.cause} — ${f.detail}`)
    const fixed = repaired.length > 0
      ? ` (${repaired.length} other position${repaired.length === 1 ? '' : 's'} did settle)`
      : ''
    return {
      severity: 'critical',
      text:
        `${name}: could NOT settle ${failed.length} expired position` +
        `${failed.length === 1 ? '' : 's'}${fixed}. Entries stay BLOCKED until this is ` +
        `fixed by hand.\n${lines.join('\n')}`,
    }
  }

  const pnl = repaired.reduce((s, r) => s + r.pnl, 0)
  const sign = pnl >= 0 ? '+' : '-'
  return {
    severity: 'info',
    text:
      `${name}: force-settled ${repaired.length} expired position` +
      `${repaired.length === 1 ? '' : 's'}, ${sign}$${Math.abs(pnl).toFixed(2)}, entries unblocked.`,
  }
}
