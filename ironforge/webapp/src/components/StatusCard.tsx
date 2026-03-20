'use client'

import { useState, useEffect } from 'react'
import { getCurrentPTTier, secondsUntilNextTier, isMarketOpen, getCTNow, formatCloseReason } from '@/lib/pt-tiers'

interface SandboxAccount {
  name: string
  account_id: string | null
  total_equity: number | null
  option_buying_power: number | null
  day_pnl: number | null
  unrealized_pnl: number | null
  unrealized_pnl_pct: number | null
  open_positions: number
}

interface StatusData {
  bot_name: string
  strategy: string
  is_active: boolean
  account: {
    balance: number
    cumulative_pnl: number
    unrealized_pnl: number | null
    today_realized_pnl?: number
    today_trades_closed?: number
    total_pnl: number
    return_pct: number
    buying_power: number
    total_trades: number
    collateral_in_use: number
    starting_capital?: number
  }
  open_positions: number
  last_scan: string | null
  last_snapshot: string | null
  scan_count: number
  scans_today: number
  spot_price: number | null
  vix: number | null
  bot_state: string | null
  sandbox_accounts?: SandboxAccount[]
  today_close_reasons?: { close_reason: string; realized_pnl: number }[]
}

interface ConfigData {
  sd_multiplier?: number
  spread_width?: number
  buying_power_usage_pct?: number
  profit_target_pct?: number
  stop_loss_pct?: number
  vix_skip?: number
  max_contracts?: number
  starting_capital?: number
}

const SCAN_INTERVAL_SEC = 60 // 1 minute

/** Compute seconds until next scan based on last heartbeat. */
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

/** How many minutes since last_scan? */
function scanAgeMinutes(lastScan: string | null): number | null {
  if (!lastScan) return null
  const ms = Date.now() - new Date(lastScan).getTime()
  if (isNaN(ms)) return null
  return ms / 60_000
}

