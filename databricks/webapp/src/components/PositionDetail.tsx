'use client'

/* ------------------------------------------------------------------ */
/*  PositionDetail — full transparency view for an open Iron Condor    */
/*  Shows: per-leg quotes, P&L math, key metrics, sandbox P&L,        */
/*  and a max-loss <-> max-profit progress bar.                        */
/* ------------------------------------------------------------------ */

interface Leg {
  type: string
  label: string
  strike: number
  option_type: string
  side: 'buy' | 'sell'
  occ: string
  quantity: number
  current_bid: number | null
  current_ask: number | null
  current_mid: number | null
}

interface SandboxAccount {
  name: string
  order_id: number | string | null
  contracts: number
  entry_credit_total: number
  current_debit_total: number | null
  calculated_pnl: number | null
  tradier_pnl: number | null
  tradier_cost_basis: number | null
  tradier_market_value: number | null
}

interface PositionDetailData {
  position_id: string
  ticker: string
  expiration: string
  put_short_strike: number
  put_long_strike: number
  put_credit: number
  call_short_strike: number
  call_long_strike: number
  call_credit: number
  contracts: number
  total_credit: number
  collateral_required: number
  spy_price: number | null
  legs: Leg[]
  entry_credit: number
  current_debit: number | null
  spread_pnl_per_contract: number | null
  paper_pnl: number | null
  max_profit: number
  max_loss: number
  put_breakeven: number
  call_breakeven: number
  distance_to_put: number | null
  distance_to_call: number | null
  pct_profit_captured: number | null
  current_pt_tier: string
  current_pt_pct: number
  pt_target_price: number
  pt_target_dollar: number
  pct_to_pt: number | null
  progress: {
    max_loss: number
    current: number | null
    zero: number
    pt_target: number
    max_profit: number
  }
  sandbox_accounts: SandboxAccount[]
}

function pnlColor(val: number | null): string {
  if (val == null) return 'text-gray-400'
  return val >= 0 ? 'text-emerald-400' : 'text-red-400'
}

function fmtDollar(val: number | null, decimals = 2): string {
  if (val == null) return '--'
  const sign = val >= 0 ? '' : '-'
  return `${sign}$${Math.abs(val).toFixed(decimals)}`
}

function fmtPct(val: number | null): string {
  if (val == null) return '--'
  return `${val >= 0 ? '+' : ''}${val.toFixed(1)}%`
}

/* ------------------------------------------------------------------ */
/*  Per-Leg Breakdown Table                                            */
/* ------------------------------------------------------------------ */

