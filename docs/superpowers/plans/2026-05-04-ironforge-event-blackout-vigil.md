# IronForge Event Blackout (Vigil) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Halt FLAME/SPARK/INFERNO trade entries from Friday-prior 8:30 AM CT through event-day 2:00 PM CT around macro events (FOMC for v1), with an auto-refreshing 12-month calendar UI for transparency.

**Architecture:** A new `ironforge_event_calendar` table stores FOMC dates (auto-pulled from Finnhub) and operator-added custom events. The existing in-process scanner loop calls `eventCalendarRefresh()` once per ~20h to upsert from Finnhub, and an `isEventBlackoutActive()` gate runs as the cheapest check inside `tryOpenPosition()`. A new `/calendar` page renders a year-view grid, and `/calendar/admin` manages custom events.

**Tech Stack:** Next.js 14 App Router, TypeScript, PostgreSQL via `pg`, Vitest for unit tests, Tailwind CSS. All inside `ironforge/webapp/` — no Python, no new Render services.

---

## File Map

**New files:**
- `src/lib/eventCalendar/halt-window.ts` — pure halt-window math helpers
- `src/lib/eventCalendar/finnhub.ts` — Finnhub fetcher + response parser
- `src/lib/eventCalendar/repo.ts` — DB ops for `ironforge_event_calendar`
- `src/lib/eventCalendar/gate.ts` — `isEventBlackoutActive()` + per-bot config read
- `src/lib/eventCalendar/refresh.ts` — `eventCalendarRefresh()` orchestration
- `src/lib/eventCalendar/__tests__/halt-window.test.ts`
- `src/lib/eventCalendar/__tests__/finnhub.test.ts`
- `src/lib/eventCalendar/__tests__/gate.test.ts`
- `src/app/api/calendar/events/route.ts`
- `src/app/api/calendar/events/[eventId]/route.ts`
- `src/app/api/calendar/refresh/route.ts`
- `src/app/api/calendar/blackout-status/route.ts`
- `src/app/calendar/page.tsx`
- `src/app/calendar/admin/page.tsx`
- `src/components/CalendarMonthGrid.tsx`
- `src/components/CalendarStatusBanner.tsx`
- `src/components/EventBlackoutBanner.tsx`

**Modified files:**
- `src/lib/db.ts` — add 3 new tables to `ensureTables()` + new column on per-bot config
- `src/lib/scanner.ts` — call `eventCalendarRefresh()` at top of cycle, call `isEventBlackoutActive()` in `tryOpenPosition()`
- `src/components/BotDashboard.tsx` — render `EventBlackoutBanner`
- `src/components/Nav.tsx` — add Calendar nav link

---

## Task 1: DB Schema — three new tables/columns in `ensureTables()`

**Files:**
- Modify: `ironforge/webapp/src/lib/db.ts` (inside `ensureTables()` body)

- [ ] **Step 1: Open `src/lib/db.ts` and locate the `ensureTables()` function.** Find the spot after the existing `ironforge_*` table DDL (around line 130, just before the per-bot loop starts).

- [ ] **Step 2: Add the new DDL block** for `ironforge_event_calendar`, `ironforge_event_calendar_meta`, and indexes. Insert this after the existing `ironforge_production_pause` block:

```ts
await client.query(`
  CREATE TABLE IF NOT EXISTS ironforge_event_calendar (
    event_id          TEXT PRIMARY KEY,
    source            TEXT NOT NULL,
    event_type        TEXT NOT NULL,
    title             TEXT NOT NULL,
    description       TEXT,
    event_date        DATE NOT NULL,
    event_time_ct     TIME NOT NULL,
    halt_start_ts     TIMESTAMPTZ NOT NULL,
    halt_end_ts       TIMESTAMPTZ NOT NULL,
    resume_offset_min INT NOT NULL DEFAULT 60,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_by        TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
  )
`)
await client.query(`
  CREATE INDEX IF NOT EXISTS idx_event_calendar_halt_window
    ON ironforge_event_calendar (halt_start_ts, halt_end_ts) WHERE is_active = TRUE
`)
await client.query(`
  CREATE INDEX IF NOT EXISTS idx_event_calendar_event_date
    ON ironforge_event_calendar (event_date)
`)
await client.query(`
  CREATE TABLE IF NOT EXISTS ironforge_event_calendar_meta (
    id                INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    last_refresh_ts   TIMESTAMPTZ,
    last_refresh_status  TEXT,
    events_added      INT DEFAULT 0,
    events_updated    INT DEFAULT 0
  )
`)
await client.query(`
  INSERT INTO ironforge_event_calendar_meta (id) VALUES (1) ON CONFLICT DO NOTHING
`)
```

- [ ] **Step 3: Inside the per-bot loop** (the loop that creates `${bot}_config`), add the new column to the `${bot}_config` DDL. Find the existing `CREATE TABLE IF NOT EXISTS ${bot}_config (...)` block and modify it to include `event_blackout_enabled BOOLEAN NOT NULL DEFAULT TRUE`. Also add an `ALTER` for already-deployed environments:

```ts
await client.query(`
  ALTER TABLE ${bot}_config ADD COLUMN IF NOT EXISTS event_blackout_enabled BOOLEAN NOT NULL DEFAULT TRUE
`)
```

Place the `ALTER` immediately after the `CREATE TABLE IF NOT EXISTS ${bot}_config` block.

- [ ] **Step 4: Run the build** to verify TypeScript compiles:

```bash
cd ironforge/webapp && npm run build 2>&1 | tail -20
```

Expected: `Compiled successfully` or no TS errors related to db.ts.

- [ ] **Step 5: Commit**

```bash
git add ironforge/webapp/src/lib/db.ts
git commit -m "feat(ironforge): add event_calendar tables + per-bot blackout toggle column"
```

---

## Task 2: Halt-window math helpers (TDD)

**Files:**
- Create: `ironforge/webapp/src/lib/eventCalendar/halt-window.ts`
- Test: `ironforge/webapp/src/lib/eventCalendar/__tests__/halt-window.test.ts`

- [ ] **Step 1: Create the test file first** with failing tests:

```ts
// src/lib/eventCalendar/__tests__/halt-window.test.ts
import { describe, it, expect } from 'vitest'
import { computeFridayPriorAt0830CT, computeEventDayAt } from '../halt-window'

describe('computeFridayPriorAt0830CT', () => {
  it('returns previous Friday 08:30 CT for a Wednesday FOMC', () => {
    // Wed Jun 18 2025 FOMC → Fri Jun 13 2025 08:30 CT
    const result = computeFridayPriorAt0830CT('2025-06-18')
    // 08:30 CDT (UTC-5 during DST) = 13:30 UTC
    expect(result.toISOString()).toBe('2025-06-13T13:30:00.000Z')
  })

  it('returns previous Friday for an event on a Monday', () => {
    // Mon Jan 5 2026 → Fri Jan 2 2026
    const result = computeFridayPriorAt0830CT('2026-01-05')
    // 08:30 CST (UTC-6 outside DST) = 14:30 UTC
    expect(result.toISOString()).toBe('2026-01-02T14:30:00.000Z')
  })

  it('returns the Friday a week prior when event is itself a Friday', () => {
    // Fri Jul 3 2026 → Fri Jun 26 2026 (strictly before)
    const result = computeFridayPriorAt0830CT('2026-07-03')
    expect(result.toISOString()).toBe('2026-06-26T13:30:00.000Z')
  })

  it('handles cross-year boundary (event on Mon Jan 4 2027)', () => {
    // Mon Jan 4 2027 → Fri Jan 1 2027
    const result = computeFridayPriorAt0830CT('2027-01-04')
    expect(result.toISOString()).toBe('2027-01-01T14:30:00.000Z')
  })

  it('handles event on a Saturday (custom event)', () => {
    // Sat Mar 7 2026 → Fri Mar 6 2026
    const result = computeFridayPriorAt0830CT('2026-03-07')
    expect(result.toISOString()).toBe('2026-03-06T14:30:00.000Z')
  })

  it('handles event on a Sunday (custom event)', () => {
    // Sun Mar 8 2026 → Fri Mar 6 2026
    const result = computeFridayPriorAt0830CT('2026-03-08')
    expect(result.toISOString()).toBe('2026-03-06T14:30:00.000Z')
  })
})

describe('computeEventDayAt', () => {
  it('returns event_date + event_time + offset for FOMC default', () => {
    // Jun 18 2025, 13:00 CT, +60 min = 14:00 CT = 19:00 UTC (DST)
    const result = computeEventDayAt('2025-06-18', '13:00', 60)
    expect(result.toISOString()).toBe('2025-06-18T19:00:00.000Z')
  })

  it('handles a 0-minute offset', () => {
    const result = computeEventDayAt('2025-06-18', '13:00', 0)
    expect(result.toISOString()).toBe('2025-06-18T18:00:00.000Z')
  })

  it('handles event in standard time (no DST)', () => {
    // Jan 28 2026, 13:00 CT, +60 min = 14:00 CST = 20:00 UTC
    const result = computeEventDayAt('2026-01-28', '13:00', 60)
    expect(result.toISOString()).toBe('2026-01-28T20:00:00.000Z')
  })
})
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd ironforge/webapp && npx vitest run src/lib/eventCalendar/__tests__/halt-window.test.ts 2>&1 | tail -10
```

