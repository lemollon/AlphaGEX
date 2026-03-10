'use client'

import { useState, useEffect } from 'react'
import { getCurrentPTTier, secondsUntilNextTier, isMarketOpen, getCTNow } from '@/lib/pt-tiers'

interface StatusData {
  bot_name: string
  strategy: string
  is_active: boolean
  account: {
    balance: number
    cumulative_pnl: number
    unrealized_pnl: number
    total_pnl: number
    return_pct: number
    buying_power: number
    total_trades: number
    collateral_in_use: number
  }
  open_positions: number
  last_scan: string | null
  last_snapshot: string | null
  scan_count: number
  scans_today?: number
  spot_price?: number | null
  vix?: number | null
  bot_state?: string
  last_error?: { time: string | null; message: string | null } | null
}

interface ConfigData {
  sd_multiplier?: number
  spread_width?: number
  buying_power_usage_pct?: number
  profit_target_pct?: number
  stop_loss_pct?: number
  vix_skip?: number
  max_contracts?: number
}

const SCAN_INTERVAL_SEC = 60 // 1 minute

function getSecondsUntilNextScan(lastScan: string | null): number | null {
  if (!lastScan) return null
  const lastMs = new Date(lastScan).getTime()
  if (isNaN(lastMs)) return null
  const nextMs = lastMs + SCAN_INTERVAL_SEC * 1000
  const remaining = Math.max(0, Math.ceil((nextMs - Date.now()) / 1000))
  return remaining
}

