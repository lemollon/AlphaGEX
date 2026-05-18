import { useEffect, useState } from 'react';
import { botApi } from '../lib/botApi';

export function useBotStatus(bot, intervalMs = 5000) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const d = await botApi.status(bot);
        if (!cancelled) setData(d);
      } catch (e) {
        if (!cancelled) setError(e);
      }
    }
    tick();
    const h = setInterval(tick, intervalMs);
    return () => { cancelled = true; clearInterval(h); };
  }, [bot, intervalMs]);
  return { data, error };
}
