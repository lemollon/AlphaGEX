'use client'

/**
 * FlamePutSpreadTab — "Spread Chart" view for FLAME's 2DTE Put Credit Spread.
 *
 * Uses the read-only /api/flame/preview-put-spread endpoint (shipped in
 * PR #2198 + #2201 credit fix) to render:
 *   - Current live Tradier User sandbox balance
 *   - SPY + VIX + expected move
 *   - Target 2DTE expiration
 *   - Put-long / put-short strikes with distance from spot (in $ and SD)
 *   - Real put-spread credit from Tradier bid/ask (mid fallback)
 *   - 10%-risk sizing — contracts, total risk, max profit
 *   - 50% PT and 200% SL cost-to-close + $ P&L
 *   - VIX gate + credit gate + account gate status
 *   - Payoff diagram at expiration (2-leg put credit spread)
 *
 * This component is intentionally FLAME-only — SPARK/INFERNO still use
 * BuilderTab which renders the 4-leg IC payoff.
 */
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'

const PREVIEW_REFRESH_MS = 30_000

interface PreviewResponse {
  preview_time: string
  bot: string
  strategy: string
  account: { balance: number | null; source: string; error: string | null }
  market: { spy: number; vix: number; expected_move: number; expected_move_pct: number }
  expiration: string
  strikes: {
    put_long: number
    put_short: number
    short_distance_dollars: number
    short_distance_sd: number
  }
  credit: {
    per_contract: number
    source: string
    raw_legs?: {
      put_short: { bid: number; ask: number } | null
      put_long: { bid: number; ask: number } | null
    }
  }
  sizing: {
    risk_pct: number
    max_loss_per_contract: number
    contracts: number
    total_risk_dollar: number
    max_profit_total_dollar: number
  }
  exits: {
    profit_target: { pct_of_credit: number; cost_to_close: number; pnl_dollar: number }
    stop_loss: { multiplier_of_credit: number; cost_to_close: number; pnl_dollar: number }
  }
  gates: {
    vix: { required: string; actual: number | string; pass: boolean }
    credit: { required: string; actual: number | string; pass: boolean }
    account: { required: string; actual: number | string; pass: boolean }
  }
  go_no_go: 'READY' | 'BLOCKED'
  reasons_blocked: string[]
  error?: string
}

