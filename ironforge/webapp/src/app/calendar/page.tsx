'use client'

import useSWR from 'swr'
import Link from 'next/link'
import { useState } from 'react'
import { fetcher } from '@/lib/fetcher'
import CalendarStatusBanner from '@/components/CalendarStatusBanner'
import CalendarMonthGrid from '@/components/CalendarMonthGrid'
import UpcomingMacroEvents from '@/components/UpcomingMacroEvents'

export default function CalendarPage() {
  const [year, setYear] = useState(new Date().getFullYear())
  const from = `${year}-01-01`
  const to   = `${year}-12-31`
  const { data, isLoading } = useSWR<{ events: any[] }>(
    `/api/calendar/events?from=${from}&to=${to}`,
    fetcher,
    { refreshInterval: 5 * 60 * 1000 },
  )

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Calendar</h1>
        <Link href="/calendar/admin" className="text-sm text-amber-400 hover:text-amber-300">
          + Manage events
        </Link>
      </div>

      <CalendarStatusBanner />

      <section className="rounded-lg border border-amber-800/40 bg-amber-950/20 p-4 text-sm">
        <div className="text-amber-300 font-medium mb-1">Day-of-news halt policy</div>
        <div className="text-amber-200/80 leading-snug">
          IronForge IC bots (FLAME · SPARK · INFERNO) only stand aside on the
          actual release day — not the days before.
        </div>
        <ul className="mt-2 space-y-1 text-gray-300 list-disc list-inside marker:text-amber-500/60">
          <li>
            <span className="text-emerald-300">Pre-market release</span>{' '}
            (before 8:30 AM CT) — bots wake up and trade normally at the bell.
            IV crush has already happened by the time RTH opens.
          </li>
          <li>
            <span className="text-red-300">Mid-day release</span>{' '}
            (during RTH) — bots stay flat through the print and the initial
            whipsaw, then resume <span className="text-white">30 minutes after</span>{' '}
            the release.
          </li>
          <li>
            <span className="text-gray-300">Tier 2 / Tier 3 events</span> appear
            in the upcoming list for context but do not pause the bots.
          </li>
        </ul>
      </section>

      <UpcomingMacroEvents />

      <div className="flex items-center justify-between">
        <button
          onClick={() => setYear(y => y - 1)}
          className="text-sm text-gray-400 hover:text-gray-200"
        >
          ◀ {year - 1}
        </button>
        <div className="text-xl text-white">{year}</div>
        <button
          onClick={() => setYear(y => y + 1)}
          className="text-sm text-gray-400 hover:text-gray-200"
        >
          {year + 1} ▶
        </button>
      </div>

      {isLoading ? (
        <div className="text-gray-400">Loading…</div>
      ) : (
        <CalendarMonthGrid
          year={year}
          // Only halt-triggering events get the red blackout shading on
          // the year grid. Informational Tier-2/3 events still appear in
          // the Upcoming panel above with full context.
          events={(data?.events || []).filter((e: any) => e.halts_bots !== false)}
        />
      )}

      <div className="text-xs text-gray-500 flex gap-4 flex-wrap pt-2 border-t border-gray-800">
        <span><span className="inline-block w-3 h-3 rounded bg-emerald-900/30 align-middle mr-1" /> Trading day</span>
        <span><span className="inline-block w-3 h-3 rounded bg-red-800/40 align-middle mr-1" /> Event day (intraday halt)</span>
        <span><span className="inline-block w-3 h-3 rounded bg-gray-800/30 align-middle mr-1" /> Weekend</span>
      </div>
    </div>
  )
}
