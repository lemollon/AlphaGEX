'use client'

/* ------------------------------------------------------------------ */
/*  PdtCalendar — Monthly visual showing which days a bot can trade    */
/*  Shows business days only (Mon–Fri). Past = actual, Future = projected */
/*  based on the rolling 5-day PDT window with max_day_trades limit.   */
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
  | 'weekend'       // Sat/Sun — never trades
  | 'outside'       // Padding day outside current month

/** Build a 4-week (Mon-Fri) grid starting from the Monday of today's week */
function buildFourWeekGrid(today: Date): Date[][] {
  // Find Monday of this week
  const monday = new Date(today)
  const dow = monday.getDay()
  const diff = dow === 0 ? -6 : 1 - dow // Sunday = go back 6, else go back to Monday
  monday.setDate(monday.getDate() + diff)

  const weeks: Date[][] = []
  const cursor = new Date(monday)
  for (let w = 0; w < 4; w++) {
    const week: Date[] = []
    for (let d = 0; d < 5; d++) {
      week.push(new Date(cursor))
      cursor.setDate(cursor.getDate() + 1)
    }
    // Skip weekend
    cursor.setDate(cursor.getDate() + 2)
    weeks.push(week)
  }
  return weeks
}

/** Format as YYYY-MM-DD in local time (NOT UTC — avoids day-off bugs near midnight) */
function dateStr(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function classifyDays(
  weeks: Date[][],
  status: PdtStatus,
  todayStr: string,
): Map<string, DayKind> {
  const result = new Map<string, DayKind>()

  // Set of dates where trades actually happened
  const tradedDates = new Set(status.trigger_trades.map(t => t.trade_date))

  // Actual trade dates including today if traded
  const actualTradeDates = Array.from(tradedDates)
  if (status.traded_today && !tradedDates.has(todayStr)) {
    actualTradeDates.push(todayStr)
  }
  actualTradeDates.sort()

  const max = status.max_day_trades
  const allDays = weeks.flat()

  for (const day of allDays) {
    const ds = dateStr(day)
    const dow = day.getDay()

    if (dow === 0 || dow === 6) {
      result.set(ds, 'weekend')
      continue
    }

    if (ds < todayStr) {
      // Past day — show what actually happened
      result.set(ds, tradedDates.has(ds) ? 'traded' : 'skipped')
    } else if (ds === todayStr) {
      // Today — live status from API
      if (!status.pdt_enabled) {
        result.set(ds, status.traded_today ? 'today_traded' : 'today_open')
      } else if (status.traded_today) {
        result.set(ds, 'today_traded')
      } else if (status.is_blocked) {
        result.set(ds, 'today_blocked')
      } else {
        result.set(ds, 'today_open')
      }
    } else {
      // Future day — only count ACTUAL trades in its rolling window
      // No greedy simulation: we don't assume the bot will trade
      if (!status.pdt_enabled) {
        result.set(ds, 'available')
        continue
      }

      // Count actual trades that fall within this day's trailing window
      const windowStart = getBusinessDaysBefore(day, status.window_days)
      const windowStartStr = dateStr(windowStart)
      let tradesInWindow = 0
      actualTradeDates.forEach(td => {
        if (td >= windowStartStr && td <= ds) {
          tradesInWindow++
        }
      })

      if (tradesInWindow >= max) {
        result.set(ds, 'blocked')
      } else {
        result.set(ds, 'available')
      }
    }
  }

  return result
}

/** Go back N business days from a date */
function getBusinessDaysBefore(from: Date, nBizDays: number): Date {
  const d = new Date(from)
  let count = 0
  while (count < nBizDays) {
    d.setDate(d.getDate() - 1)
    const dow = d.getDay()
    if (dow >= 1 && dow <= 5) count++
  }
  // We want the window to START the day after (inclusive of nBizDays ago)
  d.setDate(d.getDate() + 1)
  return d
}

/* ------------------------------------------------------------------ */
/*  Styling per DayKind                                                */
/* ------------------------------------------------------------------ */

function dayStyle(kind: DayKind, isToday: boolean): string {
  const base = 'w-9 h-9 rounded-md flex items-center justify-center text-xs font-mono transition-all'
  const todayRing = isToday ? ' ring-2 ring-white/60' : ''

  switch (kind) {
    case 'traded':
      return `${base} bg-emerald-600/40 text-emerald-300${todayRing}`
    case 'skipped':
      return `${base} bg-forge-border/30 text-gray-600${todayRing}`
    case 'today_traded':
      return `${base} bg-emerald-600/50 text-emerald-200 ring-2 ring-emerald-400`
    case 'today_open':
      return `${base} bg-blue-600/40 text-blue-200 ring-2 ring-blue-400`
    case 'today_blocked':
      return `${base} bg-red-600/30 text-red-300 ring-2 ring-red-400`
    case 'available':
      return `${base} bg-emerald-900/30 text-emerald-400/70 border border-emerald-800/40${todayRing}`
    case 'blocked':
      return `${base} bg-red-900/20 text-red-500/50 border border-red-900/30${todayRing}`
    case 'weekend':
      return `${base} bg-transparent text-gray-800${todayRing}`
    case 'outside':
      return `${base} bg-transparent text-gray-800${todayRing}`
  }
}

function dayLabel(kind: DayKind): string {
  switch (kind) {
    case 'traded':
    case 'today_traded':
      return 'Traded'
    case 'skipped':
      return 'No trade'
    case 'today_open':
      return 'Can trade today'
    case 'today_blocked':
      return 'Blocked today (PDT)'
    case 'available':
      return 'Available (projected)'
    case 'blocked':
      return 'Blocked (projected)'
    default:
      return ''
  }
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function PdtCalendar({ status }: { status: PdtStatus }) {
  const now = new Date()
  const todayStr = now.toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })
  const todayDate = new Date(todayStr + 'T12:00:00')

  const weeks = buildFourWeekGrid(todayDate)
  const kinds = classifyDays(weeks, status, todayStr)

  // Week label: date range
  const fmtShort = (d: Date) =>
    d.toLocaleDateString('en-US', {
      timeZone: 'America/Chicago',
      month: 'short',
      day: 'numeric',
    })

  return (
    <div className="rounded-lg bg-forge-bg/60 border border-forge-border/40 p-3">
      <div className="flex items-center justify-between mb-3">
        <div className="text-[11px] text-forge-muted uppercase tracking-wide">
          4-Week Trading Calendar
        </div>
        <div className="flex items-center gap-3 text-[10px]">
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded bg-emerald-600/40" /> Traded
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded bg-emerald-900/30 border border-emerald-800/40" /> Available
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded bg-red-900/20 border border-red-900/30" /> Blocked
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded bg-forge-border/30" /> No trade
          </span>
        </div>
      </div>

      {/* Header row */}
      <div className="grid grid-cols-[60px_repeat(5,1fr)] gap-1 mb-1">
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
            className={`grid grid-cols-[60px_repeat(5,1fr)] gap-1 mb-1 ${
              isThisWeek ? 'bg-white/[0.02] rounded-lg py-0.5' : ''
            }`}
          >
            <div className="flex items-center text-[10px] text-forge-muted pl-1">
              {fmtShort(week[0])}
            </div>
            {week.map((day) => {
              const ds = dateStr(day)
              const kind = kinds.get(ds) || 'outside'
              const isToday = ds === todayStr
              return (
                <div key={ds} className="flex justify-center" title={dayLabel(kind)}>
                  <div className={dayStyle(kind, isToday)}>
                    {day.getDate()}
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
          <span className="text-amber-400">PDT OFF — all days available for trading</span>
        ) : (
          <>
            Rolling {status.window_days}-day window · {status.max_day_trades} day trades max ·{' '}
            {status.max_trades_per_day} trade/day limit
            {status.next_slot_opens && status.is_blocked && (
              <span className="ml-2 text-emerald-400">
                · Next slot: {new Date(status.next_slot_opens + 'T12:00:00').toLocaleDateString('en-US', {
                  timeZone: 'America/Chicago',
                  weekday: 'short',
                  month: 'short',
                  day: 'numeric',
                })}
              </span>
            )}
          </>
        )}
      </div>
    </div>
  )
}
