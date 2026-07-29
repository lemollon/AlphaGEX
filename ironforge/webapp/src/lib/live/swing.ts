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
