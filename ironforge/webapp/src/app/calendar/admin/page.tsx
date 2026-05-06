'use client'

import useSWR, { mutate } from 'swr'
import Link from 'next/link'
import { useState } from 'react'
import { fetcher } from '@/lib/fetcher'

export default function CalendarAdminPage() {
  const { data: meta } = useSWR<{ meta: any }>('/api/calendar/refresh', fetcher, { refreshInterval: 30_000 })
  const { data: events } = useSWR<{ events: any[] }>('/api/calendar/events', fetcher)
  const [refreshing, setRefreshing] = useState(false)
  const [form, setForm] = useState({
    title: '',
    event_type: 'CUSTOM',
    event_date: '',
    event_time_ct: '13:00',
    resume_offset_min: 30,
    description: '',
  })

  async function refreshNow() {
    setRefreshing(true)
    await fetch('/api/calendar/refresh', { method: 'POST' })
    await mutate('/api/calendar/refresh')
    await mutate('/api/calendar/events')
    setRefreshing(false)
  }

  async function addEvent(e: React.FormEvent) {
    e.preventDefault()
    const res = await fetch('/api/calendar/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })
    if (res.ok) {
      setForm({ title: '', event_type: 'CUSTOM', event_date: '', event_time_ct: '13:00', resume_offset_min: 30, description: '' })
      await mutate('/api/calendar/events')
    } else {
      alert('Failed to add event: ' + (await res.text()))
    }
  }

  async function deleteEvent(eventId: string) {
    if (!confirm('Soft-delete this event?')) return
    await fetch(`/api/calendar/events/${encodeURIComponent(eventId)}`, { method: 'DELETE' })
    await mutate('/api/calendar/events')
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Manage Events</h1>
        <Link href="/calendar" className="text-sm text-gray-400 hover:text-gray-200">← Back to calendar</Link>
      </div>

      <section className="bg-forge-card rounded-lg p-4">
        <h2 className="text-lg text-amber-300 mb-2">Refresh status</h2>
        <div className="text-sm text-gray-300 space-y-1">
          <div>
            Last refresh: {meta?.meta?.last_refresh_ts
              ? new Date(meta.meta.last_refresh_ts).toLocaleString('en-US', { timeZone: 'America/Chicago' }) + ' CT'
              : '— never —'}
          </div>
          <div>
            Status: <span className={meta?.meta?.last_refresh_status === 'ok' ? 'text-emerald-400' : 'text-red-400'}>
              {meta?.meta?.last_refresh_status || '—'}
            </span>
          </div>
          <div>Events added: {meta?.meta?.events_added ?? 0} · updated: {meta?.meta?.events_updated ?? 0}</div>
        </div>
        <button
          onClick={refreshNow}
          disabled={refreshing}
          className="mt-3 px-3 py-1.5 rounded bg-amber-700 hover:bg-amber-600 text-white text-sm disabled:opacity-50"
        >
          {refreshing ? 'Refreshing…' : 'Refresh now'}
        </button>
      </section>

      <section className="bg-forge-card rounded-lg p-4">
        <h2 className="text-lg text-amber-300 mb-3">Add custom event</h2>
        <form onSubmit={addEvent} className="grid grid-cols-2 gap-3 text-sm">
          <label className="flex flex-col text-gray-300">Title
            <input
              value={form.title}
              onChange={e => setForm({ ...form, title: e.target.value })}
              required
              className="bg-forge-bg border border-gray-700 rounded px-2 py-1 text-white"
            />
          </label>
          <label className="flex flex-col text-gray-300">Type
            <select
              value={form.event_type}
              onChange={e => setForm({ ...form, event_type: e.target.value })}
              className="bg-forge-bg border border-gray-700 rounded px-2 py-1 text-white"
            >
              <option>CUSTOM</option><option>CPI</option><option>NFP</option><option>PPI</option><option>OTHER</option>
            </select>
          </label>
          <label className="flex flex-col text-gray-300">Event date
            <input
              type="date"
              value={form.event_date}
              onChange={e => setForm({ ...form, event_date: e.target.value })}
              required
              className="bg-forge-bg border border-gray-700 rounded px-2 py-1 text-white"
            />
          </label>
          <label className="flex flex-col text-gray-300">Event time (CT)
            <input
              type="time"
              value={form.event_time_ct}
              onChange={e => setForm({ ...form, event_time_ct: e.target.value })}
              required
              className="bg-forge-bg border border-gray-700 rounded px-2 py-1 text-white"
            />
          </label>
          <label className="flex flex-col text-gray-300">Resume offset (min)
            <input
              type="number"
              min={0}
              value={form.resume_offset_min}
              onChange={e => setForm({ ...form, resume_offset_min: parseInt(e.target.value) || 0 })}
              className="bg-forge-bg border border-gray-700 rounded px-2 py-1 text-white"
            />
          </label>
          <label className="flex flex-col text-gray-300 col-span-2">Description
            <textarea
              rows={2}
              value={form.description}
              onChange={e => setForm({ ...form, description: e.target.value })}
              className="bg-forge-bg border border-gray-700 rounded px-2 py-1 text-white"
            />
          </label>
          <div className="col-span-2">
            <button type="submit" className="px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white text-sm">
              Add event
            </button>
          </div>
        </form>
      </section>

      <section className="bg-forge-card rounded-lg p-4">
        <h2 className="text-lg text-amber-300 mb-3">Active events</h2>
        <table className="w-full text-sm text-gray-300">
          <thead className="text-xs text-gray-500 uppercase border-b border-gray-700">
            <tr>
              <th className="text-left py-2">Date</th>
              <th className="text-left">Title</th>
              <th className="text-left">Source</th>
              <th className="text-left">Resumes</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(events?.events || []).map((ev: any) => (
              <tr key={ev.event_id} className="border-b border-gray-800">
                <td className="py-2">{ev.event_date}</td>
                <td>{ev.title}</td>
                <td className="text-xs uppercase text-gray-500">{ev.source}</td>
                <td className="text-xs">
                  {new Date(ev.halt_end_ts).toLocaleString('en-US', { timeZone: 'America/Chicago' })}
                </td>
                <td className="text-right">
                  {ev.source === 'manual'
                    ? <button onClick={() => deleteEvent(ev.event_id)} className="text-red-400 hover:text-red-300 text-xs">Delete</button>
                    : <span className="text-xs text-gray-600">read-only</span>}
                </td>
              </tr>
            ))}
            {(!events?.events || events.events.length === 0) && (
              <tr><td colSpan={5} className="py-4 text-center text-gray-500">No active events</td></tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  )
}
