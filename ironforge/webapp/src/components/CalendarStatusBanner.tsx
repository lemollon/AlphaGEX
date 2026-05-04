'use client'

import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'

interface BlackoutStatus {
  bot: string
  now: string
  blackout: { blocked: boolean; eventTitle?: string; resumesAt?: string }
  next_blackout: { title: string; halt_start_ts: string; halt_end_ts: string } | null
}

function fmtCT(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    timeZone: 'America/Chicago',
    weekday: 'short', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit', hour12: true,
  }) + ' CT'
}

function fmtDuration(ms: number): string {
  const totalMin = Math.max(0, Math.floor(ms / 60000))
  const days = Math.floor(totalMin / (24 * 60))
  const hours = Math.floor((totalMin % (24 * 60)) / 60)
  const mins = totalMin % 60
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${mins}m`
  return `${mins}m`
}

export default function CalendarStatusBanner() {
  const { data, isLoading } = useSWR<BlackoutStatus>(
    '/api/calendar/blackout-status?bot=flame',
    fetcher,
    { refreshInterval: 60_000 },
  )
  if (isLoading || !data) return <div className="h-16 bg-forge-card rounded animate-pulse" />

  const now = new Date(data.now).getTime()
  if (data.blackout.blocked && data.blackout.resumesAt) {
    const resumes = new Date(data.blackout.resumesAt)
    return (
      <div className="rounded-lg border border-amber-700/60 bg-amber-950/40 p-4">
        <div className="text-amber-300 font-medium">⚠ Event blackout in effect — {data.blackout.eventTitle}</div>
        <div className="text-sm text-amber-200/80 mt-1">
          No new entries until {fmtCT(data.blackout.resumesAt)} (resumes in {fmtDuration(resumes.getTime() - now)})
        </div>
      </div>
    )
  }

  if (data.next_blackout) {
    const start = new Date(data.next_blackout.halt_start_ts)
    return (
      <div className="rounded-lg border border-emerald-800/40 bg-emerald-950/20 p-4">
        <div className="text-emerald-300 font-medium">✓ Trading normally</div>
        <div className="text-sm text-emerald-200/80 mt-1">
          Next blackout: {data.next_blackout.title} starts {fmtCT(data.next_blackout.halt_start_ts)} (in {fmtDuration(start.getTime() - now)})
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-emerald-800/40 bg-emerald-950/20 p-4">
      <div className="text-emerald-300 font-medium">✓ Trading normally</div>
      <div className="text-sm text-emerald-200/80 mt-1">No upcoming blackouts scheduled.</div>
    </div>
  )
}
