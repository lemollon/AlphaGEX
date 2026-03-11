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
  today_trades_count: number
  today_trade_time: string | null
}

interface AuditEntry {
  action: string
  old_value: string | null
  new_value: string | null
  reason: string | null
  performed_by: string | null
  created_at: string | null
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

/** Compute the start of the rolling window (windowDays business days back, inclusive) */
function computeWindowStart(today: Date, windowDays: number): Date {
  const d = new Date(today)
  let remaining = windowDays - 1
  while (remaining > 0) {
    d.setDate(d.getDate() - 1)
    if (d.getDay() >= 1 && d.getDay() <= 5) remaining--
  }
  return d
}

/** Last business day on or before d */
function lastBizDay(d: Date): Date {
  const r = new Date(d)
  while (r.getDay() === 0 || r.getDay() === 6) r.setDate(r.getDate() - 1)
  return r
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function PdtCard({
  bot,
  accent,
  botStatus,
}: {
  bot: 'flame' | 'spark' | 'inferno'
  accent: 'amber' | 'blue' | 'red'
  botStatus?: BotStatus | null
}) {
  const [status, setStatus] = useState<PdtStatus | null>(null)
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [showAudit, setShowAudit] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmAction, setConfirmAction] = useState<'toggle_off' | 'reset' | null>(null)
  const [todayStr, setTodayStr] = useState<string | null>(null)

  useEffect(() => {
    setTodayStr(new Date().toLocaleDateString('en-CA', { timeZone: 'America/Chicago' }))
  }, [])

  /* ---- Fetch ---- */
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
    } catch { /* non-critical */ }
  }, [bot])

  useEffect(() => {
    fetchStatus()
    const timer = setInterval(fetchStatus, 60_000)
    return () => clearInterval(timer)
  }, [fetchStatus])

  useEffect(() => {
    if (showAudit) fetchAudit()
  }, [showAudit, fetchAudit])

  /* ---- Actions ---- */
  async function doToggle(enabled: boolean) {
    setLoading(true)
    setConfirmAction(null)
    if (status) setStatus({ ...status, pdt_enabled: enabled })
    try {
      const res = await fetch(`/api/${bot}/pdt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'toggle', enabled }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setStatus(await res.json())
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
      setStatus(await res.json())
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  /* ---- Loading / Error states ---- */
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

  /* ---- Computed values ---- */
  const accentBorder = accent === 'amber' ? 'border-amber-500/30' : accent === 'red' ? 'border-red-500/30' : 'border-blue-500/30'
  const count = status.day_trade_count
  const max = status.max_day_trades
  const pct = max > 0 ? (count / max) * 100 : 0
  const remaining = status.trades_remaining ?? Math.max(0, max - count)
  const pdtStatus = status.pdt_status

  // Window dates (client-side computation)
  const todayDate = todayStr ? new Date(todayStr + 'T12:00:00') : new Date()
  const effectiveToday = lastBizDay(todayDate)
  const windowStart = computeWindowStart(effectiveToday, status.window_days)

  // Next available trade explanation
  const oldestTrade = status.trigger_trades.length > 0 ? status.trigger_trades[0] : null

  return (
    <div className={`rounded-xl border ${accentBorder} bg-forge-card/80 p-4 space-y-4`}>
      {/* ============================================ */}
      {/* Confirmation modal                           */}
      {/* ============================================ */}
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

      {/* ============================================ */}
      {/* SECTION 1: STATUS BANNER                     */}
      {/* ============================================ */}
      <StatusBanner
        pdtStatus={pdtStatus}
        remaining={remaining}
        max={max}
        count={count}
        nextAvailableDate={status.next_available_date}
        todayTradeTime={status.today_trade_time}
      />

      {/* ============================================ */}
      {/* SECTION 2: WINDOW ROW                        */}
      {/* ============================================ */}
      <WindowRow
        pdtEnabled={status.pdt_enabled}
        count={count}
        max={max}
        pct={pct}
        windowDays={status.window_days}
        windowStart={windowStart}
        windowEnd={effectiveToday}
      />

      {/* ============================================ */}
      {/* SECTION 3: ROLLING CALENDAR (merged expiry)  */}
      {/* ============================================ */}
      <PdtCalendar status={status} />

      {/* ============================================ */}
      {/* SECTION 4: NEXT AVAILABLE TRADE              */}
      {/* ============================================ */}
      <NextAvailableTrade
        pdtStatus={pdtStatus}
        nextAvailableDate={status.next_available_date}
        tradedToday={status.traded_today}
        isBlocked={status.is_blocked}
        oldestTrade={oldestTrade}
        maxTradesPerDay={status.max_trades_per_day}
      />

      {/* ============================================ */}
      {/* SECTION 5: TODAY'S STATUS                    */}
      {/* ============================================ */}
      <TodayStatus
        pdtStatus={pdtStatus}
        tradedToday={status.traded_today}
        todayTradeTime={status.today_trade_time}
        todayTradesCount={status.today_trades_count ?? 0}
        maxTradesPerDay={status.max_trades_per_day}
        botStatus={botStatus}
      />

      {/* ============================================ */}
      {/* SECTION 6: PDT ENFORCEMENT TOGGLE            */}
      {/* ============================================ */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xs text-forge-muted">PDT Enforcement:</span>
          <div className="flex rounded-lg overflow-hidden border border-forge-border">
            <button
              onClick={() => { if (!status.pdt_enabled) doToggle(true) }}
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
              onClick={() => { if (status.pdt_enabled) setConfirmAction('toggle_off') }}
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
        <span className="text-[11px] text-forge-muted max-w-[280px] text-right">
          {status.pdt_enabled
            ? `FINRA Rule 4210 \u2014 max ${max} day trades per rolling ${status.window_days} business days`
            : `PDT bypassed \u2014 unlimited trades. Counter paused at ${count}.`}
        </span>
      </div>

      {/* ============================================ */}
      {/* SECTION 7: RESET & AUDIT                     */}
      {/* ============================================ */}
      <div className="pt-3 border-t border-forge-border/50 space-y-3">
        <div className="flex items-center justify-between">
          <div>
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
            <span className="text-[10px] text-forge-muted ml-2">
              Manual override — use only to correct errors
            </span>
          </div>
          {status.last_reset_at && (
            <span className="text-[11px] text-forge-muted">
              Last reset:{' '}
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
        <div>
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
                let detail = ''
                if (entry.action === 'toggle_on' || entry.action === 'toggle_off') {
                  detail = `enabled: ${entry.action === 'toggle_off' ? 'true\u2192false' : 'false\u2192true'}`
                } else if (entry.action === 'reset') {
                  try {
                    const oldVal = JSON.parse(entry.old_value || '{}')
                    detail = `count: ${oldVal.day_trade_count ?? '?'}\u21920`
                  } catch { detail = 'count\u21920' }
                } else if (entry.action === 'day_trade_recorded') {
                  try {
                    const oldVal = JSON.parse(entry.old_value || '{}')
                    const newVal = JSON.parse(entry.new_value || '{}')
                    detail = `count: ${oldVal.day_trade_count ?? '?'}\u2192${newVal.day_trade_count ?? '?'}`
                  } catch { detail = 'count +1' }
                } else if (entry.action === 'auto_decrement') {
                  try {
                    const oldVal = JSON.parse(entry.old_value || '{}')
                    const newVal = JSON.parse(entry.new_value || '{}')
                    detail = `count: ${oldVal.day_trade_count ?? '?'}\u2192${newVal.day_trade_count ?? '?'}`
                  } catch { detail = 'auto-decrement' }
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
    </div>
  )
}

/* ================================================================== */
/*  Section sub-components (inline — tightly coupled to PdtCard data) */
/* ================================================================== */

function StatusBanner({
  pdtStatus,
  remaining,
  max,
  count,
  nextAvailableDate,
  todayTradeTime,
}: {
  pdtStatus: string
  remaining: number
  max: number
  count: number
  nextAvailableDate: string | null
  todayTradeTime: string | null
}) {
  let bg: string, dotColor: string, primary: string, secondary: string

  if (pdtStatus === 'PDT_OFF') {
    bg = 'bg-gray-800/50 border-gray-500/30'
    dotColor = 'bg-gray-400'
    primary = 'PDT BYPASSED'
    secondary = 'Unlimited trading \u2014 paper mode'
  } else if (pdtStatus === 'BLOCKED') {
    bg = 'bg-red-900/30 border-red-500/30'
    dotColor = 'bg-red-400'
    primary = 'PDT BLOCKED'
    secondary = nextAvailableDate
      ? `${count}/${max} used \u2014 next slot opens ${fmtDateFromStr(nextAvailableDate)}`
      : `${count}/${max} day trades used`
  } else if (pdtStatus === 'TRADED_TODAY') {
    bg = 'bg-amber-900/30 border-amber-500/30'
    dotColor = 'bg-amber-400'
    primary = 'DONE FOR TODAY'
    secondary = todayTradeTime
      ? `Traded at ${fmtTime(todayTradeTime)} CT \u2014 resumes tomorrow`
      : 'Already traded today \u2014 resumes tomorrow'
  } else {
    bg = 'bg-emerald-900/30 border-emerald-500/30'
    dotColor = 'bg-emerald-400'
    primary = 'CAN TRADE'
    secondary = `${remaining} of ${max} slots available`
  }

  const textColor = pdtStatus === 'BLOCKED' ? 'text-red-300'
    : pdtStatus === 'TRADED_TODAY' ? 'text-amber-300'
    : pdtStatus === 'PDT_OFF' ? 'text-gray-300'
    : 'text-emerald-300'

  const subColor = pdtStatus === 'BLOCKED' ? 'text-red-400/70'
    : pdtStatus === 'TRADED_TODAY' ? 'text-amber-400/60'
    : pdtStatus === 'PDT_OFF' ? 'text-gray-400'
    : 'text-emerald-400/70'

  return (
    <div className={`rounded-lg px-4 py-3 flex items-center gap-3 border ${bg}`}>
      <div className={`w-3 h-3 rounded-full ${dotColor} shrink-0`} />
      <div>
        <div className={`text-sm font-bold ${textColor}`}>{primary}</div>
        <div className={`text-xs ${subColor}`}>{secondary}</div>
      </div>
    </div>
  )
}

function WindowRow({
  pdtEnabled,
  count,
  max,
  pct,
  windowDays,
  windowStart,
  windowEnd,
}: {
  pdtEnabled: boolean
  count: number
  max: number
  pct: number
  windowDays: number
  windowStart: Date
  windowEnd: Date
}) {
  if (!pdtEnabled) {
    return (
      <div className="text-xs text-amber-400/70">
        PDT bypassed \u2014 no window tracking
      </div>
    )
  }

  const barColor = count >= max ? 'bg-red-500' : count >= max - 1 ? 'bg-amber-500' : 'bg-emerald-500'
  const label = count === 0 ? 'All slots clear'
    : count >= max ? `${count} / ${max} used \u2014 FULL`
    : count === max - 1 ? `${count} / ${max} used \u2014 last slot`
    : `${count} / ${max} used`

  return (
    <div>
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="text-forge-muted">
          Window:{' '}
          <span className="text-white">{fmtDate(windowStart)}</span>
          {' \u2192 '}
          <span className="text-white">{fmtDate(windowEnd)}</span>
          <span className="text-forge-muted ml-1">({windowDays} biz days)</span>
        </span>
        <span className="text-white font-mono text-xs">{label}</span>
      </div>
      <div className="w-full bg-forge-border rounded-full h-1.5">
        <div
          className={`${barColor} h-1.5 rounded-full transition-all duration-300`}
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </div>
    </div>
  )
}

function NextAvailableTrade({
  pdtStatus,
  nextAvailableDate,
  tradedToday,
  isBlocked,
  oldestTrade,
  maxTradesPerDay,
}: {
  pdtStatus: string
  nextAvailableDate: string | null
  tradedToday: boolean
  isBlocked: boolean
  oldestTrade: TriggerTrade | null
  maxTradesPerDay: number
}) {
  // Only show when bot cannot currently trade
  if (pdtStatus === 'CAN_TRADE' || pdtStatus === 'PDT_OFF') return null

  if (pdtStatus === 'BLOCKED' && nextAvailableDate) {
    const reason = oldestTrade
      ? ` \u2014 oldest trade (${fmtDateFromStr(oldestTrade.trade_date)}) expires, freeing 1 slot`
      : ''
    return (
      <div className="rounded-lg bg-amber-900/20 border border-amber-500/20 px-3 py-2">
        <span className="text-xs text-amber-300">Next trade available: </span>
        <span className="text-xs text-emerald-400 font-medium">{fmtDateFromStr(nextAvailableDate)}</span>
        <span className="text-xs text-amber-300/70">{reason}</span>
      </div>
    )
  }

  if (pdtStatus === 'TRADED_TODAY' && !isBlocked && maxTradesPerDay > 0) {
    return (
      <div className="rounded-lg bg-blue-900/20 border border-blue-500/20 px-3 py-2">
        <span className="text-xs text-blue-300">
          Next trade: <span className="text-white font-medium">tomorrow</span>
          {' '}\u2014 {maxTradesPerDay}-trade/day limit resets at market open
        </span>
      </div>
    )
  }

  // TRADED_TODAY + would be BLOCKED tomorrow
  if (pdtStatus === 'TRADED_TODAY' && isBlocked && nextAvailableDate) {
    return (
      <div className="rounded-lg bg-amber-900/20 border border-amber-500/20 px-3 py-2">
        <span className="text-xs text-amber-300">
          Next trade: <span className="text-emerald-400 font-medium">{fmtDateFromStr(nextAvailableDate)}</span>
          {' '}\u2014 PDT limit reached, slot opens when oldest trade expires
        </span>
      </div>
    )
  }

  // Fallback for BLOCKED with no next_available_date
  if (pdtStatus === 'BLOCKED') {
    return (
      <div className="rounded-lg bg-red-900/20 border border-red-500/20 px-3 py-2">
        <span className="text-xs text-red-300">PDT blocked \u2014 calculating next available slot...</span>
      </div>
    )
  }

  return null
}

function TodayStatus({
  pdtStatus,
  tradedToday,
  todayTradeTime,
  todayTradesCount,
  maxTradesPerDay,
  botStatus,
}: {
  pdtStatus: string
  tradedToday: boolean
  todayTradeTime: string | null
  todayTradesCount: number
  maxTradesPerDay: number
  botStatus?: BotStatus | null
}) {
  const botState = botStatus?.bot_state
  const openPositions = botStatus?.open_positions ?? 0
  const scansToday = botStatus?.scans_today ?? 0

  let dotColor: string, text: string, textColor: string

  // INFERNO multi-trade: maxTradesPerDay === 0 means unlimited
  const isUnlimitedPerDay = maxTradesPerDay === 0

  if (todayTradesCount > 0 || tradedToday) {
    const timeStr = todayTradeTime ? ` at ${fmtTime(todayTradeTime)} CT` : ''

    if (isUnlimitedPerDay && todayTradesCount > 1) {
      // INFERNO: multiple trades
      dotColor = 'bg-emerald-400'
      text = `Today: ${todayTradesCount} trades${timeStr ? ` (first${timeStr})` : ''} \u2014 ${openPositions} open, ${todayTradesCount - openPositions} closed`
      textColor = 'text-emerald-300'
    } else if (openPositions > 0) {
      dotColor = 'bg-amber-400 animate-pulse'
      text = `Today: Traded${timeStr} \u2014 position open, monitoring`
      textColor = 'text-amber-300'
    } else {
      dotColor = 'bg-emerald-400'
      text = `Today: Traded${timeStr} \u2014 position closed`
      textColor = 'text-emerald-300'
    }
  } else if (botState === 'market_closed') {
    dotColor = 'bg-gray-500'
    text = 'Today: Market closed \u2014 no trading'
    textColor = 'text-gray-500'
  } else if (pdtStatus === 'BLOCKED') {
    dotColor = 'bg-red-400'
    text = 'Today: Cannot trade \u2014 PDT blocked'
    textColor = 'text-red-400'
  } else if (botState === 'scanning' || botState === 'idle') {
    dotColor = 'bg-blue-400'
    text = `Today: No trade yet \u2014 scanning (${scansToday} scans)`
    textColor = 'text-blue-400'
  } else if (botState === 'error') {
    dotColor = 'bg-red-400'
    text = 'Today: Bot error \u2014 check logs'
    textColor = 'text-red-400'
  } else {
    dotColor = 'bg-gray-500'
    text = 'Today: No trade yet'
    textColor = 'text-gray-400'
  }

  return (
    <div className="flex items-center gap-2">
      <div className={`w-2 h-2 rounded-full ${dotColor} shrink-0`} />
      <span className={`text-xs ${textColor}`}>{text}</span>
    </div>
  )
}
