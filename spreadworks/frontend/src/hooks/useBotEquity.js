import { useEffect, useState } from 'react';
import { botApi } from '../lib/botApi';

// `period` is the selected timeframe: 'intraday' reads the today-only snapshot feed;
// any other value ('1d'|'1w'|'1m'|'3m'|'all') is passed through as the equity-curve
// window so the backend filters the dense snapshot series to that range.
// `bot` may be null/undefined (e.g. no compare peer) — the hook then returns
// an empty curve without fetching.
export function useBotEquity(bot, period = 'intraday', intervalMs = 30000) {
  const [curve, setCurve] = useState([]);
  const [error, setError] = useState(null);
  useEffect(() => {
    if (!bot) { setCurve([]); return undefined; }
    let cancelled = false;
    async function tick() {
      try {
        const d = period === 'intraday'
          ? await botApi.equityIntraday(bot)
          : await botApi.equityCurve(bot, period);
        const points = period === 'intraday'
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
  }, [bot, period, intervalMs]);
  return { curve, error };
}