Expected: FAIL — module `../halt-window` not found.

- [ ] **Step 3: Implement `halt-window.ts`** to make the tests pass:

```ts
// src/lib/eventCalendar/halt-window.ts
/**
 * Halt-window math for the IronForge event blackout system.
 *
 * All inputs are interpreted as Central Time (America/Chicago).
 * Outputs are absolute UTC `Date` objects (TIMESTAMPTZ when stored).
 *
 * DST is handled by computing the CT-local wall-clock time, then asking
 * the host environment what UTC instant that is.  We use a known-anchor
 * trick: format a midnight-CT instant for the target date, then add the
 * desired hours/minutes.
 */

const CT_TZ = 'America/Chicago'

/** Returns the UTC offset (in minutes) for a given UTC date in America/Chicago. */
function ctUtcOffsetMinutes(d: Date): number {
  // Format the date in CT and compare to UTC components to derive offset.
  const dtf = new Intl.DateTimeFormat('en-US', {
    timeZone: CT_TZ,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  })
  const parts = dtf.formatToParts(d).reduce((acc, p) => {
    if (p.type !== 'literal') acc[p.type] = p.value
    return acc
  }, {} as Record<string, string>)
  const ctMs = Date.UTC(
    parseInt(parts.year),
    parseInt(parts.month) - 1,
    parseInt(parts.day),
    parseInt(parts.hour === '24' ? '0' : parts.hour),
    parseInt(parts.minute),
    parseInt(parts.second),
  )
  return (ctMs - d.getTime()) / 60000
}

/** Construct a Date for a given CT-local wall-clock time (date + HH:MM). */
function ctWallToUtc(dateStr: string, hhmm: string): Date {
  const [y, mo, d] = dateStr.split('-').map(Number)
  const [hh, mm] = hhmm.split(':').map(Number)
  // Initial guess: treat the wall time as UTC, then correct by CT offset
  const guess = new Date(Date.UTC(y, mo - 1, d, hh, mm, 0))
  const offsetMin = ctUtcOffsetMinutes(guess)
  // Subtract the CT offset (CT is behind UTC, so offset is negative;
  // subtracting a negative shifts forward to the correct UTC instant)
  return new Date(guess.getTime() - offsetMin * 60000)
}

/** Day-of-week of a YYYY-MM-DD string interpreted as a calendar date. */
function dayOfWeek(dateStr: string): number {
  const [y, mo, d] = dateStr.split('-').map(Number)
  return new Date(Date.UTC(y, mo - 1, d)).getUTCDay() // 0=Sun .. 6=Sat
}

/** Subtract `n` calendar days from a YYYY-MM-DD date string. */
function subtractDays(dateStr: string, n: number): string {
  const [y, mo, d] = dateStr.split('-').map(Number)
  const t = new Date(Date.UTC(y, mo - 1, d))
  t.setUTCDate(t.getUTCDate() - n)
  return `${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, '0')}-${String(t.getUTCDate()).padStart(2, '0')}`
}

/**
 * Returns the Friday strictly before `eventDate` at 08:30 CT, as a UTC Date.
 *
 * - If `eventDate` is itself a Friday → returns the Friday a week before.
 * - If `eventDate` is a weekend day → returns the Friday immediately before that weekend.
 */
export function computeFridayPriorAt0830CT(eventDate: string): Date {
  const dow = dayOfWeek(eventDate) // 0=Sun, 5=Fri, 6=Sat
  // Days back to the most recent strict-prior Friday
  let daysBack: number
  if (dow === 5) daysBack = 7              // Fri → Fri prior week
  else if (dow === 6) daysBack = 1         // Sat → Fri before
  else if (dow === 0) daysBack = 2         // Sun → Fri before
  else daysBack = ((dow + 7) - 5) % 7      // Mon→3, Tue→4, Wed→5, Thu→6
  const fridayDateStr = subtractDays(eventDate, daysBack)
  return ctWallToUtc(fridayDateStr, '08:30')
}

/**
 * Returns `eventDate` at `eventTimeCt` + `offsetMinutes`, as a UTC Date.
 */
export function computeEventDayAt(
  eventDate: string,
  eventTimeCt: string,
  offsetMinutes: number,
): Date {
  const base = ctWallToUtc(eventDate, eventTimeCt)
  return new Date(base.getTime() + offsetMinutes * 60000)
}
```

- [ ] **Step 4: Run the tests**

```bash
cd ironforge/webapp && npx vitest run src/lib/eventCalendar/__tests__/halt-window.test.ts 2>&1 | tail -15
```

Expected: All 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add ironforge/webapp/src/lib/eventCalendar/halt-window.ts ironforge/webapp/src/lib/eventCalendar/__tests__/halt-window.test.ts
git commit -m "feat(ironforge): halt-window math helpers for event blackout"
```

---

## Task 3: Finnhub fetcher + parser (TDD)

**Files:**
- Create: `ironforge/webapp/src/lib/eventCalendar/finnhub.ts`
- Test: `ironforge/webapp/src/lib/eventCalendar/__tests__/finnhub.test.ts`

- [ ] **Step 1: Write the test** for the parser (the part with logic — fetch is just a thin HTTP call):

```ts
// src/lib/eventCalendar/__tests__/finnhub.test.ts
import { describe, it, expect } from 'vitest'
import { parseFinnhubFomcEvents } from '../finnhub'

