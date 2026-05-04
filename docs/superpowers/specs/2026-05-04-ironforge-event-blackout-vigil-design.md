# IronForge Event Blackout (Vigil) — Design

**Date:** 2026-05-04
**Author:** Claude (brainstormed with Optionist Prime)
**Status:** Approved — proceeding to implementation plan
**Scope:** `ironforge/webapp/` (FLAME / SPARK / INFERNO bots)

---

## 1. Problem & Goal

The IronForge bots (FLAME 2DTE, SPARK 1DTE, INFERNO 0DTE) currently trade through high-impact macro events such as FOMC rate decisions. These events routinely produce ±2σ SPY moves, which is fatal for the short-vol Iron Condor strategies all three bots run.

**Goal:** halt all new IronForge entries from the Friday before each FOMC meeting through the day of the announcement (resume same day at 2:00 PM CT, after Powell's press conference). Provide an auto-updating year-view calendar so the schedule is fully transparent.

## 2. Scope

**In scope (v1):**
- Auto-pull the 8 scheduled FOMC meetings per year from Finnhub's economic calendar
- Allow the operator to add/edit/delete custom one-off blackout events (CPI prints, election day, geopolitical risk)
- Per-bot opt-out toggle (default: on for all three bots)
- Year-view calendar UI with per-bot status dots
- Admin UI for managing custom events and seeing refresh status
- Banner on each bot dashboard when in (or about to enter) blackout

**Out of scope (v1):**
- Auto-pulling CPI / NFP / PPI / other event types (Finnhub supports it; ship FOMC first)
- Automatic close of existing positions when blackout starts (existing exit logic handles it)
- Per-event resume-time customization beyond a configurable `resume_offset_minutes` field
- Alerting / Discord notifications when blackout begins (can be added later by reusing `lib/discord.ts`)

## 3. Non-Goals

- Not a directional trade engine — only a halt switch
- Not a position-management change — open positions exit through normal PT / SL / EOD logic
- Not a rebuild of the existing PDT calendar (`PdtCalendar.tsx` stays as-is)

## 4. Architecture

All work lives inside `ironforge/webapp/`. No new Render services, no Python.

| Component | File | Purpose |
|---|---|---|
| Events table | `ironforge_event_calendar` (Postgres) | Stores FOMC + manual events with halt timestamps |
| Refresh meta | `ironforge_event_calendar_meta` (Postgres) | Single-row tracker for last-refresh status |
| Per-bot toggle | `event_blackout_enabled` column on `{bot}_config` | Default `TRUE` |
| Finnhub helpers | `lib/finnhubCalendar.ts` (new) | Fetch + parse + upsert |
| Refresh job | `eventCalendarRefresh()` in `lib/scanner.ts` | Once-per-day, called from existing scan loop |
| Gate helper | `isEventBlackoutActive(bot, now)` (new) | Returns `{blocked, reason, eventId, eventTitle, resumesAt}` |
| Gate call | Inside `tryOpenPosition()` in `lib/scanner.ts` | Fail-fast before PDT/BP gates; emits `skip_reason: 'event_blackout(...)'` |
| Calendar UI | `app/calendar/page.tsx` (new) | 12-month grid + 30-day strip + status banner |
| Admin UI | `app/calendar/admin/page.tsx` (new) | Add/edit/delete custom events, manual refresh, refresh history |
| Events API | `app/api/calendar/events/route.ts` (new) | GET / POST / PUT / DELETE |
| Refresh API | `app/api/calendar/refresh/route.ts` (new) | POST manual trigger |
| Status API | `app/api/calendar/blackout-status/route.ts` (new) | Read-only "are we in blackout right now?" |
| Nav link | `components/Nav.tsx` | Insert `Calendar` between `Compare` and `Accounts` |
| Dashboard banner | `components/BotDashboard.tsx` | Yellow strip when in blackout, info strip when blackout < 7 days away |

**Env var added:** `FINNHUB_API_KEY` in Render service config (one-time manual step).

## 5. Data Model

### 5.1 `ironforge_event_calendar`

```sql
CREATE TABLE IF NOT EXISTS ironforge_event_calendar (
  event_id          TEXT PRIMARY KEY,
  source            TEXT NOT NULL,           -- 'finnhub' | 'manual'
  event_type        TEXT NOT NULL,           -- 'FOMC' | 'CUSTOM' | 'CPI' | 'NFP' | 'PPI' | 'OTHER'
  title             TEXT NOT NULL,
  description       TEXT,
  event_date        DATE NOT NULL,
  event_time_ct     TIME NOT NULL,           -- 13:00 default for FOMC
  halt_start_ts     TIMESTAMPTZ NOT NULL,    -- Fri-prior 08:30 CT
  halt_end_ts       TIMESTAMPTZ NOT NULL,    -- event_date event_time_ct + resume_offset
  resume_offset_min INT NOT NULL DEFAULT 60, -- minutes after event_time to resume
  is_active         BOOLEAN NOT NULL DEFAULT TRUE,
  created_by        TEXT NOT NULL,           -- 'finnhub-refresh' | 'admin-ui'
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_event_calendar_halt_window
  ON ironforge_event_calendar (halt_start_ts, halt_end_ts) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_event_calendar_event_date
  ON ironforge_event_calendar (event_date);
```

### 5.2 `ironforge_event_calendar_meta`

```sql
CREATE TABLE IF NOT EXISTS ironforge_event_calendar_meta (
  id                INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  last_refresh_ts   TIMESTAMPTZ,
  last_refresh_status  TEXT,
  events_added      INT DEFAULT 0,
  events_updated    INT DEFAULT 0
);
INSERT INTO ironforge_event_calendar_meta (id) VALUES (1) ON CONFLICT DO NOTHING;
```

### 5.3 Per-bot toggle

```sql
ALTER TABLE flame_config   ADD COLUMN IF NOT EXISTS event_blackout_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE spark_config   ADD COLUMN IF NOT EXISTS event_blackout_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE inferno_config ADD COLUMN IF NOT EXISTS event_blackout_enabled BOOLEAN NOT NULL DEFAULT TRUE;
```

### 5.4 Audit trail

Reuses existing `{bot}_logs`. Each blocked scan emits:
```
action='SKIP', payload={ reason: 'event_blackout', event_id, event_title, halt_end_ts }
```

### 5.5 Halt-window math (precomputed at insert)

- `halt_start_ts` = the Friday **strictly before** `event_date` at 08:30 CT.
  - If `event_date` is itself a Friday (rare for FOMC; possible for custom events), `halt_start_ts` is the *previous* Friday — never the same day. This matches the user's intent of "stop trading the Friday before the event".
  - If `event_date` is a Saturday or Sunday (custom events only), `halt_start_ts` is the Friday immediately before that weekend (i.e., the Friday `event_date - 1d` or `event_date - 2d`).
- `halt_end_ts` = `event_date` at `event_time_ct` + `resume_offset_min`
- Default for FOMC: event 13:00 CT + 60 min → resume 14:00 CT
- All timestamps stored as `TIMESTAMPTZ` (absolute UTC); CT formatting at display layer only — handles DST automatically

### 5.6 Idempotent IDs

- Finnhub events: `'finnhub:FOMC:<YYYY-MM-DD>'` — re-fetching always upserts the same row
- Manual events: `'manual:<uuid>'`

### 5.7 Soft delete

"Delete" in admin UI sets `is_active=false`. Preserves audit trail. Calendar UI hides inactive events; gate ignores them.

## 6. Refresh Job

Function `eventCalendarRefresh()` added to `lib/scanner.ts`. Called at the **top** of `runScanCycle()` so failures never block trading.

```ts
async function eventCalendarRefresh() {
  const meta = await query(`SELECT last_refresh_ts FROM ironforge_event_calendar_meta WHERE id=1`);
  const lastRefresh = meta.rows[0]?.last_refresh_ts;
  const hoursSince = lastRefresh ? (Date.now() - lastRefresh.getTime()) / 3.6e6 : 999;
  if (hoursSince < 20) return;

  if (!process.env.FINNHUB_API_KEY) {
    await markRefreshError('FINNHUB_API_KEY not set');
    return;
  }

  try {
    const events = await fetchFinnhubFomcEvents();
    let added = 0, updated = 0;
    for (const ev of events) {
      const id = `finnhub:FOMC:${ev.date}`;
      const haltStart = computeFridayPriorAt0830CT(ev.date);
      const haltEnd   = computeEventDayAt(ev.date, ev.time, 60);
      const result = await dbExecute(`
        INSERT INTO ironforge_event_calendar (event_id, source, event_type, title,
          event_date, event_time_ct, halt_start_ts, halt_end_ts, created_by)
        VALUES ($1,'finnhub','FOMC',$2,$3,$4,$5,$6,'finnhub-refresh')
        ON CONFLICT (event_id) DO UPDATE SET
          title=EXCLUDED.title, event_time_ct=EXCLUDED.event_time_ct,
          halt_start_ts=EXCLUDED.halt_start_ts, halt_end_ts=EXCLUDED.halt_end_ts,
          updated_at=NOW()
        RETURNING (xmax = 0) AS inserted
      `, [id, ev.title, ev.date, ev.time, haltStart, haltEnd]);
      result.rows[0].inserted ? added++ : updated++;
    }
    await dbExecute(`UPDATE ironforge_event_calendar_meta SET last_refresh_ts=NOW(),
                     last_refresh_status='ok', events_added=$1, events_updated=$2 WHERE id=1`,
                    [added, updated]);
  } catch (err) {
    await markRefreshError(`finnhub fetch failed: ${err.message}`);
  }
}
```

### 6.1 Finnhub specifics

- Endpoint: `GET /calendar/economic?from=YYYY-MM-DD&to=YYYY-MM-DD&token=<API_KEY>`
- Filter response to `country='US'` AND `event` matches `/FOMC|Fed Interest Rate|Federal Funds/i` AND `impact='high'`
- Window: `from=today, to=today+395d` (~13 months — covers a full year ahead at year boundaries)
- Free tier limit: 60 req/min; we call once a day

## 7. Scanner Gate

```ts
async function isEventBlackoutActive(bot: string, now: Date): Promise<{
  blocked: boolean;
  reason?: string;
  eventId?: string;
  eventTitle?: string;
  resumesAt?: Date;
}> {
  const config = await loadBotConfig(bot);
  if (!config.event_blackout_enabled) return { blocked: false };

  const result = await query(`
    SELECT event_id, title, halt_end_ts
    FROM ironforge_event_calendar
    WHERE is_active = TRUE AND $1 BETWEEN halt_start_ts AND halt_end_ts
    ORDER BY halt_end_ts ASC LIMIT 1
  `, [now]);

  if (result.rows.length === 0) return { blocked: false };
  const row = result.rows[0];
  return {
    blocked: true,
    reason: `event_blackout(${row.title} until ${formatCT(row.halt_end_ts)})`,
    eventId: row.event_id,
    eventTitle: row.title,
    resumesAt: row.halt_end_ts,
  };
}
```

Plugged into `tryOpenPosition()` in `scanner.ts` BEFORE the existing PDT / traded-today / BP gates (cheapest gate first, fail-fast):

```ts
const blackout = await isEventBlackoutActive(bot.name, now);
if (blackout.blocked) {
  await logScanSkip(bot, blackout.reason, { event_id: blackout.eventId });
  return;
}
```

### 7.1 Hard guarantee

The gate ONLY blocks `tryOpenPosition()`. Existing position management (PT, SL, EOD, stale-cleanup) runs untouched. If a Friday-prior position is already open when blackout starts, it exits via normal logic. **Never wipes positions** (per `Common Mistakes #19`).

## 8. UI

### 8.1 Calendar page (`/calendar`)

- Top status banner: either "✓ Trading normally — Next blackout: FOMC starts Fri Jun 13 8:30 AM CT (10 days)" or "⚠ Event blackout in effect — FOMC, resumes Wed Jun 18 2:00 PM CT (14h 22m)"
- "Next 30 days" detail strip — rolling list of upcoming days with status
- 12-month grid (3 cols × 4 rows of mini-months), with year nav arrows
- Cell rendering:
  - **Green** = trading day
  - **Red** = full blackout day
  - **Yellow gradient (red→green)** = event day with mid-day resume
  - **Gray** = weekend
  - Today's date: thicker amber border
- Three small per-bot dots per blackout cell (FLAME amber, SPARK blue, INFERNO red — matching nav)
- Bot dot color: red = halted, green = trading (i.e., bot's `event_blackout_enabled=false`)
- Hover tooltip: `"FOMC Rate Decision · Halt Fri 6/13 8:30 AM CT → Wed 6/18 2:00 PM CT · Source: Finnhub"`
- Click cell → side panel with details + Edit (manual events only); Finnhub events show "Read-only — auto-pulled"
- Year nav: ◀ ▶ for past years (audit) / next year (sparse until Finnhub publishes them)

### 8.2 Admin page (`/calendar/admin`)

- Refresh status section: `Last refresh: 2026-05-04 06:00:12 CT  ✓ ok`, with "Refresh now" button
- Add custom event form: title, type, date, time, resume +min (default 60), description
- Active events table (next 12 months): date, title, source, halt-duration, actions
  - Manual events: Edit / Delete buttons
  - Finnhub events: read-only

### 8.3 Dashboard banner (`BotDashboard.tsx`)

- **In blackout:** yellow strip "⚠ Event blackout in effect — FOMC Rate Decision · No new entries until Wed Jun 18 2:00 PM CT (resumes in 14h 22m)"
- **< 7 days away:** quieter info strip "ℹ Upcoming blackout: FOMC begins Fri Jun 13 8:30 AM CT (3d 4h)"
- Otherwise: no banner

### 8.4 Nav link (`Nav.tsx`)

Insert `Calendar` between `Compare` and `Accounts`. Neutral gray styling matching `Compare`.

## 9. Failure Modes

| Failure | Behavior | User-visible signal |
|---|---|---|
| `FINNHUB_API_KEY` missing | Refresh logs error to meta table; gate uses existing DB rows incl. manual events | Admin page shows "API key not configured" warning |
| Finnhub API down / 5xx | Refresh catches, logs, **does not throw**; gate uses last good data | Admin page status; banner if last refresh > 48h |
| Finnhub returns 0 events | Treated as soft error; existing rows NOT deleted | Admin page warning |
| DB unavailable | Existing scanner DB-error path fires | Same as today |
| Stale data (>48h) | Banner on admin page: "⚠ Data may be stale" | Manual refresh button |
| DST transitions | All comparisons in UTC `TIMESTAMPTZ`; CT formatting only at display | Postgres handles DST automatically |
| Holiday on Fri-prior | Halt still starts Fri 8:30 CT (bots wouldn't trade anyway) | Calendar overlays "Blackout" on holiday |
| Past-dated event | Refresh skips (`event_date >= today` filter) | — |
| Past custom event | Admin UI shows under "History" tab; gate ignores | — |
| Two events overlap | Gate's `LIMIT 1 ORDER BY halt_end_ts ASC` returns first-ending; next query catches the next. Halt extends naturally. | Calendar tooltip lists both |
| Custom event time after EOD cutoff | Resume effectively never fires that day (no entries possible after EOD) | Calendar cell stays red for INFERNO |
| Bot toggle flipped mid-blackout | Next scan reads fresh config, gate returns `blocked:false` | Bot dot turns green within 1 min |

## 10. Testing Strategy

### 10.1 Unit tests (`tests/calendar/`)
- `computeFridayPriorAt0830CT` — every weekday Mon-Sun + cross-year-boundary cases
- `computeEventDayAt(date, time, +offset)` — resume offset math
- `isEventBlackoutActive` — table-driven over a fixture event with `now` set to: before halt, exactly at halt_start, mid-blackout, exactly at halt_end, after halt; with toggle on/off
- Finnhub response parser — fixtures for valid response, empty array, malformed JSON, non-FOMC noise

### 10.2 Integration tests (`tests/calendar/integration/`)
- Seed one FOMC event in test DB, call gate from simulated `tryOpenPosition`, assert `skip_reason` text
- Idempotency: run `eventCalendarRefresh` twice with same Finnhub fixture; assert row count unchanged, `events_updated` increments
- Per-bot isolation: toggle `event_blackout_enabled=false` for SPARK only; assert FLAME and INFERNO stay blocked while SPARK is allowed

### 10.3 Manual / staging verification (mandatory before merge)
1. `npm run build` — TypeScript compiles
2. `POST /api/calendar/refresh` with real Finnhub key in staging; verify `ironforge_event_calendar` populates with current FOMC dates
3. Open `/calendar` in browser; verify 12 months render and June FOMC shows red cells Fri-Wed
4. Add a custom event for tomorrow; verify gate blocks `tryOpenPosition` for tomorrow's scan
5. Flip `inferno_config.event_blackout_enabled=false`; verify INFERNO scans on a blackout day while FLAME/SPARK skip

## 11. Rollout Plan

Per the user's standing "act autonomously" + "merge proactively" rules:

1. Build feature on `claude/event-blackout-vigil` branch
2. Verify with `npm run build` + the manual checklist on Render preview
3. Merge to `main` (Render auto-deploys)
4. **Set `FINNHUB_API_KEY` in Render env vars — one-time manual step (flagged because it's a credential per the "always confirm credentials" rule)**
5. Hit `POST /api/calendar/refresh` once to populate; subsequent refreshes happen automatically every 20h via the scanner loop

## 12. Open Items / Future Work

- Add CPI / NFP / PPI auto-pulling once FOMC is proven in production (just a filter change in `fetchFinnhubFomcEvents`)
- Discord notifications on blackout start/end via existing `lib/discord.ts`
- A "test mode" admin button that lets the operator simulate a `now` timestamp for verifying the gate end-to-end without waiting for a real event
