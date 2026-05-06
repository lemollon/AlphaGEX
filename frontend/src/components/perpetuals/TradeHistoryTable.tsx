'use client'

import { useState } from 'react'
import { History, Loader2, RefreshCw } from 'lucide-react'
import { useAgapePerpTrades, type RangePreset, type Trade } from '@/lib/hooks/useAgapePerpTrades'

const RANGE_PRESETS: { id: RangePreset; label: string }[] = [
  { id: '7d', label: '7d' },
  { id: '30d', label: '30d' },
  { id: '90d', label: '90d' },
  { id: 'all', label: 'All' },
]

type Props = {
  bots: string[]
  showBotColumn?: boolean
  defaultRange?: RangePreset
  pageSize?: number
  title?: string
}

function fmtUsd(v: number | null | undefined) {
  if (v == null) return '---'
  const sign = v >= 0 ? '+' : ''
  return `${sign}$${v.toFixed(2)}`
}

function pnlColor(v: number) {
  return v >= 0 ? 'text-green-400' : 'text-red-400'
}

export function TradeHistoryTable({
  bots,
  showBotColumn = bots.length > 1,
  defaultRange = '30d',
  pageSize = 100,
  title,
}: Props) {
  const [preset, setPreset] = useState<RangePreset>(defaultRange)
  const [customMode, setCustomMode] = useState(false)
  const [customSince, setCustomSince] = useState<string>('')
  const [customUntil, setCustomUntil] = useState<string>('')

  const range =
    customMode && customSince && customUntil
      ? { since: new Date(customSince), until: new Date(customUntil) }
      : preset

  const { trades, hasMore, loadMore, isLoading, isLoadingMore, error, reset } =
    useAgapePerpTrades({ bots, range, pageSize })

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800">
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-gray-800 flex-wrap">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-gray-400" />
          <h3 className="text-sm font-medium text-gray-200">{title || 'Trade History'}</h3>
          <span className="text-xs text-gray-500">
            ({trades.length}
            {hasMore ? '+' : ''})
          </span>
        </div>
        <div className="flex items-center gap-1 flex-wrap">
          {RANGE_PRESETS.map(p => (
            <button
              key={p.id}
              type="button"
              aria-label={p.label}
              onClick={() => {
                setCustomMode(false)
                setPreset(p.id)
              }}
              className={`px-2 py-1 text-xs rounded border ${
                !customMode && preset === p.id
                  ? 'bg-cyan-600/30 border-cyan-500 text-cyan-200'
                  : 'border-gray-700 text-gray-400 hover:bg-gray-800'
              }`}
            >
              {p.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setCustomMode(v => !v)}
            className={`px-2 py-1 text-xs rounded border ${
              customMode
                ? 'bg-cyan-600/30 border-cyan-500 text-cyan-200'
                : 'border-gray-700 text-gray-400 hover:bg-gray-800'
            }`}
          >
            Custom
          </button>
          {customMode && (
            <>
              <input
                type="date"
                value={customSince}
                onChange={e => setCustomSince(e.target.value)}
                className="px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-gray-200"
              />
              <span className="text-gray-500 text-xs">→</span>
              <input
                type="date"
                value={customUntil}
                onChange={e => setCustomUntil(e.target.value)}
                className="px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-gray-200"
              />
            </>
          )}
        </div>
      </div>

      {error ? (
        <div className="p-6 text-center text-red-400 text-sm">
          Failed to load trades: {error.message}
          <button onClick={reset} className="ml-2 underline">
            Retry
          </button>
        </div>
      ) : isLoading ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="w-5 h-5 text-gray-500 animate-spin" />
        </div>
      ) : trades.length === 0 ? (
        <div className="p-8 text-center text-gray-500 text-sm">
          No closed trades in this range. Try widening the date range.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-800/50 sticky top-0">
              <tr>
                <th className="text-left px-3 py-2 text-gray-500 font-medium">Closed</th>
                {showBotColumn && (
                  <th className="text-left px-3 py-2 text-gray-500 font-medium">Bot</th>
                )}
                <th className="text-left px-3 py-2 text-gray-500 font-medium">Side</th>
                <th className="text-right px-3 py-2 text-gray-500 font-medium">Qty</th>
                <th className="text-right px-3 py-2 text-gray-500 font-medium">Entry</th>
                <th className="text-right px-3 py-2 text-gray-500 font-medium">Close</th>
                <th className="text-right px-3 py-2 text-gray-500 font-medium">PnL ($)</th>
                <th className="text-right px-3 py-2 text-gray-500 font-medium">PnL (%)</th>
                <th className="text-left px-3 py-2 text-gray-500 font-medium">Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {trades.map((t: Trade) => (
                <tr key={`${t.bot_id}-${t.position_id}`} className="hover:bg-gray-800/30">
                  <td className="px-3 py-2 text-gray-500 font-mono text-xs">
                    {t.close_time ? new Date(t.close_time).toLocaleString() : '---'}
                  </td>
                  {showBotColumn && (
                    <td className="px-3 py-2 text-gray-200 font-mono text-xs">{t.bot_label}</td>
                  )}
                  <td className="px-3 py-2">
                    <span
                      className={`text-xs font-bold ${
                        t.side === 'long' ? 'text-green-400' : 'text-red-400'
                      }`}
                    >
                      {t.side?.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right text-white font-mono text-xs">
                    {t.quantity}
                  </td>
                  <td className="px-3 py-2 text-right text-white font-mono text-xs">
                    {t.entry_price?.toLocaleString(undefined, { maximumFractionDigits: 8 })}
                  </td>
                  <td className="px-3 py-2 text-right text-white font-mono text-xs">
                    {t.close_price != null
                      ? t.close_price.toLocaleString(undefined, { maximumFractionDigits: 8 })
                      : '---'}
                  </td>
                  <td
                    className={`px-3 py-2 text-right font-mono font-semibold text-xs ${pnlColor(
                      t.realized_pnl ?? 0,
                    )}`}
                  >
                    {fmtUsd(t.realized_pnl)}
                  </td>
                  <td
                    className={`px-3 py-2 text-right font-mono text-xs ${pnlColor(
                      t.realized_pnl ?? 0,
                    )}`}
                  >
                    {t.realized_pnl_pct != null
                      ? `${t.realized_pnl_pct >= 0 ? '+' : ''}${t.realized_pnl_pct.toFixed(2)}%`
                      : '---'}
                  </td>
                  <td className="px-3 py-2">
                    <span className="text-xs text-gray-400">{t.close_reason || '---'}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {hasMore && !isLoading && (
        <div className="px-4 py-3 border-t border-gray-800 flex items-center justify-between">
          <span className="text-xs text-gray-500">Showing {trades.length} trades</span>
          <button
            type="button"
            onClick={loadMore}
            disabled={isLoadingMore}
            className="px-3 py-1.5 text-xs rounded bg-gray-800 border border-gray-700 text-gray-200 hover:bg-gray-700 disabled:opacity-60 inline-flex items-center gap-1.5"
          >
            {isLoadingMore && <Loader2 className="w-3 h-3 animate-spin" />}
            Load more
          </button>
        </div>
      )}
    </div>
  )
}
