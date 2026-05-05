/**
 * Daily refresh of FOMC events from Finnhub.
 *
 * Called from the scanner's per-cycle loop.  Idempotent: skips if the last
 * refresh was within REFRESH_COOLDOWN_HOURS unless `force: true` is passed.
 *
 * Never throws — errors are logged to ironforge_event_calendar_meta so the
 * admin UI surfaces them, but the scanner cycle continues.
 */

import { fetchFinnhubFomcEvents, FOMC_EXCLUDE_RE } from './finnhub'
import { upsertEvent, getRefreshMeta, setRefreshMeta } from './repo'
import { dbExecute } from '../db'

const REFRESH_COOLDOWN_HOURS = 20

function todayPlus(days: number): string {
  const d = new Date()
  d.setUTCDate(d.getUTCDate() + days)
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`
}

/**
 * Refresh FOMC events from Finnhub if the last refresh was older than the cooldown.
 * Returns true if a refresh attempt was made, false if skipped.
 */
export async function eventCalendarRefresh(opts: { force?: boolean } = {}): Promise<boolean> {
  if (!opts.force) {
    try {
      const meta = await getRefreshMeta()
      if (meta.last_refresh_ts) {
        const hoursSince = (Date.now() - meta.last_refresh_ts.getTime()) / 3.6e6
        if (hoursSince < REFRESH_COOLDOWN_HOURS) return false
      }
    } catch {
      // If meta read fails, fall through and try the refresh anyway.
    }
  }

  const apiKey = process.env.FINNHUB_API_KEY
  if (!apiKey) {
    await setRefreshMeta('error: FINNHUB_API_KEY not set').catch(() => {})
    return true
  }

  try {
    const events = await fetchFinnhubFomcEvents(todayPlus(0), todayPlus(395), apiKey)
    let added = 0
    let updated = 0
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
      if (result.inserted) added++
      else updated++
    }
    // Self-heal: deactivate any previously-stored finnhub events whose title
    // now matches the exclusion regex (e.g. "FOMC Minutes" rows persisted
    // before the parser tightened). Idempotent + cheap.
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
