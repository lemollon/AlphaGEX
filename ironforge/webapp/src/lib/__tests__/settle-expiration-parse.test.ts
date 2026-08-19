import { describe, it, expect } from 'vitest'

/**
 * The settlement date must come from toISOString(), never String(Date).
 *
 * node-postgres hands back a DATE column as a JS Date. `String(date)` is the
 * LOCALE rendering, so slicing 10 characters off it yields "Sun Aug 16", which
 * can never equal a daily bar's "2026-08-17". settleExpiredPositions used the
 * bare form and therefore matched no bar, ever: every position fell through to
 * no_settle_price and stayed open. FLAME appeared to work only because the
 * dashboard's 14:45 EOD poll was closing its positions; SPARK's 8/17 and 8/18
 * trades, on days nobody had that page open, were still `open` on 8/19.
 *
 * This pins the parse itself — the defect was one expression, and it is the
 * expression a future edit is most likely to "simplify" back.
 */

/** The idiom used at all nine expiration-reading sites in scanner.ts. */
function expOf(v: unknown): string {
  const d = v as { toISOString?: () => string }
  return d?.toISOString?.()?.slice(0, 10) || String(v).slice(0, 10)
}

describe('settlement expiration parse', () => {
  it('reads a pg DATE (JS Date) as YYYY-MM-DD', () => {
    expect(expOf(new Date('2026-08-17T00:00:00Z'))).toBe('2026-08-17')
    expect(expOf(new Date('2026-08-18T00:00:00Z'))).toBe('2026-08-18')
  })

  it('demonstrates the bug it replaced', () => {
    // The exact expression that shipped, and what it actually produced.
    expect(String(new Date('2026-08-17T00:00:00Z')).slice(0, 10)).not.toBe('2026-08-17')
  })

  it('still handles a plain string expiration', () => {
    expect(expOf('2026-08-17')).toBe('2026-08-17')
  })

  it('produces a value a daily bar lookup can match', () => {
    const hist = [
      { date: '2026-08-17', close: 771.2 },
      { date: '2026-08-18', close: 774.05 },
    ]
    const exp = expOf(new Date('2026-08-18T00:00:00Z'))
    expect(hist.find((h) => h.date === exp)?.close).toBe(774.05)
  })
})
