'use client'

import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'

interface BlackoutStatus {
  blackout: { blocked: boolean; eventTitle?: string; resumesAt?: string }
  next_blackout: { title: string; halt_start_ts: string } | null
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

export default function EventBlackoutBanner({ bot }: { bot: string }) {
  const { data } = useSWR<BlackoutStatus>(
    `/api/calendar/blackout-status?bot=${bot}`,
    fetcher,
    { refreshInterval: 60_000 },
  )
  if (!data) return null
  const now = Date.now()

  if (data.blackout.blocked && data.blackout.resumesAt) {
    const resumes = new Date(data.blackout.resumesAt)
    return (
      <div className="rounded border border-amber-700/60 bg-amber-950/40 px-4 py-2 text-sm">
        <span className="text-amber-300 font-medium">⚠ Event blackout in effect — {data.blackout.eventTitle} </span>
        <span className="text-amber-200/80">
          · no new entries until {fmtCT(data.blackout.resumesAt)} (resumes in {fmtDuration(resumes.getTime() - now)})
        </span>
      </div>
    )
  }

  if (data.next_blackout) {
    const start = new Date(data.next_blackout.halt_start_ts)
    const ms = start.getTime() - now
    if (ms < 7 * 24 * 3600 * 1000 && ms > 0) {
      return (
        <div className="rounded border border-blue-800/40 bg-blue-950/20 px-4 py-2 text-sm">
          <span className="text-blue-300">
            ℹ Upcoming blackout: {data.next_blackout.title} begins {fmtCT(data.next_blackout.halt_start_ts)} ({fmtDuration(ms)})
          </span>
        </div>
      )
    }
  }
  return null
}
