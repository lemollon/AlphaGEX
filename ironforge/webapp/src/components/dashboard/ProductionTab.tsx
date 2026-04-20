'use client'

import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'

const REFRESH_MS = 15_000

type AccentColor = 'amber' | 'blue' | 'red'

interface BalanceRow {
  name: string
  account_id: string | null
  account_number?: string | null
  total_equity?: number | null
  total_cash?: number | null
  option_buying_power?: number | null
  stock_buying_power?: number | null
  day_trade_buying_power?: number | null
  cash_available?: number | null
  open_pl?: number | null
  close_pl?: number | null
  market_value?: number | null
  error?: string
}

interface PositionRow {
  symbol: string
  quantity: number
  cost_basis: number
  market_value: number
  gain_loss: number
  gain_loss_percent: number
}

interface PositionsAccount {
  name: string
  account_id: string | null
  positions: PositionRow[]
}

interface OrderLeg {
  option_symbol: string | null
  side: string | null
  quantity: number | null
  exec_quantity: number | null
  last_fill_price: number | null
  type: string | null
}

interface OrderRow {
  id: number | string
  status: string
  type: string | null
  duration: string | null
  side: string | null
  symbol: string | null
  quantity: number | null
  price: number | null
  avg_fill_price: number | null
  exec_quantity: number | null
  last_fill_price: number | null
  class: string | null
  create_date: string | null
  transaction_date: string | null
  tag: string | null
  reason_description: string | null
  legs: OrderLeg[]
}

interface OrdersAccount {
  name: string
  account_id: string | null
  open: OrderRow[]
  history: OrderRow[]
  error?: string
}

function fmtMoney(v: number | null | undefined, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return `$${v.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })}`
}

function fmtQty(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return v.toLocaleString()
}

function fmtTs(v: string | null | undefined): string {
  if (!v) return '—'
  const t = Date.parse(v)
  if (isNaN(t)) return v
  return new Date(t).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone: 'America/Chicago',
  })
}

function LoadingCard() {
  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 p-6 text-center">
      <p className="text-forge-muted text-sm animate-pulse">Loading...</p>
    </div>
  )
}

function ErrorCard({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4">
      <p className="text-red-400 text-sm">Failed to load: {message}</p>
    </div>
  )
}

