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

/** One row of the IronForge regime-daily history (only the fields we read). */
interface RegimeDailyRow {
  regime_label: string | null
  active_signals: string[] | null
  updated_at: string | null
}
interface RegimeDailyPayload {
  rows: RegimeDailyRow[]
}

/** Current per-signal ladder state from /api/vol-alerts/ladder. */
interface LadderStateRow {
  signal_key: string
  state: string
  direction: string | null
  proximity: number | null
}
interface LadderPayload {
  states: LadderStateRow[]
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

/**
 * Pre-confirmation ladder strip: signals that have TRIPPED (crossed trigger, not
 * yet debounce-confirmed) or are on WATCH (approaching). Surfaces the never-drop
 * observation layer so an early sign is visible before it becomes a full alert.
 * Confirmed signals already show as active rows below; idle ones are hidden.
 */
function LadderStrip({ states }: { states: LadderStateRow[] }) {
  const pre = states
    .filter((s) => s.state === 'tripped' || s.state === 'watch')
    .sort((a) => (a.state === 'tripped' ? -1 : 1)) // tripped first
  if (pre.length === 0) return null
  return (
    <div className="mb-2 flex flex-wrap gap-1.5">
      {pre.map((s) => {
        const tripped = s.state === 'tripped'
        const cls = tripped
          ? 'border-amber-500/40 text-amber-300 bg-amber-500/10'
          : 'border-sky-500/40 text-sky-300 bg-sky-500/10'
        const pct = s.proximity != null ? ` ${(s.proximity * 100).toFixed(0)}%` : ''
        return (
          <span
            key={s.signal_key}
            className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wider ${cls}`}
            title={tripped ? 'Crossed trigger — not yet confirmed' : 'Approaching trigger'}
          >
            {tripped ? '⚠ ' : ''}
            {signalDisplayName(s.signal_key)} · {tripped ? 'tripped' : `watch${pct}`}
          </span>
        )
      })}
    </div>
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
  // Latest scanner regime read — proves the feed is live even when nothing has
  // fired. `updated_at` is stamped every 5-min scanner cycle (regime_daily).
  const { data: regime } = useSWR<RegimeDailyPayload>('/api/regime/daily?days=1', fetcher, {
    refreshInterval: REFRESH,
  })
  // Escalation ladder — surfaces watch/tripped signals before they confirm.
  const { data: ladder } = useSWR<LadderPayload>('/api/vol-alerts/ladder?events=1', fetcher, {
    refreshInterval: REFRESH,
  })
  const alerts = data?.alerts ?? []
  const latest = regime?.rows?.[0]
  const activeCount = alerts.filter((a) => a.status === 'active').length

  // Freshness line: when last checked + current regime, so a quiet feed reads as
  // "live and calm" rather than "frozen/dead".
  let freshness: string | null = null
  if (latest?.updated_at) {
    const regimeLabel = (latest.regime_label || '—').replace(/_/g, ' ')
    const statePart =
      activeCount > 0
        ? `${activeCount} active alert${activeCount === 1 ? '' : 's'}`
        : 'no active alerts'
    freshness = `Live · checked ${fmtCT(latest.updated_at)} · regime ${regimeLabel} · ${statePart}`
  }

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
        <span className={LABEL}>Recent regime alerts</span>
        {freshness && (
          <span className="font-mono text-[10px] text-forge-muted">{freshness}</span>
        )}
      </div>
      <LadderStrip states={ladder?.states ?? []} />
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
