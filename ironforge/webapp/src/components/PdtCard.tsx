'use client'

import { useState, useEffect, useCallback } from 'react'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface PdtStatus {
  bot_name: string
  pdt_enabled: boolean
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

  /* ---- Fetch PDT status ---- */
  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`/api/${bot}/pdt`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setStatus(data)
      setError(null)
    } catch (e: any) {
      setError(e.message)
    }
  }, [bot])

  const fetchAudit = useCallback(async () => {
    try {
      const res = await fetch(`/api/${bot}/pdt/audit`)
      if (!res.ok) return
      const data = await res.json()
      setAudit(data.entries || [])
    } catch {}
  }, [bot])

  // Initial fetch + 15s polling
  useEffect(() => {
    fetchStatus()
    const timer = setInterval(fetchStatus, 15_000)
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
    } catch (e: any) {
      // Rollback optimistic update
      fetchStatus()
      setError(e.message)
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
    } catch (e: any) {
      setError(e.message)
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
  let statusIcon: string
  let statusText: string
  let statusClass: string

  if (!status.pdt_enabled) {
    statusIcon = '\u26A0\uFE0F'
    statusText = 'PDT BYPASSED \u2014 trading unrestricted'
    statusClass = 'text-amber-400'
  } else if (status.is_blocked) {
    statusIcon = '\uD83D\uDD34'
    statusText = `BLOCKED \u2014 ${status.block_reason}`
    statusClass = 'text-red-400'
  } else {
    statusIcon = '\u2705'
    statusText = 'CAN TRADE'
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

      {/* Traded today + Status */}
      <div className="grid grid-cols-2 gap-4 mb-3 text-sm">
        <div>
          <span className="text-xs text-forge-muted">Traded Today:</span>
          <span className="ml-2 text-white">{status.traded_today ? 'Yes' : 'No'}</span>
        </div>
        <div>
          <span className="text-xs text-forge-muted">Status:</span>
          <span className={`ml-2 ${statusClass}`}>
            {statusIcon} {statusText}
          </span>
        </div>
      </div>

      {/* Reset button + last reset */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setConfirmAction('reset')}
          disabled={loading || count === 0}
          className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
            count === 0
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
