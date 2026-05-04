'use client'

import useSWR from 'swr'
import Link from 'next/link'
import { useState } from 'react'
import { fetcher } from '@/lib/fetcher'
import CalendarStatusBanner from '@/components/CalendarStatusBanner'
import CalendarMonthGrid from '@/components/CalendarMonthGrid'

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
        <CalendarMonthGrid year={year} events={data?.events || []} />
      )}

      <div className="text-xs text-gray-500 flex gap-4 flex-wrap pt-2 border-t border-gray-800">
        <span><span className="inline-block w-3 h-3 rounded bg-emerald-900/30 align-middle mr-1" /> Trading day</span>
        <span><span className="inline-block w-3 h-3 rounded bg-red-800/40 align-middle mr-1" /> Blackout day</span>
        <span><span className="inline-block w-3 h-3 rounded bg-gradient-to-r from-red-700/50 to-emerald-700/40 align-middle mr-1" /> Event day (split)</span>
        <span><span className="inline-block w-3 h-3 rounded bg-gray-800/30 align-middle mr-1" /> Weekend</span>
      </div>
    </div>
  )
}
