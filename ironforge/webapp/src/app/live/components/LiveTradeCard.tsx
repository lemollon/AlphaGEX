'use client'

import { Area, ComposedChart, ReferenceDot, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import type { CustomerState, LiveTrade } from '@/lib/live/types'
import { formatDollarPnl } from '@/lib/format'
import type { AccentTheme } from './accent'

function formatCT(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString('en-US', {
    timeZone: 'America/Chicago', hour: 'numeric', minute: '2-digit',
  })
}

function formatDuration(min: number | null): string {
  if (min == null) return '—'
  const h = Math.floor(min / 60)
  const m = min % 60
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function statusLabel(trade: LiveTrade | null, state: CustomerState | null): { title: string; sub: string } {
  if (state?.key === 'PAUSED') return { title: 'Trading Paused', sub: 'Open positions remain managed' }
  if (trade?.active) {
    return state?.key === 'TRADE_ACTIVE'
      ? { title: 'Trade Active', sub: 'Opening Position' }
      : { title: 'Trade Active', sub: 'Managing Position' }
  }
  if (trade?.today_result) return { title: 'Trade Complete', sub: "Today's result is in" }
  if (state?.key === 'BLOCKED') return { title: 'No Trade Today', sub: 'Protection rules held Spark back' }
  return { title: 'Waiting', sub: 'No live trade right now' }
}

export default function LiveTradeCard({
  trade,
  error,
  state,
  accent,
}: {
  trade: LiveTrade | null
  error: boolean
  state: CustomerState | null
  accent: AccentTheme
}) {
  const label = statusLabel(trade, state)
  const pnl = trade?.active ? trade.unrealized_pnl : trade?.today_result?.pnl ?? null
  const pct = trade?.active ? trade.unrealized_pnl_pct : trade?.today_result?.pct ?? null
  const pnlPositive = pnl != null && pnl >= 0
  const series = trade?.spark_series ?? []
  const showChart = series.length >= 2
  const lastPnl = series.length ? series[series.length - 1].pnl : 0
  // Color by the OUTCOME the card reports, not the raw last series point — post-close
  // snapshots used to zero out and paint a −$208 day green (2026-07-17 fix).
  const outcomePnl = pnl ?? lastPnl
  const chartColor = outcomePnl >= 0 ? '#34d399' : '#f87171'

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <h3 className={`text-xs font-semibold uppercase tracking-widest ${accent.text}`}>Live Trade</h3>

      {error && !trade ? (
        <p className="mt-4 text-sm text-gray-400">Live trade data is temporarily unavailable.</p>
      ) : (
        <>
          <div className="mt-3 flex items-center gap-3">
            <div className={`flex h-11 w-11 items-center justify-center rounded-full border ${accent.chip}`}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
                <path d="M3 17l6-6 4 4 8-8m0 0h-5m5 0v5" />
              </svg>
            </div>
            <div>
              <div className="text-lg font-semibold text-white">{label.title}</div>
              <div className={`text-sm ${accent.text}`}>{label.sub}</div>
            </div>
          </div>

          {trade?.active && (
            <div className="mt-4 grid grid-cols-3 gap-2 border-t border-forge-border pt-3 text-sm">
              <div>
                <div className="text-xs text-gray-500">Opened</div>
                <div className="mt-0.5 text-gray-200">{formatCT(trade.opened_at)} CT</div>
              </div>
              <div>
                <div className="text-xs text-gray-500">Expires</div>
                <div className="mt-0.5 text-gray-200">{trade.expires_label ?? '—'}</div>
              </div>
              <div>
                <div className="text-xs text-gray-500">Time in Trade</div>
                <div className="mt-0.5 text-gray-200">{formatDuration(trade.time_in_trade_min)}</div>
              </div>
            </div>
          )}

          {(trade?.active || trade?.today_result) && (
            <div className="mt-4 rounded-lg border border-forge-border/70 bg-forge-bg/60 p-3">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <div className="shrink-0">
                  <div className="text-xs text-gray-500">
                    {trade.active ? 'Unrealized P&L' : "Today's Result"}
                  </div>
                  <div className={`mt-1 font-mono text-3xl font-semibold ${pnl == null ? 'text-gray-400' : pnlPositive ? 'text-emerald-400' : 'text-red-400'}`}>
                    {formatDollarPnl(pnl)}
                  </div>
                  {pct != null && (
                    <div className={`mt-0.5 text-sm ${pnlPositive ? 'text-emerald-400' : 'text-red-400'}`}>
                      {pct > 0 ? '+' : ''}{pct.toFixed(2)}%
                    </div>
                  )}
                </div>
                {showChart && (
                  <div className="h-[100px] min-w-0 flex-1">
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart data={series} margin={{ top: 6, right: 4, bottom: 0, left: 4 }}>
                        <XAxis dataKey="timestamp" hide />
                        <YAxis
                          orientation="right"
                          domain={['auto', 'auto']}
                          tickFormatter={(v: number) => (v > 0 ? `+$${Math.round(v)}` : v < 0 ? `-$${Math.abs(Math.round(v))}` : '$0')}
                          stroke="transparent"
                          tick={{ fill: '#78716c', fontSize: 10 }}
                          width={48}
                          tickCount={3}
                        />
                        <ReferenceLine y={0} stroke="#78716c" strokeDasharray="4 4" />
                        <Area
                          type="monotone"
                          dataKey="pnl"
                          stroke={chartColor}
                          strokeWidth={2}
                          fill={outcomePnl >= 0 ? 'rgba(52,211,153,0.15)' : 'rgba(248,113,113,0.15)'}
                          isAnimationActive={false}
                          dot={false}
                        />
                        <ReferenceDot
                          x={series[series.length - 1].timestamp}
                          y={lastPnl}
                          r={4}
                          fill={chartColor}
                          stroke="none"
                        />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>
              {trade.active && (
                <div className="mt-2 flex items-center gap-1.5 text-xs text-gray-500">
                  <span className={`h-1.5 w-1.5 rounded-full ${accent.dot}`} />
                  Live updates every 30 seconds
                  {trade.pnl_source === 'scanner_snapshot' && ' · as of last check'}
                </div>
              )}
            </div>
          )}

          {!trade?.active && !trade?.today_result && trade && (
            <p className="mt-4 text-sm text-gray-400">
              {state?.key === 'WORKING_WAITING' && state.dot === 'gray'
                ? 'Markets are closed — Spark opens trades only during market hours.'
                : 'Spark will show the trade here the moment one opens.'}
            </p>
          )}
        </>
      )}
    </section>
  )
}