function formatCountdown(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

function scanAgeMinutes(lastScan: string | null): number | null {
  if (!lastScan) return null
  const ms = Date.now() - new Date(lastScan).getTime()
  if (isNaN(ms)) return null
  return ms / 60_000
}

/** Get the next weekday (Mon-Fri) from today in CT. */
function getNextTradingDay(): string {
  const now = getCTNow()
  const next = new Date(now)
  next.setDate(next.getDate() + 1)
  // Skip Saturday → Monday, Sunday → Monday
  while (next.getDay() === 0 || next.getDay() === 6) {
    next.setDate(next.getDate() + 1)
  }
  return next.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
}

export default function StatusCard({
  data,
  accent,
  config,
  bot,
}: {
  data: StatusData
  accent: 'amber' | 'blue' | 'red'
  config?: ConfigData | null
  bot?: 'flame' | 'spark' | 'inferno'
}) {
  const { account } = data
  const realizedPositive = account.cumulative_pnl >= 0
  const unrealized = account.unrealized_pnl || 0
  const unrealizedPositive = unrealized >= 0
  const totalPnl = account.total_pnl || account.cumulative_pnl + unrealized
  const totalPositive = totalPnl >= 0

  const accentMap = { amber: { border: 'border-amber-500/30', text: 'text-amber-400' }, blue: { border: 'border-blue-500/30', text: 'text-blue-400' }, red: { border: 'border-red-500/30', text: 'text-red-400' } }
  const accentBorder = accentMap[accent].border
  const accentText = accentMap[accent].text

  const nextDay = getNextTradingDay()
  const isZeroDte = bot === 'inferno'
  const showNextDay = data.bot_state === 'market_closed' || (data.bot_state === 'traded' && data.open_positions === 0 && isZeroDte)
  const stateLabel = data.bot_state === 'market_closed' ? `NEXT: ${nextDay}`
    : data.bot_state === 'traded' && data.open_positions === 0 && isZeroDte ? `DONE — NEXT: ${nextDay}`
    : data.bot_state === 'traded' && data.open_positions === 0 && account.total_trades === 0 ? 'WAITING'
    : data.bot_state ? data.bot_state.toUpperCase()
    : null

  const stateColor = data.bot_state === 'monitoring' ? 'bg-amber-500/20 text-amber-400'
    : data.bot_state === 'scanning' ? 'bg-blue-500/20 text-blue-400'
    : data.bot_state === 'traded' ? 'bg-emerald-500/20 text-emerald-400'
    : data.bot_state === 'error' ? 'bg-red-500/20 text-red-400'
    : 'bg-gray-600/20 text-gray-400'

  /* ---- Next-scan countdown timer ---- */
  const [countdown, setCountdown] = useState<number | null>(
    getSecondsUntilNextScan(data.last_scan),
  )

  /* ---- PT tier + next-tier countdown (ticks every 1s) ---- */
  const [ptState, setPtState] = useState(() => {
    const tier = getCurrentPTTier()
    const next = secondsUntilNextTier()
    const open = isMarketOpen()
    return { tier, next, open }
  })

  useEffect(() => {
    setCountdown(getSecondsUntilNextScan(data.last_scan))
  }, [data.last_scan])

  useEffect(() => {
    const timer = setInterval(() => {
      setCountdown((c) => (c !== null && c > 0 ? c - 1 : 0))
      const ctNow = getCTNow()
      setPtState({
        tier: getCurrentPTTier(ctNow),
        next: secondsUntilNextTier(ctNow),
        open: isMarketOpen(ctNow),
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  /* ---- Scanner health ---- */
  const ageMin = scanAgeMinutes(data.last_scan)
  let healthDot = 'bg-gray-500'
  let healthTooltip = 'Market closed'
  if (ptState.open) {
    if (ageMin === null) {
      healthDot = 'bg-red-400'
      healthTooltip = 'Scanner status unknown'
    } else if (ageMin <= 3) {
      healthDot = 'bg-emerald-400'
      healthTooltip = `Last scan: ${Math.round(ageMin)}m ago`
    } else if (ageMin <= 7) {
      healthDot = 'bg-yellow-400'
      healthTooltip = `Scanner delayed: ${Math.round(ageMin)}m ago`
    } else {
      healthDot = 'bg-red-400'
      healthTooltip = `Scanner offline: ${Math.round(ageMin)}m ago`
    }
  }

  return (
    <div className={`rounded-xl border ${accentBorder} bg-forge-card/80 p-4`}>
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        {/* Scanner health dot */}
        <span
          className={`w-2 h-2 rounded-full shrink-0 ${healthDot}`}
          title={healthTooltip}
        />
        <h2 className={`text-lg font-bold ${accentText}`}>{data.bot_name}</h2>
        <span className="text-xs text-gray-400 bg-forge-border px-2 py-0.5 rounded">
          {data.strategy}
        </span>
        <span
          className={`text-xs px-2 py-0.5 rounded ${
            data.is_active
              ? 'bg-emerald-500/20 text-emerald-400'
              : 'bg-gray-600/20 text-gray-400'
          }`}
        >
          {data.is_active ? 'ACTIVE' : 'INACTIVE'}
        </span>
        {stateLabel && data.bot_state !== 'unknown' && (
          <span className={`text-xs px-2 py-0.5 rounded ${stateColor}`}>
            {stateLabel}
          </span>
        )}

        {/* PT tier badge */}
        {ptState.open ? (
          <span
            className={`text-xs font-medium px-2 py-0.5 rounded ${ptState.tier.bgColor} ${ptState.tier.color}`}
          >
            PT {Math.round(ptState.tier.pct * 100)}% {ptState.tier.label}
          </span>
        ) : (
          <span className="text-xs font-medium px-2 py-0.5 rounded bg-gray-600/20 text-gray-500">
            PT — Closed
          </span>
        )}

        {/* Next scan countdown — only during market hours */}
        {data.last_scan && countdown !== null && ptState.open && (
          <span
            className={`ml-auto text-xs font-mono px-2 py-0.5 rounded ${
              countdown === 0
                ? 'bg-amber-500/20 text-amber-400 animate-pulse'
                : 'bg-forge-border text-gray-400'
            }`}
          >
            {countdown === 0 ? 'Scanning...' : `Next scan ${formatCountdown(countdown)}`}
          </span>
        )}

        {/* After-hours: pipeline offline indicator */}
        {data.last_scan && !ptState.open && (
          <span className="ml-auto text-xs font-mono px-2 py-0.5 rounded bg-forge-border text-gray-500">
            Offline &mdash; resumes at open
          </span>
        )}

        {/* No worker running indicator */}
        {!data.last_scan && data.scan_count === 0 && (
          <span className="ml-auto text-xs font-mono px-2 py-0.5 rounded bg-red-500/15 text-red-400">
            Worker not running
          </span>
        )}
      </div>

      {/* PT next-tier countdown */}
      {ptState.open && ptState.next && (
        <p className="text-[11px] text-forge-muted mb-3 -mt-2">
          {ptState.next.seconds > 0
            ? `PT drops to ${ptState.next.nextLabel} in ${formatCountdown(ptState.next.seconds)}`
            : `PT changing to ${ptState.next.nextLabel}...`}
        </p>
      )}

      {/* SPY/VIX market data */}
      {(data.spot_price || data.vix) && (
        <div className="flex items-center gap-4 mb-3 text-sm font-mono text-gray-300">
          {data.spot_price != null && (
            <span>SPY <span className="text-white font-semibold">${data.spot_price.toFixed(2)}</span></span>
          )}
          {data.vix != null && (
            <span>VIX <span className={`font-semibold ${data.vix > 28 ? 'text-red-400' : data.vix > 22 ? 'text-amber-400' : 'text-white'}`}>{data.vix.toFixed(1)}</span></span>
          )}
          {data.last_scan && (
            <span className="text-forge-muted text-xs">
              Updated {new Date(data.last_scan).toLocaleTimeString('en-US', {
                timeZone: 'America/Chicago', hour: 'numeric', minute: '2-digit', hour12: true,
              })} CT
            </span>
          )}
        </div>
      )}

      {/* Main metrics: Balance | Realized | Unrealized | Total */}
      <div className="grid grid-cols-4 gap-4 mb-4">
        <div>
          <p className="text-xs text-forge-muted">Balance</p>
          <p className="text-xl font-semibold">
            ${account.balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Realized P&L</p>
          <p
            className={`text-xl font-semibold ${realizedPositive ? 'text-emerald-400' : 'text-red-400'}`}
          >
            {realizedPositive ? '+' : ''}$
            {account.cumulative_pnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Unrealized P&L</p>
          <p
            className={`text-xl font-semibold ${
              unrealized === 0
                ? 'text-gray-400'
                : unrealizedPositive
                  ? 'text-emerald-400'
                  : 'text-red-400'
            }`}
          >
            {unrealized === 0
              ? '$0.00'
              : `${unrealizedPositive ? '+' : ''}$${unrealized.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                })}`}
          </p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Total P&L</p>
          <p
            className={`text-xl font-bold ${totalPositive ? 'text-emerald-400' : 'text-red-400'}`}
          >
            {totalPositive ? '+' : ''}$
            {totalPnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            <span className="text-sm ml-1">
              ({totalPositive ? '+' : ''}
              {account.return_pct.toFixed(1)}%)
            </span>
          </p>
        </div>
      </div>

      {/* Bottom row */}
      <div className="grid grid-cols-6 gap-4 text-sm">
        <div>
          <p className="text-xs text-forge-muted">Open</p>
          <p className="font-medium">{data.open_positions}</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Total Trades</p>
          <p className="font-medium">{account.total_trades}</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Collateral</p>
          <p className="font-medium">
            ${account.collateral_in_use.toLocaleString(undefined, { minimumFractionDigits: 0 })}
          </p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Buying Power</p>
          <p className="font-medium">
            ${account.buying_power.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Scans Today</p>
          <p className="font-medium">{data.scans_today ?? 0}</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Total Scans</p>
          <p className="font-medium">{data.scan_count}</p>
        </div>
      </div>

      {/* Config summary */}
      {config && (
        <div className="flex flex-wrap gap-3 mt-3 pt-3 border-t border-forge-border/50">
          <span className="text-[10px] text-forge-muted uppercase tracking-wider">Config</span>
          <span className="text-xs font-mono text-gray-400">{config.sd_multiplier ?? 1.2}x SD</span>
          <span className="text-xs font-mono text-gray-400">${config.spread_width ?? 5} wings</span>
          <span className="text-xs font-mono text-gray-400">{((config.buying_power_usage_pct ?? 0.85) * 100).toFixed(0)}% BP</span>
          <span className="text-xs font-mono text-gray-400">PT 30/20/15%</span>
          <span className="text-xs font-mono text-gray-400">SL {config.stop_loss_pct ?? 100}%</span>
          <span className="text-xs font-mono text-gray-400">VIX&gt;{config.vix_skip ?? 32} skip</span>
          <span className="text-xs font-mono text-gray-400">max {config.max_contracts ?? 10}x</span>
        </div>
      )}

      {data.last_scan && (
        <p className="text-xs text-forge-muted mt-3">
          Last scan: {new Date(data.last_scan).toLocaleString('en-US', {
            timeZone: 'America/Chicago',
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
            second: '2-digit',
            hour12: true,
          })} CT
        </p>
      )}
      {data.last_error && (
        <p className="text-xs text-red-400/70 mt-1 truncate" title={data.last_error.message || ''}>
          Last error: {data.last_error.message}
        </p>
      )}
    </div>
  )
}
