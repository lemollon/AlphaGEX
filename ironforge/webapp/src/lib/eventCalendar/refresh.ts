/**
 * Daily refresh of macro events for the IronForge blackout calendar.
 *
 * Called from the scanner's per-cycle loop.  Idempotent: skips if the last
 * refresh was within REFRESH_COOLDOWN_HOURS unless `force: true` is passed.
 *
 * Two authoritative sources, both hardcoded for predictable forward
 * coverage. Finnhub was retired here because the free tier only publishes
 * ~16 days ahead and uses inconsistent naming — the user wants 3-month
 * forward visibility on every release that could move SPY ±2%.
 *
 *   1. fedSchedule.ts       — FOMC rate decisions (16 dates, 2026–2027)
 *   2. blsSchedule.ts       — BLS / BEA / ISM macro releases for the next
 *                             12 months (CPI, PPI, NFP, PCE, GDP,
 *                             ISM Services, Retail Sales)
 *
 * The Finnhub fetch + parser remain in finnhub.ts and are still callable
 * from /api/calendar/diagnose-finnhub for ops inspection. They are no
 * longer wired into the refresh cycle.
 *
 * Never throws — errors are logged to ironforge_event_calendar_meta so the
 * admin UI surfaces them, but the scanner cycle continues.
 */

import { FOMC_EXCLUDE_RE } from './finnhub'
import { upsertEvent, getRefreshMeta, setRefreshMeta } from './repo'
import { FED_FOMC_SCHEDULE, fedFomcTitle } from './fedSchedule'
import { BLS_RELEASES } from './blsSchedule'
import { getPlaybook } from './playbook'
import { dbExecute } from '../db'

/**
 * Returns YYYY-MM-DD in America/Chicago for the given Date.
 * Used so the refresh fires once per CT calendar day — first scanner
 * cycle after midnight CT picks it up, well before market open.
 */
function ctDateString(d: Date): string {
  const dtf = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Chicago',
    year: 'numeric', month: '2-digit', day: '2-digit',
  })
  return dtf.format(d) // en-CA → "YYYY-MM-DD"
}

/**
 * Refresh the calendar from the hardcoded schedules. Returns true if a
 * refresh attempt was made, false if skipped.
 *
 * Cooldown: fires at most once per CT calendar day (so the first scanner
 * cycle after midnight CT picks it up — bots wake to fresh data well
 * before the 8:30 CT market open). `force: true` overrides.
 */
export async function eventCalendarRefresh(opts: { force?: boolean } = {}): Promise<boolean> {
  if (!opts.force) {
    try {
      const meta = await getRefreshMeta()
      if (meta.last_refresh_ts) {
        const lastCtDay = ctDateString(meta.last_refresh_ts)
        const todayCtDay = ctDateString(new Date())
        if (lastCtDay === todayCtDay) return false
      }
    } catch {
      // If meta read fails, fall through and try the refresh anyway.
    }
  }

  try {
    let added = 0
    let updated = 0

    // Skip rows whose date is more than 2 days in the past so we don't churn
    // historical entries on every refresh.
    const cutoffMs = Date.now() - 2 * 86400 * 1000
    const isCurrent = (dateStr: string) => Date.parse(`${dateStr}T00:00:00Z`) >= cutoffMs

    // 1. Federal Reserve FOMC schedule — authoritative for rate decisions.
    for (const m of FED_FOMC_SCHEDULE) {
      if (!isCurrent(m.date)) continue
      const result = await upsertEvent({
        event_id: `fed:FOMC:${m.date}`,
        source: 'fed',
        event_type: 'FOMC',
        title: fedFomcTitle(m),
        event_date: m.date,
        event_time_ct: m.time_ct,
        created_by: 'fed-schedule',
      })
      if (result.inserted) added++
      else updated++
    }

    // 2. BLS / BEA / ISM macro releases — 12 months of forward visibility.
    //    halts_bots flag is sourced from the per-type playbook so Tier 2/3
    //    events (PCE, GDP, ISM Services, Retail Sales) appear on the
    //    calendar but do NOT freeze the bots.
    for (const r of BLS_RELEASES) {
      if (!isCurrent(r.date)) continue
      const pb = getPlaybook(r.type)
      const result = await upsertEvent({
        event_id: `bls:${r.type}:${r.date}`,
        source: 'manual',           // 'bls' would need the source CHECK loosened; reuse 'manual'
        event_type: r.type,
        title: r.title,
        event_date: r.date,
        event_time_ct: r.time_ct,
        halts_bots: pb.halts_bots,
        created_by: 'bls-schedule',
      })
      if (result.inserted) added++
      else updated++
    }

    // 3. Self-heal: deactivate any previously-stored finnhub events whose
    //    title now matches the FOMC-exclusion regex (e.g. "FOMC Minutes"
    //    rows persisted before the parser tightened, or before we retired
    //    the Finnhub seed entirely). Idempotent + cheap.
    const excludeSrc = FOMC_EXCLUDE_RE.source
    await dbExecute(
      `UPDATE ironforge_event_calendar
       SET is_active = FALSE, updated_at = NOW()
       WHERE source = 'finnhub' AND is_active = TRUE
         AND title ~* $1`,
      [excludeSrc],
    ).catch(() => {})

    await setRefreshMeta('ok', added, updated)
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    await setRefreshMeta(`error: ${msg.slice(0, 200)}`).catch(() => {})
  }
  return true
}
