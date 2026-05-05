import type { BotKey, BriefType } from './types'

const PER_BOTS: BotKey[] = ['flame', 'spark', 'inferno']

export interface Trigger { bot: BotKey; brief_type: BriefType; brief_date: string }

export interface UpcomingEvent { event_date: string; halt_start_ts: string }
export interface RecentlyEndedEvent { event_date: string; halt_end_ts: string }

function ctParts(now: Date): { y: number; m: number; d: number; dow: number; hhmm: number; ymd: string } {
  const dtf = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Chicago',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', weekday: 'short', hour12: false,
  })
  const parts = dtf.formatToParts(now).reduce((acc, p) => {
    if (p.type !== 'literal') acc[p.type] = p.value
    return acc
  }, {} as Record<string, string>)
  const y = parseInt(parts.year)
  const m = parseInt(parts.month)
  const d = parseInt(parts.day)
  const hh = parseInt(parts.hour === '24' ? '0' : parts.hour)
  const mm = parseInt(parts.minute)
  const dowMap: Record<string, number> = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 }
  const dow = dowMap[parts.weekday] ?? 0
  return {
    y, m, d, dow, hhmm: hh * 100 + mm,
    ymd: `${parts.year}-${parts.month}-${parts.day}`,
  }
}

function inWindow(hhmm: number, startInclusive: number, endInclusive: number): boolean {
  return hhmm >= startInclusive && hhmm <= endInclusive
}

function isLastBusinessDayOfMonth(y: number, m: number, d: number, dow: number): boolean {
  if (dow === 0 || dow === 6) return false
  // Compute days in month: month here is 1-indexed; Date(y, m, 0) returns last day of month m
  const daysInMonth = new Date(y, m, 0).getDate()
  for (let next = d + 1; next <= daysInMonth; next++) {
    const nd = new Date(Date.UTC(y, m - 1, next)).getUTCDay()
    if (nd >= 1 && nd <= 5) return false
  }
  return true
}

function thursdayBefore(eventDate: string): string {
  const [y, mo, d] = eventDate.split('-').map(Number)
  const dt = new Date(Date.UTC(y, mo - 1, d))
  const dow = dt.getUTCDay()
  let back: number
  if (dow === 4) back = 7
  else if (dow > 4) back = dow - 4
  else back = dow + 3
  dt.setUTCDate(dt.getUTCDate() - back)
  return `${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, '0')}-${String(dt.getUTCDate()).padStart(2, '0')}`
}

function dayAfter(dateStr: string): string {
  const [y, mo, d] = dateStr.split('-').map(Number)
  const dt = new Date(Date.UTC(y, mo - 1, d))
  dt.setUTCDate(dt.getUTCDate() + 1)
  return `${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, '0')}-${String(dt.getUTCDate()).padStart(2, '0')}`
}

export function decideTriggers(
  now: Date,
  upcomingEvents: UpcomingEvent[],
  recentlyEndedEvents: RecentlyEndedEvent[],
): Trigger[] {
  const ct = ctParts(now)
  const out: Trigger[] = []
  const isWeekend = ct.dow === 0 || ct.dow === 6

  // 1. Daily EOD — Mon-Fri 15:30-15:34 CT
  if (!isWeekend && inWindow(ct.hhmm, 1530, 1534)) {
    for (const bot of PER_BOTS) out.push({ bot, brief_type: 'daily_eod', brief_date: ct.ymd })
    out.push({ bot: 'portfolio', brief_type: 'daily_eod', brief_date: ct.ymd })
  }

  // 2. Weekly synth — Friday 16:00-16:04 CT
  if (ct.dow === 5 && inWindow(ct.hhmm, 1600, 1604)) {
    for (const bot of PER_BOTS) out.push({ bot, brief_type: 'weekly_synth', brief_date: ct.ymd })
    out.push({ bot: 'portfolio', brief_type: 'weekly_synth', brief_date: ct.ymd })
  }

  // 3. Codex monthly — last business day 17:00-17:04 CT
  if (isLastBusinessDayOfMonth(ct.y, ct.m, ct.d, ct.dow) && inWindow(ct.hhmm, 1700, 1704)) {
    for (const bot of PER_BOTS) out.push({ bot, brief_type: 'codex_monthly', brief_date: ct.ymd })
    out.push({ bot: 'portfolio', brief_type: 'codex_monthly', brief_date: ct.ymd })
  }

  // 4. FOMC eve — Thursday before each upcoming FOMC, 15:35-15:39 CT
  if (!isWeekend && inWindow(ct.hhmm, 1535, 1539)) {
    for (const ev of upcomingEvents) {
      if (thursdayBefore(ev.event_date) === ct.ymd) {
        for (const bot of PER_BOTS) out.push({ bot, brief_type: 'fomc_eve', brief_date: ct.ymd })
        break
      }
    }
  }

  // 5. Post-event — day after a halt_end_ts, 09:00-09:04 CT
  if (!isWeekend && inWindow(ct.hhmm, 900, 904)) {
    for (const ev of recentlyEndedEvents) {
      if (dayAfter(ev.event_date) === ct.ymd) {
        for (const bot of PER_BOTS) out.push({ bot, brief_type: 'post_event', brief_date: ct.ymd })
        break
      }
    }
  }

  return out
}
