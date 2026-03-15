import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { isMarketOpen } from './useMarketHours';

const API_URL = import.meta.env.VITE_API_URL || '';

/**
 * Fetches GEX analysis (per-strike gamma + reference levels)
 * and intraday 5-min OHLC bars from the AlphaGEX proxy endpoints.
 *
 * Returns everything the Plotly candlestick + GEX overlay chart needs.
 */
export default function useGexAnalysis(symbol) {
  const [gexAnalysis, setGexAnalysis] = useState(null);
  const [intradayBars, setIntradayBars] = useState([]);
  const [sessionDate, setSessionDate] = useState(null);
  const [loading, setLoading] = useState(true);
  const timerRef = useRef(null);
  const tickRef = useRef(0);

  const fetchAll = useCallback(async (clearFirst = false) => {
    try {
      if (clearFirst) { setGexAnalysis(null); setIntradayBars([]); setLoading(true); }

      const [gexRes, barsRes] = await Promise.all([
        fetch(`${API_URL}/api/spreadworks/gex-analysis?symbol=${symbol}`).then(r => r.json()).catch(() => null),
        fetch(`${API_URL}/api/spreadworks/intraday-bars?symbol=${symbol}&interval=5min&fallback=true`).then(r => r.json()).catch(() => null),
      ]);

      if (gexRes?.success && gexRes?.data) {
        setGexAnalysis(gexRes.data);
      }

      if (barsRes?.success && barsRes?.data?.bars?.length > 0) {
        setIntradayBars(barsRes.data.bars);
        if (barsRes.data.session_date) setSessionDate(barsRes.data.session_date);
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  const refreshBars = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/spreadworks/intraday-bars?symbol=${symbol}&interval=5min&fallback=true`);
      const json = await res.json();
      if (json?.success && json?.data?.bars?.length > 0) setIntradayBars(json.data.bars);
    } catch { /* silent */ }
  }, [symbol]);

  // Initial fetch
  useEffect(() => {
    fetchAll(true);
  }, [fetchAll]);

  // Auto-refresh: bars every 10s, full GEX every 30s
  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    tickRef.current = 0;

    timerRef.current = setInterval(() => {
      if (!isMarketOpen()) return;
      tickRef.current++;
      refreshBars();
      if (tickRef.current % 3 === 0) fetchAll(false);
    }, 10_000);

    return () => clearInterval(timerRef.current);
  }, [fetchAll, refreshBars]);

  // Derive sorted strikes (nearest 40 to current price)
  const sortedStrikes = useMemo(() => {
    if (!gexAnalysis?.gex_chart?.strikes) return [];
    const price = gexAnalysis.header?.price || 0;
    return [...gexAnalysis.gex_chart.strikes]
      .filter(ss => Math.abs(ss.net_gamma) > 0.00001 || Math.abs(ss.call_gamma) > 0.000001)
      .sort((a, b) => Math.abs(a.strike - price) - Math.abs(b.strike - price))
      .slice(0, 40)
      .sort((a, b) => b.strike - a.strike)
      .map(ss => ({
        ...ss,
        abs_net_gamma: Math.abs(ss.net_gamma),
      }));
  }, [gexAnalysis]);

  // Derive reference levels
  const levels = useMemo(() => {
    if (!gexAnalysis?.levels) return null;
    return gexAnalysis.levels;
  }, [gexAnalysis]);

  return { gexAnalysis, intradayBars, sortedStrikes, levels, sessionDate, loading, refetch: fetchAll };
}