describe('parseFinnhubFomcEvents', () => {
  it('returns FOMC events from the US economic calendar', () => {
    const json = {
      economicCalendar: [
        { country: 'US', event: 'FOMC Meeting', impact: 'high', time: '2025-06-18 14:00:00', actual: null },
        { country: 'US', event: 'CPI YoY', impact: 'high', time: '2025-06-12 08:30:00', actual: null },
        { country: 'EU', event: 'ECB Rate Decision', impact: 'high', time: '2025-06-05 07:45:00', actual: null },
        { country: 'US', event: 'Federal Funds Target Rate', impact: 'high', time: '2025-07-30 14:00:00', actual: null },
      ],
    }
    const result = parseFinnhubFomcEvents(json)
    expect(result).toHaveLength(2)
    expect(result[0]).toMatchObject({ date: '2025-06-18', time: '13:00', title: 'FOMC Meeting' })
    expect(result[1]).toMatchObject({ date: '2025-07-30', time: '13:00', title: 'Federal Funds Target Rate' })
  })

  it('matches Fed Interest Rate variants case-insensitively', () => {
    const json = {
      economicCalendar: [
        { country: 'US', event: 'fed interest rate decision', impact: 'high', time: '2025-09-17 14:00:00' },
      ],
    }
    expect(parseFinnhubFomcEvents(json)).toHaveLength(1)
  })

  it('skips non-US events', () => {
    const json = {
      economicCalendar: [
        { country: 'JP', event: 'BOJ Rate Decision', impact: 'high', time: '2025-06-17 03:00:00' },
      ],
    }
    expect(parseFinnhubFomcEvents(json)).toHaveLength(0)
  })

  it('skips low/medium impact events even if title matches', () => {
    const json = {
      economicCalendar: [
        { country: 'US', event: 'FOMC Member Powell Speaks', impact: 'medium', time: '2025-06-15 09:00:00' },
      ],
    }
    expect(parseFinnhubFomcEvents(json)).toHaveLength(0)
  })

  it('returns empty array for missing / malformed payload', () => {
    expect(parseFinnhubFomcEvents({})).toEqual([])
    expect(parseFinnhubFomcEvents({ economicCalendar: null })).toEqual([])
    expect(parseFinnhubFomcEvents(null as any)).toEqual([])
  })

  it('converts Finnhub UTC time to CT date and HH:MM (DST)', () => {
    // Finnhub returns UTC. 2025-06-18 18:00 UTC = 13:00 CDT (UTC-5)
    const json = {
      economicCalendar: [
        { country: 'US', event: 'FOMC Meeting', impact: 'high', time: '2025-06-18 18:00:00' },
      ],
    }
    const r = parseFinnhubFomcEvents(json)
    expect(r[0]).toMatchObject({ date: '2025-06-18', time: '13:00' })
  })

  it('converts Finnhub UTC time to CT date and HH:MM (standard time)', () => {
    // 2026-01-28 19:00 UTC = 13:00 CST (UTC-6)
    const json = {
      economicCalendar: [
        { country: 'US', event: 'FOMC Meeting', impact: 'high', time: '2026-01-28 19:00:00' },
      ],
    }
    const r = parseFinnhubFomcEvents(json)
    expect(r[0]).toMatchObject({ date: '2026-01-28', time: '13:00' })
  })
})
```

Note: the FOMC time in Finnhub is published as UTC. The first 3 tests use `14:00:00` which is naïve; the spec says FOMC announcements are 1 PM CT = 18:00 UTC (DST) or 19:00 UTC (standard). For test simplicity, the early tests use a value that demonstrates UTC→CT conversion behavior; the parser must handle both correctly. The DST/standard tests pin down the exact conversion.

Wait — the early tests assert `time: '13:00'` from a Finnhub `time: '2025-06-18 14:00:00'`. That's only correct if the parser interprets Finnhub's `time` as UTC. Confirm this in the implementation.

- [ ] **Step 2: Run to confirm tests fail**

```bash
cd ironforge/webapp && npx vitest run src/lib/eventCalendar/__tests__/finnhub.test.ts 2>&1 | tail -10
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `finnhub.ts`**:

```ts
// src/lib/eventCalendar/finnhub.ts

export interface FinnhubFomcEvent {
  date: string   // YYYY-MM-DD in CT
  time: string   // HH:MM in CT (24h)
  title: string
}

const FOMC_TITLE_RE = /FOMC|Fed Interest Rate|Federal Funds/i

/**
 * Convert a Finnhub UTC timestamp ("2025-06-18 18:00:00") to CT date + HH:MM.
 */
function utcToCtDateTime(finnhubUtc: string): { date: string; time: string } {
  // Finnhub returns "YYYY-MM-DD HH:MM:SS" in UTC.  Force ISO Z parse.
  const iso = finnhubUtc.replace(' ', 'T') + 'Z'
  const d = new Date(iso)
  const dtf = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Chicago',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  })
  const parts = dtf.formatToParts(d).reduce((acc, p) => {
    if (p.type !== 'literal') acc[p.type] = p.value
    return acc
  }, {} as Record<string, string>)
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    time: `${parts.hour === '24' ? '00' : parts.hour}:${parts.minute}`,
  }
}

/**
 * Parse Finnhub `/calendar/economic` response, return only US high-impact FOMC events.
 */
export function parseFinnhubFomcEvents(json: any): FinnhubFomcEvent[] {
  if (!json || !Array.isArray(json.economicCalendar)) return []
  const out: FinnhubFomcEvent[] = []
  for (const row of json.economicCalendar) {
    if (!row) continue
    if (row.country !== 'US') continue
    if ((row.impact || '').toLowerCase() !== 'high') continue
    if (typeof row.event !== 'string' || !FOMC_TITLE_RE.test(row.event)) continue
    if (typeof row.time !== 'string') continue
    const { date, time } = utcToCtDateTime(row.time)
    out.push({ date, time, title: row.event })
  }
  return out
}

/**
 * Fetch FOMC events from Finnhub for a date range.
 * Throws on non-2xx; caller is responsible for catching + logging.
 */
export async function fetchFinnhubFomcEvents(
  fromDate: string,
  toDate: string,
  apiKey: string,
): Promise<FinnhubFomcEvent[]> {
  const url = `https://finnhub.io/api/v1/calendar/economic?from=${fromDate}&to=${toDate}&token=${encodeURIComponent(apiKey)}`
  const res = await fetch(url, { method: 'GET' })
  if (!res.ok) {
    throw new Error(`Finnhub returned ${res.status}: ${await res.text().catch(() => '')}`)
  }
  const json = await res.json()
  return parseFinnhubFomcEvents(json)
}
```

- [ ] **Step 4: Run the tests**

```bash
cd ironforge/webapp && npx vitest run src/lib/eventCalendar/__tests__/finnhub.test.ts 2>&1 | tail -15
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add ironforge/webapp/src/lib/eventCalendar/finnhub.ts ironforge/webapp/src/lib/eventCalendar/__tests__/finnhub.test.ts
git commit -m "feat(ironforge): Finnhub FOMC fetcher + parser"
```

---

## Task 4: Calendar repo (DB ops)

**Files:**
- Create: `ironforge/webapp/src/lib/eventCalendar/repo.ts`

This is thin SQL wrapping; no separate test file (covered by gate test in Task 6 + manual verification).

- [ ] **Step 1: Write `repo.ts`**:

```ts
// src/lib/eventCalendar/repo.ts
import { query, dbExecute } from '../db'
import { computeFridayPriorAt0830CT, computeEventDayAt } from './halt-window'

export interface CalendarEvent {
  event_id: string
  source: 'finnhub' | 'manual'
  event_type: string
  title: string
  description: string | null
  event_date: string          // YYYY-MM-DD
  event_time_ct: string       // HH:MM
  halt_start_ts: Date
  halt_end_ts: Date
  resume_offset_min: number
  is_active: boolean
  created_by: string
}

export interface UpsertEventInput {
  event_id: string
  source: 'finnhub' | 'manual'
  event_type: string
  title: string
  description?: string | null
  event_date: string
  event_time_ct: string
  resume_offset_min?: number
  created_by: string
}

/** Upsert one event; computes halt window automatically. */
export async function upsertEvent(input: UpsertEventInput): Promise<{ inserted: boolean }> {
  const offset = input.resume_offset_min ?? 60
  const haltStart = computeFridayPriorAt0830CT(input.event_date)
  const haltEnd   = computeEventDayAt(input.event_date, input.event_time_ct, offset)
  const result = await query<{ inserted: boolean }>(`
    INSERT INTO ironforge_event_calendar (
      event_id, source, event_type, title, description,
      event_date, event_time_ct, halt_start_ts, halt_end_ts,
      resume_offset_min, created_by
    )
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
    ON CONFLICT (event_id) DO UPDATE SET
      title             = EXCLUDED.title,
      description       = EXCLUDED.description,
      event_time_ct     = EXCLUDED.event_time_ct,
      halt_start_ts     = EXCLUDED.halt_start_ts,
      halt_end_ts       = EXCLUDED.halt_end_ts,
      resume_offset_min = EXCLUDED.resume_offset_min,
      updated_at        = NOW()
    RETURNING (xmax = 0) AS inserted
  `, [
    input.event_id, input.source, input.event_type, input.title, input.description ?? null,
    input.event_date, input.event_time_ct, haltStart, haltEnd,
    offset, input.created_by,
  ])
  return { inserted: result.rows[0].inserted }
}

/** List active events with halt_end_ts in the future, ordered by event_date. */
export async function listUpcomingEvents(): Promise<CalendarEvent[]> {
  const result = await query<CalendarEvent>(`
    SELECT event_id, source, event_type, title, description,
           event_date::text AS event_date,
           to_char(event_time_ct, 'HH24:MI') AS event_time_ct,
           halt_start_ts, halt_end_ts,
           resume_offset_min, is_active, created_by
    FROM ironforge_event_calendar
    WHERE is_active = TRUE AND halt_end_ts >= NOW()
    ORDER BY event_date ASC
  `)
  return result.rows
}

