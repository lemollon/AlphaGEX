import { useEffect, useState } from 'react';
import { botApi } from '../../lib/botApi';

export default function PerformanceTab({ bot }) {
  const [perf, setPerf] = useState(null);
  useEffect(() => { botApi.performance(bot).then(setPerf).catch(()=>{}); }, [bot]);
  if (!perf) return <div className="loading">Loading…</div>;
  return (
    <div className="performance-grid">
      <div><label>Trades</label><span>{perf.trades}</span></div>
      <div><label>Win rate</label><span>{(perf.win_rate*100).toFixed(1)}%</span></div>
      <div><label>Total P&amp;L</label><span>${perf.total_pnl.toFixed(2)}</span></div>
      <div><label>Avg win</label><span>${perf.avg_win.toFixed(2)}</span></div>
      <div><label>Avg loss</label><span>${perf.avg_loss.toFixed(2)}</span></div>
    </div>
  );
}
