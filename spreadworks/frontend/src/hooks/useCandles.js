import { useState, useEffect, useCallback, useRef } from 'react';
import { isMarketOpen } from './useMarketHours';
import { API_URL } from '../lib/api';
const REFRESH_INTERVAL = 30000;

export default function useCandles(symbol, interval = '15min') {
  const [candles, setCandles] = useState([]);
  const [spotPrice, setSpotPrice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dataAsOf, setDataAsOf] = useState(null);
  const timerRef = useRef(null);

  const fetchCandles = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/spreadworks/candles?symbol=${symbol}&interval=${interval}`);
      // Detect static site returning HTML instead of JSON
      const contentType = res.headers.get('content-type') || '';
      if (contentType.includes('text/html')) {
        throw new Error('API unreachable — got HTML instead of JSON. Check VITE_API_URL or use the backend URL directly.');
      }
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const data = await res.json();
      setCandles(data.candles || []);
      if (data.last_price) setSpotPrice(data.last_price);
      if (data.data_as_of) setDataAsOf(data.data_as_of);
      setError(null);
      setLoading(false);
    } catch (err) {
      console.error('Candle fetch error:', err.message);
      setError(err.message);
      setLoading(false);
    }
  }, [symbol, interval]);

  // Initial fetch
  useEffect(() => {
    setLoading(true);
    fetchCandles();
  }, [fetchCandles]);

  // Auto-refresh when market open
  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);

    timerRef.current = setInterval(() => {
      if (isMarketOpen()) {
        fetchCandles();
      }
    }, REFRESH_INTERVAL);

    return () => clearInterval(timerRef.current);
  }, [fetchCandles]);

  return { candles, spotPrice, loading, error, dataAsOf, refetch: fetchCandles };
}
