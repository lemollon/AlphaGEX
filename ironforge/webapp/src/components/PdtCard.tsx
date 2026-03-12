'use client'

import { useState, useEffect, useCallback } from 'react'
import PdtCalendar from './PdtCalendar'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface TriggerTrade {
  trade_date: string
  falls_off: string
  position_ids?: string[]
}

interface PdtStatus {
  bot_name: string
  pdt_enabled: boolean
  pdt_status: 'BLOCKED' | 'CAN_TRADE' | 'TRADED_TODAY' | 'PDT_OFF'
  day_trade_count: number
  max_day_trades: number
  trades_remaining: number
  max_trades_per_day: number
  traded_today: boolean
  can_trade: boolean
  window_days: number
  last_reset_at: string | null
  last_reset_by: string | null
  is_blocked: boolean
  block_reason: string | null
  trigger_trades: TriggerTrade[]
  next_slot_opens: string | null
  next_available_date: string | null
}

interface AuditEntry {
  action: string
  old_value: string | null
  new_value: string | null
  reason: string | null
  performed_by: string | null
  created_at: string | null
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function PdtCard({
  bot,
  accent,
}: {
  bot: 'flame' | 'spark' | 'inferno'
  accent: 'amber' | 'blue' | 'red'
}) {
  const [status, setStatus] = useState<PdtStatus | null>(null)
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [showAudit, setShowAudit] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmAction, setConfirmAction] = useState<'toggle_off' | 'reset' | null>(null)
  const [todayStr, setTodayStr] = useState<string | null>(null)

  // Resolve "today" on client only to avoid hydration mismatch
  useEffect(() => {
    setTodayStr(new Date().toLocaleDateString('en-CA', { timeZone: 'America/Chicago' }))
  }, [])

