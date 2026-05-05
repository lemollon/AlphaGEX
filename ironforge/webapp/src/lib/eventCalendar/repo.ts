/**
 * DB ops for the IronForge event-blackout calendar (Vigil).
 *
 * Wraps `ironforge_event_calendar` and `ironforge_event_calendar_meta`.
 * Halt windows are computed at insert time so the gate query stays a single
 * indexed range scan.
 */

import { query, dbExecute } from '../db'
import { computeNTradingDaysPriorAt0830CT, computeEventDayAt } from './halt-window'

/**
 * IronForge halt policy: short-premium ICs are short vega. IV inflates for
 * ~2 trading days running into a known macro event (FOMC, CPI, PPI, NFP),
 * MTM hits the 2x stop before the post-event vol crush, so the bots eat
 * vega-up but never collect vega-down. Halting `EVENT_HALT_TRADING_DAYS`
 * trading days before the event keeps every position flat through the
 * runup. Same window for FOMC, CPI, PPI, NFP, manual entries; same window
 * for FLAME, SPARK, INFERNO.
 */
const EVENT_HALT_TRADING_DAYS = 2

export type CalendarSource = 'finnhub' | 'manual' | 'fed'

export interface CalendarEvent {
  event_id: string
  source: CalendarSource
  event_type: string
  title: string
  description: string | null
  event_date: string          // YYYY-MM-DD
  event_time_ct: string       // HH:MM
  halt_start_ts: string | Date
  halt_end_ts: string | Date
  resume_offset_min: number
  is_active: boolean
  created_by: string
}

export interface UpsertEventInput {
  event_id: string
  source: CalendarSource
  event_type: string
  title: string
  description?: string | null
  event_date: string
  event_time_ct: string
  resume_offset_min?: number
  created_by: string
}

export interface RefreshMeta {
  last_refresh_ts: Date | null
  last_refresh_status: string | null
  events_added: number
  events_updated: number
}

/** Upsert one event; computes halt window automatically. */
export async function upsertEvent(input: UpsertEventInput): Promise<{ inserted: boolean }> {
  const offset = input.resume_offset_min ?? 60
  const haltStart = computeNTradingDaysPriorAt0830CT(input.event_date, EVENT_HALT_TRADING_DAYS)
  const haltEnd   = computeEventDayAt(input.event_date, input.event_time_ct, offset)
  const rows = await query<{ inserted: boolean }>(`
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
      is_active         = TRUE,
      updated_at        = NOW()
    RETURNING (xmax = 0) AS inserted
  `, [
    input.event_id, input.source, input.event_type, input.title, input.description ?? null,
    input.event_date, input.event_time_ct, haltStart, haltEnd,
    offset, input.created_by,
  ])
  return { inserted: rows[0]?.inserted ?? false }
}

/** List active upcoming events (halt_end_ts >= now), ordered by event_date. */
export async function listUpcomingEvents(): Promise<CalendarEvent[]> {
  return query<CalendarEvent>(`
    SELECT event_id, source, event_type, title, description,
           event_date::text AS event_date,
           to_char(event_time_ct, 'HH24:MI') AS event_time_ct,
           halt_start_ts, halt_end_ts,
           resume_offset_min, is_active, created_by
    FROM ironforge_event_calendar
    WHERE is_active = TRUE AND halt_end_ts >= NOW()
    ORDER BY event_date ASC
  `)
}

/** List active events in a date range — for the calendar grid. */
export async function listEventsInRange(fromDate: string, toDate: string): Promise<CalendarEvent[]> {
  return query<CalendarEvent>(`
    SELECT event_id, source, event_type, title, description,
           event_date::text AS event_date,
           to_char(event_time_ct, 'HH24:MI') AS event_time_ct,
           halt_start_ts, halt_end_ts,
           resume_offset_min, is_active, created_by
    FROM ironforge_event_calendar
    WHERE is_active = TRUE AND event_date BETWEEN $1::date AND $2::date
    ORDER BY event_date ASC
  `, [fromDate, toDate])
}

/** Find currently-active blackout (halt_start_ts <= now <= halt_end_ts). */
export async function findCurrentBlackout(now: Date): Promise<CalendarEvent | null> {
  const rows = await query<CalendarEvent>(`
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
  return rows[0] ?? null
}

/** Soft-delete an event (set is_active=false). */
export async function deactivateEvent(eventId: string): Promise<number> {
  return dbExecute(
    `UPDATE ironforge_event_calendar SET is_active=FALSE, updated_at=NOW() WHERE event_id=$1`,
    [eventId],
  )
}

/** Get refresh meta. */
export async function getRefreshMeta(): Promise<RefreshMeta> {
  const rows = await query<any>(`SELECT last_refresh_ts, last_refresh_status, events_added, events_updated FROM ironforge_event_calendar_meta WHERE id=1`)
  const r = rows[0]
  if (!r) return { last_refresh_ts: null, last_refresh_status: null, events_added: 0, events_updated: 0 }
  return {
    last_refresh_ts: r.last_refresh_ts ? new Date(r.last_refresh_ts) : null,
    last_refresh_status: r.last_refresh_status ?? null,
    events_added: r.events_added ?? 0,
    events_updated: r.events_updated ?? 0,
  }
}

/** Update refresh meta after a refresh attempt. */
export async function setRefreshMeta(status: string, added = 0, updated = 0): Promise<void> {
  await dbExecute(`
    UPDATE ironforge_event_calendar_meta
    SET last_refresh_ts=NOW(), last_refresh_status=$1, events_added=$2, events_updated=$3
    WHERE id=1
  `, [status, added, updated])
}
