'use client'

import { useState, useEffect } from 'react'

/* ------------------------------------------------------------------ */
/*  PdtCalendar — 3-week rolling view (past + current + next week)    */
/*  Shows business days only (Mon–Fri). Each cell: date, status,      */
/*  and expiry annotation for traded days. Merged with slot expiry.   */
/* ------------------------------------------------------------------ */

interface TriggerTrade {
  trade_date: string
  falls_off: string
  position_ids?: string[]
}

interface PdtStatus {
  pdt_enabled: boolean
  pdt_status: string
  day_trade_count: number
  max_day_trades: number
  traded_today: boolean
  can_trade: boolean
  is_blocked: boolean
  window_days: number
  trigger_trades: TriggerTrade[]
  next_slot_opens: string | null
  next_available_date: string | null
  max_trades_per_day: number
}

type DayKind =
  | 'traded'        // Past day — bot traded
  | 'skipped'       // Past day — no trade
  | 'today_traded'  // Today, already traded
  | 'today_open'    // Today, can still trade
  | 'today_blocked' // Today, PDT blocked
  | 'available'     // Future day — slot open
  | 'blocked'       // Future day — all slots consumed
  | 'future_opens'  // Future day — a slot frees up here

interface DayInfo {
  kind: DayKind
  expiryDate?: string    // falls_off date (for traded days)
  slotsOpening?: number  // how many slots free up (for future_opens)
  positionIds?: string[] // position IDs (for traded days)
}

/* ---- Grid construction ---- */

/** Build a 3-week grid: last week, this week, next week (Mon-Fri each) */
function buildThreeWeekGrid(today: Date): Date[][] {
  const thisMonday = new Date(today)
  const dow = thisMonday.getDay()
  const diff = dow === 0 ? -6 : 1 - dow
  thisMonday.setDate(thisMonday.getDate() + diff)

  const lastMonday = new Date(thisMonday)
  lastMonday.setDate(lastMonday.getDate() - 7)

  const nextMonday = new Date(thisMonday)
  nextMonday.setDate(nextMonday.getDate() + 7)

  return [lastMonday, thisMonday, nextMonday].map(monday => {
    const week: Date[] = []
    for (let d = 0; d < 5; d++) {
      const day = new Date(monday)
      day.setDate(monday.getDate() + d)
      week.push(day)
    }
    return week
  })
}

