import { useState, useEffect, useCallback, useRef } from 'react';
import { isMarketOpen } from './useMarketHours';

const API_URL = import.meta.env.VITE_API_URL || '';
const REFRESH_INTERVAL = 30000;

export default function useGex(symbol) {
  const [gexData, setGexData] = useState(null);
  const timerRef = useRef(null);

  const fetchGex = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/spreadworks/gex?symbol=${symbol}`);
      if (!res.ok) return;
      const data = await res.json();
      setGexData(data);
    } catch {
      // GEX unavailable — hide silently
    }
  }, [symbol]);

  useEffect(() => {
    fetchGex();
  }, [fetchGex]);

  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);

    timerRef.current = setInterval(() => {
      if (isMarketOpen()) {
        fetchGex();
      }
    }, REFRESH_INTERVAL);

    return () => clearInterval(timerRef.current);
  }, [fetchGex]);

  return { gexData, refetch: fetchGex };
}