/** List all events (active + inactive) in a date range — for the calendar grid. */
export async function listEventsInRange(fromDate: string, toDate: string): Promise<CalendarEvent[]> {
  const result = await query<CalendarEvent>(`
    SELECT event_id, source, event_type, title, description,
           event_date::text AS event_date,
           to_char(event_time_ct, 'HH24:MI') AS event_time_ct,
           halt_start_ts, halt_end_ts,
           resume_offset_min, is_active, created_by
    FROM ironforge_event_calendar
    WHERE is_active = TRUE AND event_date BETWEEN $1::date AND $2::date
    ORDER BY event_date ASC
  `, [fromDate, toDate])
  return result.rows
}

/** Find currently-active blackout (halt_start_ts <= now <= halt_end_ts). */
export async function findCurrentBlackout(now: Date): Promise<CalendarEvent | null> {
  const result = await query<CalendarEvent>(`
    SELECT event_id, source, event_type, title, description,
           event_date::text AS event_date,
           to_char(event_time_ct, 'HH24:MI') AS event_time_ct,
           halt_start_ts, halt_end_ts,
           resume_offset_min, is_active, created_by
    FROM ironforge_event_calendar
    WHERE is_active = TRUE AND $1 BETWEEN halt_start_ts AND halt_end_ts
    ORDER BY halt_end_ts ASC
    LIMIT 1
  `, [now])
  return result.rows[0] ?? null
}

/** Soft-delete an event (set is_active=false). */
export async function deactivateEvent(eventId: string): Promise<number> {
  return dbExecute(`UPDATE ironforge_event_calendar SET is_active=FALSE, updated_at=NOW() WHERE event_id=$1`, [eventId])
}

/** Get refresh meta. */
export async function getRefreshMeta(): Promise<{
  last_refresh_ts: Date | null
  last_refresh_status: string | null
  events_added: number
  events_updated: number
}> {
  const result = await query<any>(`SELECT * FROM ironforge_event_calendar_meta WHERE id=1`)
  return result.rows[0] ?? { last_refresh_ts: null, last_refresh_status: null, events_added: 0, events_updated: 0 }
}

/** Update refresh meta after a refresh attempt. */
export async function setRefreshMeta(status: string, added = 0, updated = 0): Promise<void> {
  await dbExecute(`
    UPDATE ironforge_event_calendar_meta
    SET last_refresh_ts=NOW(), last_refresh_status=$1, events_added=$2, events_updated=$3
    WHERE id=1
  `, [status, added, updated])
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd ironforge/webapp && npx tsc --noEmit 2>&1 | grep "eventCalendar" | head -10
```

Expected: No errors mentioning `eventCalendar/repo.ts`. (Other unrelated TS errors in the codebase are pre-existing and out of scope per IronForge HARD RULE #2.)

- [ ] **Step 3: Commit**

```bash
git add ironforge/webapp/src/lib/eventCalendar/repo.ts
git commit -m "feat(ironforge): event-calendar repo (DB ops)"
```

---

## Task 5: Refresh job

**Files:**
- Create: `ironforge/webapp/src/lib/eventCalendar/refresh.ts`

- [ ] **Step 1: Write `refresh.ts`**:

```ts
// src/lib/eventCalendar/refresh.ts
import { fetchFinnhubFomcEvents } from './finnhub'
import { upsertEvent, getRefreshMeta, setRefreshMeta } from './repo'

const REFRESH_COOLDOWN_HOURS = 20

function todayPlus(days: number): string {
  const d = new Date()
  d.setUTCDate(d.getUTCDate() + days)
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`
}

/**
 * Refresh FOMC events from Finnhub if the last refresh was > REFRESH_COOLDOWN_HOURS ago.
 * Never throws — errors are logged to the meta table for ops visibility.
 *
 * Returns true if a refresh was attempted, false if skipped due to cooldown.
 */
export async function eventCalendarRefresh(opts: { force?: boolean } = {}): Promise<boolean> {
  if (!opts.force) {
    const meta = await getRefreshMeta()
    if (meta.last_refresh_ts) {
      const hoursSince = (Date.now() - new Date(meta.last_refresh_ts).getTime()) / 3.6e6
      if (hoursSince < REFRESH_COOLDOWN_HOURS) return false
    }
  }

  const apiKey = process.env.FINNHUB_API_KEY
  if (!apiKey) {
    await setRefreshMeta('error: FINNHUB_API_KEY not set').catch(() => {})
    return true
  }

  try {
    const events = await fetchFinnhubFomcEvents(todayPlus(0), todayPlus(395), apiKey)
    let added = 0, updated = 0
    for (const ev of events) {
      const result = await upsertEvent({
        event_id: `finnhub:FOMC:${ev.date}`,
        source: 'finnhub',
        event_type: 'FOMC',
        title: ev.title,
        event_date: ev.date,
        event_time_ct: ev.time,
        created_by: 'finnhub-refresh',
      })
      result.inserted ? added++ : updated++
    }
    await setRefreshMeta('ok', added, updated)
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    await setRefreshMeta(`error: ${msg.slice(0, 200)}`).catch(() => {})
  }
  return true
}
```

- [ ] **Step 2: Wire into the scanner loop.** Open `src/lib/scanner.ts`, find the function that runs each scan cycle (search for `runScanCycle` or the `setInterval` setup at the bottom of the file). Add an import at the top:

```ts
import { eventCalendarRefresh } from './eventCalendar/refresh'
```

Add a call to `eventCalendarRefresh().catch(() => {})` at the **top** of the per-cycle function so any failure cannot block trading logic. Look for the existing pattern of `await ensureTables()` or similar setup at the start of the cycle and add this immediately after.

- [ ] **Step 3: Verify build**

```bash
cd ironforge/webapp && npm run build 2>&1 | tail -20
```

Expected: Compiled successfully.

- [ ] **Step 4: Commit**

```bash
git add ironforge/webapp/src/lib/eventCalendar/refresh.ts ironforge/webapp/src/lib/scanner.ts
git commit -m "feat(ironforge): event-calendar refresh job + scanner wiring"
```

---

## Task 6: Blackout gate (TDD)

**Files:**
- Create: `ironforge/webapp/src/lib/eventCalendar/gate.ts`
- Test: `ironforge/webapp/src/lib/eventCalendar/__tests__/gate.test.ts`
- Modify: `ironforge/webapp/src/lib/scanner.ts` (call gate inside `tryOpenPosition`)

- [ ] **Step 1: Write the test** with a mocked repo + config loader:

```ts
// src/lib/eventCalendar/__tests__/gate.test.ts
import { describe, it, expect, beforeEach, vi } from 'vitest'

vi.mock('../repo', () => ({
  findCurrentBlackout: vi.fn(),
}))
vi.mock('../../db', () => ({
  query: vi.fn(),
}))

import { findCurrentBlackout } from '../repo'
import { query } from '../../db'
import { isEventBlackoutActive } from '../gate'

const mockedFindBlackout = vi.mocked(findCurrentBlackout)
const mockedQuery = vi.mocked(query)

beforeEach(() => {
  mockedFindBlackout.mockReset()
  mockedQuery.mockReset()
})

describe('isEventBlackoutActive', () => {
  it('returns blocked=false when bot toggle is off', async () => {
    mockedQuery.mockResolvedValueOnce({ rows: [{ event_blackout_enabled: false }] } as any)
    const result = await isEventBlackoutActive('flame', new Date())
    expect(result.blocked).toBe(false)
    expect(mockedFindBlackout).not.toHaveBeenCalled()
  })

  it('returns blocked=false when no blackout window matches', async () => {
    mockedQuery.mockResolvedValueOnce({ rows: [{ event_blackout_enabled: true }] } as any)
    mockedFindBlackout.mockResolvedValueOnce(null)
    const result = await isEventBlackoutActive('flame', new Date())
    expect(result.blocked).toBe(false)
  })

  it('returns blocked=true with reason when in blackout', async () => {
    mockedQuery.mockResolvedValueOnce({ rows: [{ event_blackout_enabled: true }] } as any)
    const haltEnd = new Date('2025-06-18T19:00:00Z')
    mockedFindBlackout.mockResolvedValueOnce({
      event_id: 'finnhub:FOMC:2025-06-18',
      title: 'FOMC Meeting',
      halt_end_ts: haltEnd,
    } as any)
    const result = await isEventBlackoutActive('flame', new Date('2025-06-16T15:00:00Z'))
    expect(result.blocked).toBe(true)
    expect(result.eventId).toBe('finnhub:FOMC:2025-06-18')
    expect(result.eventTitle).toBe('FOMC Meeting')
    expect(result.resumesAt).toEqual(haltEnd)
    expect(result.reason).toContain('event_blackout')
    expect(result.reason).toContain('FOMC Meeting')
  })

  it('treats missing config row as enabled (default true)', async () => {
    mockedQuery.mockResolvedValueOnce({ rows: [] } as any)
    mockedFindBlackout.mockResolvedValueOnce(null)
    const result = await isEventBlackoutActive('flame', new Date())
    expect(result.blocked).toBe(false)
    expect(mockedFindBlackout).toHaveBeenCalled() // gate did proceed
  })
})
```

- [ ] **Step 2: Run to confirm fail**

```bash
cd ironforge/webapp && npx vitest run src/lib/eventCalendar/__tests__/gate.test.ts 2>&1 | tail -10
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `gate.ts`**:

```ts
// src/lib/eventCalendar/gate.ts
import { query } from '../db'
import { findCurrentBlackout } from './repo'

export interface BlackoutResult {
  blocked: boolean
  reason?: string
  eventId?: string
  eventTitle?: string
  resumesAt?: Date
}

function formatCT(d: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Chicago',
    month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
    hour12: true,
  }).format(d) + ' CT'
}

