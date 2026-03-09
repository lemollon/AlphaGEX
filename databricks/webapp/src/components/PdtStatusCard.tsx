'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'

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

export default function PdtStatusCard({
  bot,
  accent,
}: {
  bot: 'flame' | 'spark'
  accent: 'amber' | 'blue'
}) {
  const { data, mutate } = useSWR<PdtStatus>(`/api/${bot}/pdt`, fetcher, {
    refreshInterval: 15_000,
  })

  const [confirmOff, setConfirmOff] = useState(false)
  const [confirmReset, setConfirmReset] = useState(false)
  const [busy, setBusy] = useState(false)

  if (!data) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card p-4 animate-pulse">
        <div className="h-4 bg-forge-border rounded w-32 mb-3" />
        <div className="h-3 bg-forge-border rounded w-48" />
      </div>
    )
  }

  const pct = data.max_day_trades > 0 ? (data.day_trade_count / data.max_day_trades) * 100 : 0
  const barColor =
    data.day_trade_count === 0
      ? 'bg-emerald-500'
      : data.day_trade_count >= data.max_day_trades
        ? 'bg-red-500'
        : 'bg-amber-500'

  async function handleToggle(enabled: boolean) {
    setBusy(true)
    setConfirmOff(false)
    // Optimistic update
    mutate({ ...data!, pdt_enabled: enabled }, false)
    try {
      await fetch(`/api/${bot}/pdt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'toggle', enabled }),
      })
      mutate()
    } catch {
      mutate() // Revert on error
    } finally {
      setBusy(false)
    }
  }

  async function handleReset() {
    setBusy(true)
    setConfirmReset(false)
    mutate({ ...data!, day_trade_count: 0, trades_remaining: data!.max_day_trades, is_blocked: false, block_reason: null }, false)
    try {
      await fetch(`/api/${bot}/pdt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'reset' }),
      })
      mutate()
    } catch {
      mutate()
    } finally {
      setBusy(false)
    }
  }

  function formatResetTime(ts: string | null, by: string | null): string {
    if (!ts) return 'Never'
    try {
      const d = new Date(ts)
      const fmt = d.toLocaleDateString('en-US', {
        month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
        timeZone: 'America/Chicago',
      })
      return `${fmt} CT${by ? ` (${by})` : ''}`
    } catch {
      return ts
    }
  }

  const accentBorder = accent === 'amber' ? 'border-amber-500/30' : 'border-blue-500/30'

  return (
    <div className={`rounded-xl border ${accentBorder} bg-forge-card p-4 space-y-3`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-white">PDT Status</span>
        <span className={`text-xs ${accent === 'amber' ? 'text-amber-400' : 'text-blue-400'}`}>
          {data.bot_name}
        </span>
      </div>

      {/* Toggle */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-forge-muted">Enforcement</span>
        <div className="flex gap-1">
          <button
            onClick={() => data.pdt_enabled ? null : handleToggle(true)}
            disabled={busy || data.pdt_enabled}
            className={`px-3 py-1 text-xs rounded-l font-medium transition-colors ${
              data.pdt_enabled
                ? `${accent === 'amber' ? 'bg-amber-600 text-white' : 'bg-blue-600 text-white'}`
                : 'bg-forge-border text-forge-muted hover:text-white'
            }`}
          >
            ON
          </button>
          <button
            onClick={() => {
              if (!data.pdt_enabled) return
              setConfirmOff(true)
            }}
            disabled={busy || !data.pdt_enabled}
            className={`px-3 py-1 text-xs rounded-r font-medium transition-colors ${
              !data.pdt_enabled
                ? 'bg-gray-600 text-white'
                : 'bg-forge-border text-forge-muted hover:text-white'
            }`}
          >
            OFF
          </button>
        </div>
      </div>

      {/* Confirmation dialog for toggling OFF */}
      {confirmOff && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-xs space-y-2">
          <p className="text-red-400">
            Disabling PDT enforcement will allow unlimited day trades. Are you sure?
          </p>
          <div className="flex gap-2 justify-end">
            <button
              onClick={() => setConfirmOff(false)}
              className="px-3 py-1 rounded border border-forge-border text-forge-muted hover:text-white"
            >
              Cancel
            </button>
            <button
              onClick={() => handleToggle(false)}
              className="px-3 py-1 rounded bg-red-600 text-white hover:bg-red-500"
            >
              Disable PDT
            </button>
          </div>
        </div>
      )}

      {/* Day Trade Counter */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-forge-muted">
            Day Trades: {data.day_trade_count} / {data.max_day_trades}{' '}
            <span className="text-forge-muted/60">(rolling {data.window_days} days)</span>
          </span>
          <span className="text-xs text-forge-muted">{Math.round(pct)}%</span>
        </div>
        <div className="h-2 bg-forge-border rounded-full overflow-hidden">
          <div
            className={`h-full ${barColor} rounded-full transition-all duration-300`}
            style={{ width: `${Math.min(100, pct)}%` }}
          />
        </div>
      </div>

      {/* Status row */}
      <div className="flex items-center justify-between text-xs">
        <span className="text-forge-muted">
          Traded Today: {data.traded_today ? 'Yes' : 'No'}
        </span>
        <span>
          {!data.pdt_enabled ? (
            <span className="text-amber-400">&#9888;&#65039; PDT BYPASSED</span>
          ) : data.is_blocked ? (
            <span className="text-red-400">
              &#128308; BLOCKED &mdash; {data.block_reason}
            </span>
          ) : (
            <span className="text-emerald-400">&#9989; CAN TRADE</span>
          )}
        </span>
      </div>

      {/* Reset Button */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-forge-muted/60">
          Last Reset: {formatResetTime(data.last_reset_at, data.last_reset_by)}
        </span>
        <button
          onClick={() => setConfirmReset(true)}
          disabled={busy || data.day_trade_count === 0}
          className="px-3 py-1 text-xs rounded border border-forge-border text-forge-muted hover:text-white hover:border-forge-muted transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          RESET COUNTER
        </button>
      </div>

      {/* Reset confirmation */}
      {confirmReset && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 text-xs space-y-2">
          <p className="text-amber-400">Reset the day trade counter to 0?</p>
          <div className="flex gap-2 justify-end">
            <button
              onClick={() => setConfirmReset(false)}
              className="px-3 py-1 rounded border border-forge-border text-forge-muted hover:text-white"
            >
              Cancel
            </button>
            <button
              onClick={handleReset}
              className={`px-3 py-1 rounded text-white ${accent === 'amber' ? 'bg-amber-600 hover:bg-amber-500' : 'bg-blue-600 hover:bg-blue-500'}`}
            >
              Reset
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
