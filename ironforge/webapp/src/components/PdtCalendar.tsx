'use client'

import { useState, useEffect } from 'react'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
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
  window_start?: string | null
  window_end?: string | null
}

type DayKind =
  | 'traded'
  | 'skipped'
  | 'today_traded'
  | 'today_open'
  | 'today_blocked'
  | 'available'
  | 'blocked'
  | 'future_opens'

interface DayInfo {
  kind: DayKind
  expiryDate?: string
  slotsOpening?: number
  positionIds?: string[]
}

/* ------------------------------------------------------------------ */
/*  Grid construction — 2 weeks: past 5 biz + next 5 biz              */
/* ------------------------------------------------------------------ */

function buildTwoWeekGrid(today: Date): Date[][] {
  // Find this week's Monday
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

function dateStr(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function fmtShortDate(ds: string): string {
  const d = new Date(ds + 'T12:00:00')
  return d.toLocaleDateString('en-US', {
    timeZone: 'America/Chicago',
    month: 'short',
    day: 'numeric',
  })
}

function getBusinessDaysBefore(from: Date, nBizDays: number): Date {
  const d = new Date(from)
  let count = 0
  while (count < nBizDays) {
    d.setDate(d.getDate() - 1)
    const dow = d.getDay()
    if (dow >= 1 && dow <= 5) count++
  }
  d.setDate(d.getDate() + 1)
  return d
}

/* ------------------------------------------------------------------ */
/*  Day classification                                                 */
/* ------------------------------------------------------------------ */

function classifyDays(
  weeks: Date[][],
  status: PdtStatus,
  todayStr: string,
): Map<string, DayInfo> {
  const result = new Map<string, DayInfo>()

  const tradeDateMap = new Map<string, { falls_off: string; position_ids: string[] }>()
  const fallsOffCount = new Map<string, number>()

  for (const t of status.trigger_trades) {
    tradeDateMap.set(t.trade_date, {
      falls_off: t.falls_off,
      position_ids: t.position_ids || [],
    })
    fallsOffCount.set(t.falls_off, (fallsOffCount.get(t.falls_off) || 0) + 1)
  }

  const actualTradeDates = Array.from(tradeDateMap.keys())
  if (status.traded_today && !tradeDateMap.has(todayStr)) {
    actualTradeDates.push(todayStr)
  }
  actualTradeDates.sort()

  const max = status.max_day_trades

  for (const day of weeks.flat()) {
    const ds = dateStr(day)
    const dow = day.getDay()
    if (dow === 0 || dow === 6) continue

    if (ds < todayStr) {
      const trade = tradeDateMap.get(ds)
      if (trade) {
        result.set(ds, { kind: 'traded', expiryDate: trade.falls_off, positionIds: trade.position_ids })
      } else {
        result.set(ds, { kind: 'skipped' })
      }
    } else if (ds === todayStr) {
      const trade = tradeDateMap.get(ds)
      if (!status.pdt_enabled) {
        result.set(ds, { kind: status.traded_today ? 'today_traded' : 'today_open', expiryDate: trade?.falls_off })
      } else if (status.traded_today) {
        result.set(ds, { kind: 'today_traded', expiryDate: trade?.falls_off })
      } else if (status.is_blocked) {
        result.set(ds, { kind: 'today_blocked' })
      } else {
        result.set(ds, { kind: 'today_open' })
      }
    } else {
      if (!status.pdt_enabled) {
        result.set(ds, { kind: 'available' })
        continue
      }
      const slotsOpening = fallsOffCount.get(ds) || 0
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

/* ------------------------------------------------------------------ */
/*  Cell styling                                                       */
/* ------------------------------------------------------------------ */

function cellClasses(kind: DayKind, isToday: boolean): string {
  const ring = isToday ? ' ring-2' : ''
  switch (kind) {
    case 'traded':
      return `bg-emerald-600/40 text-emerald-300 border border-emerald-700/40${ring} ring-emerald-400/50`
    case 'skipped':
      return `bg-gray-800/20 text-gray-600 border border-forge-border/20${ring} ring-white/20`
    case 'today_traded':
      return 'bg-amber-600/30 text-amber-200 border border-amber-500/40 ring-2 ring-amber-400'
    case 'today_open':
      return 'bg-blue-600/40 text-blue-200 border border-blue-500/40 ring-2 ring-blue-400'
    case 'today_blocked':
      return 'bg-red-600/30 text-red-300 border border-red-500/30 ring-2 ring-red-400'
    case 'available':
      return `bg-emerald-900/20 text-emerald-400/60 border border-emerald-800/30${ring} ring-white/20`
    case 'blocked':
      return `bg-red-900/15 text-red-500/40 border border-red-900/20${ring} ring-white/20`
    case 'future_opens':
      return `bg-amber-900/20 text-amber-400/60 border border-amber-700/30${ring} ring-white/20`
  }
}

function statusLabel(kind: DayKind, slotsOpening?: number): string {
  switch (kind) {
    case 'traded': return 'Traded'
    case 'skipped': return 'No trade'
    case 'today_traded': return 'Done'
    case 'today_open': return 'Can trade'
    case 'today_blocked': return 'Blocked'
    case 'available': return 'Open'
    case 'blocked': return 'Blocked'
    case 'future_opens':
      return slotsOpening === 1 ? 'Opens \u2713' : `${slotsOpening} open`
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

function dateNumColor(kind: DayKind): string {
  switch (kind) {
    case 'traded': return 'text-emerald-300'
    case 'skipped': return 'text-gray-600'
    case 'today_traded': return 'text-amber-200'
    case 'today_open': return 'text-blue-200'
    case 'today_blocked': return 'text-red-300'
    case 'available': return 'text-emerald-400/60'
    case 'blocked': return 'text-red-500/40'
    case 'future_opens': return 'text-amber-300'
  }
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function PdtCalendar({ status }: { status: PdtStatus }) {
  const [todayStr, setTodayStr] = useState<string | null>(null)

  useEffect(() => {
    setTodayStr(new Date().toLocaleDateString('en-CA', { timeZone: 'America/Chicago' }))
  }, [])

  if (!todayStr) return null

  const todayDate = new Date(todayStr + 'T12:00:00')
  const weeks = buildTwoWeekGrid(todayDate)
  const dayInfoMap = classifyDays(weeks, status, todayStr)

  const fmtWeekLabel = (d: Date) =>
    d.toLocaleDateString('en-US', { timeZone: 'America/Chicago', month: 'short', day: 'numeric' })

  return (
    <div className="rounded-lg bg-forge-bg/60 border border-forge-border/40 p-3">
      {/* Header + Legend */}
      <div className="flex items-center justify-between mb-3">
        <div className="text-[11px] text-forge-muted uppercase tracking-wide font-medium">
          Rolling Calendar
        </div>
        <div className="flex items-center gap-3 text-[10px] text-forge-muted">
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Traded
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/40 border border-emerald-600/40" /> Open
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400/60" /> Slot opens
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-gray-600" /> No trade
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-red-400/40" /> Blocked
          </span>
        </div>
      </div>

      {/* Column headers */}
      <div className="grid grid-cols-[52px_repeat(5,1fr)] gap-1 mb-1">
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
            className={`grid grid-cols-[52px_repeat(5,1fr)] gap-1 mb-1 ${
              isThisWeek ? 'bg-white/[0.02] rounded-lg py-0.5' : ''
            }`}
          >
            <div className="flex items-center text-[10px] text-forge-muted pl-1">
              {fmtWeekLabel(week[0])}
            </div>

            {week.map(day => {
              const ds = dateStr(day)
              const info = dayInfoMap.get(ds)
              if (!info) return <div key={ds} />

              const isToday = ds === todayStr
              const cls = cellClasses(info.kind, isToday)
              const label = statusLabel(info.kind, info.slotsOpening)

              return (
                <div key={ds} className="flex justify-center">
                  <div
                    className={`w-full min-h-[52px] rounded-lg flex flex-col items-center justify-center py-1 px-0.5 ${cls}`}
                    title={`${ds} \u2014 ${label}${info.expiryDate ? ` (expires ${info.expiryDate})` : ''}`}
                  >
                    <span className={`text-sm font-mono font-bold leading-none ${dateNumColor(info.kind)}`}>
                      {day.getDate()}
                    </span>
                    <span className={`text-[9px] leading-tight mt-0.5 ${labelColor(info.kind)}`}>
                      {label}
                    </span>
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

      {/* Summary */}
      <div className="mt-2 pt-2 border-t border-forge-border/30 text-[11px] text-forge-muted">
        {!status.pdt_enabled ? (
          <span className="text-amber-400">PDT bypassed — all days available</span>
        ) : (
          <>
            Rolling {status.window_days}-day window
            {' \u00b7 '}{status.max_day_trades} day trades max
            {' \u00b7 '}{status.max_trades_per_day > 0 ? `${status.max_trades_per_day} trade/day limit` : 'unlimited trades/day'}
          </>
        )}
      </div>
    </div>
  )
}
