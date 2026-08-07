import { useState, useEffect, useCallback, useRef } from 'react';
import { botApi } from '../lib/botApi';

// ── useFleet — one poll of GET /api/spreadworks/bots feeds the whole fleet
// page. That endpoint already loops every registry bot server-side and returns
// a full status row each (equity, equity_mtm, today_pnl, unrealized_pnl,
// open_positions, enabled, last_scan_at), so 23 cards cost ONE request. Do not
// "enrich" these cards with per-bot /performance or /equity-curve calls — that
// turns a page load into 23+ round trips, which is the documented frontend
// perf trap in .claude/rules/common-mistakes.md §9.
//
// A bot whose status raises server-side comes back as {bot, error} instead of a
// status row; those are passed through untouched so the card can render an
// error state rather than silently showing $0 (which reads as a flat bot).
export default function useFleet(pollMs = 15_000) {
  const [bots, setBots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [updatedAt, setUpdatedAt] = useState(null);
  const cancelled = useRef(false);

  const load = useCallback(async () => {
    try {
      const data = await botApi.listAll();
      if (cancelled.current) return;
      const rows = Array.isArray(data?.bots) ? data.bots : Array.isArray(data) ? data : [];
      setBots(rows);
      setError(null);
      setUpdatedAt(Date.now());
    } catch (e) {
      // Keep the last good rows on screen — a blip in one poll shouldn't blank
      // a dashboard the operator is watching. Surface the error in the header.
      if (!cancelled.current) setError(e?.message || 'Failed to load bots');
    } finally {
      if (!cancelled.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    cancelled.current = false;
    load();
    const iv = setInterval(load, pollMs);
    return () => { cancelled.current = true; clearInterval(iv); };
  }, [load, pollMs]);

  return { bots, loading, error, updatedAt, refetch: load };
}
