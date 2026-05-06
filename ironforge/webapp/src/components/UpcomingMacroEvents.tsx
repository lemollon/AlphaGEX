'use client'

import useSWR from 'swr'
import { useState } from 'react'
import { fetcher } from '@/lib/fetcher'
import {
  getPlaybook,
  getEventStrategy,
  type PlaybookTier,
  type EventStrategyKind,
} from '@/lib/eventCalendar/playbook'

interface CalendarEvent {
  event_id: string
  source: string
  event_type: string
  title: string
  event_date: string       // YYYY-MM-DD
  event_time_ct: string    // HH:MM
  halt_start_ts: string
  halt_end_ts: string
  resume_offset_min?: number
  halts_bots?: boolean
}

const STRATEGY_BADGE: Record<EventStrategyKind, { cls: string }> = {
  pre_market: {
    cls: 'bg-emerald-900/40 text-emerald-300 border border-emerald-700/40',
  },
  mid_day: {
    cls: 'bg-red-900/40 text-red-300 border border-red-700/40',
  },
  no_halt: {
    cls: 'bg-gray-800/40 text-gray-400 border border-gray-700/40',
  },
}

const TIER_BADGE: Record<PlaybookTier, { label: string; cls: string; cellCls: string }> = {
  tier1: {
    label: 'Tier 1',
    cls: 'bg-red-900/40 text-red-300 border border-red-700/40',
    cellCls: 'border-l-2 border-red-700/60',
  },
  tier2: {
    label: 'Tier 2',
    cls: 'bg-amber-900/40 text-amber-300 border border-amber-700/40',
    cellCls: 'border-l-2 border-amber-700/60',
  },
  tier3: {
    label: 'Tier 3',
    cls: 'bg-gray-800/40 text-gray-400 border border-gray-700/40',
    cellCls: 'border-l-2 border-gray-700/60',
  },
}

function todayPlus(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function fmtDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!m) return iso
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  const dow = new Date(iso + 'T12:00:00Z').toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' })
  return `${dow} ${months[Number(m[2]) - 1]} ${Number(m[3])}`
}

function fmtHaltSpan(haltStart: string, haltEnd: string): string {
  const a = new Date(haltStart).toLocaleString('en-US', {
    timeZone: 'America/Chicago', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit', hour12: true,
  })
  const b = new Date(haltEnd).toLocaleString('en-US', {
    timeZone: 'America/Chicago', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit', hour12: true,
  })
  return `${a} → ${b} CT`
}