function LegsTable({ legs }: { legs: Leg[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs font-mono">
        <thead>
          <tr className="text-forge-muted text-left border-b border-forge-border/50">
            <th className="py-1.5 pr-3">Leg</th>
            <th className="py-1.5 pr-3">Strike</th>
            <th className="py-1.5 pr-3">Side</th>
            <th className="py-1.5 pr-3 text-right">Bid</th>
            <th className="py-1.5 pr-3 text-right">Ask</th>
            <th className="py-1.5 pr-3 text-right">Mid</th>
            <th className="py-1.5 text-right">Qty</th>
          </tr>
        </thead>
        <tbody>
          {legs.map((leg) => (
            <tr key={leg.type} className="border-b border-forge-border/20">
              <td className="py-1.5 pr-3 text-gray-300">{leg.label}</td>
              <td className="py-1.5 pr-3">
                {leg.strike}
                <span className="text-forge-muted">{leg.option_type}</span>
              </td>
              <td className={`py-1.5 pr-3 ${leg.side === 'sell' ? 'text-red-400' : 'text-emerald-400'}`}>
                {leg.side === 'sell' ? 'Sell' : 'Buy'}
              </td>
              <td className="py-1.5 pr-3 text-right">
                {leg.current_bid != null ? `$${leg.current_bid.toFixed(2)}` : '--'}
              </td>
              <td className="py-1.5 pr-3 text-right">
                {leg.current_ask != null ? `$${leg.current_ask.toFixed(2)}` : '--'}
              </td>
              <td className="py-1.5 pr-3 text-right font-medium">
                {leg.current_mid != null ? `$${leg.current_mid.toFixed(2)}` : '--'}
              </td>
              <td className={`py-1.5 text-right ${leg.side === 'sell' ? 'text-red-400' : 'text-emerald-400'}`}>
                {leg.side === 'sell' ? '-' : '+'}{leg.quantity}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  P&L Math Breakdown                                                 */
/* ------------------------------------------------------------------ */

function PnlMath({ pos }: { pos: PositionDetailData }) {
  return (
    <div className="bg-forge-card/50 rounded-lg p-3 font-mono text-xs space-y-1">
      <div className="flex justify-between">
        <span className="text-forge-muted">Net Credit at Entry:</span>
        <span className="text-emerald-400">${pos.entry_credit.toFixed(2)}</span>
      </div>
      <div className="flex justify-between">
        <span className="text-forge-muted">Net Debit to Close:</span>
        <span className={pnlColor(pos.current_debit != null ? -1 : null)}>
          {pos.current_debit != null ? `$${pos.current_debit.toFixed(2)}` : '--'}
        </span>
      </div>
      <div className="border-t border-forge-border/30 pt-1 flex justify-between">
        <span className="text-forge-muted">
          Spread P&L/contract:
        </span>
        <span className={pnlColor(pos.spread_pnl_per_contract)}>
          {pos.spread_pnl_per_contract != null
            ? `${pos.spread_pnl_per_contract >= 0 ? '+' : ''}$${pos.spread_pnl_per_contract.toFixed(2)}`
            : '--'}
        </span>
      </div>
      <div className="flex justify-between font-bold">
        <span className="text-gray-300">
          Paper P&L:
          <span className="text-forge-muted font-normal ml-1">
            {pos.spread_pnl_per_contract != null
              ? `(${pos.spread_pnl_per_contract >= 0 ? '' : '-'}$${Math.abs(pos.spread_pnl_per_contract).toFixed(2)} x 100 x ${pos.contracts})`
              : ''}
          </span>
        </span>
        <span className={pnlColor(pos.paper_pnl)}>
          {fmtDollar(pos.paper_pnl)}
        </span>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Key Metrics Row                                                    */
/* ------------------------------------------------------------------ */

function KeyMetrics({ pos }: { pos: PositionDetailData }) {
  const metrics = [
    { label: 'Max Profit', value: fmtDollar(pos.max_profit), color: 'text-emerald-400' },
    { label: 'Max Loss', value: fmtDollar(-pos.max_loss), color: 'text-red-400' },
    { label: 'Put BE', value: `$${pos.put_breakeven.toFixed(2)}`, color: 'text-gray-300' },
    { label: 'Call BE', value: `$${pos.call_breakeven.toFixed(2)}`, color: 'text-gray-300' },
    {
      label: 'SPY',
      value: pos.spy_price != null ? `$${pos.spy_price.toFixed(2)}` : '--',
      color: 'text-white',
    },
    {
      label: 'Dist Put',
      value: pos.distance_to_put != null ? `$${pos.distance_to_put.toFixed(2)}` : '--',
      color: pos.distance_to_put != null && pos.distance_to_put < 5 ? 'text-red-400' : 'text-emerald-400',
    },
    {
      label: 'Dist Call',
      value: pos.distance_to_call != null ? `$${pos.distance_to_call.toFixed(2)}` : '--',
      color: pos.distance_to_call != null && pos.distance_to_call < 5 ? 'text-red-400' : 'text-emerald-400',
    },
    {
      label: '% Captured',
      value: fmtPct(pos.pct_profit_captured),
      color: pnlColor(pos.pct_profit_captured),
    },
  ]

  return (
    <div className="grid grid-cols-4 sm:grid-cols-8 gap-2 text-xs">
      {metrics.map((m) => (
        <div key={m.label} className="text-center">
          <p className="text-forge-muted text-[10px]">{m.label}</p>
          <p className={`font-mono font-medium ${m.color}`}>{m.value}</p>
        </div>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Per-Account Sandbox P&L Table                                      */
/* ------------------------------------------------------------------ */

function SandboxPnlTable({ accounts }: { accounts: SandboxAccount[] }) {
  if (!accounts.length) return null

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs font-mono">
        <thead>
          <tr className="text-forge-muted text-left border-b border-forge-border/50">
            <th className="py-1.5 pr-3">Account</th>
            <th className="py-1.5 pr-3 text-right">Contracts</th>
            <th className="py-1.5 pr-3 text-right">Entry Credit</th>
            <th className="py-1.5 pr-3 text-right">Current Debit</th>
            <th className="py-1.5 pr-3 text-right">Calc P&L</th>
            <th className="py-1.5 text-right">Tradier P&L</th>
          </tr>
        </thead>
        <tbody>
          {accounts.map((acct) => (
            <tr key={acct.name} className="border-b border-forge-border/20">
              <td className="py-1.5 pr-3">
                <span className="text-gray-300">{acct.name}</span>
                {acct.order_id && (
                  <span className="text-forge-muted ml-1 text-[10px]">
                    #{acct.order_id}
                  </span>
                )}
              </td>
              <td className="py-1.5 pr-3 text-right">{acct.contracts}x</td>
              <td className="py-1.5 pr-3 text-right text-emerald-400">
                {fmtDollar(acct.entry_credit_total)}
              </td>
              <td className="py-1.5 pr-3 text-right">
                {fmtDollar(acct.current_debit_total)}
              </td>
              <td className={`py-1.5 pr-3 text-right ${pnlColor(acct.calculated_pnl)}`}>
                {fmtDollar(acct.calculated_pnl)}
              </td>
              <td className={`py-1.5 text-right ${pnlColor(acct.tradier_pnl)}`}>
                {acct.tradier_pnl != null ? (
                  <span title="From Tradier API">{fmtDollar(acct.tradier_pnl)}</span>
                ) : (
                  <span className="text-forge-muted">--</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Progress Bar: Max Loss <-> Max Profit                              */
/* ------------------------------------------------------------------ */

function ProgressBar({ pos }: { pos: PositionDetailData }) {
  const { max_loss, max_profit, progress } = pos
  if (progress.current == null) return null

  // Total range from max_loss to max_profit
  const totalRange = max_loss + max_profit
  if (totalRange <= 0) return null

  // Positions on the bar (0% = max loss, 100% = max profit)
  const toPercent = (val: number) =>
    Math.max(0, Math.min(100, ((val + max_loss) / totalRange) * 100))

  const currentPct = toPercent(progress.current)
  const zeroPct = toPercent(0)
  const ptPct = toPercent(progress.pt_target)

  const currentColor =
    progress.current >= 0 ? 'bg-emerald-400' : 'bg-red-400'

  return (
    <div className="space-y-1.5">
      {/* Labels row */}
      <div className="flex justify-between text-[10px] text-forge-muted font-mono">
        <span className="text-red-400">-{fmtDollar(max_loss)}</span>
        <span className="text-gray-400">$0</span>
        <span className="text-amber-400">PT {fmtDollar(pos.pt_target_dollar)}</span>
        <span className="text-emerald-400">{fmtDollar(max_profit)}</span>
      </div>

      {/* Bar */}
      <div className="h-3 bg-forge-border rounded-full overflow-hidden relative">
        {/* Red zone (loss) */}
        <div
          className="absolute inset-y-0 left-0 bg-red-500/20"
          style={{ width: `${zeroPct}%` }}
        />
        {/* Green zone (profit to PT) */}
        <div
          className="absolute inset-y-0 bg-emerald-500/15"
          style={{ left: `${zeroPct}%`, width: `${ptPct - zeroPct}%` }}
        />
        {/* Beyond PT */}
        <div
          className="absolute inset-y-0 bg-emerald-500/25"
          style={{ left: `${ptPct}%`, width: `${100 - ptPct}%` }}
        />

        {/* Zero line */}
        <div
          className="absolute inset-y-0 w-px bg-gray-500"
          style={{ left: `${zeroPct}%` }}
        />

        {/* PT marker */}
        <div
          className="absolute inset-y-0 w-px bg-amber-400/70"
          style={{ left: `${ptPct}%` }}
        />

        {/* Current position marker */}
        <div
          className={`absolute top-0 h-full w-2 rounded ${currentColor}`}
          style={{ left: `${currentPct}%`, transform: 'translateX(-50%)' }}
        />
      </div>

      {/* Current value annotation */}
      <div className="text-center">
        <span className={`text-xs font-mono font-bold ${pnlColor(progress.current)}`}>
          Current: {fmtDollar(progress.current)}
        </span>
        {pos.pct_to_pt != null && (
          <span className="text-[10px] text-forge-muted ml-2">
            ({pos.pct_to_pt.toFixed(0)}% to {pos.current_pt_pct}% {pos.current_pt_tier} PT)
          </span>
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Main Component                                                     */
/* ------------------------------------------------------------------ */

export default function PositionDetail({
  data,
}: {
  data: PositionDetailData
}) {
  return (
    <div className="space-y-3 mt-3 border-t border-forge-border/50 pt-3">
      {/* Section: Per-Leg Breakdown */}
      <div>
        <p className="text-[10px] text-forge-muted uppercase tracking-wider mb-1.5">
          Per-Leg Quotes (Live)
        </p>
        <LegsTable legs={data.legs} />
      </div>

      {/* Section: P&L Math */}
      <div>
        <p className="text-[10px] text-forge-muted uppercase tracking-wider mb-1.5">
          P&L Breakdown
        </p>
        <PnlMath pos={data} />
      </div>

      {/* Section: Key Metrics */}
      <div>
        <p className="text-[10px] text-forge-muted uppercase tracking-wider mb-1.5">
          Key Metrics
        </p>
        <KeyMetrics pos={data} />
      </div>

      {/* Section: Progress Bar */}
      <div>
        <p className="text-[10px] text-forge-muted uppercase tracking-wider mb-1.5">
          Position Progress
        </p>
        <ProgressBar pos={data} />
      </div>

      {/* Section: Sandbox P&L */}
      {data.sandbox_accounts.length > 0 && (
        <div>
          <p className="text-[10px] text-forge-muted uppercase tracking-wider mb-1.5">
            Per-Account P&L
          </p>
          <SandboxPnlTable accounts={data.sandbox_accounts} />
        </div>
      )}
    </div>
  )
}