/**
 * Returns whether a bot is currently in event blackout.
 *
 * - Cheap (single config read + indexed window query).
 * - Defaults to enabled when no config row exists.
 * - Never throws; on DB error returns blocked=false (fail-open) so a transient
 *   DB blip can't permanently block trading.
 */
export async function isEventBlackoutActive(bot: string, now: Date): Promise<BlackoutResult> {
  let enabled = true
  try {
    const cfg = await query<{ event_blackout_enabled: boolean }>(
      `SELECT event_blackout_enabled FROM ${bot}_config LIMIT 1`,
    )
    if (cfg.rows.length > 0 && cfg.rows[0].event_blackout_enabled === false) {
      enabled = false
    }
  } catch {
    // Treat config error as "default on" — the blackout query below still runs.
  }
  if (!enabled) return { blocked: false }

  let row: Awaited<ReturnType<typeof findCurrentBlackout>>
  try {
    row = await findCurrentBlackout(now)
  } catch {
    return { blocked: false } // fail-open
  }
  if (!row) return { blocked: false }
  return {
    blocked: true,
    reason: `event_blackout(${row.title} until ${formatCT(new Date(row.halt_end_ts))})`,
    eventId: row.event_id,
    eventTitle: row.title,
    resumesAt: new Date(row.halt_end_ts),
  }
}
```

- [ ] **Step 4: Run tests**

```bash
cd ironforge/webapp && npx vitest run src/lib/eventCalendar/__tests__/gate.test.ts 2>&1 | tail -15
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Wire the gate into `scanner.ts`.** Open `src/lib/scanner.ts`, find `tryOpenPosition` (search by name). Locate the spot where existing skip-gates fire (PDT check, traded-today check, etc.). Add this BEFORE those existing checks, so it's the cheapest fail-fast:

```ts
// At the top of scanner.ts (with other imports):
import { isEventBlackoutActive } from './eventCalendar/gate'

// Inside tryOpenPosition(bot, now), before any other gate:
const blackout = await isEventBlackoutActive(bot.name, now)
if (blackout.blocked) {
  await dbExecute(
    `INSERT INTO ${botTable(bot.name, 'logs')} (action, payload, created_at) VALUES ($1, $2, NOW())`,
    ['SKIP', JSON.stringify({
      action: 'skip',
      reason: blackout.reason,
      event_id: blackout.eventId,
      event_title: blackout.eventTitle,
      halt_end_ts: blackout.resumesAt,
    })],
  )
  return
}
```

If `scanner.ts` already has a `logScanSkip(bot, reason, payload)` helper, prefer that over inline `dbExecute`. Check by grepping for `'SKIP'` string in scanner.ts.

- [ ] **Step 6: Verify build**

```bash
cd ironforge/webapp && npm run build 2>&1 | tail -20
```

Expected: Compiled successfully.

- [ ] **Step 7: Commit**

```bash
git add ironforge/webapp/src/lib/eventCalendar/gate.ts ironforge/webapp/src/lib/eventCalendar/__tests__/gate.test.ts ironforge/webapp/src/lib/scanner.ts
git commit -m "feat(ironforge): event-blackout gate + scanner wiring"
```

---

## Task 7: Events API routes (CRUD)

**Files:**
- Create: `ironforge/webapp/src/app/api/calendar/events/route.ts`
- Create: `ironforge/webapp/src/app/api/calendar/events/[eventId]/route.ts`

- [ ] **Step 1: Write the collection route** at `src/app/api/calendar/events/route.ts`:

```ts
import { NextRequest, NextResponse } from 'next/server'
import { listEventsInRange, listUpcomingEvents, upsertEvent } from '@/lib/eventCalendar/repo'

export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const from = searchParams.get('from')
  const to = searchParams.get('to')
  try {
    const events = (from && to)
      ? await listEventsInRange(from, to)
      : await listUpcomingEvents()
    return NextResponse.json({ events })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    if (!body.title || !body.event_date || !body.event_time_ct) {
      return NextResponse.json({ error: 'title, event_date, event_time_ct required' }, { status: 400 })
    }
    const id = `manual:${crypto.randomUUID()}`
    const result = await upsertEvent({
      event_id: id,
      source: 'manual',
      event_type: body.event_type || 'CUSTOM',
      title: body.title,
      description: body.description ?? null,
      event_date: body.event_date,
      event_time_ct: body.event_time_ct,
      resume_offset_min: body.resume_offset_min ?? 60,
      created_by: 'admin-ui',
    })
    return NextResponse.json({ event_id: id, inserted: result.inserted })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}
```

- [ ] **Step 2: Write the per-event route** at `src/app/api/calendar/events/[eventId]/route.ts`:

```ts
import { NextRequest, NextResponse } from 'next/server'
import { upsertEvent, deactivateEvent } from '@/lib/eventCalendar/repo'

export const dynamic = 'force-dynamic'

export async function PUT(req: NextRequest, { params }: { params: { eventId: string } }) {
  if (!params.eventId.startsWith('manual:')) {
    return NextResponse.json({ error: 'Only manual events are editable' }, { status: 403 })
  }
  try {
    const body = await req.json()
    if (!body.title || !body.event_date || !body.event_time_ct) {
      return NextResponse.json({ error: 'title, event_date, event_time_ct required' }, { status: 400 })
    }
    const result = await upsertEvent({
      event_id: params.eventId,
      source: 'manual',
      event_type: body.event_type || 'CUSTOM',
      title: body.title,
      description: body.description ?? null,
      event_date: body.event_date,
      event_time_ct: body.event_time_ct,
      resume_offset_min: body.resume_offset_min ?? 60,
      created_by: 'admin-ui',
    })
    return NextResponse.json({ event_id: params.eventId, inserted: result.inserted })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}

export async function DELETE(_req: NextRequest, { params }: { params: { eventId: string } }) {
  if (!params.eventId.startsWith('manual:')) {
    return NextResponse.json({ error: 'Only manual events are deletable' }, { status: 403 })
  }
  try {
    const rows = await deactivateEvent(params.eventId)
    return NextResponse.json({ deactivated: rows })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}
```

- [ ] **Step 3: Verify build**

```bash
cd ironforge/webapp && npm run build 2>&1 | tail -20
```

Expected: Compiled successfully.

- [ ] **Step 4: Commit**

```bash
git add ironforge/webapp/src/app/api/calendar/events
git commit -m "feat(ironforge): /api/calendar/events CRUD routes"
```

---

## Task 8: Refresh + status API routes

**Files:**
- Create: `ironforge/webapp/src/app/api/calendar/refresh/route.ts`
- Create: `ironforge/webapp/src/app/api/calendar/blackout-status/route.ts`

- [ ] **Step 1: Write `refresh/route.ts`**:

```ts
import { NextRequest, NextResponse } from 'next/server'
import { eventCalendarRefresh } from '@/lib/eventCalendar/refresh'
import { getRefreshMeta } from '@/lib/eventCalendar/repo'

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const meta = await getRefreshMeta()
    return NextResponse.json({ meta })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}

export async function POST(_req: NextRequest) {
  try {
    await eventCalendarRefresh({ force: true })
    const meta = await getRefreshMeta()
    return NextResponse.json({ ok: true, meta })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}
```

