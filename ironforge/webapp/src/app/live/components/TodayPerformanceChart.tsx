'use client'

import { Area, ComposedChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { LiveSummary } from '@/lib/live/types'
import type { AccentTheme } from './accent'
import { formatDollarPnl } from '@/lib/format'

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleTimeString('en-US', {
    timeZone: 'America/Chicago', hour: 'numeric', minute: '2-digit',
  })
}

function signedDollars(v: number): string {
  const r = Math.round(v)
  return r > 0 ? `+$${r}` : r < 0 ? `-$${Math.abs(r)}` : '$0'
}

export default function TodayPerformanceChart({
  account,
  intraday,
  marketOpen,
  accent,
}: {
  account: LiveSummary['account'] | null
  intraday: LiveSummary['intraday'] | null
  marketOpen: boolean
  accent: AccentTheme
}) {
  const raw = intraday ?? []
  const showChart = raw.length >= 2
  const dayOpenEquity = raw.length ? raw[0].equity : null
  // ±$ on the day: prefer the server's day-P&L (anchored at day-open BALANCE, so an
  // overnight hold's carry shows from the first tick and the curve ends where the
  // "Today's Result" headline reads — the 2026-07-17 fix). Fall back to the old
  // equity-relative delta for cached payloads without `pnl`.
  const series = dayOpenEquity != null
    ? raw.map((p) => ({
        ...p,
        delta: p.pnl ?? Math.round((p.equity - dayOpenEquity) * 100) / 100,
      }))
    : []
  const todayPositive = (account?.today_pnl ?? 0) >= 0

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <h3 className={`text-xs font-semibold uppercase tracking-widest ${accent.text}`}>
        Today&apos;s Performance
      </h3>

      <div className="mt-3 flex flex-col gap-4 lg:flex-row lg:items-center">
        <div className="flex shrink-0 flex-wrap gap-x-10 gap-y-3 lg:w-[320px] lg:flex-col lg:gap-y-4">
          <div>
            <div className="text-xs text-gray-500">Account Value</div>
            <div className="mt-1 font-mono text-3xl font-semibold text-white">
              {account?.value != null
                ? `$${account.value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                : '—'}
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Today&apos;s Result</div>
            <div className={`mt-1 font-mono text-2xl font-semibold ${account?.today_pnl == null ? 'text-gray-400' : todayPositive ? 'text-emerald-400' : 'text-red-400'}`}>
              {formatDollarPnl(account?.today_pnl)}
              {account?.today_pnl_pct != null && (
                <span className="ml-2 text-base font-normal">
                  ({account.today_pnl_pct > 0 ? '+' : ''}{account.today_pnl_pct.toFixed(2)}%)
                </span>
              )}
            </div>
          </div>
        </div>

        {showChart ? (
          <div className="h-[220px] min-w-0 flex-1">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={series} margin={{ top: 8, right: 4, bottom: 0, left: 8 }}>
                <XAxis
                  dataKey="timestamp"
                  tickFormatter={formatTime}
                  stroke="#44403c"
                  tick={{ fill: '#a8a29e', fontSize: 11 }}
                  minTickGap={48}
                />
                <YAxis
                  orientation="right"
                  tickFormatter={signedDollars}
                  stroke="transparent"
                  tick={{ fill: '#a8a29e', fontSize: 11 }}
                  domain={['auto', 'auto']}
                  width={56}
                />
                <ReferenceLine y={0} stroke="#78716c" strokeDasharray="4 4" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1c1917',
                    border: '1px solid #292524',
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  labelFormatter={(iso: string) => `${formatTime(iso)} CT`}
                  formatter={(value: number, _name: string, entry: { payload?: { equity?: number } }) => [
                    `${signedDollars(value)} (value $${Number(entry?.payload?.equity ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`,
                    'Today',
                  ]}
                />
                <Area
                  type="monotone"
                  dataKey="delta"
                  stroke={accent.chartHex}
                  strokeWidth={2}
                  fill={accent.chartFill}
                  isAnimationActive={false}
                  dot={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="flex-1 pb-2 text-sm text-gray-500">
            {marketOpen
              ? "Today's chart appears once Spark records its first check-in of the session."
              : "Markets are closed — today's chart appears at the next market open (8:30 AM CT)."}
          </p>
        )}
      </div>
    </section>
  )
}
