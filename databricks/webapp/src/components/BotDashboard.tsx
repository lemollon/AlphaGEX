'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import StatusCard from './StatusCard'
import PerformanceCard from './PerformanceCard'
import EquityChart from './EquityChart'
import PositionTable from './PositionTable'
import TradeHistory from './TradeHistory'
import LogsTable from './LogsTable'

const TABS = ['Equity Curve', 'Performance', 'Positions', 'Trade History', 'Logs'] as const
type Tab = (typeof TABS)[number]

const REFRESH = 30_000

export default function BotDashboard({
  bot,
  accent,
}: {
  bot: 'flame' | 'spark'
  accent: 'amber' | 'blue'
}) {
  const [tab, setTab] = useState<Tab>('Equity Curve')

  const { data: status, error: statusErr } = useSWR(`/api/${bot}/status`, fetcher, { refreshInterval: REFRESH })
  const { data: equity } = useSWR(`/api/${bot}/equity-curve`, fetcher, { refreshInterval: REFRESH })
  const { data: perf } = useSWR(tab === 'Performance' ? `/api/${bot}/performance` : null, fetcher, { refreshInterval: REFRESH })
  const { data: positions } = useSWR(tab === 'Positions' ? `/api/${bot}/positions` : null, fetcher, { refreshInterval: REFRESH })
  const { data: trades } = useSWR(tab === 'Trade History' ? `/api/${bot}/trades` : null, fetcher, { refreshInterval: REFRESH })
  const { data: logs } = useSWR(tab === 'Logs' ? `/api/${bot}/logs` : null, fetcher, { refreshInterval: REFRESH })

  if (statusErr) {
    return (
      <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4">
        <p className="text-red-400">Failed to load {bot.toUpperCase()} status: {statusErr.message}</p>
      </div>
    )
  }

  const accentActive = accent === 'amber' ? 'border-amber-400 text-amber-400' : 'border-blue-400 text-blue-400'

  return (
    <div className="space-y-6">
      <div className="flex items-baseline gap-2">
        <h1 className={`text-2xl font-bold ${accent === 'amber' ? 'text-amber-400' : 'text-blue-400'}`}>
          {bot.toUpperCase()}
        </h1>
        <span className="text-gray-500">{bot === 'flame' ? '2DTE' : '1DTE'} Iron Condor</span>
      </div>

      {status && <StatusCard data={status} accent={accent} />}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-700">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t
                ? accentActive
                : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {tab === 'Equity Curve' && equity && (
          <EquityChart
            data={equity.curve}
            startingCapital={equity.starting_capital}
            color={accent === 'amber' ? '#f59e0b' : '#3b82f6'}
            title={`${bot.toUpperCase()} Equity Curve`}
          />
        )}
        {tab === 'Performance' && perf && (
          <PerformanceCard data={perf} label={bot.toUpperCase()} />
        )}
        {tab === 'Positions' && positions && (
          <PositionTable positions={positions.positions} />
        )}
        {tab === 'Trade History' && trades && (
          <TradeHistory trades={trades.trades} />
        )}
        {tab === 'Logs' && logs && (
          <LogsTable logs={logs.logs} />
        )}
      </div>
    </div>
  )
}