/** Format as YYYY-MM-DD in local time */
function dateStr(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** Short date: "Mar 18" */
function fmtShortDate(ds: string): string {
  const d = new Date(ds + 'T12:00:00')
  return d.toLocaleDateString('en-US', {
    timeZone: 'America/Chicago',
    month: 'short',
    day: 'numeric',
  })
}

/** Go back N business days from a date, return the start day (inclusive) */
function getBusinessDaysBefore(from: Date, nBizDays: number): Date {
  const d = new Date(from)
  let count = 0
  while (count < nBizDays) {
    d.setDate(d.getDate() - 1)
    const dow = d.getDay()
    if (dow >= 1 && dow <= 5) count++
  }
  d.setDate(d.getDate() + 1) // inclusive start
  return d
}

/* ---- Day classification ---- */

function classifyDays(
  weeks: Date[][],
  status: PdtStatus,
  todayStr: string,
): Map<string, DayInfo> {
  const result = new Map<string, DayInfo>()

  // Build lookup maps from trigger_trades
  const tradeDateMap = new Map<string, { falls_off: string; position_ids: string[] }>()
  const fallsOffCount = new Map<string, number>()

  for (const t of status.trigger_trades) {
    tradeDateMap.set(t.trade_date, {
      falls_off: t.falls_off,
      position_ids: t.position_ids || [],
    })
    fallsOffCount.set(t.falls_off, (fallsOffCount.get(t.falls_off) || 0) + 1)
  }

  // Build sorted list of actual trade dates
  const actualTradeDates = Array.from(tradeDateMap.keys())
  if (status.traded_today && !tradeDateMap.has(todayStr)) {
    actualTradeDates.push(todayStr)
  }
  actualTradeDates.sort()

  const max = status.max_day_trades

  for (const day of weeks.flat()) {
    const ds = dateStr(day)
    const dow = day.getDay()

    if (dow === 0 || dow === 6) continue // skip weekends (grid is Mon-Fri)

    if (ds < todayStr) {
      // Past day
      const trade = tradeDateMap.get(ds)
      if (trade) {
        result.set(ds, {
          kind: 'traded',
          expiryDate: trade.falls_off,
          positionIds: trade.position_ids,
        })
      } else {
        result.set(ds, { kind: 'skipped' })
      }
    } else if (ds === todayStr) {
      // Today
      const trade = tradeDateMap.get(ds)
      if (!status.pdt_enabled) {
        result.set(ds, {
          kind: status.traded_today ? 'today_traded' : 'today_open',
          expiryDate: trade?.falls_off,
        })
      } else if (status.traded_today) {
        result.set(ds, {
          kind: 'today_traded',
          expiryDate: trade?.falls_off,
        })
      } else if (status.is_blocked) {
        result.set(ds, { kind: 'today_blocked' })
      } else {
        result.set(ds, { kind: 'today_open' })
      }
    } else {
      // Future day
      if (!status.pdt_enabled) {
        result.set(ds, { kind: 'available' })
        continue
      }

      const slotsOpening = fallsOffCount.get(ds) || 0

      // Count actual trades in this day's rolling window
      const windowStart = getBusinessDaysBefore(day, status.window_days)
      const windowStartStr = dateStr(windowStart)
      let tradesInWindow = 0
      for (const td of actualTradeDates) {
        if (td >= windowStartStr && td <= ds) tradesInWindow++
      }

      const isAvailable = tradesInWindow < max
      if (slotsOpening > 0 && isAvailable) {
        result.set(ds, { kind: 'future_opens', slotsOpening })
      } else if (!isAvailable) {
        result.set(ds, { kind: 'blocked' })
      } else {
        result.set(ds, { kind: 'available' })
      }
    }
  }

  return result
}

/* ---- Cell styling ---- */

function cellBg(kind: DayKind, isToday: boolean): string {
  const ring = isToday ? ' ring-2' : ''
  switch (kind) {
    case 'traded':
      return `bg-emerald-600/30 border border-emerald-700/40${ring} ring-emerald-400/50`
    case 'skipped':
      return `bg-forge-border/15 border border-forge-border/20${ring} ring-white/30`
    case 'today_traded':
      return 'bg-emerald-600/40 border border-emerald-500/50 ring-2 ring-emerald-400'
    case 'today_open':
      return 'bg-blue-600/30 border border-blue-500/40 ring-2 ring-blue-400'
    case 'today_blocked':
      return 'bg-red-600/20 border border-red-500/30 ring-2 ring-red-400'
    case 'available':
      return `bg-emerald-900/15 border border-emerald-800/25${ring} ring-white/30`
    case 'blocked':
      return `bg-red-900/10 border border-red-900/20${ring} ring-white/30`
    case 'future_opens':
      return `bg-amber-900/20 border border-amber-700/30${ring} ring-white/30`
  }
}

function dateColor(kind: DayKind): string {
  switch (kind) {
    case 'traded': return 'text-emerald-300'
    case 'skipped': return 'text-gray-600'
    case 'today_traded': return 'text-emerald-200'
    case 'today_open': return 'text-blue-200'
    case 'today_blocked': return 'text-red-300'
    case 'available': return 'text-emerald-400/60'
    case 'blocked': return 'text-red-500/40'
    case 'future_opens': return 'text-amber-300'
  }
}

function statusLabel(kind: DayKind, slotsOpening?: number): string {
  switch (kind) {
    case 'traded': return 'Traded'
    case 'skipped': return 'No trade'
    case 'today_traded': return 'Traded'
    case 'today_open': return 'Can trade'
    case 'today_blocked': return 'Blocked'
    case 'available': return 'Open'
    case 'blocked': return 'Blocked'
    case 'future_opens':
      return slotsOpening === 1 ? 'Slot opens' : `${slotsOpening} open`
  }
}

function labelColor(kind: DayKind): string {
  switch (kind) {
    case 'traded':
    case 'today_traded': return 'text-emerald-400/70'
    case 'skipped': return 'text-gray-700'
    case 'today_open': return 'text-blue-300/70'
    case 'today_blocked':
    case 'blocked': return 'text-red-400/60'
    case 'available': return 'text-emerald-500/40'
    case 'future_opens': return 'text-amber-400/70'
  }
}

/* ---- Component ---- */

export default function PdtCalendar({ status }: { status: PdtStatus }) {
  const [todayStr, setTodayStr] = useState<string | null>(null)

  useEffect(() => {
    setTodayStr(new Date().toLocaleDateString('en-CA', { timeZone: 'America/Chicago' }))
  }, [])

  if (!todayStr) return null

  const todayDate = new Date(todayStr + 'T12:00:00')
  const weeks = buildThreeWeekGrid(todayDate)
  const dayInfoMap = classifyDays(weeks, status, todayStr)

  const fmtWeekLabel = (d: Date) =>
    d.toLocaleDateString('en-US', {
      timeZone: 'America/Chicago',
      month: 'short',
      day: 'numeric',
    })

  return (
    <div className="rounded-lg bg-forge-bg/60 border border-forge-border/40 p-3">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="text-[11px] text-forge-muted uppercase tracking-wide">
          Rolling Window Calendar
        </div>
        <div className="flex items-center gap-2.5 text-[10px]">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded bg-emerald-600/40 border border-emerald-700/40" /> Traded
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded bg-emerald-900/20 border border-emerald-800/30" /> Open
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded bg-amber-900/25 border border-amber-700/30" /> Slot opens
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded bg-red-900/15 border border-red-900/20" /> Blocked
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded bg-forge-border/20" /> No trade
          </span>
        </div>
      </div>

      {/* Column headers */}
      <div className="grid grid-cols-[56px_repeat(5,1fr)] gap-1 mb-1">
        <div />
        {['Mon', 'Tue', 'Wed', 'Thu', 'Fri'].map(d => (
          <div key={d} className="text-center text-[10px] text-forge-muted font-medium">
            {d}
          </div>
        ))}
      </div>

      {/* Week rows */}
      {weeks.map((week, wi) => {
        const isThisWeek = week.some(d => dateStr(d) === todayStr)
        return (
          <div
            key={wi}
            className={`grid grid-cols-[56px_repeat(5,1fr)] gap-1 mb-1 ${
              isThisWeek ? 'bg-white/[0.03] rounded-lg py-0.5' : ''
            }`}
          >
            {/* Week label */}
            <div className="flex items-center text-[10px] text-forge-muted pl-1">
              {fmtWeekLabel(week[0])}
            </div>

            {/* Day cells */}
            {week.map(day => {
              const ds = dateStr(day)
              const info = dayInfoMap.get(ds)
              if (!info) return <div key={ds} />

              const isToday = ds === todayStr
              const bg = cellBg(info.kind, isToday)
              const label = statusLabel(info.kind, info.slotsOpening)

              return (
                <div key={ds} className="flex justify-center">
                  <div
                    className={`w-full min-h-[52px] rounded-lg flex flex-col items-center justify-center py-1 px-0.5 ${bg}`}
                    title={`${ds} — ${label}${info.expiryDate ? ` (expires ${info.expiryDate})` : ''}`}
                  >
                    {/* Date number */}
                    <span className={`text-sm font-mono font-bold leading-none ${dateColor(info.kind)}`}>
                      {day.getDate()}
                    </span>

                    {/* Status label */}
                    <span className={`text-[9px] leading-tight mt-0.5 ${labelColor(info.kind)}`}>
                      {label}
                    </span>

                    {/* Expiry annotation (only for traded days) */}
                    {info.expiryDate && (
                      <span className="text-[8px] leading-tight mt-px text-forge-muted/60">
                        exp {fmtShortDate(info.expiryDate)}
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )
      })}

      {/* Summary line */}
      <div className="mt-2 pt-2 border-t border-forge-border/30 text-[11px] text-forge-muted">
        {!status.pdt_enabled ? (
          <span className="text-amber-400">PDT bypassed — all days available</span>
        ) : (
          <>
            Rolling {status.window_days}-day window
            {' '}&middot;{' '}{status.max_day_trades} day trades max
            {' '}&middot;{' '}{status.max_trades_per_day > 0 ? `${status.max_trades_per_day} trade/day limit` : 'unlimited trades/day'}
          </>
        )}
      </div>
    </div>
  )
}
