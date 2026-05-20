import { useState, useEffect, useCallback, useRef } from 'react';
import { isMarketOpen } from './useMarketHours';
import { API_URL } from '../lib/api';
const REFRESH_INTERVAL = 30000;

// Module-level cache keyed by `${symbol}|${interval}`. Survives unmount/
// remount of the Builder page, so navigating Builder → Positions → Builder
// shows the last candles instantly and only the background refresh waits on
// the network. Backend cache-first already cuts most of that wait anyway.
const candleCache = new Map();

export default function useCandles(symbol, interval = '15min') {
  const cacheKey = `${symbol}|${interval}`;
  const cached = candleCache.get(cacheKey);

  const [candles, setCandles] = useState(cached?.candles || []);
  const [spotPrice, setSpotPrice] = useState(cached?.spotPrice || null);
  const [loading, setLoading] = useState(!cached);
  const [error, setError] = useState(null);
  const [dataAsOf, setDataAsOf] = useState(cached?.dataAsOf || null);
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
      const nextCandles = data.candles || [];
      setCandles(nextCandles);
      if (data.last_price) setSpotPrice(data.last_price);
      if (data.data_as_of) setDataAsOf(data.data_as_of);
      candleCache.set(cacheKey, {
        candles: nextCandles,
        spotPrice: data.last_price ?? null,
        dataAsOf: data.data_as_of ?? null,
      });
      setError(null);
      setLoading(false);
    } catch (err) {
      console.error('Candle fetch error:', err.message);
      setError(err.message);
      setLoading(false);
    }
  }, [symbol, interval, cacheKey]);

  // Initial fetch. Keep stale candles visible (don't flip loading=true) if
  // we already have cached data — the user sees the chart immediately and
  // the network call replaces the data in place.
  useEffect(() => {
    if (!candleCache.has(cacheKey)) setLoading(true);
    fetchCandles();
  }, [fetchCandles, cacheKey]);

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
