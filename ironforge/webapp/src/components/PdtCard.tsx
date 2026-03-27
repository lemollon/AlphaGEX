'use client'

import { useState, useEffect, useCallback } from 'react'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface PdtStatus {
  pdt_enabled: boolean
  bot_pdt_enabled?: boolean
  account_pdt_enabled?: boolean
  pdt_override_source?: string | null
  pdt_status: 'BLOCKED' | 'CAN_TRADE' | 'TRADED_TODAY' | 'PDT_OFF'
  day_trade_count: number
  max_day_trades: number
  trades_remaining: number
  max_trades_per_day: number
  traded_today: boolean
  can_trade: boolean
  window_days: number
  window_start: string | null
  window_end: string | null
  is_blocked: boolean
  next_available_date: string | null
  today_trade_time: string | null
}

interface BotStatus {
  bot_state?: string
  open_positions?: number
  scans_today?: number
  last_scan?: string | null
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function fmtDate(d: Date): string {
  return d.toLocaleDateString('en-US', {
    timeZone: 'America/Chicago',
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
}

function fmtDateFromStr(ds: string): string {
  return fmtDate(new Date(ds + 'T12:00:00'))
}

function fmtTime(isoStr: string): string {
  return new Date(isoStr).toLocaleTimeString('en-US', {
    timeZone: 'America/Chicago',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  })
}

function computeWindowStart(today: Date, windowDays: number): Date {
  const d = new Date(today)
  let remaining = windowDays - 1
  while (remaining > 0) {
    d.setDate(d.getDate() - 1)
    if (d.getDay() >= 1 && d.getDay() <= 5) remaining--
  }
  return d
}

function lastBizDay(d: Date): Date {
  const r = new Date(d)
  while (r.getDay() === 0 || r.getDay() === 6) r.setDate(r.getDate() - 1)
  return r
}

/* ------------------------------------------------------------------ */
/*  Compact PdtCard — 3 rows only                                      */
/*  Row 1: Status banner (colored strip + pulsing dot)                 */
/*  Row 2: Window progress bar                                         */
/*  Row 3: Today's status dot + one-liner                              */
/*  Everything else lives in the PDT tab (PdtTabContent.tsx)           */
/* ------------------------------------------------------------------ */

export default function PdtCard({
  bot,
  accent,
  botStatus,
  accountType,
}: {
  bot: 'flame' | 'spark' | 'inferno'
  accent: 'amber' | 'blue' | 'red'
  botStatus?: BotStatus | null
  accountType?: 'sandbox' | 'production'
}) {
  const [status, setStatus] = useState<PdtStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [todayStr, setTodayStr] = useState<string | null>(null)

  useEffect(() => {
    setTodayStr(new Date().toLocaleDateString('en-CA', { timeZone: 'America/Chicago' }))
  }, [])

  const fetchStatus = useCallback(async () => {
    try {
      const url = accountType ? `/api/${bot}/pdt?account_type=${accountType}` : `/api/${bot}/pdt`
      const res = await fetch(url)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setStatus(data)
      setError(null)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [bot, accountType])

  useEffect(() => {
    fetchStatus()
    const timer = setInterval(fetchStatus, 30_000)
    return () => clearInterval(timer)
  }, [fetchStatus])

  /* Error state */
  if (error && !status) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm">
        <span className="text-red-400">PDT status unavailable</span>
        <button
          onClick={fetchStatus}
          className="ml-3 px-2 py-0.5 text-xs rounded border border-red-500/30 text-red-400 hover:text-white transition-colors"
        >
          Retry
        </button>
      </div>
    )
  }

  /* Loading skeleton */
  if (!status) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-3 space-y-2">
        <div className="h-8 bg-forge-border/40 rounded-lg skeleton-pulse" />
        <div className="h-4 bg-forge-border/30 rounded w-2/3 skeleton-pulse" />
      </div>
    )
  }

  const count = status.day_trade_count
  const max = status.max_day_trades
  const pct = max > 0 ? (count / max) * 100 : 0
  const remaining = status.trades_remaining ?? Math.max(0, max - count)
  const pdtStatus = status.pdt_status

  const todayDate = todayStr ? new Date(todayStr + 'T12:00:00') : new Date()
  const effectiveToday = lastBizDay(todayDate)
  const windowStart = status.window_start
    ? new Date(status.window_start + 'T12:00:00')
    : computeWindowStart(effectiveToday, status.window_days)
  const windowEnd = status.window_end
    ? new Date(status.window_end + 'T12:00:00')
    : effectiveToday

  /* --- Status banner colors --- */
  let bg: string, dotColor: string, pulsing: boolean, primary: string, secondary: string

  if (pdtStatus === 'PDT_OFF') {
    bg = 'bg-gray-800/50'
    dotColor = 'bg-gray-400'
    pulsing = false
    primary = 'PDT BYPASSED'
    const src = status.pdt_override_source
    const dailyCap = status.max_trades_per_day > 0
      ? `Max ${status.max_trades_per_day} trade${status.max_trades_per_day > 1 ? 's' : ''}/day`
      : 'Unlimited trading'
    const srcLabel = src === 'bot_config' ? ' \u2014 bot config'
      : src === 'account' ? ' \u2014 account override'
      : ''
    secondary = dailyCap + srcLabel
  } else if (pdtStatus === 'BLOCKED') {
    bg = 'bg-red-900/30'
    dotColor = 'bg-red-400'
    pulsing = false
    primary = 'PDT BLOCKED'
    secondary = status.next_available_date
      ? `${count}/${max} used \u2014 opens ${fmtDateFromStr(status.next_available_date)}`
      : `${count}/${max} day trades used`
  } else if (pdtStatus === 'TRADED_TODAY') {
    bg = 'bg-amber-900/30'
    dotColor = 'bg-amber-400'
    pulsing = true
    primary = 'DONE FOR TODAY'
    secondary = status.today_trade_time
      ? `Traded ${fmtTime(status.today_trade_time)} CT`
      : 'Already traded today'
  } else {
    bg = 'bg-emerald-900/40'
    dotColor = 'bg-emerald-400'
    pulsing = true
    primary = 'CAN TRADE'
    secondary = `${remaining}/${max} slots`
  }

  const textColor = pdtStatus === 'BLOCKED' ? 'text-red-300'
    : pdtStatus === 'TRADED_TODAY' ? 'text-amber-300'
    : pdtStatus === 'PDT_OFF' ? 'text-gray-300'
    : 'text-emerald-300'

  const subColor = pdtStatus === 'BLOCKED' ? 'text-red-400/70'
    : pdtStatus === 'TRADED_TODAY' ? 'text-amber-400/60'
    : pdtStatus === 'PDT_OFF' ? 'text-gray-400'
    : 'text-emerald-400/70'

  /* --- Today status --- */
  const botState = botStatus?.bot_state
  const openPositions = botStatus?.open_positions ?? 0
  const scansToday = botStatus?.scans_today ?? 0

  let todayDot: string, todayPulsing: boolean, todayText: string, todayColor: string

  if (status.traded_today) {
    const timeStr = status.today_trade_time ? ` at ${fmtTime(status.today_trade_time)} CT` : ''
    if (openPositions > 0) {
      todayDot = 'bg-amber-400'; todayPulsing = true
      todayText = `Traded${timeStr} \u2014 position open`; todayColor = 'text-amber-300'
    } else {
      todayDot = 'bg-emerald-400'; todayPulsing = false
      todayText = `Traded${timeStr} \u2014 complete`; todayColor = 'text-emerald-300'
    }
  } else if (botState === 'market_closed') {
    todayDot = 'bg-gray-500'; todayPulsing = false
    todayText = 'Market closed'; todayColor = 'text-gray-500'
  } else if (pdtStatus === 'BLOCKED') {
    todayDot = 'bg-red-400'; todayPulsing = false
    todayText = 'Cannot trade \u2014 PDT blocked'; todayColor = 'text-red-400'
  } else if (botState === 'scanning' || botState === 'idle') {
    todayDot = 'bg-blue-400'; todayPulsing = true
    todayText = `Scanning (${scansToday} scans)`; todayColor = 'text-blue-400'
  } else {
    todayDot = 'bg-gray-500'; todayPulsing = false
    todayText = 'No trade yet'; todayColor = 'text-gray-400'
  }

  /* --- Window bar --- */
  const barColor = count >= max ? 'bg-red-500' : count >= max - 1 ? 'bg-amber-500' : 'bg-emerald-500'

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 overflow-hidden">
      {/* ROW 1: Status banner */}
      <div className={`px-4 py-2.5 flex items-center gap-3 ${bg} border-b border-forge-border/30`}>
        <div className="relative shrink-0 w-2.5 h-2.5">
          {pulsing && (
            <span className={`absolute inset-0 rounded-full ${dotColor} animate-ping opacity-40`} />
          )}
          <span className={`absolute inset-0 rounded-full ${dotColor}`} />
        </div>
        <div className="flex items-baseline gap-2">
          <span className={`text-xs font-bold tracking-wide ${textColor}`}>{primary}</span>
          <span className={`text-[11px] ${subColor}`}>{secondary}</span>
        </div>
      </div>

      <div className="px-4 py-2.5 space-y-2">
        {/* ROW 2: Window progress bar */}
        {status.pdt_enabled ? (
          <div>
            <div className="flex items-center justify-between text-[11px] mb-1">
              <span className="text-forge-muted">
                {fmtDate(windowStart)} \u2192 {fmtDate(windowEnd)}
                <span className="ml-1 text-forge-muted/60">({status.window_days}d)</span>
              </span>
              <span className="text-white font-mono">{count}/{max}</span>
            </div>
            <div className="w-full bg-forge-border rounded-full h-1.5">
              <div
                className={`${barColor} h-1.5 rounded-full transition-all duration-500`}
                style={{ width: `${Math.min(100, pct)}%` }}
              />
            </div>
          </div>
        ) : (
          <div className="text-[11px] text-amber-400/70">PDT bypassed \u2014 no window tracking</div>
        )}

        {/* ROW 3: Today's status dot */}
        <div className="flex items-center gap-2">
          <div className="relative shrink-0 w-1.5 h-1.5">
            {todayPulsing && (
              <span className={`absolute inset-0 rounded-full ${todayDot} animate-ping opacity-40`} />
            )}
            <span className={`absolute inset-0 rounded-full ${todayDot}`} />
          </div>
          <span className={`text-[11px] ${todayColor}`}>{todayText}</span>
        </div>
      </div>
    </div>
  )
}