  /* ---- Fetch PDT status ---- */
  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`/api/${bot}/pdt`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setStatus(data)
      setError(null)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [bot])

  const fetchAudit = useCallback(async () => {
    try {
      const res = await fetch(`/api/${bot}/pdt/audit`)
      if (!res.ok) return
      const data = await res.json()
      setAudit(data.entries || [])
    } catch (e: unknown) {
      console.error(`[PdtCard] Failed to fetch audit for ${bot}:`, e instanceof Error ? e.message : e)
    }
  }, [bot])

  // Initial fetch + 60s polling (PDT status only changes when a trade executes)
  useEffect(() => {
    fetchStatus()
    const timer = setInterval(fetchStatus, 60_000)
    return () => clearInterval(timer)
  }, [fetchStatus])

  // Fetch audit when expanded
  useEffect(() => {
    if (showAudit) fetchAudit()
  }, [showAudit, fetchAudit])

  /* ---- Actions ---- */

  async function doToggle(enabled: boolean) {
    setLoading(true)
    setConfirmAction(null)
    // Optimistic update
    if (status) setStatus({ ...status, pdt_enabled: enabled })
    try {
      const res = await fetch(`/api/${bot}/pdt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'toggle', enabled }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setStatus(data)
    } catch (e: unknown) {
      fetchStatus()
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  async function doReset() {
    setLoading(true)
    setConfirmAction(null)
    try {
      const res = await fetch(`/api/${bot}/pdt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'reset' }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setStatus(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  /* ---- Render ---- */

  if (error && !status) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
        PDT status unavailable: {error}
      </div>
    )
  }

  if (!status) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4 animate-pulse">
        <div className="h-4 bg-forge-border rounded w-32 mb-2" />
        <div className="h-6 bg-forge-border rounded w-48" />
      </div>
    )
  }

  const accentBorder = accent === 'amber' ? 'border-amber-500/30' : accent === 'red' ? 'border-red-500/30' : 'border-blue-500/30'
  const accentText = accent === 'amber' ? 'text-amber-400' : accent === 'red' ? 'text-red-400' : 'text-blue-400'
  const count = status.day_trade_count
  const max = status.max_day_trades
  const pct = max > 0 ? (count / max) * 100 : 0

  // Progress bar color
  const barColor =
    count >= max ? 'bg-red-500' : count >= max - 1 ? 'bg-amber-500' : 'bg-emerald-500'

  // Status indicator
  let statusText: string
  let statusClass: string

  // Format next_available_date for inline display
  const nextDateFormatted = status.next_available_date
    ? new Date(status.next_available_date + 'T12:00:00').toLocaleDateString('en-US', {
        timeZone: 'America/Chicago',
        weekday: 'short',
        month: 'short',
        day: 'numeric',
      })
    : null

  const pdtStatus = status.pdt_status
  const remaining = status.trades_remaining ?? (max - count)

  if (pdtStatus === 'PDT_OFF') {
    statusText = 'PDT OFF \u2014 Unlimited trading, counter auto-resets on toggle'
    statusClass = 'text-amber-400'
  } else if (pdtStatus === 'BLOCKED') {
    statusText = nextDateFormatted
      ? `BLOCKED \u2014 ${count}/${max} day trades used. Next slot opens ${nextDateFormatted}`
      : `BLOCKED \u2014 ${count}/${max} day trades used`
    statusClass = 'text-red-400'
  } else if (pdtStatus === 'TRADED_TODAY') {
    statusText = `TRADED TODAY \u2014 ${count}/${max} day trades used, next trade tomorrow`
    statusClass = 'text-amber-300'
  } else {
    statusText = `CLEAR \u2014 ${count}/${max} day trades used, ${remaining} remaining`
    statusClass = 'text-emerald-400'
  }

  return (
    <div className={`rounded-xl border ${accentBorder} bg-forge-card/80 p-4`}>
      {/* Confirmation dialog overlay */}
      {confirmAction && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-forge-card border border-forge-border rounded-xl p-6 max-w-md mx-4 shadow-xl">
            <h3 className="text-lg font-bold text-white mb-3">
              {confirmAction === 'toggle_off' ? 'Disable PDT Enforcement?' : 'Reset PDT Counter?'}
            </h3>
            <p className="text-sm text-gray-300 mb-5">
              {confirmAction === 'toggle_off'
                ? 'Disabling PDT enforcement will allow unlimited day trades. This bypasses the Pattern Day Trader safety limit. Are you sure?'
                : 'Reset the day trade counter to 0? This will allow the bot to trade again if it was PDT-blocked.'}
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setConfirmAction(null)}
                className="px-4 py-2 text-sm rounded-lg border border-forge-border text-gray-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() =>
                  confirmAction === 'toggle_off' ? doToggle(false) : doReset()
                }
                className={`px-4 py-2 text-sm rounded-lg font-medium transition-colors ${
                  confirmAction === 'toggle_off'
                    ? 'bg-amber-600 hover:bg-amber-500 text-white'
                    : 'bg-blue-600 hover:bg-blue-500 text-white'
                }`}
              >
                {confirmAction === 'toggle_off' ? 'Disable PDT' : 'Reset Counter'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-gray-300">PDT Status</h3>
          <span className={`text-xs ${accentText}`}>{status.bot_name}</span>
        </div>
      </div>

      {/* Toggle switch */}
      <div className="flex items-center gap-3 mb-4">
        <span className="text-xs text-forge-muted">Enforcement:</span>
        <div className="flex rounded-lg overflow-hidden border border-forge-border">
          <button
            onClick={() => {
              if (!status.pdt_enabled) doToggle(true)
            }}
            disabled={loading}
            className={`px-3 py-1 text-xs font-medium transition-colors ${
              status.pdt_enabled
                ? 'bg-amber-600/80 text-white'
                : 'bg-forge-card text-gray-500 hover:text-gray-300'
            }`}
          >
            ON
          </button>
          <button
            onClick={() => {
              if (status.pdt_enabled) setConfirmAction('toggle_off')
            }}
            disabled={loading}
            className={`px-3 py-1 text-xs font-medium transition-colors ${
              !status.pdt_enabled
                ? 'bg-gray-600 text-white'
                : 'bg-forge-card text-gray-500 hover:text-gray-300'
            }`}
          >
            OFF
          </button>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-3">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-forge-muted">
            Day Trades:{'  '}
            <span className="text-white font-mono">
              {!status.pdt_enabled ? `counter paused (${count} / ${max})` : `${count} / ${max}`}
            </span>
            <span className="text-forge-muted ml-1">(rolling {status.window_days} days)</span>
          </span>
          <span className="text-xs text-forge-muted font-mono">{Math.round(pct)}%</span>
        </div>
        <div className="w-full bg-forge-border rounded-full h-2">
          <div
            className={`${barColor} h-2 rounded-full transition-all duration-300`}
            style={{ width: `${Math.min(100, pct)}%` }}
          />
        </div>
      </div>

      {/* Today's Status — live indicator dot */}
      <div className="flex items-start gap-3 mb-3 rounded-lg bg-forge-bg/60 border border-forge-border/40 px-3 py-2.5">
        {/* Pulsing dot: outer ring pings, inner dot stays solid */}
        <div className="relative flex h-3 w-3 mt-0.5 shrink-0">
          {(pdtStatus === 'CAN_TRADE' || pdtStatus === 'TRADED_TODAY') && (
            <span
              className={`absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping ${
                pdtStatus === 'CAN_TRADE' ? 'bg-emerald-400' : 'bg-amber-400'
              }`}
            />
          )}
          <span
            className={`relative inline-flex rounded-full h-3 w-3 ${
              pdtStatus === 'PDT_OFF'
                ? 'bg-gray-500'
                : pdtStatus === 'BLOCKED'
                  ? 'bg-red-500'
                  : pdtStatus === 'TRADED_TODAY'
                    ? 'bg-amber-400'
                    : 'bg-emerald-400'
            }`}
          />
        </div>
        <div className="min-w-0">
          <div className={`text-sm font-medium ${statusClass}`}>{statusText}</div>
          {status.traded_today && (
            <div className="text-[11px] text-forge-muted mt-0.5">Traded today</div>
          )}
        </div>
      </div>

      {/* Trigger trades — which dates count toward PDT + when each slot opens */}
      {status.trigger_trades && status.trigger_trades.length > 0 && (
        <div className="mb-3 rounded-lg bg-forge-bg/60 border border-forge-border/40 p-3">
          <div className="text-[11px] text-forge-muted uppercase tracking-wide mb-2">
            Day Trades in Window
          </div>
          <div className="space-y-1.5">
            {status.trigger_trades.map((t, i) => {
              const td = new Date(t.trade_date + 'T12:00:00')
              const fo = new Date(t.falls_off + 'T12:00:00')
              const fmtDate = (d: Date) =>
                d.toLocaleDateString('en-US', {
                  timeZone: 'America/Chicago',
                  weekday: 'short',
                  month: 'short',
                  day: 'numeric',
                })
              // Highlight today's row (todayStr resolved in useEffect to avoid hydration mismatch)
              const isToday = todayStr ? t.trade_date === todayStr : false
              return (
                <div key={i} className={`text-xs rounded px-1.5 py-1 ${isToday ? 'bg-amber-500/10 border border-amber-500/30' : ''}`}>
                  <div className="flex items-center justify-between">
                    <span className="text-white font-mono">
                      #{i + 1} {fmtDate(td)}{isToday ? ' (today)' : ''}
                    </span>
                    <span className="text-forge-muted">
                      slot opens <span className="text-emerald-400">{fmtDate(fo)}</span>
                    </span>
                  </div>
                  {t.position_ids && t.position_ids.length > 0 && (
                    <div className="text-[10px] text-forge-muted mt-0.5 pl-4 font-mono">
                      {t.position_ids.join(', ')}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          {status.next_available_date && status.is_blocked && (
            <div className="mt-2 pt-2 border-t border-forge-border/30 text-[11px] text-amber-400">
              Next available trade:{' '}
              <span className="text-emerald-400 font-medium">
                {new Date(status.next_available_date + 'T12:00:00').toLocaleDateString('en-US', {
                  timeZone: 'America/Chicago',
                  weekday: 'long',
                  month: 'short',
                  day: 'numeric',
                })}
              </span>
            </div>
          )}
        </div>
      )}

      {/* 4-Week Trading Calendar */}
      <div className="mb-3">
        <PdtCalendar status={status} />
      </div>

      {/* Reset button + last reset */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setConfirmAction('reset')}
          disabled={loading || count === 0 || !status.pdt_enabled}
          className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
            count === 0 || !status.pdt_enabled
              ? 'border-forge-border text-gray-600 cursor-not-allowed'
              : 'border-forge-border text-gray-300 hover:text-white hover:border-gray-500'
          }`}
        >
          RESET COUNTER
        </button>

        {status.last_reset_at && (
          <span className="text-[11px] text-forge-muted">
            Last Reset:{' '}
            {new Date(status.last_reset_at).toLocaleString('en-US', {
              timeZone: 'America/Chicago',
              month: 'short',
              day: 'numeric',
              hour: 'numeric',
              minute: '2-digit',
              hour12: true,
            })}{' '}
            CT ({status.last_reset_by || 'unknown'})
          </span>
        )}
      </div>

      {/* Audit log (collapsible) */}
      <div className="mt-3 pt-3 border-t border-forge-border/50">
        <button
          onClick={() => setShowAudit(!showAudit)}
          className="text-[11px] text-forge-muted hover:text-gray-300 transition-colors"
        >
          {showAudit ? '\u25BC' : '\u25B6'} PDT History (last 10 events)
        </button>

        {showAudit && (
          <div className="mt-2 space-y-1">
            {audit.length === 0 && (
              <p className="text-[11px] text-forge-muted">No PDT events yet.</p>
            )}
            {audit.map((entry, i) => {
              // Parse old/new values for display
              let detail = ''
              if (entry.action === 'toggle_on' || entry.action === 'toggle_off') {
                detail = `enabled: ${entry.action === 'toggle_off' ? 'true\u2192false' : 'false\u2192true'}`
              } else if (entry.action === 'reset') {
                try {
                  const oldVal = JSON.parse(entry.old_value || '{}')
                  detail = `count: ${oldVal.day_trade_count ?? '?'}\u21920`
                } catch {
                  detail = 'count\u21920'
                }
              } else if (entry.action === 'day_trade_recorded') {
                try {
                  const oldVal = JSON.parse(entry.old_value || '{}')
                  const newVal = JSON.parse(entry.new_value || '{}')
                  detail = `count: ${oldVal.day_trade_count ?? '?'}\u2192${newVal.day_trade_count ?? '?'}`
                } catch {
                  detail = 'count +1'
                }
              } else if (entry.action === 'auto_decrement') {
                try {
                  const oldVal = JSON.parse(entry.old_value || '{}')
                  const newVal = JSON.parse(entry.new_value || '{}')
                  detail = `count: ${oldVal.day_trade_count ?? '?'}\u2192${newVal.day_trade_count ?? '?'}`
                } catch {
                  detail = 'auto-decrement'
                }
              }

              const time = entry.created_at
                ? new Date(entry.created_at).toLocaleString('en-US', {
                    timeZone: 'America/Chicago',
                    month: 'short',
                    day: 'numeric',
                    hour: 'numeric',
                    minute: '2-digit',
                    hour12: true,
                  })
                : '?'

              return (
                <div key={i} className="flex items-center gap-3 text-[11px] font-mono">
                  <span className="text-forge-muted w-32 shrink-0">{time}</span>
                  <span className="text-gray-300 w-36 shrink-0">{entry.action}</span>
                  <span className="text-gray-400">{detail}</span>
                  <span className="text-forge-muted">({entry.performed_by})</span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
