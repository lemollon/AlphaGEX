'use client'

import { Area, ComposedChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { LiveSummary } from '@/lib/live/types'
import { BOT_COLORS } from '@/lib/botColors'
import { formatDollarPnl } from '@/lib/format'

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleTimeString('en-US', {
    timeZone: 'America/Chicago', hour: 'numeric', minute: '2-digit',
  })
}

export default function TodayPerformanceChart({
  account,
  intraday,
  marketOpen,
}: {
  account: LiveSummary['account'] | null
  intraday: LiveSummary['intraday'] | null
  marketOpen: boolean
}) {
  const series = intraday ?? []
  const showChart = series.length >= 2
  const dayOpenEquity = series.length ? series[0].equity : null
  const todayPositive = (account?.today_pnl ?? 0) >= 0

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-spark">
        Today&apos;s Performance
      </h3>

      <div className="mt-3 flex flex-wrap items-end gap-x-10 gap-y-3">
        <div>
          <div className="text-xs text-gray-500">Account Value</div>
          <div className="mt-1 font-mono text-3xl font-semibold text-white md:text-4xl">
            {account?.value != null
              ? `$${account.value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
              : '—'}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500">Today&apos;s Result</div>
          <div className={`mt-1 font-mono text-2xl font-semibold md:text-3xl ${account?.today_pnl == null ? 'text-gray-400' : todayPositive ? 'text-emerald-400' : 'text-red-400'}`}>
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
        <div className="mt-4 h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={series} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
              <XAxis
                dataKey="timestamp"
                tickFormatter={formatTime}
                stroke="#44403c"
                tick={{ fill: '#a8a29e', fontSize: 11 }}
                minTickGap={48}
              />
              <YAxis
                tickFormatter={(v: number) => `$${v.toLocaleString()}`}
                stroke="#44403c"
                tick={{ fill: '#a8a29e', fontSize: 11 }}
                domain={['auto', 'auto']}
                width={72}
              />
              {dayOpenEquity != null && (
                <ReferenceLine y={dayOpenEquity} stroke="#78716c" strokeDasharray="4 4" />
              )}
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1c1917',
                  border: '1px solid #292524',
                  borderRadius: 8,
                  fontSize: 12,
                }}
                labelFormatter={(iso: string) => `${formatTime(iso)} CT`}
                formatter={(value: number) => [
                  `$${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
                  'Account Value',
                ]}
              />
              <Area
                type="monotone"
                dataKey="equity"
                stroke={BOT_COLORS.spark}
                strokeWidth={2}
                fill="rgba(59,130,246,0.15)"
                isAnimationActive={false}
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="mt-6 pb-2 text-sm text-gray-500">
          {marketOpen
            ? "Today's chart appears once Spark records its first check-in of the session."
            : "Markets are closed — today's chart appears at the next market open (8:30 AM CT)."}
        </p>
      )}
    </section>
  )
}
