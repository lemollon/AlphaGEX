'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { useState } from 'react'
import { fetcher } from '@/lib/fetcher'
import CalendarBriefBadge from './CalendarBriefBadge'
import CalendarBriefMiniCard from './CalendarBriefMiniCard'
import type { Mood } from '@/lib/forgeBriefings/types'

interface CalendarEvent {
  event_id: string
  title: string
  event_date: string
  event_time_ct: string
  halt_start_ts: string
  halt_end_ts: string
  source: string
}

interface DayBadge {
  brief_date: string
  per_bot: Record<string, { mood: Mood | null; risk_score: number | null; brief_id: string }>
  lead: { brief_id: string; risk_score: number | null; first_sentence: string } | null
}

interface MonthProps {
  year: number
  month: number
  events: CalendarEvent[]
  todayIso: string
  badgesByDate: Record<string, DayBadge>
  hoverDate: string | null
  onHover: (iso: string | null) => void
}

function dateIso(y: number, m: number, d: number): string {
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
}

function dayInBlackout(iso: string, ev: CalendarEvent): boolean {
  const startDate = (typeof ev.halt_start_ts === 'string' ? ev.halt_start_ts : new Date(ev.halt_start_ts).toISOString()).slice(0, 10)
  const endDate = ev.event_date
  return iso >= startDate && iso <= endDate
}

function MiniMonth({ year, month, events, todayIso, badgesByDate, hoverDate, onHover }: MonthProps) {
  const monthName = new Date(year, month, 1).toLocaleString('en-US', { month: 'long' })
  const firstDow = new Date(year, month, 1).getDay()
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
          const badge = badgesByDate[c.iso]

          let bg = 'bg-emerald-900/30'
          if (isWeekend) bg = 'bg-gray-800/30'
          if (blackout) bg = isEventDay ? 'bg-gradient-to-r from-red-700/50 to-emerald-700/40' : 'bg-red-800/40'

          const tooltip = blackout
            ? `${blackout.title}\nHalt: ${(typeof blackout.halt_start_ts === 'string' ? blackout.halt_start_ts : new Date(blackout.halt_start_ts).toISOString()).slice(0, 10)}\nResume: ${new Date(blackout.halt_end_ts).toLocaleString('en-US', { timeZone: 'America/Chicago' })} CT\nSource: ${blackout.source}`
            : ''

          const moodForBadge = badge?.lead ? (badge.per_bot.portfolio?.mood ?? badge.per_bot.flame?.mood ?? null) : null

          const cellInner = (
            <>
              <span>{c.day}</span>
              {badge ? <CalendarBriefBadge mood={moodForBadge} /> : null}
              {badge && hoverDate === c.iso ? <CalendarBriefMiniCard day={badge} /> : null}
            </>
          )

          const className = `relative h-7 text-center text-[10px] rounded ${bg} ${isToday ? 'ring-1 ring-amber-400' : ''} text-gray-200 leading-7 ${badge ? 'cursor-pointer hover:bg-amber-900/40' : ''}`

          if (badge?.lead) {
            return (
              <Link
                key={i}
                href={`/briefings/${encodeURIComponent(badge.lead.brief_id)}`}
                title={tooltip}
                className={className}
                onMouseEnter={() => onHover(c.iso!)}
                onMouseLeave={() => onHover(null)}
              >
                {cellInner}
              </Link>
            )
          }

          return (
            <div
              key={i}
              title={tooltip}
              className={className}
              onMouseEnter={() => onHover(c.iso!)}
              onMouseLeave={() => onHover(null)}
            >
              {cellInner}
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
  const { data: badgesResp } = useSWR<{ days: DayBadge[] }>(
    `/api/briefings/calendar-badges?from=${year}-01-01&to=${year}-12-31`,
    fetcher,
  )
  const badgesByDate: Record<string, DayBadge> = {}
  for (const d of (badgesResp?.days || [])) badgesByDate[d.brief_date] = d
  const [hoverDate, setHoverDate] = useState<string | null>(null)

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {Array.from({ length: 12 }, (_, m) => (
        <MiniMonth
          key={m}
          year={year}
          month={m}
          events={events}
          todayIso={todayIso}
          badgesByDate={badgesByDate}
          hoverDate={hoverDate}
          onHover={setHoverDate}
        />
      ))}
    </div>
  )
}
