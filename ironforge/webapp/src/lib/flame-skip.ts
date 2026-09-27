/**
 * FLAME_SKIP_WEEKDAYS / FLAME_SKIP_SCOPE — skip EBB and FLINT entries on
 * specific weekdays, on FLAME only (Leron, 2026-09-27, "Add it now": arms
 * W3 from RESULT_2k_wednesday_skip.md — Wed+Thu is the only rule that beat
 * the random-skip placebo, cutting customer bad-case below-deposit days
 * 78->33 and weeks-erasing losses 3.6%->1.4% at -23% typical profit).
 *
 * `FLAME_SKIP_WEEKDAYS` unset/empty = no skipping, byte-for-byte the prior
 * behavior — this module changes nothing until an operator sets it.
 *
 * `FLAME_SKIP_SCOPE` controls whether the skip also reaches FLAME's OWN
 * production account (6YB71371, 'Flame'):
 *   customers (default) — skip every non-owner customer/sandbox account
 *   (resolveEligibleAccounts('flame') returns User/Matt/Logan today) and
 *   FLAME's own paper book. Production keeps trading.
 *   all — also skip the production account.
 *
 * This file holds ONLY pure, DB/network-free logic (same split as
 * lib/flint.ts, lib/ebb-sizing.ts) so it is unit-testable without mocking
 * Postgres or Tradier.
 *
 * TWO CALLING CONVENTIONS, because this codebase carries two different kinds
 * of "now" (see scanner.ts getCentralTime()'s own comment on the bug this
 * avoids):
 *   - A real Date instant (tradier.ts's `new Date()`, or any wall-clock
 *     timestamp) — convert with `centralWeekdayAbbrev` / `isFlameSkipWeekday`,
 *     which route through Intl's America/Chicago timezone. This is what
 *     correctly resolves "UTC Thursday 01:00 = Wednesday 19:00 CT".
 *   - scanner.ts's `ct` — a Date whose LOCAL fields (getDay(), getHours())
 *     are already the Central-Time wall-clock fields (see getCentralTime()).
 *     Re-running that through Intl/America-Chicago would shift it a SECOND
 *     time. Use `weekdayAbbrevFromDow(ct.getDay())` instead, matching every
 *     other `dow = ct.getDay()` check already in scanner.ts.
 */

export type FlameSkipScope = 'customers' | 'all'

const WEEKDAY_ABBREVS = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'] as const

/** JS Date.getDay() index (0=Sunday..6=Saturday) -> 3-letter lowercase abbreviation. */
export function weekdayAbbrevFromDow(dow: number): string {
  return WEEKDAY_ABBREVS[((dow % 7) + 7) % 7]
}

/**
 * The America/Chicago weekday abbreviation ('sun'..'sat') for a REAL Date
 * instant. Do NOT pass scanner.ts's `ct` here — see the file header.
 */
export function centralWeekdayAbbrev(instant: Date): string {
  const wd = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Chicago', weekday: 'short' }).format(instant)
  return wd.toLowerCase().slice(0, 3)
}

/**
 * FLAME_SKIP_WEEKDAYS — comma list of weekday names/abbreviations
 * ("wed,thu", "Wednesday, Thursday" — case-insensitive; only the first 3
 * letters are read). Unset or empty = no skipping — the default, and this
 * whole feature's off switch.
 */
export function getFlameSkipWeekdays(): Set<string> {
  const raw = (process.env.FLAME_SKIP_WEEKDAYS ?? '').trim().toLowerCase()
  if (!raw) return new Set()
  const days = new Set<string>()
  for (const part of raw.split(',')) {
    const abbrev = part.trim().slice(0, 3)
    if ((WEEKDAY_ABBREVS as readonly string[]).includes(abbrev)) days.add(abbrev)
  }
  return days
}

/** FLAME_SKIP_SCOPE — 'all' opts the production account in too. Anything else (including unset) is 'customers'. */
export function getFlameSkipScope(): FlameSkipScope {
  return (process.env.FLAME_SKIP_SCOPE ?? '').trim().toLowerCase() === 'all' ? 'all' : 'customers'
}

/** True when `weekday` (a 3-letter abbrev) is in the configured skip set. Empty set (env unset) never skips. */
export function isWeekdayInSkipSet(weekday: string, skipWeekdays: Set<string> = getFlameSkipWeekdays()): boolean {
  return skipWeekdays.size > 0 && skipWeekdays.has(weekday)
}

/**
 * True when a REAL Date instant's America/Chicago weekday is in
 * FLAME_SKIP_WEEKDAYS. Use this from tradier.ts (`new Date()`), never with
 * scanner.ts's `ct` — see the file header.
 */
export function isFlameSkipWeekday(instant: Date, skipWeekdays: Set<string> = getFlameSkipWeekdays()): boolean {
  return isWeekdayInSkipSet(centralWeekdayAbbrev(instant), skipWeekdays)
}

/**
 * Should THIS account be skipped for THIS entry, right now?
 * `isSkipWeekdayToday` is the caller's own weekday check (from either
 * `isFlameSkipWeekday(new Date())` or `isWeekdayInSkipSet(weekdayAbbrevFromDow(ct.getDay()))`,
 * so this function stays convention-agnostic). Production is skipped ONLY
 * when `scope==='all'`; every other account (sandbox mirrors, the bot's own
 * paper book) is skipped whenever the weekday matches, regardless of scope.
 * `accountType` matches SandboxAccount.type: undefined is treated as
 * 'sandbox', same as every other account-type check in tradier.ts.
 */
export function shouldSkipAccountForWeekday(
  accountType: string | undefined,
  isSkipWeekdayToday: boolean,
  scope: FlameSkipScope = getFlameSkipScope(),
): boolean {
  if (!isSkipWeekdayToday) return false
  if (accountType === 'production' && scope !== 'all') return false
  return true
}

/** The exact log-suffix the spec calls for: `skip:weekday_skip(wed)`. */
export function weekdaySkipLogTag(weekday: string): string {
  return `skip:weekday_skip(${weekday})`
}