export default function StatusCard({
  data,
  accent,
  config,
  bot,
  liveUnrealizedPnl,
  liveUnrealizedPct: liveUnrealizedPctProp,
  pendingOrderCount,
  quotesDelayed,
  quoteAgeSeconds,
  todaysClosedTrades,
}: {
  data: StatusData
  accent: 'amber' | 'blue' | 'red'
  config?: ConfigData | null
  bot: 'flame' | 'spark' | 'inferno'
  liveUnrealizedPnl?: number | null
  liveUnrealizedPct?: number | null
  pendingOrderCount?: number
  quotesDelayed?: boolean
  quoteAgeSeconds?: number
  todaysClosedTrades?: { close_reason: string; realized_pnl: number }[]
}) {
  const { account } = data
  const startingCapital = config?.starting_capital ?? (account.balance - account.cumulative_pnl)
  const realizedPositive = account.cumulative_pnl >= 0
  // Realized as % of starting capital
  const realizedPct = startingCapital > 0
    ? (account.cumulative_pnl / startingCapital) * 100
    : null
  // Prefer position-monitor's live unrealized P&L (single source of truth with position cards)
  // null means "unavailable" (MTM failed) — display "—" instead of $0
  const unrealized = liveUnrealizedPnl ?? account.unrealized_pnl
  const unrealizedAvailable = unrealized != null
  const unrealizedPositive = (unrealized ?? 0) >= 0
  // Unrealized % from position-monitor: (credit_received - cost_to_close) / credit_received
  // This is the IC perspective: "I sold for $X, can buy back for $Y, so I've captured Z%"
  // Matches Tradier's portfolio Gain/Loss % exactly
  const unrealizedPct = liveUnrealizedPctProp ?? null
  const totalPnl = unrealizedAvailable
    ? account.cumulative_pnl + (unrealized ?? 0)
    : null
  const totalPositive = (totalPnl ?? 0) >= 0

  // Today's P&L
  const todayRealized = account.today_realized_pnl ?? 0
  const todayRealizedPositive = todayRealized >= 0
  const todayRealizedPct = startingCapital > 0 ? (todayRealized / startingCapital) * 100 : null
  const todayUnrealized = unrealized ?? 0
  const todayUnrealizedPositive = todayUnrealized >= 0
  const todayTotal = todayRealized + todayUnrealized
  const todayTotalPositive = todayTotal >= 0
  const todayTotalPct = startingCapital > 0 ? (todayTotal / startingCapital) * 100 : null

  const accentBorder = accent === 'amber' ? 'border-amber-500/30' : 'border-blue-500/30'
  const accentText = accent === 'amber' ? 'text-amber-400' : 'text-blue-400'

  /* ---- Toggle bot active state ---- */
  const [toggling, setToggling] = useState(false)
  const [confirmToggle, setConfirmToggle] = useState(false)

  /* ---- Editable config fields ---- */
  const [editingBP, setEditingBP] = useState(false)
  const [bpDraft, setBpDraft] = useState('')
  const [editingCapital, setEditingCapital] = useState(false)
  const [capitalDraft, setCapitalDraft] = useState('')
  const [configSaving, setConfigSaving] = useState(false)
  const [savedField, setSavedField] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  async function saveConfigField(field: string, value: number) {
    setConfigSaving(true)
    setSavedField(null)
    setSaveError(null)
    try {
      const res = await fetch(`/api/${bot}/config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [field]: value }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setSavedField(field)
      setTimeout(() => setSavedField(null), 2500)
    } catch (e: unknown) {
      console.error('Config save failed:', e)
      setSaveError(field)
      setTimeout(() => setSaveError(null), 3000)
    } finally {
      setConfigSaving(false)
      setEditingBP(false)
      setEditingCapital(false)
    }
  }

  async function handleToggle(active: boolean) {
    setToggling(true)
    setConfirmToggle(false)
    try {
      const res = await fetch(`/api/${bot}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      // Status will update on next SWR refresh
    } catch (e: any) {
      console.error('Toggle failed:', e)
    } finally {
      setToggling(false)
    }
  }

  /* ---- Next-scan countdown timer ---- */
  const [countdown, setCountdown] = useState<number | null>(null)

  /* ---- PT tier + next-tier countdown (initialized client-side to avoid hydration mismatch) ---- */
  const [ptState, setPtState] = useState<{
    tier: ReturnType<typeof getCurrentPTTier>
    next: ReturnType<typeof secondsUntilNextTier>
    open: boolean
  } | null>(null)

  // Initialize on client + re-sync when last_scan changes
  useEffect(() => {
    setCountdown(getSecondsUntilNextScan(data.last_scan))
  }, [data.last_scan])

  // Initialize PT state + unified 1-second tick
  useEffect(() => {
    function tick() {
      setCountdown((c) => (c !== null && c > 0 ? c - 1 : 0))
      const ctNow = getCTNow()
      setPtState({
        tier: getCurrentPTTier(ctNow),
        next: secondsUntilNextTier(ctNow),
        open: isMarketOpen(ctNow),
      })
    }
    tick() // immediate first tick to initialize
    const timer = setInterval(tick, 1000)
    return () => clearInterval(timer)
  }, [])

  /* ---- Scanner health ---- */
  const ageMin = scanAgeMinutes(data.last_scan)
  let healthDot = 'bg-gray-500'    // market closed default
  let healthTooltip = 'Market closed'
  if (ptState?.open) {
    if (ageMin === null) {
      healthDot = 'bg-red-400'
      healthTooltip = 'Scanner status unknown'
    } else if (ageMin <= 7) {
      healthDot = 'bg-emerald-400'
      healthTooltip = `Last scan: ${Math.round(ageMin)}m ago`
    } else if (ageMin <= 15) {
      healthDot = 'bg-yellow-400'
      healthTooltip = `Scanner delayed: ${Math.round(ageMin)}m ago`
    } else {
      healthDot = 'bg-red-400'
      healthTooltip = `Scanner offline: ${Math.round(ageMin)}m ago`
    }
  }

  return (
    <div className={`rounded-xl border ${accentBorder} bg-forge-card/80 p-4`}>
      {/* Toggle confirmation dialog */}
      {confirmToggle && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-forge-card border border-forge-border rounded-xl p-6 max-w-md mx-4 shadow-xl">
            <h3 className="text-lg font-bold text-white mb-3">
              {data.is_active ? 'Disable Bot?' : 'Enable Bot?'}
            </h3>
            <p className="text-sm text-gray-300 mb-5">
              {data.is_active
                ? `Disabling ${data.bot_name} will stop it from scanning and opening new trades. Existing positions will NOT be closed.`
                : `Enable ${data.bot_name} to resume scanning for Iron Condor opportunities.`}
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setConfirmToggle(false)}
                className="px-4 py-2 text-sm rounded-lg border border-forge-border text-gray-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleToggle(!data.is_active)}
                className={`px-4 py-2 text-sm rounded-lg font-medium transition-colors ${
                  data.is_active
                    ? 'bg-red-600 hover:bg-red-500 text-white'
                    : 'bg-emerald-600 hover:bg-emerald-500 text-white'
                }`}
              >
                {data.is_active ? 'Disable' : 'Enable'}
              </button>
            </div>
          </div>
        </div>
      )}

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
            data.bot_state === 'monitoring'
              ? 'bg-blue-500/20 text-blue-400'
              : data.bot_state === 'awaiting_fill' || data.bot_state === 'pending_fill'
                ? 'bg-yellow-500/20 text-yellow-400'
              : data.bot_state === 'scanning' || data.bot_state === 'traded'
                ? 'bg-emerald-500/20 text-emerald-400'
              : data.bot_state === 'error'
                ? 'bg-red-500/20 text-red-400'
              : data.bot_state === 'market_closed' || data.bot_state === 'idle'
                ? 'bg-gray-600/20 text-gray-400'
              : data.is_active
                ? 'bg-emerald-500/20 text-emerald-400'
                : 'bg-gray-600/20 text-gray-400'
          }`}
        >
          {data.bot_state === 'awaiting_fill' ? 'AWAITING FILL'
            : data.bot_state === 'pending_fill' ? 'PENDING FILL'
            : data.bot_state === 'monitoring' ? 'MONITORING'
            : data.bot_state === 'scanning' ? 'SCANNING'
            : data.bot_state === 'traded' ? 'TRADED'
            : data.bot_state === 'error' ? 'ERROR'
            : data.bot_state === 'market_closed' || data.bot_state === 'idle' ? 'MARKET CLOSED'
            : data.is_active ? 'ACTIVE' : 'INACTIVE'}
        </span>

        {/* PT tier badge */}
        {ptState?.open ? (
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

        {/* Toggle bot active */}
        <button
          onClick={() => setConfirmToggle(true)}
          disabled={toggling}
          className={`text-xs px-2.5 py-1 rounded-lg border font-medium transition-colors ${
            data.is_active
              ? 'border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10'
              : 'border-red-500/30 text-red-400 hover:bg-red-500/10'
          } ${toggling ? 'opacity-50' : ''}`}
        >
          {toggling ? '...' : data.is_active ? 'ON' : 'OFF'}
        </button>

        {/* Next scan countdown */}
        {data.last_scan && countdown !== null && (
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

        {/* No worker running indicator */}
        {!data.last_scan && data.scan_count === 0 && (
          <span className="ml-auto text-xs font-mono px-2 py-0.5 rounded bg-red-500/15 text-red-400">
            Worker not running
          </span>
        )}
      </div>

      {/* PT next-tier countdown (small text below header) */}
      {ptState?.open && ptState.next && (
        <p className="text-[11px] text-forge-muted mb-3 -mt-2">
          {ptState.next.seconds > 0
            ? `PT drops to ${ptState.next.nextLabel} in ${formatCountdown(ptState.next.seconds)}`
            : `PT changing to ${ptState.next.nextLabel}...`}
        </p>
      )}

      {/* Live market data */}
      {(data.spot_price || data.vix) && (
        <div className="flex items-center gap-4 mb-3 text-sm font-mono text-gray-300">
          {data.spot_price != null && data.spot_price > 0 && (
            <span>SPY <span className="text-white font-semibold">${data.spot_price.toFixed(2)}</span></span>
          )}
          {data.vix != null && data.vix > 0 && (
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
            {realizedPct != null && account.cumulative_pnl !== 0 && (
              <span className="text-sm ml-1" title="% return on account capital">
                ({realizedPct >= 0 ? '+' : ''}{realizedPct.toFixed(1)}%
                <span className="text-[9px] text-forge-muted"> of acct</span>)
              </span>
            )}
          </p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">
            Unrealized P&L
            {quotesDelayed && (
              <span className="ml-1 text-yellow-500" title={`Quotes are ${quoteAgeSeconds ? Math.round(quoteAgeSeconds / 60) + 'min' : ''} old — Tradier API may be returning delayed data`}>
                (DELAYED)
              </span>
            )}
          </p>
          <p
            className={`text-xl font-semibold ${
              !unrealizedAvailable
                ? 'text-gray-500'
                : unrealized === 0
                  ? 'text-gray-400'
                  : unrealizedPositive
                    ? 'text-emerald-400'
                    : 'text-red-400'
            }`}
          >
            {!unrealizedAvailable
              ? '—'
              : unrealized === 0
                ? '$0.00'
                : `${unrealizedPositive ? '+' : ''}$${(unrealized ?? 0).toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                  })}`}
            {unrealizedPct != null && unrealized !== 0 && (
              <span className="text-sm ml-1" title="% of IC credit captured (position return)">
                ({unrealizedPct >= 0 ? '+' : ''}{unrealizedPct.toFixed(1)}%
                <span className="text-[9px] text-forge-muted"> of credit</span>)
              </span>
            )}
          </p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Total P&L</p>
          {totalPnl != null ? (
            <p
              className={`text-xl font-bold ${totalPositive ? 'text-emerald-400' : 'text-red-400'}`}
            >
              {totalPositive ? '+' : ''}$
              {totalPnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}
              <span className="text-sm ml-1" title="% return on account capital">
                ({totalPositive ? '+' : ''}
                {account.return_pct.toFixed(1)}%
                <span className="text-[9px] text-forge-muted"> of acct</span>)
              </span>
            </p>
          ) : (
            <p className="text-xl font-bold text-gray-500">—</p>
          )}
        </div>
      </div>

      {/* Today's P&L row */}
      <div className="grid grid-cols-4 gap-4 mb-4 pt-3 border-t border-forge-border/30">
        <div>
          <p className="text-[10px] text-forge-muted uppercase tracking-wider">Today</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Realized Today</p>
          <p className={`text-base font-semibold ${todayRealized === 0 ? 'text-gray-400' : todayRealizedPositive ? 'text-emerald-400' : 'text-red-400'}`}>
            {todayRealized === 0
              ? '$0.00'
              : `${todayRealizedPositive ? '+' : ''}$${todayRealized.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
            {todayRealizedPct != null && todayRealized !== 0 && (
              <span className="text-xs ml-1">({todayRealizedPct >= 0 ? '+' : ''}{todayRealizedPct.toFixed(1)}%)</span>
            )}
          </p>
          {/* Close reason breakdown — shows which PT tiers hit today */}
          {(() => {
            // Prefer status API data (always available), fall back to position-monitor
            const trades = data.today_close_reasons?.length
              ? data.today_close_reasons
              : todaysClosedTrades
            if (!trades || trades.length === 0) return null
            return (
              <div className="flex flex-wrap gap-1.5 mt-1">
                {trades.map((t, i) => {
                  const r = formatCloseReason(t.close_reason, bot)
                  const pnlPos = t.realized_pnl >= 0
                  return (
                    <span key={i} className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                      r.color.includes('emerald') ? 'bg-emerald-500/15' :
                      r.color.includes('yellow') ? 'bg-yellow-500/15' :
                      r.color.includes('orange') ? 'bg-orange-500/15' :
                      r.color.includes('red') ? 'bg-red-500/15' :
                      r.color.includes('amber') ? 'bg-amber-500/15' :
                      'bg-gray-500/15'
                    } ${r.color}`}>
                      {pnlPos ? '+' : ''}{Math.abs(t.realized_pnl) < 1000 ? `$${t.realized_pnl.toFixed(0)}` : `$${(t.realized_pnl/1000).toFixed(1)}k`}
                      {' '}{r.text.replace('Profit Target ', '').replace('(', '').replace(')', '')}
                    </span>
                  )
                })}
              </div>
            )
          })()}
        </div>
        <div>
          <p className="text-xs text-forge-muted">Unrealized Now</p>
          <p className={`text-base font-semibold ${!unrealizedAvailable ? 'text-gray-500' : todayUnrealized === 0 ? 'text-gray-400' : todayUnrealizedPositive ? 'text-emerald-400' : 'text-red-400'}`}>
            {!unrealizedAvailable
              ? '—'
              : todayUnrealized === 0
                ? '$0.00'
                : `${todayUnrealizedPositive ? '+' : ''}$${todayUnrealized.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
            {unrealizedPct != null && todayUnrealized !== 0 && (
              <span className="text-xs ml-1" title="% of IC credit captured">({unrealizedPct >= 0 ? '+' : ''}{unrealizedPct.toFixed(1)}% <span className="text-[9px] text-forge-muted">of credit</span>)</span>
            )}
          </p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Today Total</p>
          <p className={`text-base font-bold ${todayTotal === 0 ? 'text-gray-400' : todayTotalPositive ? 'text-emerald-400' : 'text-red-400'}`}>
            {todayTotal === 0
              ? '$0.00'
              : `${todayTotalPositive ? '+' : ''}$${todayTotal.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
            {todayTotalPct != null && todayTotal !== 0 && (
              <span className="text-xs ml-1" title="% return on account capital">({todayTotalPct >= 0 ? '+' : ''}{todayTotalPct.toFixed(1)}% <span className="text-[9px] text-forge-muted">of acct</span>)</span>
            )}
          </p>
        </div>
      </div>

      {/* Bottom row */}
      <div className="grid grid-cols-6 gap-4 text-sm">
        <div>
          <p className="text-xs text-forge-muted">Open</p>
          <p className="font-medium">
            {data.open_positions}
            {(pendingOrderCount ?? 0) > 0 && (
              <span className="ml-1 text-xs text-yellow-400" title="Pending sandbox orders awaiting fill">
                (+{pendingOrderCount} pending)
              </span>
            )}
          </p>
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
          <p className="font-medium">{data.scans_today || 0}</p>
        </div>
        <div>
          <p className="text-xs text-forge-muted">Total Scans</p>
          <p className="font-medium">{data.scan_count}</p>
        </div>
      </div>

      {/* Sandbox accounts — per-account P&L from Tradier */}
      {data.sandbox_accounts && data.sandbox_accounts.length > 0 && (
        <div className="grid gap-2 mb-3 pt-3 border-t border-forge-border/30">
          <p className="text-[10px] text-forge-muted uppercase tracking-wider">Sandbox Accounts</p>
          <div className="grid grid-cols-3 gap-3">
            {data.sandbox_accounts.map((acct) => {
              const hasData = acct.account_id != null
              const dayPnl = acct.day_pnl ?? 0
              const dayPositive = dayPnl >= 0
              const uPnl = acct.unrealized_pnl
              const uPct = acct.unrealized_pnl_pct
              const uPositive = (uPnl ?? 0) >= 0
              const bp = acct.option_buying_power
              const bpNeg = bp != null && bp < 0
              return (
                <div key={acct.name} className="bg-forge-bg/50 rounded-lg px-3 py-2">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-gray-300">{acct.name}</span>
                    <span className="text-[10px] text-gray-500">{acct.open_positions} pos</span>
                  </div>
                  {hasData ? (
                    <>
                      <p className={`text-sm font-semibold ${dayPnl === 0 ? 'text-gray-400' : dayPositive ? 'text-emerald-400' : 'text-red-400'}`}>
                        {dayPnl === 0 ? '$0.00' : `${dayPositive ? '+' : ''}$${dayPnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
                        <span className="text-[10px] text-forge-muted ml-1">day P&L</span>
                      </p>
                      {uPnl != null && acct.open_positions > 0 && (
                        <p className={`text-xs mt-0.5 font-medium ${uPnl === 0 ? 'text-gray-400' : uPositive ? 'text-emerald-400' : 'text-red-400'}`}>
                          {uPnl === 0 ? '$0.00' : `${uPositive ? '+' : ''}$${uPnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
                          {uPct != null && uPnl !== 0 && (
                            <span className="ml-1">({uPositive ? '+' : ''}{uPct.toFixed(1)}%)</span>
                          )}
                          <span className="text-[10px] text-forge-muted ml-1">unreal</span>
                        </p>
                      )}
                      <p className={`text-xs mt-0.5 ${bpNeg ? 'text-red-400 font-semibold' : 'text-gray-500'}`}>
                        BP: ${bp != null ? bp.toLocaleString(undefined, { minimumFractionDigits: 0 }) : '—'}
                      </p>
                    </>
                  ) : (
                    <p className="text-xs text-gray-600">Not configured</p>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Config summary with editable allocation */}
      {config && (
        <div className="flex flex-wrap items-center gap-3 mt-3 pt-3 border-t border-forge-border/50">
          <span className="text-[10px] text-forge-muted uppercase tracking-wider">Config</span>
          <span className="text-xs font-mono text-gray-400">{config.sd_multiplier ?? 1.2}x SD</span>
          <span className="text-xs font-mono text-gray-400">${config.spread_width ?? 5} wings</span>

          {/* Editable BP% */}
          {editingBP ? (
            <span className="inline-flex items-center gap-1">
              <input
                type="number"
                min={10}
                max={100}
                step={5}
                autoFocus
                className="w-14 text-xs font-mono bg-forge-bg border border-amber-500/40 rounded px-1.5 py-0.5 text-white text-center"
                value={bpDraft}
                onChange={(e) => setBpDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    const v = parseFloat(bpDraft)
                    if (v >= 10 && v <= 100) saveConfigField('buying_power_usage_pct', v / 100)
                  }
                  if (e.key === 'Escape') setEditingBP(false)
                }}
                onBlur={() => {
                  const v = parseFloat(bpDraft)
                  if (v >= 10 && v <= 100) saveConfigField('buying_power_usage_pct', v / 100)
                  else setEditingBP(false)
                }}
                disabled={configSaving}
              />
              <span className="text-xs text-gray-500">% BP</span>
            </span>
          ) : (
            <span className="inline-flex items-center gap-1">
              <button
                onClick={() => { setBpDraft(String(((config.buying_power_usage_pct ?? 0.85) * 100).toFixed(0))); setEditingBP(true) }}
                className="text-xs font-mono text-amber-400 hover:text-amber-300 underline underline-offset-2 decoration-dotted cursor-pointer"
                title="Click to edit buying power allocation %"
              >
                {((config.buying_power_usage_pct ?? 0.85) * 100).toFixed(0)}% BP
              </button>
              {savedField === 'buying_power_usage_pct' && (
                <span className="text-emerald-400 text-[10px] font-medium animate-pulse">Saved</span>
              )}
              {saveError === 'buying_power_usage_pct' && (
                <span className="text-red-400 text-[10px] font-medium">Failed</span>
              )}
            </span>
          )}

          {/* Editable Starting Capital */}
          {editingCapital ? (
            <span className="inline-flex items-center gap-1">
              <span className="text-xs text-gray-500">$</span>
              <input
                type="number"
                min={100}
                step={1000}
                autoFocus
                className="w-20 text-xs font-mono bg-forge-bg border border-amber-500/40 rounded px-1.5 py-0.5 text-white text-center"
                value={capitalDraft}
                onChange={(e) => setCapitalDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    const v = parseFloat(capitalDraft)
                    if (v >= 100) saveConfigField('starting_capital', v)
                  }
                  if (e.key === 'Escape') setEditingCapital(false)
                }}
                onBlur={() => {
                  const v = parseFloat(capitalDraft)
                  if (v >= 100) saveConfigField('starting_capital', v)
                  else setEditingCapital(false)
                }}
                disabled={configSaving}
              />
              <span className="text-xs text-gray-500">capital</span>
            </span>
          ) : (
            <span className="inline-flex items-center gap-1">
              <button
                onClick={() => { setCapitalDraft(String(config.starting_capital ?? 10000)); setEditingCapital(true) }}
                className="text-xs font-mono text-amber-400 hover:text-amber-300 underline underline-offset-2 decoration-dotted cursor-pointer"
                title="Click to edit starting capital"
              >
                ${(config.starting_capital ?? 10000).toLocaleString()} capital
              </button>
              {savedField === 'starting_capital' && (
                <span className="text-emerald-400 text-[10px] font-medium animate-pulse">Saved</span>
              )}
              {saveError === 'starting_capital' && (
                <span className="text-red-400 text-[10px] font-medium">Failed</span>
              )}
            </span>
          )}

          <span className="text-xs font-mono text-gray-400">PT {config.profit_target_pct ?? 30}%</span>
          <span className="text-xs font-mono text-gray-400">SL {config.stop_loss_pct ?? 100}%</span>
          <span className="text-xs font-mono text-gray-400">VIX&gt;{config.vix_skip ?? 32} skip</span>
          <span className="text-xs font-mono text-gray-400">max {config.max_contracts === 0 ? '∞' : (config.max_contracts ?? 10)}x</span>
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
          {(data as any).last_scan_reason && (
            <span className="ml-2 text-gray-500">
              &mdash; {(data as any).last_scan_reason}
            </span>
          )}
        </p>
      )}
    </div>
  )
}
