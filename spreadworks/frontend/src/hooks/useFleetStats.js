import { useState, useEffect, useCallback, useRef } from 'react';
import { API_URL } from '../lib/api';

// ── useFleetStats — one poll of GET /api/spreadworks/bots/fleet-stats (60s
// server-side cache, see routes_bots.py) feeds the Fleet page's risk row,
// sparklines, trade lines, drawdown chips, and fleet-wide equity/concentration
// widgets. Same "one aggregated call" discipline as useFleet.js — do not add
// per-bot calls here. Also fetches the Risk Advisor's /state headline in
// parallel on the same 60s cadence; that call is best-effort (null on any
// failure) since the banner is advisory, never load-bearing.
export default function useFleetStats(pollMs = 60_000) {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const [riskState, setRiskState] = useState(null);
  const cancelled = useRef(false);

  const load = useCallback(async () => {
    const [statsResult, riskResult] = await Promise.allSettled([
      fetch(`${API_URL}/api/spreadworks/bots/fleet-stats`).then(r => {
        if (!r.ok) throw new Error(`fleet-stats: ${r.status}`);
        return r.json();
      }),
      fetch(`${API_URL}/api/spreadworks/risk-advisor/state`).then(r => {
        if (!r.ok) throw new Error(`risk-advisor/state: ${r.status}`);
        return r.json();
      }),
    ]);
    if (cancelled.current) return;

    if (statsResult.status === 'fulfilled') {
      setStats(statsResult.value);
      setError(null);
    } else {
      // Keep the last good stats on screen — a blip in one poll shouldn't
      // blank widgets the operator is watching.
      setError(statsResult.reason?.message || 'Failed to load fleet stats');
    }

    // Advisory only — tolerate failure silently, banner just doesn't render.
    setRiskState(riskResult.status === 'fulfilled' ? riskResult.value : null);
  }, []);

  useEffect(() => {
    cancelled.current = false;
    load();
    const iv = setInterval(load, pollMs);
    return () => { cancelled.current = true; clearInterval(iv); };
  }, [load, pollMs]);

  return { stats, error, riskState };
}
