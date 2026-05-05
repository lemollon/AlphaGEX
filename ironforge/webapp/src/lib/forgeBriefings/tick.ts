import { query } from '../db'
import { decideTriggers, type Trigger } from './scheduler'
import { generateBrief } from './generate'
import { pruneIfDue } from './prune'

const BASE_URL = process.env.IRONFORGE_BASE_URL || 'http://localhost:3000'

async function loadEventLists() {
  const upcoming = await query<{ event_date: string; halt_start_ts: string }>(`
    SELECT event_date::text AS event_date, halt_start_ts
    FROM ironforge_event_calendar
    WHERE is_active = TRUE AND event_date > CURRENT_DATE
      AND event_date <= CURRENT_DATE + INTERVAL '14 days'
    ORDER BY event_date ASC
  `).catch(() => [])
  const recent = await query<{ event_date: string; halt_end_ts: string }>(`
    SELECT event_date::text AS event_date, halt_end_ts
    FROM ironforge_event_calendar
    WHERE is_active = TRUE AND halt_end_ts >= NOW() - INTERVAL '2 days'
      AND halt_end_ts < NOW()
    ORDER BY halt_end_ts DESC
  `).catch(() => [])
  return { upcoming, recent }
}

export async function forgeBriefingsTick(): Promise<void> {
  // Best-effort prune (once per day)
  pruneIfDue().catch(() => {})

  let triggers: Trigger[] = []
  try {
    const { upcoming, recent } = await loadEventLists()
    triggers = decideTriggers(new Date(), upcoming, recent)
  } catch (err) {
    console.warn('[forge-briefings] tick — decideTriggers failed (non-fatal):', err)
    return
  }
  if (triggers.length === 0) return

  for (const t of triggers) {
    try {
      const result = await generateBrief({
        bot: t.bot, brief_type: t.brief_type,
        brief_date: t.brief_date, baseUrl: BASE_URL,
      })
      console.log(`[forge-briefings] ${t.bot}/${t.brief_type}: ${result.status}${result.reason ? ' — ' + result.reason : ''}`)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      console.warn(`[forge-briefings] ${t.bot}/${t.brief_type}: unexpected error: ${msg}`)
    }
  }
}
