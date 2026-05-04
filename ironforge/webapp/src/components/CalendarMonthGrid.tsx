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

/**
 * A day is "in blackout" if its calendar date sits between the halt_start
 * and event_date (inclusive on both ends).  We work on calendar-date strings
 * because TIMESTAMPTZ precision isn't needed for the cell coloring.
 */
function dayInBlackout(iso: string, ev: CalendarEvent): boolean {
  const startDate = (typeof ev.halt_start_ts === 'string' ? ev.halt_start_ts : new Date(ev.halt_start_ts).toISOString()).slice(0, 10)
  const endDate = ev.event_date
  return iso >= startDate && iso <= endDate
}

function MiniMonth({ year, month, events, todayIso }: MonthProps) {
  const monthName = new Date(year, month, 1).toLocaleString('en-US', { month: 'long' })
  const firstDow = new Date(year, month, 1).getDay() // 0=Sun
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const cells: Array<{ iso: string | null; day: number | null }> = []
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
          if (!c.iso) return <div key={i} className="h-7" />
          const dow = new Date(c.iso + 'T12:00:00Z').getUTCDay()
          const isWeekend = dow === 0 || dow === 6
          const isToday = c.iso === todayIso
          const blackout = events.find(ev => dayInBlackout(c.iso!, ev))
          const isEventDay = blackout && c.iso === blackout.event_date

          let bg = 'bg-emerald-900/30'
          if (isWeekend) bg = 'bg-gray-800/30'
          if (blackout) bg = isEventDay ? 'bg-gradient-to-r from-red-700/50 to-emerald-700/40' : 'bg-red-800/40'

          const tooltip = blackout
            ? `${blackout.title}\nHalt: ${(typeof blackout.halt_start_ts === 'string' ? blackout.halt_start_ts : new Date(blackout.halt_start_ts).toISOString()).slice(0, 10)}\nResume: ${new Date(blackout.halt_end_ts).toLocaleString('en-US', { timeZone: 'America/Chicago' })} CT\nSource: ${blackout.source}`
            : ''

          return (
            <div
              key={i}
              title={tooltip}
              className={`h-7 text-center text-[10px] rounded ${bg} ${isToday ? 'ring-1 ring-amber-400' : ''} text-gray-200 leading-7`}
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
