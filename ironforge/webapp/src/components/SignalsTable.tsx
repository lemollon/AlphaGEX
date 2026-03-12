'use client'

interface Signal {
  id: number
  signal_time: string | null
  spot_price: number
  vix: number
  put_short: number
  put_long: number
  call_short: number
  call_long: number
  total_credit: number
  confidence: number
  was_executed: boolean
  skip_reason: string | null
  wings_adjusted: boolean
}

export default function SignalsTable({ signals }: { signals: Signal[] }) {
  if (!signals.length) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-8 text-center">
        <p className="text-forge-muted text-sm">No signals recorded yet</p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-forge-border text-forge-muted text-xs">
            <th className="text-left p-3">Time</th>
            <th className="text-right p-3">SPY</th>
            <th className="text-right p-3">VIX</th>
            <th className="text-center p-3">Strikes</th>
            <th className="text-right p-3">Credit</th>
            <th className="text-center p-3">Status</th>
            <th className="text-left p-3">Reason</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s) => (
            <tr key={s.id} className="border-b border-forge-border/50 hover:bg-forge-card/50">
              <td className="p-3 font-mono text-xs whitespace-nowrap">
                {s.signal_time
                  ? new Date(s.signal_time).toLocaleString('en-US', {
                      timeZone: 'America/Chicago',
                      month: 'short',
                      day: 'numeric',
                      hour: 'numeric',
                      minute: '2-digit',
                      hour12: true,
                    })
                  : '—'}
              </td>
              <td className="p-3 text-right font-mono">${s.spot_price.toFixed(2)}</td>
              <td className="p-3 text-right font-mono">{s.vix.toFixed(1)}</td>
              <td className="p-3 text-center font-mono text-xs">
                {s.put_long}/{s.put_short}P {s.call_short}/{s.call_long}C
                {s.wings_adjusted && (
                  <span className="ml-1 text-amber-400" title="Wings adjusted">*</span>
                )}
              </td>
              <td className="p-3 text-right font-mono">${s.total_credit.toFixed(4)}</td>
              <td className="p-3 text-center">
                <span
                  className={`text-xs px-2 py-0.5 rounded ${
                    s.was_executed
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : 'bg-gray-600/20 text-gray-400'
                  }`}
                >
                  {s.was_executed ? 'EXECUTED' : 'SKIPPED'}
                </span>
              </td>
              <td className="p-3 text-xs text-gray-400 max-w-[200px] truncate" title={s.skip_reason || ''}>
                {s.skip_reason || '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
