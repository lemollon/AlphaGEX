import { useEffect, useState } from 'react';
import { botApi } from '../lib/botApi';

export function useBotPositions(bot, intervalMs = 5000) {
  const [positions, setPositions] = useState([]);
  const [error, setError] = useState(null);
  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const d = await botApi.positions(bot);
        if (!cancelled) setPositions(d.positions || []);
      } catch (e) {
        if (!cancelled) setError(e);
      }
    }
    tick();
    const h = setInterval(tick, intervalMs);
    return () => { cancelled = true; clearInterval(h); };
  }, [bot, intervalMs]);
  return { positions, error };
}
