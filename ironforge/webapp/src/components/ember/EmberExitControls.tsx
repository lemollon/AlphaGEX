'use client'

import { type ExitParams } from '@/app/ember/page'
import InfoTip from '@/components/ember/InfoTip'

interface Props {
  params: ExitParams
  onChange: (ep: ExitParams) => void
  disabled: boolean
}

// Values stay as-is (minutes since 8:30 AM open). Labels updated to CT clock times.
// 8:30 AM CT open + 180 min = 11:30 AM CT
// 8:30 AM CT open + 300 min = 1:30 PM CT
// 8:30 AM CT open + 385 min = 2:55 PM CT
const TIME_STOP_OPTIONS: { value: number | null; label: string }[] = [
  { value: null, label: 'None (hold to EOD)' },
  { value: 180, label: '11:30 AM CT' },
  { value: 300, label: '1:30 PM CT' },
  { value: 385, label: '2:55 PM CT' },
]

export default function EmberExitControls({ params, onChange, disabled }: Props) {
  function set<K extends keyof ExitParams>(k: K, v: ExitParams[K]) {
    onChange({ ...params, [k]: v })
  }

  const dimCls = disabled ? 'opacity-40 pointer-events-none' : ''

  return (
    <div className={`rounded-xl border border-forge-border bg-forge-card/80 p-5 transition-opacity ${dimCls}`}>
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        {/* Sliders glyph */}
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="text-amber-400">
          <path d="M2 4h3M9 4h5M5 4a1.5 1.5 0 1 0 3 0 1.5 1.5 0 0 0-3 0ZM2 8h7M13 8h1M9 8a1.5 1.5 0 1 0 3 0 1.5 1.5 0 0 0-3 0ZM2 12h2M8 12h6M4 12a1.5 1.5 0 1 0 3 0 1.5 1.5 0 0 0-4 0Z" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
        <h2 className="text-sm font-semibold text-gray-300">Exit Parameters</h2>
        <span className="text-xs text-forge-muted ml-1">
          {disabled ? '— build a universe first' : '— changes re-evaluate instantly'}
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {/* Profit target % */}
        <div className="lg:col-span-1">
          <label className="block text-xs text-forge-muted mb-1.5">
            Profit Target %
            <span className="ml-1 text-forge-muted/60">(of credit)</span>
            <InfoTip text="Take profit — close once the trade has captured this % of the credit collected at entry. e.g. 40% on a $1.00 credit closes when you can buy it back for ~$0.60, locking $0.40. Higher % holds for more but wins less often." />
          </label>
          <div className="space-y-1.5">
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={params.profit_target_pct}
              onChange={(e) => set('profit_target_pct', parseInt(e.target.value, 10))}
              className="w-full accent-amber-500"
            />
            <div className="flex justify-between text-xs font-mono">
              <span className="text-forge-muted">0%</span>
              <span className="text-amber-300 font-semibold">{params.profit_target_pct}%</span>
              <span className="text-forge-muted">100%</span>
            </div>
          </div>
        </div>

        {/* Stop loss multiplier */}
        <div className="lg:col-span-1">
          <label className="block text-xs text-forge-muted mb-1.5">
            Stop Loss ×credit
            <span className="ml-1 text-forge-muted/60">(0–3×)</span>
            <InfoTip text="Cut losses — close when the loss reaches this multiple of the credit collected. e.g. 1.0× on a $1.00 credit closes when down ~$1.00. Lower = tighter stop (more frequent, smaller losses); higher = looser." />
          </label>
          <div className="space-y-1.5">
            <input
              type="range"
              min={0}
              max={3}
              step={0.25}
              value={params.stop_loss_mult}
              onChange={(e) => set('stop_loss_mult', parseFloat(e.target.value))}
              className="w-full accent-amber-500"
            />
            <div className="flex justify-between text-xs font-mono">
              <span className="text-forge-muted">0×</span>
              <span className="text-amber-300 font-semibold">{params.stop_loss_mult.toFixed(2)}×</span>
              <span className="text-forge-muted">3×</span>
            </div>
          </div>
        </div>

        {/* Time stop */}
        <div className="lg:col-span-1">
          <label className="block text-xs text-forge-muted mb-1.5">
            Time Stop
            <InfoTip text="Force-close at a fixed time of day regardless of profit or loss. 'None (hold to EOD)' keeps the position until the end of the day." />
          </label>
          <select
            value={params.time_stop_minute === null ? 'none' : String(params.time_stop_minute)}
            onChange={(e) => {
              const v = e.target.value === 'none' ? null : parseInt(e.target.value, 10)
              set('time_stop_minute', v)
            }}
            className="w-full bg-forge-bg border border-forge-border rounded-lg px-2.5 py-2 text-sm text-gray-200 focus:outline-none focus:border-amber-500/60"
          >
            {TIME_STOP_OPTIONS.map((o) => (
              <option key={o.value === null ? 'none' : o.value} value={o.value === null ? 'none' : o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        {/* Trail activation */}
        <div className="lg:col-span-1">
          <label className="block text-xs text-forge-muted mb-1.5">
            Trail Activation %
            <span className="ml-1 text-forge-muted/60">(optional)</span>
            <InfoTip text="Optional trailing stop — once profit reaches this % of the credit, arm a trailing stop. Leave Off to disable trailing." />
          </label>
          <input
            type="number"
            min={0}
            max={100}
            step={5}
            placeholder="Off"
            value={params.trail_activation_pct ?? ''}
            onChange={(e) => {
              const v = e.target.value === '' ? null : parseFloat(e.target.value)
              set('trail_activation_pct', v)
            }}
            className="w-full bg-forge-bg border border-forge-border rounded-lg px-2.5 py-2 text-sm text-gray-200 focus:outline-none focus:border-amber-500/60 placeholder-forge-muted"
          />
        </div>

        {/* Trail giveback */}
        <div className="lg:col-span-1">
          <label className="block text-xs text-forge-muted mb-1.5">
            Trail Giveback %
            <span className="ml-1 text-forge-muted/60">(optional)</span>
            <InfoTip text="Once the trailing stop is armed, close if profit falls back by this % of the credit from its peak." />
          </label>
          <input
            type="number"
            min={0}
            max={50}
            step={5}
            placeholder="Off"
            value={params.trail_giveback_pct ?? ''}
            onChange={(e) => {
              const v = e.target.value === '' ? null : parseFloat(e.target.value)
              set('trail_giveback_pct', v)
            }}
            className="w-full bg-forge-bg border border-forge-border rounded-lg px-2.5 py-2 text-sm text-gray-200 focus:outline-none focus:border-amber-500/60 placeholder-forge-muted"
          />
        </div>

        {/* Min hold minutes */}
        <div className="lg:col-span-1">
          <label className="block text-xs text-forge-muted mb-1.5">
            Min Hold
            <span className="ml-1 text-forge-muted/60">(minutes)</span>
            <InfoTip text="Block any exit for this many minutes after entry — prevents instant exits on noisy opening-minute prices." />
          </label>
          <input
            type="number"
            min={0}
            max={60}
            step={5}
            value={params.min_hold_minutes}
            onChange={(e) => set('min_hold_minutes', parseInt(e.target.value, 10))}
            className="w-full bg-forge-bg border border-forge-border rounded-lg px-2.5 py-2 text-sm text-gray-200 focus:outline-none focus:border-amber-500/60"
          />
        </div>
      </div>

      {/* Summary line */}
      <div className="mt-4 pt-3 border-t border-forge-border/50 text-xs font-mono text-forge-muted">
        {(() => {
          const timeLabel = TIME_STOP_OPTIONS.find((o) => o.value === params.time_stop_minute)?.label ?? 'EOD'
          return (
            <>
              Policy: PT={params.profit_target_pct}% / SL={params.stop_loss_mult.toFixed(2)}× /
              Time={timeLabel} /
              Trail={params.trail_activation_pct != null ? `act@${params.trail_activation_pct}%,give${params.trail_giveback_pct ?? 0}%` : 'off'} /
              MinHold={params.min_hold_minutes}min
            </>
          )
        })()}
      </div>
    </div>
  )
}