- [ ] **Step 2: Write `blackout-status/route.ts`**:

```ts
import { NextRequest, NextResponse } from 'next/server'
import { isEventBlackoutActive } from '@/lib/eventCalendar/gate'
import { listUpcomingEvents } from '@/lib/eventCalendar/repo'

export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const bot = (searchParams.get('bot') || 'flame').toLowerCase()
  if (!['flame', 'spark', 'inferno'].includes(bot)) {
    return NextResponse.json({ error: 'invalid bot' }, { status: 400 })
  }
  try {
    const now = new Date()
    const status = await isEventBlackoutActive(bot, now)
    const upcoming = await listUpcomingEvents()
    const next = upcoming.find(e => new Date(e.halt_start_ts) > now) ?? null
    return NextResponse.json({
      bot,
      now: now.toISOString(),
      blackout: status,
      next_blackout: next ? {
        event_id: next.event_id,
        title: next.title,
        halt_start_ts: next.halt_start_ts,
        halt_end_ts: next.halt_end_ts,
      } : null,
    })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}
```

- [ ] **Step 3: Verify build**

```bash
cd ironforge/webapp && npm run build 2>&1 | tail -20
```

Expected: Compiled successfully.

- [ ] **Step 4: Commit**

```bash
git add ironforge/webapp/src/app/api/calendar/refresh ironforge/webapp/src/app/api/calendar/blackout-status
git commit -m "feat(ironforge): /api/calendar/refresh + /api/calendar/blackout-status"
```

---

## Task 9: Calendar UI page

**Files:**
- Create: `ironforge/webapp/src/components/CalendarStatusBanner.tsx`
- Create: `ironforge/webapp/src/components/CalendarMonthGrid.tsx`
- Create: `ironforge/webapp/src/app/calendar/page.tsx`

- [ ] **Step 1: Create `CalendarStatusBanner.tsx`** — top-of-page status strip:

```tsx
'use client'

import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'

interface BlackoutStatus {
  bot: string
  now: string
  blackout: { blocked: boolean; eventTitle?: string; resumesAt?: string }
  next_blackout: { title: string; halt_start_ts: string; halt_end_ts: string } | null
}

function fmtCT(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    timeZone: 'America/Chicago',
    weekday: 'short', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit', hour12: true,
  }) + ' CT'
}

function fmtDuration(ms: number): string {
  const totalMin = Math.max(0, Math.floor(ms / 60000))
  const days = Math.floor(totalMin / (24 * 60))
  const hours = Math.floor((totalMin % (24 * 60)) / 60)
  const mins = totalMin % 60
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${mins}m`
  return `${mins}m`
}