function fmt(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return '—'
  return n.toFixed(digits)
}
function fmt$(n: number | null | undefined, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return '—'
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })}`
}

/**
 * Render a bull put credit spread payoff at expiration as inline SVG.
 * The payoff is piecewise-linear:
 *   price <= put_long          : max_loss  (negative)
 *   put_long < price < put_short: linear from max_loss to max_profit
 *   price >= put_short          : max_profit (positive)
 * Breakeven = put_short − credit.
 */
function PayoffChart({
  putLong,
  putShort,
  credit,
  contracts,
  spot,
  rangePct = 0.035,
}: {
  putLong: number
  putShort: number
  credit: number
  contracts: number
  spot: number
  rangePct?: number
}) {
  if (!Number.isFinite(spot) || spot <= 0) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-6 text-center text-forge-muted text-xs">
        Payoff chart unavailable — SPY spot not loaded.
      </div>
    )
  }

  const padBelow = Math.min(spot * rangePct, spot - putLong + 4)
  const minPrice = Math.min(putLong - 4, spot - padBelow)
  const maxPrice = Math.max(spot * (1 + rangePct), putShort + 4)
  const contractsMult = Math.max(contracts, 1)
  const maxProfit = credit * 100 * contractsMult
  const maxLoss = -(5 - credit) * 100 * contractsMult
  const breakeven = putShort - credit

  const W = 800
  const H = 260
  const padL = 50
  const padR = 20
  const padT = 20
  const padB = 30
  const plotW = W - padL - padR
  const plotH = H - padT - padB

  const xForPrice = (p: number) => padL + ((p - minPrice) / (maxPrice - minPrice)) * plotW
  const yForPnl = (pnl: number) => {
    const absMax = Math.max(Math.abs(maxProfit), Math.abs(maxLoss))
    const ratio = pnl / absMax
    return padT + plotH / 2 - (ratio * plotH) / 2
  }

  // Payoff points: flat max_loss below put_long, linear to put_short, flat max_profit above
  const points = [
    { p: minPrice, v: maxLoss },
    { p: putLong, v: maxLoss },
    { p: putShort, v: maxProfit },
    { p: maxPrice, v: maxProfit },
  ]

  const pathD = points.map((pt, i) => `${i === 0 ? 'M' : 'L'}${xForPrice(pt.p).toFixed(2)},${yForPnl(pt.v).toFixed(2)}`).join(' ')
  const fillD = `${pathD} L${xForPrice(maxPrice).toFixed(2)},${yForPnl(0).toFixed(2)} L${xForPrice(minPrice).toFixed(2)},${yForPnl(0).toFixed(2)} Z`

  const zeroY = yForPnl(0)

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 p-3">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" preserveAspectRatio="none">
        {/* Zero axis */}
        <line x1={padL} x2={W - padR} y1={zeroY} y2={zeroY} stroke="#374151" strokeWidth={1} strokeDasharray="3,3" />
        {/* Profit fill (green above 0) clipped to the payoff path's profit section */}
        <path d={fillD} fill="#10b98133" />
        {/* Payoff line */}
        <path d={pathD} fill="none" stroke="#f59e0b" strokeWidth={2} />
        {/* Put long strike */}
        <line x1={xForPrice(putLong)} x2={xForPrice(putLong)} y1={padT} y2={H - padB} stroke="#10b981" strokeWidth={1} strokeDasharray="2,3" />
        <text x={xForPrice(putLong)} y={padT + 10} fill="#10b981" fontSize={10} textAnchor="middle">{putLong}</text>
        {/* Put short strike */}
        <line x1={xForPrice(putShort)} x2={xForPrice(putShort)} y1={padT} y2={H - padB} stroke="#ef4444" strokeWidth={1} strokeDasharray="2,3" />
        <text x={xForPrice(putShort)} y={padT + 10} fill="#ef4444" fontSize={10} textAnchor="middle">{putShort}</text>
        {/* Breakeven */}
        <line x1={xForPrice(breakeven)} x2={xForPrice(breakeven)} y1={padT} y2={H - padB} stroke="#eab308" strokeWidth={1} strokeDasharray="1,2" />
        <text x={xForPrice(breakeven)} y={H - padB + 14} fill="#eab308" fontSize={9} textAnchor="middle">BE {breakeven.toFixed(2)}</text>
        {/* Spot marker */}
        <line x1={xForPrice(spot)} x2={xForPrice(spot)} y1={padT} y2={H - padB} stroke="#60a5fa" strokeWidth={1.5} />
        <text x={xForPrice(spot)} y={H - padB + 14} fill="#60a5fa" fontSize={10} textAnchor="middle">Spot {spot.toFixed(2)}</text>
        {/* P&L labels */}
        <text x={W - padR - 4} y={yForPnl(maxProfit) - 2} fill="#10b981" fontSize={10} textAnchor="end">+{maxProfit.toFixed(0)}</text>
        <text x={padL + 4} y={yForPnl(maxLoss) + 12} fill="#ef4444" fontSize={10} textAnchor="start">{maxLoss.toFixed(0)}</text>
      </svg>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-forge-muted font-mono mt-1 pl-[50px]">
        <span><span className="inline-block w-2 h-2 bg-emerald-500 rounded-sm mr-1" />Put long {putLong}</span>
        <span><span className="inline-block w-2 h-2 bg-red-500 rounded-sm mr-1" />Put short {putShort}</span>
        <span><span className="inline-block w-2 h-2 bg-yellow-500 rounded-sm mr-1" />Breakeven {breakeven.toFixed(2)}</span>
        <span><span className="inline-block w-2 h-2 bg-blue-400 rounded-sm mr-1" />SPY spot {spot.toFixed(2)}</span>
      </div>
    </div>
  )
}

export default function FlamePutSpreadTab() {
  const { data: snap, error } = useSWR<PreviewResponse>(
    `/api/flame/preview-put-spread`,
    fetcher,
    { refreshInterval: PREVIEW_REFRESH_MS },
  )

  if (error) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4">
        <p className="text-red-400 text-sm">Put spread preview failed: {error.message}</p>
      </div>
    )
  }

  if (!snap) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-8 text-center">
        <p className="text-forge-muted text-sm animate-pulse">Loading put spread chart...</p>
      </div>
    )
  }

  if (snap.error) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4">
        <p className="text-red-400 text-sm">{snap.error}</p>
      </div>
    )
  }

  const credit = snap.credit.per_contract
  const goBadge = snap.go_no_go === 'READY'
    ? <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 uppercase tracking-wider">Ready</span>
    : <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-gray-500/20 text-gray-300 border border-gray-500/30 uppercase tracking-wider">Blocked</span>

  const GatePill = ({ label, pass, required, actual }: { label: string; pass: boolean; required: string; actual: string | number }) => (
    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${pass ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'}`}>
      {label} {required} — actual {actual} {pass ? '✓' : '✗'}
    </span>
  )

  return (
    <div className="space-y-4">
      {/* Header — strategy summary */}
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-3">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-forge-muted uppercase tracking-wider mr-1">Strategy</span>
            <span className="font-mono text-amber-400">2DTE Put Credit Spread</span>
            <span className="text-gray-500 font-mono">SPY exp {snap.expiration}</span>
            {goBadge}
          </div>
          <div className="font-mono text-gray-200">
            <span className="text-emerald-400">{snap.strikes.put_long}P</span>
            <span className="text-forge-muted"> / </span>
            <span className="text-red-400">{snap.strikes.put_short}P</span>
            <span className="text-forge-muted ml-2 text-[10px]">
              (short {fmt$(snap.strikes.short_distance_dollars)} / {fmt(snap.strikes.short_distance_sd)} SD OTM)
            </span>
          </div>
          <div>
            <span className="text-forge-muted uppercase tracking-wider mr-1">Credit</span>
            <span className="font-mono text-white">{fmt$(credit, 4)}</span>
            <span className="text-[10px] text-forge-muted ml-1">({snap.credit.source})</span>
          </div>
          <div>
            <span className="text-forge-muted uppercase tracking-wider mr-1">Contracts</span>
            <span className="font-mono text-white">{snap.sizing.contracts}</span>
            <span className="text-[10px] text-forge-muted ml-1">(10% risk)</span>
          </div>
          <div>
            <span className="text-forge-muted uppercase tracking-wider mr-1">Spot</span>
            <span className="font-mono text-white">{fmt$(snap.market.spy)}</span>
          </div>
          <div>
            <span className="text-forge-muted uppercase tracking-wider mr-1">VIX</span>
            <span className="font-mono text-white">{fmt(snap.market.vix)}</span>
          </div>
        </div>
      </div>

      {/* Key numbers */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="rounded-xl border border-forge-border bg-forge-card/80 p-3">
          <p className="text-xs text-forge-muted uppercase tracking-wider">Max Profit</p>
          <p className="text-lg font-semibold text-emerald-400">{fmt$(snap.sizing.max_profit_total_dollar)}</p>
          <p className="text-[10px] text-forge-muted mt-0.5">{snap.sizing.contracts} × credit × 100</p>
        </div>
        <div className="rounded-xl border border-forge-border bg-forge-card/80 p-3">
          <p className="text-xs text-forge-muted uppercase tracking-wider">Max Loss</p>
          <p className="text-lg font-semibold text-red-400">{fmt$(-snap.sizing.total_risk_dollar)}</p>
          <p className="text-[10px] text-forge-muted mt-0.5">{fmt$(snap.sizing.max_loss_per_contract)} × {snap.sizing.contracts} contracts</p>
        </div>
        <div className="rounded-xl border border-forge-border bg-forge-card/80 p-3">
          <p className="text-xs text-forge-muted uppercase tracking-wider">50% PT</p>
          <p className="text-lg font-semibold text-emerald-400">{fmt$(snap.exits.profit_target.pnl_dollar)}</p>
          <p className="text-[10px] text-forge-muted mt-0.5">Close at CTC {fmt$(snap.exits.profit_target.cost_to_close, 4)}</p>
        </div>
        <div className="rounded-xl border border-forge-border bg-forge-card/80 p-3">
          <p className="text-xs text-forge-muted uppercase tracking-wider">200% SL</p>
          <p className="text-lg font-semibold text-red-400">{fmt$(snap.exits.stop_loss.pnl_dollar)}</p>
          <p className="text-[10px] text-forge-muted mt-0.5">Close at CTC {fmt$(snap.exits.stop_loss.cost_to_close, 4)}</p>
        </div>
      </div>

      {/* Payoff chart */}
      <PayoffChart
        putLong={snap.strikes.put_long}
        putShort={snap.strikes.put_short}
        credit={credit}
        contracts={snap.sizing.contracts}
        spot={snap.market.spy}
      />

      {/* Gates */}
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-3">
        <p className="text-xs text-forge-muted uppercase tracking-wider mb-2">Entry Gates</p>
        <div className="flex flex-wrap gap-2">
          <GatePill label="VIX" pass={snap.gates.vix.pass} required={snap.gates.vix.required} actual={snap.gates.vix.actual} />
          <GatePill label="Credit" pass={snap.gates.credit.pass} required={snap.gates.credit.required} actual={snap.gates.credit.actual} />
          <GatePill label="Account" pass={snap.gates.account.pass} required={snap.gates.account.required} actual={snap.gates.account.actual} />
        </div>
        {snap.reasons_blocked.length > 0 && (
          <div className="mt-2 text-xs text-red-400">
            {snap.reasons_blocked.map((r, i) => <div key={i}>• {r}</div>)}
          </div>
        )}
      </div>

      {/* Transition disclaimer — can be removed once PR 2 ships the scanner rewrite */}
      <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-3 text-[11px] text-amber-300/80">
        <p className="font-semibold mb-1">Preview-only while the scanner is being rewritten.</p>
        <p>
          FLAME is migrating from Iron Condor to Put Credit Spread. This chart shows what FLAME
          <span className="italic"> would </span>trade right now under the new rules (16-delta short put,
          $5 wing, 10% account risk, 50% PT / 200% SL). Actual scanner flip ships in a follow-up PR —
          until then, FLAME is still placing Iron Condors in the background.
        </p>
      </div>
    </div>
  )
}
