/**
 * Swing-leg derivations for the Live page.
 *
 * Pulled out of summary.ts because this is date arithmetic across a timezone, driving a
 * customer-facing badge that says whether their money sat in the market overnight. It is
 * exactly the kind of thing that is wrong by one day and nobody notices.
 *
 * Both inputs are CT calendar dates ("YYYY-MM-DD") so there is no clock or zone left to
 * get wrong here — the caller resolves CT once and passes it in.
 */

/**
 * Is a SWING actually live — i.e. does the extra card belong on screen?
 *
 * A swing means a position was CARRIED THROUGH A CLOSE, so the test is that one of the
 * open positions is held overnight. Position count alone is not it: Spark can hold two
 * positions opened on the SAME day (production shows one, paper currently shows two from
 * 2026-07-29), and rendering the swing layout for those produces two "Opened Today"
 * cards describing a swing that never happened.
 *
 * Both conditions are required. A lone held-overnight position keeps the ordinary single
 * card — there is no second trade to compare it against, which is what the two-card view
 * exists to show.
 */
export function isSwingActive(
  positions: ReadonlyArray<{ held_overnight: boolean }> | null | undefined,
): boolean {
  if (!positions || positions.length < 2) return false
  return positions.some((p) => p.held_overnight)
}

export interface SwingMeta {
  /** Opened on an earlier CT date, so it was carried through a close. */
  heldOvernight: boolean
  /** 1 on the day it opened, 2 the next calendar day, and so on. Never below 1. */
  dayNumber: number
}

export function deriveSwingMeta(openedCtDate: string | null, ctToday: string): SwingMeta {
  // No open time recorded: claiming "held overnight" would assert something we cannot
  // support, so it reads as a fresh position.
  if (!openedCtDate) return { heldOvernight: false, dayNumber: 1 }

  const openedMs = Date.parse(`${openedCtDate}T00:00:00Z`)
  const todayMs = Date.parse(`${ctToday}T00:00:00Z`)
  if (Number.isNaN(openedMs) || Number.isNaN(todayMs)) {
    return { heldOvernight: false, dayNumber: 1 }
  }

  const elapsedDays = Math.round((todayMs - openedMs) / 86_400_000)
  return {
    // Strictly earlier. A position opened today is not "held overnight" however long ago
    // in the session it was opened.
    heldOvernight: elapsedDays > 0,
    // Clamped at 1 so a clock skew that puts `opened` in the future cannot render "Day 0"
    // or a negative day.
    dayNumber: Math.max(1, elapsedDays + 1),
  }
}
