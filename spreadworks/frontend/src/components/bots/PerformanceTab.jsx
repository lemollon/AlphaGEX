import { useEffect, useState } from 'react';
import { botApi } from '../../lib/botApi';

export default function PerformanceTab({ bot }) {
  const [perf, setPerf] = useState(null);
  useEffect(() => { botApi.performance(bot).then(setPerf).catch(() => {}); }, [bot]);

  if (!perf) {
    return (
      <div className="text-text-tertiary text-[13px] py-8 text-center">Loading…</div>
    );
  }

  const winRate = (perf.win_rate ?? 0) * 100;
  const totalPnl = perf.total_pnl ?? 0;
  const avgWin = perf.avg_win ?? 0;
  const avgLoss = perf.avg_loss ?? 0;

  const stats = [
    {
      label: 'Trades',
      value: perf.trades ?? 0,
      format: v => String(v),
      colorClass: 'text-text-primary',
    },
    {
      label: 'Win Rate',
      value: winRate,
      format: v => `${v.toFixed(1)}%`,
      colorClass: winRate >= 50 ? 'sw-pnl-positive' : 'sw-pnl-negative',
    },
    {
      label: 'Total P&L',
      value: totalPnl,
      format: v => `${v >= 0 ? '+' : ''}$${v.toFixed(2)}`,
      colorClass: totalPnl >= 0 ? 'sw-pnl-positive' : 'sw-pnl-negative',
    },
    {
      label: 'Avg Win',
      value: avgWin,
      format: v => `$${v.toFixed(2)}`,
      colorClass: 'sw-pnl-positive',
    },
    {
      label: 'Avg Loss',
      value: avgLoss,
      format: v => `-$${Math.abs(v).toFixed(2)}`,
      colorClass: 'sw-pnl-negative',
    },
  ];

  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3">
      {stats.map(s => (
        <div key={s.label} className="sw-stat-card">
          <div className={`sw-stat-value ${s.colorClass}`}>
            {s.format(s.value)}
          </div>
          <div className="sw-stat-sublabel">{s.label.toUpperCase()}</div>
        </div>
      ))}
    </div>
  );
}
