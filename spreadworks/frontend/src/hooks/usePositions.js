import { useState, useEffect, useCallback } from 'react';

const API_URL = import.meta.env.VITE_API_URL || '';

export default function usePositions(statusFilter = 'open') {
  const [positions, setPositions] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchPositions = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_URL}/api/spreadworks/positions?status=${statusFilter}`);
      if (!res.ok) throw new Error('Failed to fetch positions');
      const data = await res.json();
      setPositions(data.positions || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  const fetchSummary = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/spreadworks/positions/summary`);
      if (!res.ok) return;
      setSummary(await res.json());
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    fetchPositions();
    fetchSummary();
  }, [fetchPositions, fetchSummary]);

  const createPosition = async (payload) => {
    const res = await fetch(`${API_URL}/api/spreadworks/positions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'Failed to create position');
    await fetchPositions();
    await fetchSummary();
    return data;
  };

  const closePosition = async (id, closePrice) => {
    const res = await fetch(`${API_URL}/api/spreadworks/positions/${id}/close`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ close_price: closePrice }),
    });
    if (!res.ok) throw new Error('Failed to close position');
    await fetchPositions();
    await fetchSummary();
  };

  const deletePosition = async (id) => {
    const res = await fetch(`${API_URL}/api/spreadworks/positions/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete position');
    await fetchPositions();
    await fetchSummary();
  };

  const updatePosition = async (id, updates) => {
    const res = await fetch(`${API_URL}/api/spreadworks/positions/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    if (!res.ok) throw new Error('Failed to update position');
    await fetchPositions();
  };

  const postDiscordOpen = async () => {
    await fetch(`${API_URL}/api/spreadworks/discord/post-open`, { method: 'POST' });
  };

  const postDiscordEod = async () => {
    await fetch(`${API_URL}/api/spreadworks/discord/post-eod`, { method: 'POST' });
  };

  const pushPositionToDiscord = async (id) => {
    const res = await fetch(`${API_URL}/api/spreadworks/discord/push-position/${id}`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to push to Discord');
    return res.json();
  };

  return {
    positions, summary, loading, error,
    refetch: fetchPositions, refetchSummary: fetchSummary,
    createPosition, closePosition, deletePosition, updatePosition,
    postDiscordOpen, postDiscordEod, pushPositionToDiscord,
  };
}