function BalancesSection({ bot }: { bot: string }) {
  const { data, error } = useSWR<{ accounts: BalanceRow[] }>(
    `/api/${bot}/production/balances`,
    fetcher,
    { refreshInterval: REFRESH_MS },
  )

  if (error) return <ErrorCard message={error.message} />
  if (!data) return <LoadingCard />

  const accounts = data.accounts || []
  if (accounts.length === 0) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-6 text-center">
        <p className="text-forge-muted text-sm">No production accounts configured for this bot.</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {accounts.map((a) => (
        <div key={a.name} className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="text-sm font-semibold text-white">{a.name}</p>
              <p className="text-[10px] font-mono text-forge-muted">
                {a.account_number ?? a.account_id ?? '—'}
              </p>
            </div>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-red-500/20 text-red-400 border border-red-500/30 uppercase tracking-wider">
              Live
            </span>
          </div>
          {a.error ? (
            <p className="text-sm text-red-400">Balance fetch failed: {a.error}</p>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Stat label="Total Equity" value={fmtMoney(a.total_equity)} />
              <Stat label="Option BP" value={fmtMoney(a.option_buying_power)} emphasis />
              <Stat label="Cash" value={fmtMoney(a.total_cash)} />
              <Stat label="Day Trade BP" value={fmtMoney(a.day_trade_buying_power)} />
              <Stat label="Stock BP" value={fmtMoney(a.stock_buying_power)} />
              <Stat label="Cash Available" value={fmtMoney(a.cash_available)} />
              <Stat
                label="Open P&L"
                value={fmtMoney(a.open_pl)}
                tone={a.open_pl != null ? (a.open_pl >= 0 ? 'up' : 'down') : 'neutral'}
              />
              <Stat
                label="Close P&L"
                value={fmtMoney(a.close_pl)}
                tone={a.close_pl != null ? (a.close_pl >= 0 ? 'up' : 'down') : 'neutral'}
              />
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function Stat({
  label,
  value,
  emphasis,
  tone,
}: {
  label: string
  value: string
  emphasis?: boolean
  tone?: 'up' | 'down' | 'neutral'
}) {
  const toneClass =
    tone === 'up'
      ? 'text-emerald-400'
      : tone === 'down'
      ? 'text-red-400'
      : emphasis
      ? 'text-white'
      : 'text-gray-200'
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-forge-muted">{label}</p>
      <p className={`text-sm font-semibold ${toneClass}`}>{value}</p>
    </div>
  )
}

function PositionsSection({ bot }: { bot: string }) {
  const { data, error } = useSWR<{ accounts: PositionsAccount[] }>(
    `/api/${bot}/production/positions`,
    fetcher,
    { refreshInterval: REFRESH_MS },
  )

  if (error) return <ErrorCard message={error.message} />
  if (!data) return <LoadingCard />

  const accounts = data.accounts || []
  const total = accounts.reduce((n, a) => n + (a.positions?.length ?? 0), 0)

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold text-white">Broker Positions</h4>
        <span className="text-xs text-forge-muted">{total} leg{total === 1 ? '' : 's'}</span>
      </div>
      {accounts.length === 0 || total === 0 ? (
        <p className="text-sm text-forge-muted">No open broker positions.</p>
      ) : (
        <div className="space-y-3">
          {accounts.map((a) => (
            <div key={a.name}>
              <p className="text-xs font-medium text-gray-300 mb-1">{a.name}</p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-forge-muted border-b border-forge-border/50">
                      <th className="text-left py-1.5 pr-3 font-normal">Symbol</th>
                      <th className="text-right py-1.5 pr-3 font-normal">Qty</th>
                      <th className="text-right py-1.5 pr-3 font-normal">Cost Basis</th>
                      <th className="text-right py-1.5 pr-3 font-normal">Market Value</th>
                      <th className="text-right py-1.5 font-normal">G/L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {a.positions.map((p) => (
                      <tr key={p.symbol} className="border-b border-forge-border/20">
                        <td className="py-1.5 pr-3 font-mono text-gray-200">{p.symbol}</td>
                        <td className="py-1.5 pr-3 text-right text-gray-200">{fmtQty(p.quantity)}</td>
                        <td className="py-1.5 pr-3 text-right text-gray-200">{fmtMoney(p.cost_basis)}</td>
                        <td className="py-1.5 pr-3 text-right text-gray-200">{fmtMoney(p.market_value)}</td>
                        <td
                          className={`py-1.5 text-right font-semibold ${
                            p.gain_loss >= 0 ? 'text-emerald-400' : 'text-red-400'
                          }`}
                        >
                          {p.gain_loss >= 0 ? '+' : ''}
                          {fmtMoney(p.gain_loss)}
                          {p.gain_loss_percent != null && (
                            <span className="text-[10px] ml-1">
                              ({p.gain_loss_percent.toFixed(1)}%)
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function describeOrder(o: OrderRow): string {
  if (o.legs && o.legs.length > 0) {
    const legBits = o.legs.map(
      (l) => `${l.side ?? '?'} ${fmtQty(l.quantity)} ${l.option_symbol ?? '?'}`,
    )
    return legBits.join(' / ')
  }
  const bits: string[] = []
  if (o.side) bits.push(o.side)
  if (o.quantity != null) bits.push(String(o.quantity))
  if (o.symbol) bits.push(o.symbol)
  return bits.length > 0 ? bits.join(' ') : `Order #${o.id}`
}

function OrderTable({ rows, emptyMessage }: { rows: OrderRow[]; emptyMessage: string }) {
  if (rows.length === 0) {
    return <p className="text-sm text-forge-muted">{emptyMessage}</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-forge-muted border-b border-forge-border/50">
            <th className="text-left py-1.5 pr-3 font-normal">Time (CT)</th>
            <th className="text-left py-1.5 pr-3 font-normal">ID</th>
            <th className="text-left py-1.5 pr-3 font-normal">Status</th>
            <th className="text-left py-1.5 pr-3 font-normal">Type</th>
            <th className="text-left py-1.5 pr-3 font-normal">Description</th>
            <th className="text-right py-1.5 pr-3 font-normal">Price</th>
            <th className="text-right py-1.5 font-normal">Fill</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((o) => (
            <tr key={`${o.id}-${o.status}`} className="border-b border-forge-border/20">
              <td className="py-1.5 pr-3 text-gray-300">
                {fmtTs(o.transaction_date || o.create_date)}
              </td>
              <td className="py-1.5 pr-3 font-mono text-gray-400">{o.id}</td>
              <td className="py-1.5 pr-3">
                <span
                  className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                    o.status === 'filled'
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : o.status === 'canceled' || o.status === 'rejected' || o.status === 'expired'
                      ? 'bg-gray-500/20 text-gray-400'
                      : 'bg-blue-500/20 text-blue-400'
                  }`}
                >
                  {o.status}
                </span>
              </td>
              <td className="py-1.5 pr-3 text-gray-300">{o.type ?? '—'}</td>
              <td className="py-1.5 pr-3 font-mono text-gray-200 truncate max-w-[320px]">
                {describeOrder(o)}
                {o.tag ? <span className="text-forge-muted"> · tag={o.tag}</span> : null}
              </td>
              <td className="py-1.5 pr-3 text-right text-gray-200">
                {o.price != null ? fmtMoney(o.price) : '—'}
              </td>
              <td className="py-1.5 text-right text-gray-200">
                {o.avg_fill_price != null
                  ? fmtMoney(o.avg_fill_price)
                  : o.last_fill_price != null
                  ? fmtMoney(o.last_fill_price)
                  : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function OrdersSection({ bot }: { bot: string }) {
  const { data, error } = useSWR<{ accounts: OrdersAccount[]; history_window_days: number }>(
    `/api/${bot}/production/orders`,
    fetcher,
    { refreshInterval: REFRESH_MS },
  )

  if (error) return <ErrorCard message={error.message} />
  if (!data) return <LoadingCard />

  const accounts = data.accounts || []
  const windowDays = data.history_window_days ?? 30

  return (
    <div className="space-y-4">
      {accounts.map((a) => (
        <div key={a.name} className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-semibold text-white">Orders · {a.name}</h4>
            <span className="text-xs text-forge-muted">
              {a.open.length} open · {a.history.length} historical (last {windowDays}d)
            </span>
          </div>
          {a.error ? (
            <p className="text-sm text-red-400">Order fetch failed: {a.error}</p>
          ) : (
            <div className="space-y-4">
              <div>
                <p className="text-xs uppercase tracking-wider text-forge-muted mb-2">Open</p>
                <OrderTable rows={a.open} emptyMessage="No open orders." />
              </div>
              <div>
                <p className="text-xs uppercase tracking-wider text-forge-muted mb-2">
                  Historical (last {windowDays}d)
                </p>
                <OrderTable rows={a.history} emptyMessage={`No orders in the last ${windowDays} days.`} />
              </div>
            </div>
          )}
        </div>
      ))}
      {accounts.length === 0 && (
        <div className="rounded-xl border border-forge-border bg-forge-card/80 p-6 text-center">
          <p className="text-forge-muted text-sm">No production accounts configured.</p>
        </div>
      )}
    </div>
  )
}

export default function ProductionTab({
  bot,
  person,
  accent,
}: {
  bot: string
  person: string | null
  accent: AccentColor
}) {
  void accent
  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-3 text-xs text-red-300">
        Real-money production view for <span className="font-semibold">{bot.toUpperCase()}</span>
        {person ? <> · primary account <span className="font-mono">{person}</span></> : null}
        . Orders shown here are live and affect actual balances.
      </div>
      <section>
        <h3 className="text-sm font-semibold text-white mb-2">Balance &amp; Buying Power</h3>
        <BalancesSection bot={bot} />
      </section>
      <section>
        <h3 className="text-sm font-semibold text-white mb-2">Positions</h3>
        <PositionsSection bot={bot} />
      </section>
      <section>
        <h3 className="text-sm font-semibold text-white mb-2">Orders</h3>
        <OrdersSection bot={bot} />
      </section>
    </div>
  )
}
