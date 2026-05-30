'use client'

import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import { signalDisplayName, directionClass } from '@/lib/volatility'
import type { VolAlert } from '@/lib/volAlerts'

const REFRESH = 60_000
const LABEL = 'text-[10px] text-forge-muted uppercase tracking-wider'

interface AlertsPayload {
  alerts: VolAlert[]
}

/** Format an ISO timestamp in Central Time, e.g. "May 30, 9:42 AM CT". */
function fmtCT(iso?: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return (
    d.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      timeZone: 'America/Chicago',
    }) + ' CT'
  )
}

function StatusChip({ status }: { status: string }) {
  const active = status === 'active'
  return (
    <span
      className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wider ${
        active
          ? 'border-emerald-500/40 text-emerald-400'
          : 'border-forge-border text-forge-muted'
      }`}
    >
      {active ? 'active' : 'resolved'}
    </span>
  )
}

function AlertRow({ alert }: { alert: VolAlert }) {
  return (
    <div className="rounded-lg border border-forge-border bg-forge-bg/40 px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-semibold ${directionClass(alert.direction)}`}>
            {signalDisplayName(alert.signal_key)}
          </span>
          <StatusChip status={alert.status} />
        </div>
        <span className="font-mono text-[10px] text-forge-muted">
          {fmtCT(alert.fired_at)}
          {alert.status === 'resolved' && alert.resolved_at
            ? ` → ${fmtCT(alert.resolved_at)}`
            : ''}
        </span>
      </div>
      {(alert.headline || alert.message) && (
        <p className="mt-1 text-[11px] leading-snug text-white/80">
          {alert.headline || alert.message}
        </p>
      )}
      {alert.headline && alert.message && alert.message !== alert.headline && (
        <p className="mt-0.5 text-[11px] leading-snug text-forge-muted">{alert.message}</p>
      )}
    </div>
  )
}

/**
 * Recent volatility-regime trigger alerts (active + resolved), newest first.
 * Reads /api/vol-alerts?status=all. Renders a quiet empty state when none.
 */
export default function AlertsFeed() {
  const { data } = useSWR<AlertsPayload>('/api/vol-alerts?status=all', fetcher, {
    refreshInterval: REFRESH,
  })
  const alerts = data?.alerts ?? []

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <div className={`${LABEL} mb-3`}>Recent regime alerts</div>
      {alerts.length > 0 ? (
        <div className="space-y-2">
          {alerts.map((a) => (
            <AlertRow key={a.id} alert={a} />
          ))}
        </div>
      ) : (
        <p className="text-xs text-forge-muted">
          No trigger alerts yet — fires when a directional vol signal flips active.
        </p>
      )}
    </section>
  )
}