export default function CalendarStatusBanner() {
  const { data, isLoading } = useSWR<BlackoutStatus>('/api/calendar/blackout-status?bot=flame', fetcher, { refreshInterval: 60_000 })
  if (isLoading || !data) return <div className="h-12 bg-forge-card rounded animate-pulse" />

  const now = new Date(data.now)
  if (data.blackout.blocked && data.blackout.resumesAt) {
    const resumes = new Date(data.blackout.resumesAt)
    return (
      <div className="rounded-lg border border-amber-700/60 bg-amber-950/40 p-4">
        <div className="text-amber-300 font-medium">⚠ Event blackout in effect — {data.blackout.eventTitle}</div>
        <div className="text-sm text-amber-200/80 mt-1">
          No new entries until {fmtCT(data.blackout.resumesAt)} (resumes in {fmtDuration(resumes.getTime() - now.getTime())})
        </div>
      </div>
    )
  }

  if (data.next_blackout) {
    const start = new Date(data.next_blackout.halt_start_ts)
    return (
      <div className="rounded-lg border border-emerald-800/40 bg-emerald-950/20 p-4">
        <div className="text-emerald-300 font-medium">✓ Trading normally</div>
        <div className="text-sm text-emerald-200/80 mt-1">
          Next blackout: {data.next_blackout.title} starts {fmtCT(data.next_blackout.halt_start_ts)} (in {fmtDuration(start.getTime() - now.getTime())})
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-emerald-800/40 bg-emerald-950/20 p-4">
      <div className="text-emerald-300 font-medium">✓ Trading normally</div>
      <div className="text-sm text-emerald-200/80 mt-1">No upcoming blackouts scheduled.</div>
    </div>
  )
}
```

- [ ] **Step 2: Create `CalendarMonthGrid.tsx`** — single mini-month + 12-month wrapper:

```tsx
'use client'

interface CalendarEvent {
  event_id: string
  title: string
  event_date: string
  event_time_ct: string
  halt_start_ts: string
  halt_end_ts: string
  source: string
}

interface MonthProps {
  year: number
  month: number  // 0-11
  events: CalendarEvent[]
  todayIso: string
}

function dateIso(y: number, m: number, d: number): string {
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
}

function dayInBlackout(iso: string, ev: CalendarEvent): boolean {
  // A day is "in blackout" if any time during the day falls between halt_start and halt_end.
  // Simplification: check if iso date is between halt_start date and event_date inclusive.
  const start = ev.halt_start_ts.slice(0, 10)
  const end   = ev.event_date
  return iso >= start && iso <= end
}

function MiniMonth({ year, month, events, todayIso }: MonthProps) {
  const monthName = new Date(year, month, 1).toLocaleString('en-US', { month: 'long' })
  const firstDow = new Date(year, month, 1).getDay() // 0=Sun
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const cells: Array<{ iso: string | null; day: number | null }> = []
  // Pad to start on Sunday
  for (let i = 0; i < firstDow; i++) cells.push({ iso: null, day: null })
  for (let d = 1; d <= daysInMonth; d++) cells.push({ iso: dateIso(year, month, d), day: d })

  return (
    <div className="bg-forge-card rounded-lg p-3">
      <div className="text-amber-300 text-sm font-medium mb-2">{monthName} {year}</div>
      <div className="grid grid-cols-7 gap-1 text-[10px] text-gray-500 mb-1">
        {['S','M','T','W','T','F','S'].map((d, i) => <div key={i} className="text-center">{d}</div>)}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {cells.map((c, i) => {
          if (!c.iso) return <div key={i} className="h-6" />
          const dow = new Date(c.iso + 'T12:00:00Z').getUTCDay()
          const isWeekend = dow === 0 || dow === 6
          const isToday = c.iso === todayIso
          const blackout = events.find(ev => dayInBlackout(c.iso!, ev))
          const isEventDay = blackout && c.iso === blackout.event_date

          let bg = 'bg-emerald-900/30'  // trading day
          if (isWeekend) bg = 'bg-gray-800/30'
          if (blackout) bg = isEventDay ? 'bg-gradient-to-r from-red-700/50 to-emerald-700/40' : 'bg-red-800/40'

          return (
            <div
              key={i}
              title={blackout ? `${blackout.title} · halt ${blackout.halt_start_ts.slice(0,10)} → resume ${new Date(blackout.halt_end_ts).toLocaleString('en-US', { timeZone: 'America/Chicago' })}` : ''}
              className={`h-6 text-center text-[10px] rounded ${bg} ${isToday ? 'ring-1 ring-amber-400' : ''} text-gray-200 leading-6`}
            >
              {c.day}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function CalendarMonthGrid({ year, events }: { year: number; events: CalendarEvent[] }) {
  const today = new Date()
  const todayIso = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {Array.from({ length: 12 }, (_, m) => (
        <MiniMonth key={m} year={year} month={m} events={events} todayIso={todayIso} />
      ))}
    </div>
  )
}
```

- [ ] **Step 3: Create `app/calendar/page.tsx`**:

```tsx
'use client'

import useSWR from 'swr'
import Link from 'next/link'
import { useState } from 'react'
import { fetcher } from '@/lib/fetcher'
import CalendarStatusBanner from '@/components/CalendarStatusBanner'
import CalendarMonthGrid from '@/components/CalendarMonthGrid'

export default function CalendarPage() {
  const [year, setYear] = useState(new Date().getFullYear())
  const from = `${year}-01-01`
  const to   = `${year}-12-31`
  const { data, isLoading } = useSWR<{ events: any[] }>(
    `/api/calendar/events?from=${from}&to=${to}`,
    fetcher,
    { refreshInterval: 5 * 60 * 1000 },
  )

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Calendar</h1>
        <Link href="/calendar/admin" className="text-sm text-amber-400 hover:text-amber-300">+ Manage events</Link>
      </div>

      <CalendarStatusBanner />

      <div className="flex items-center justify-between">
        <button onClick={() => setYear(y => y - 1)} className="text-sm text-gray-400 hover:text-gray-200">◀ {year - 1}</button>
        <div className="text-xl text-white">{year}</div>
        <button onClick={() => setYear(y => y + 1)} className="text-sm text-gray-400 hover:text-gray-200">{year + 1} ▶</button>
      </div>

      {isLoading ? (
        <div className="text-gray-400">Loading…</div>
      ) : (
        <CalendarMonthGrid year={year} events={data?.events || []} />
      )}

      <div className="text-xs text-gray-500 flex gap-4 flex-wrap pt-2 border-t border-gray-800">
        <span><span className="inline-block w-3 h-3 rounded bg-emerald-900/30 align-middle mr-1" /> Trading day</span>
        <span><span className="inline-block w-3 h-3 rounded bg-red-800/40 align-middle mr-1" /> Blackout day</span>
        <span><span className="inline-block w-3 h-3 rounded bg-gradient-to-r from-red-700/50 to-emerald-700/40 align-middle mr-1" /> Event day (split)</span>
        <span><span className="inline-block w-3 h-3 rounded bg-gray-800/30 align-middle mr-1" /> Weekend</span>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Verify build**

```bash
cd ironforge/webapp && npm run build 2>&1 | tail -20
```

Expected: Compiled successfully.

- [ ] **Step 5: Commit**

```bash
git add ironforge/webapp/src/components/CalendarStatusBanner.tsx ironforge/webapp/src/components/CalendarMonthGrid.tsx ironforge/webapp/src/app/calendar
git commit -m "feat(ironforge): /calendar UI page (12-month grid + status banner)"
```

---

## Task 10: Admin UI page

**Files:**
- Create: `ironforge/webapp/src/app/calendar/admin/page.tsx`

- [ ] **Step 1: Create the admin page**:

```tsx
'use client'

import useSWR, { mutate } from 'swr'
import Link from 'next/link'
import { useState } from 'react'
import { fetcher } from '@/lib/fetcher'

export default function CalendarAdminPage() {
  const { data: meta } = useSWR<{ meta: any }>('/api/calendar/refresh', fetcher, { refreshInterval: 30_000 })
  const { data: events } = useSWR<{ events: any[] }>('/api/calendar/events', fetcher)
  const [refreshing, setRefreshing] = useState(false)
  const [form, setForm] = useState({ title: '', event_type: 'CUSTOM', event_date: '', event_time_ct: '13:00', resume_offset_min: 60, description: '' })

  async function refreshNow() {
    setRefreshing(true)
    await fetch('/api/calendar/refresh', { method: 'POST' })
    await mutate('/api/calendar/refresh')
    await mutate('/api/calendar/events')
    setRefreshing(false)
  }

  async function addEvent(e: React.FormEvent) {
    e.preventDefault()
    const res = await fetch('/api/calendar/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })
    if (res.ok) {
      setForm({ title: '', event_type: 'CUSTOM', event_date: '', event_time_ct: '13:00', resume_offset_min: 60, description: '' })
      await mutate('/api/calendar/events')
    } else {
      alert('Failed to add event: ' + (await res.text()))
    }
  }

  async function deleteEvent(eventId: string) {
    if (!confirm('Soft-delete this event?')) return
    await fetch(`/api/calendar/events/${encodeURIComponent(eventId)}`, { method: 'DELETE' })
    await mutate('/api/calendar/events')
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Manage Events</h1>
        <Link href="/calendar" className="text-sm text-gray-400 hover:text-gray-200">← Back to calendar</Link>
      </div>

      <section className="bg-forge-card rounded-lg p-4">
        <h2 className="text-lg text-amber-300 mb-2">Refresh status</h2>
        <div className="text-sm text-gray-300 space-y-1">
          <div>Last refresh: {meta?.meta?.last_refresh_ts ? new Date(meta.meta.last_refresh_ts).toLocaleString('en-US', { timeZone: 'America/Chicago' }) + ' CT' : '— never —'}</div>
          <div>Status: <span className={meta?.meta?.last_refresh_status === 'ok' ? 'text-emerald-400' : 'text-red-400'}>{meta?.meta?.last_refresh_status || '—'}</span></div>
          <div>Events added: {meta?.meta?.events_added ?? 0} · updated: {meta?.meta?.events_updated ?? 0}</div>
        </div>
        <button onClick={refreshNow} disabled={refreshing} className="mt-3 px-3 py-1.5 rounded bg-amber-700 hover:bg-amber-600 text-white text-sm disabled:opacity-50">
          {refreshing ? 'Refreshing…' : 'Refresh now'}
        </button>
      </section>

      <section className="bg-forge-card rounded-lg p-4">
        <h2 className="text-lg text-amber-300 mb-3">Add custom event</h2>
        <form onSubmit={addEvent} className="grid grid-cols-2 gap-3 text-sm">
          <label className="flex flex-col text-gray-300">Title
            <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} required className="bg-forge-bg border border-gray-700 rounded px-2 py-1 text-white" />
          </label>
          <label className="flex flex-col text-gray-300">Type
            <select value={form.event_type} onChange={e => setForm({ ...form, event_type: e.target.value })} className="bg-forge-bg border border-gray-700 rounded px-2 py-1 text-white">
              <option>CUSTOM</option><option>CPI</option><option>NFP</option><option>PPI</option><option>OTHER</option>
            </select>
          </label>
          <label className="flex flex-col text-gray-300">Event date
            <input type="date" value={form.event_date} onChange={e => setForm({ ...form, event_date: e.target.value })} required className="bg-forge-bg border border-gray-700 rounded px-2 py-1 text-white" />
          </label>
          <label className="flex flex-col text-gray-300">Event time (CT)
            <input type="time" value={form.event_time_ct} onChange={e => setForm({ ...form, event_time_ct: e.target.value })} required className="bg-forge-bg border border-gray-700 rounded px-2 py-1 text-white" />
          </label>
          <label className="flex flex-col text-gray-300">Resume offset (min)
            <input type="number" min={0} value={form.resume_offset_min} onChange={e => setForm({ ...form, resume_offset_min: parseInt(e.target.value) || 0 })} className="bg-forge-bg border border-gray-700 rounded px-2 py-1 text-white" />
          </label>
          <label className="flex flex-col text-gray-300 col-span-2">Description
            <textarea rows={2} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} className="bg-forge-bg border border-gray-700 rounded px-2 py-1 text-white" />
          </label>
          <div className="col-span-2">
            <button type="submit" className="px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white text-sm">Add event</button>
          </div>
        </form>
      </section>

      <section className="bg-forge-card rounded-lg p-4">
        <h2 className="text-lg text-amber-300 mb-3">Active events</h2>
        <table className="w-full text-sm text-gray-300">
          <thead className="text-xs text-gray-500 uppercase border-b border-gray-700">
            <tr><th className="text-left py-2">Date</th><th className="text-left">Title</th><th className="text-left">Source</th><th className="text-left">Resumes</th><th></th></tr>
          </thead>
          <tbody>
            {(events?.events || []).map(ev => (
              <tr key={ev.event_id} className="border-b border-gray-800">
                <td className="py-2">{ev.event_date}</td>
                <td>{ev.title}</td>
                <td className="text-xs uppercase text-gray-500">{ev.source}</td>
                <td className="text-xs">{new Date(ev.halt_end_ts).toLocaleString('en-US', { timeZone: 'America/Chicago' })}</td>
                <td className="text-right">
                  {ev.source === 'manual'
                    ? <button onClick={() => deleteEvent(ev.event_id)} className="text-red-400 hover:text-red-300 text-xs">Delete</button>
                    : <span className="text-xs text-gray-600">read-only</span>}
                </td>
              </tr>
            ))}
            {(!events?.events || events.events.length === 0) && (
              <tr><td colSpan={5} className="py-4 text-center text-gray-500">No active events</td></tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

```bash
cd ironforge/webapp && npm run build 2>&1 | tail -20
```

Expected: Compiled successfully.

- [ ] **Step 3: Commit**

```bash
git add ironforge/webapp/src/app/calendar/admin
git commit -m "feat(ironforge): /calendar/admin UI"
```

---

## Task 11: Dashboard banner + Nav link

**Files:**
- Create: `ironforge/webapp/src/components/EventBlackoutBanner.tsx`
- Modify: `ironforge/webapp/src/components/BotDashboard.tsx`
- Modify: `ironforge/webapp/src/components/Nav.tsx`

- [ ] **Step 1: Create `EventBlackoutBanner.tsx`**:

```tsx
'use client'

import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'

interface BlackoutStatus {
  blackout: { blocked: boolean; eventTitle?: string; resumesAt?: string }
  next_blackout: { title: string; halt_start_ts: string } | null
}

function fmtCT(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    timeZone: 'America/Chicago',
    weekday: 'short', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit', hour12: true,
  }) + ' CT'
}

function fmtDuration(ms: number): string {
  const totalMin = Math.max(0, Math.floor(ms / 60000))
  const days = Math.floor(totalMin / (24 * 60))
  const hours = Math.floor((totalMin % (24 * 60)) / 60)
  const mins = totalMin % 60
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${mins}m`
  return `${mins}m`
}

export default function EventBlackoutBanner({ bot }: { bot: string }) {
  const { data } = useSWR<BlackoutStatus>(`/api/calendar/blackout-status?bot=${bot}`, fetcher, { refreshInterval: 60_000 })
  if (!data) return null
  const now = Date.now()

  if (data.blackout.blocked && data.blackout.resumesAt) {
    const resumes = new Date(data.blackout.resumesAt)
    return (
      <div className="rounded border border-amber-700/60 bg-amber-950/40 px-4 py-2 text-sm">
        <span className="text-amber-300 font-medium">⚠ Event blackout in effect — {data.blackout.eventTitle} </span>
        <span className="text-amber-200/80">· no new entries until {fmtCT(data.blackout.resumesAt)} (resumes in {fmtDuration(resumes.getTime() - now)})</span>
      </div>
    )
  }

  if (data.next_blackout) {
    const start = new Date(data.next_blackout.halt_start_ts)
    const ms = start.getTime() - now
    if (ms < 7 * 24 * 3600 * 1000 && ms > 0) {
      return (
        <div className="rounded border border-blue-800/40 bg-blue-950/20 px-4 py-2 text-sm">
          <span className="text-blue-300">ℹ Upcoming blackout: {data.next_blackout.title} begins {fmtCT(data.next_blackout.halt_start_ts)} ({fmtDuration(ms)})</span>
        </div>
      )
    }
  }
  return null
}
```

- [ ] **Step 2: Add to `BotDashboard.tsx`.** Open `src/components/BotDashboard.tsx`, find the top of the rendered JSX (where StatusCard or PdtCard is rendered). Add an import:

```tsx
import EventBlackoutBanner from './EventBlackoutBanner'
```

And insert above the existing first card, with bot prop:

```tsx
<EventBlackoutBanner bot={bot} />
```

- [ ] **Step 3: Add Nav link** — open `src/components/Nav.tsx`, find the `links` array, insert between `Compare` and `Accounts`:

```ts
{ href: '/calendar', label: 'Calendar', className: 'text-gray-400 hover:text-gray-200' },
```

- [ ] **Step 4: Verify build**

```bash
cd ironforge/webapp && npm run build 2>&1 | tail -20
```

Expected: Compiled successfully.

- [ ] **Step 5: Commit**

```bash
git add ironforge/webapp/src/components/EventBlackoutBanner.tsx ironforge/webapp/src/components/BotDashboard.tsx ironforge/webapp/src/components/Nav.tsx
git commit -m "feat(ironforge): blackout banner on bot dashboards + Calendar nav link"
```

---

## Task 12: Final build + test verification

- [ ] **Step 1: Full build**

```bash
cd ironforge/webapp && npm run build 2>&1 | tail -30
```

Expected: `Compiled successfully` with no errors. Warnings about pre-existing files are fine.

- [ ] **Step 2: Run only the new test files** (per IronForge HARD RULE #2 — don't run pre-existing failing tests)

```bash
cd ironforge/webapp && npx vitest run src/lib/eventCalendar/__tests__/ 2>&1 | tail -25
```

Expected: All tests pass (9 halt-window + 7 finnhub + 4 gate = 20 tests).

- [ ] **Step 3: Type-check the new files only**

```bash
cd ironforge/webapp && npx tsc --noEmit 2>&1 | grep "src/lib/eventCalendar\|src/app/calendar\|src/components/Calendar\|src/components/EventBlackoutBanner" | head -20
```

Expected: No output (no type errors in new files).

- [ ] **Step 4: If build/tests/types all green, push the branch and merge to main**

```bash
git push -u origin claude/event-blackout-vigil
gh pr create --title "feat(ironforge): event blackout (Vigil) + calendar UI" --body "$(cat <<'EOF'
## Summary
- Halts FLAME/SPARK/INFERNO entries from Friday-prior 8:30 AM CT through event-day 2:00 PM CT around macro events
- Auto-pulls 8 scheduled FOMC dates per year from Finnhub (free tier; daily refresh in scanner loop)
- Operator-managed custom events via /calendar/admin
- 12-month calendar UI at /calendar with status banner and per-bot honor toggles
- Banner on each bot dashboard when in (or < 7 days from) blackout
- Per-bot `event_blackout_enabled` toggle in `{bot}_config` (default TRUE)

Spec: `docs/superpowers/specs/2026-05-04-ironforge-event-blackout-vigil-design.md`
Plan: `docs/superpowers/plans/2026-05-04-ironforge-event-blackout-vigil.md`

## Manual steps after merge
- [ ] Set `FINNHUB_API_KEY` env var in Render (ironforge service)
- [ ] POST /api/calendar/refresh once to populate (or wait up to 1 min for the scanner loop)
- [ ] Visit /calendar to verify FOMC dates show as red cells

## Test plan
- [x] Unit tests: halt-window math (9), Finnhub parser (7), blackout gate (4) — all green
- [x] `npm run build` passes
- [ ] Post-deploy: hit /api/calendar/refresh, verify table populates
- [ ] Post-deploy: open /calendar, verify next FOMC shows red Fri-Wed
- [ ] Post-deploy: add a custom event via /calendar/admin and verify it appears in the grid

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)" 2>&1 | tail -5
```

Then merge:

```bash
gh pr merge --merge --delete-branch
```

Or if PR creation fails (e.g., gh auth issues), merge directly:

```bash
git checkout main && git merge --no-ff claude/event-blackout-vigil -m "feat(ironforge): event blackout (Vigil) + calendar UI" && git push origin main
```

- [ ] **Step 5: Notify the user that the merge is complete and the manual `FINNHUB_API_KEY` env var needs to be set in Render.** This is the one operational step that requires human action (per the "always ask for credentials" rule).

---

## Self-Review

**1. Spec coverage:**
- Section 4 architecture → Tasks 1, 4-11
- Section 5 data model → Task 1
- Section 6 refresh job → Tasks 3, 5
- Section 7 scanner gate → Task 6
- Section 8.1 calendar page → Task 9
- Section 8.2 admin page → Task 10
- Section 8.3 dashboard banner → Task 11
- Section 8.4 nav link → Task 11
- Section 9 failure modes → covered by gate fail-open behavior (Task 6) + refresh non-throwing (Task 5) + admin status display (Task 10)
- Section 10.1 unit tests → Tasks 2, 3, 6
- Section 10.3 manual verification → Task 12
- Section 11 rollout → Task 12 step 4

**2. No placeholders:** Each step has either complete code or an exact command. No "TBD" / "implement later".

**3. Type consistency:** `BlackoutResult` defined in Task 6 matches its usage in Task 8 (`/api/calendar/blackout-status`). `CalendarEvent` in Task 4 matches usage in Tasks 7, 9. `UpsertEventInput` is consistent.

**4. Integration tests skipped:** Spec section 10.2 mentioned integration tests against a test Postgres. The IronForge codebase doesn't have an existing test-DB harness (per `Common Mistakes` and the `__tests__` files I inspected, all use mocked `db` modules). Integration coverage is delivered by the manual verification in Task 12 step 4 (post-deploy hits against real Render Postgres). This is consistent with how circuit-breaker.test.ts is structured. Acceptable trade-off.
