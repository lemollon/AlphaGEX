import { useEffect, useState } from 'react';
import { botApi } from '../lib/botApi';

export function useBotEquity(bot, mode = 'intraday', intervalMs = 30000) {
  const [curve, setCurve] = useState([]);
  const [error, setError] = useState(null);
  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const d = mode === 'intraday'
          ? await botApi.equityIntraday(bot)
          : await botApi.equityCurve(bot);
        const points = mode === 'intraday'
          ? (d.snapshots || []).map(s => ({ time: s.snapshot_time, equity: Number(s.equity) }))
          : (d.curve   || []).map(s => ({ time: s.time, equity: Number(s.equity) }));
        if (!cancelled) setCurve(points);
      } catch (e) {
        if (!cancelled) setError(e);
      }
    }
    tick();
    const h = setInterval(tick, intervalMs);
    return () => { cancelled = true; clearInterval(h); };
  }, [bot, mode, intervalMs]);
  return { curve, error };
}