export default function UpcomingMacroEvents() {
  const from = todayPlus(0)
  const to   = todayPlus(30)
  const { data, isLoading } = useSWR<{ events: CalendarEvent[] }>(
    `/api/calendar/events?from=${from}&to=${to}`,
    fetcher,
    { refreshInterval: 5 * 60 * 1000 },
  )
  const [openId, setOpenId] = useState<string | null>(null)

  if (isLoading) {
    return <div className="text-sm text-gray-500">Loading upcoming events…</div>
  }
  const events = (data?.events || []).slice().sort(
    (a, b) => a.event_date.localeCompare(b.event_date),
  )

  return (
    <section className="bg-forge-card/40 border border-gray-800 rounded-lg p-4 space-y-3">
      <header className="space-y-1">
        <div className="flex items-baseline justify-between">
          <h2 className="text-amber-300 text-sm uppercase tracking-wider">
            Upcoming 30 Days · Macro Events
          </h2>
          <div className="text-[11px] text-gray-500">
            Tier 1 = halts the bots · Tier 2 = watch · Tier 3 = informational
          </div>
        </div>
        <div className="text-[11px] text-gray-400 leading-snug">
          <span className="text-amber-300/80">Day-of-news policy:</span>{' '}
          pre-market releases → bots trade at the 8:30 AM CT open ·
          mid-day releases → bots resume 30 min after the print.
          No multi-day blackouts.
        </div>
      </header>

      {events.length === 0 ? (
        <div className="text-sm text-gray-500 italic py-4">
          No scheduled macro events in the next 30 days.
        </div>
      ) : (
        <ul className="space-y-2">
          {events.map(ev => {
            const pb = getPlaybook(ev.event_type)
            const tierMeta = TIER_BADGE[pb.tier]
            const haltsBots = ev.halts_bots ?? pb.halts_bots
            const strategy = getEventStrategy(
              ev.event_type,
              ev.event_time_ct,
              haltsBots,
              ev.resume_offset_min ?? 30,
            )
            const stratMeta = STRATEGY_BADGE[strategy.kind]
            const isOpen = openId === ev.event_id
            return (
              <li key={ev.event_id} className={`bg-forge-card/70 rounded ${tierMeta.cellCls}`}>
                <button
                  onClick={() => setOpenId(isOpen ? null : ev.event_id)}
                  className="w-full text-left px-3 py-2 flex items-center gap-3 hover:bg-forge-card transition-colors"
                >
                  <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded ${tierMeta.cls}`}>
                    {tierMeta.label}
                  </span>
                  <span className="text-sm text-gray-200 font-medium w-32 shrink-0">
                    {fmtDate(ev.event_date)}
                  </span>
                  <span className="text-xs text-gray-400 w-16 shrink-0">
                    {ev.event_time_ct} CT
                  </span>
                  <span className="text-sm text-gray-200 flex-1 truncate">
                    {pb.display_name}
                  </span>
                  <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded hidden md:inline ${stratMeta.cls}`}>
                    {strategy.label}
                  </span>
                  <span className="text-amber-400 text-xs">{isOpen ? '−' : '+'}</span>
                </button>

                {isOpen && (
                  <div className="px-3 pb-3 pt-1 space-y-3 border-t border-gray-800">
                    <p className="text-sm text-gray-300 italic">{pb.one_liner}</p>

                    <div className={`rounded border px-3 py-2 ${stratMeta.cls.replace('text-', 'border-').replace('border border-', 'border-')} bg-forge-card/40 border-l-2`}>
                      <div className="text-[10px] uppercase tracking-wider text-amber-300/80 mb-1">
                        Bot strategy · {strategy.label}
                      </div>
                      <p className="text-sm text-gray-200">{strategy.detail}</p>
                    </div>

                    <div className="grid md:grid-cols-2 gap-3 text-sm">
                      <div>
                        <div className="text-amber-300 text-xs uppercase tracking-wider mb-1">Pre-event</div>
                        <p className="text-gray-300">{pb.pre_event}</p>
                      </div>
                      <div>
                        <div className="text-amber-300 text-xs uppercase tracking-wider mb-1">Post-event</div>
                        <p className="text-gray-300">{pb.post_event}</p>
                      </div>
                    </div>

                    {pb.pattern && (
                      <div>
                        <div className="text-amber-300 text-xs uppercase tracking-wider mb-1">Common pattern</div>
                        <p className="text-gray-200 text-sm">{pb.pattern}</p>
                      </div>
                    )}

                    <div className="text-xs text-gray-400 grid md:grid-cols-2 gap-y-1 pt-2 border-t border-gray-800">
                      <div>
                        <span className="text-gray-500">Title</span>{' '}
                        <span className="text-gray-300">{ev.title}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Source</span>{' '}
                        <span className="text-gray-300 uppercase tracking-wider">{ev.source}</span>
                      </div>
                      <div className="md:col-span-2">
                        <span className="text-gray-500">Halt window</span>{' '}
                        <span className={haltsBots ? 'text-red-300' : 'text-gray-400'}>
                          {haltsBots ? fmtHaltSpan(ev.halt_start_ts, ev.halt_end_ts) : 'No halt — bots continue trading'}
                        </span>
                      </div>
                    </div>

                    {pb.sources.length > 0 && (
                      <div className="text-[11px] text-gray-500 pt-2 border-t border-gray-800">
                        Research:{' '}
                        {pb.sources.map((s, i) => (
                          <span key={s.url}>
                            {i > 0 ? ' · ' : ''}
                            <a
                              href={s.url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-amber-400 hover:text-amber-300 underline-offset-2 hover:underline"
                            >
                              {s.label}
                            </a>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
