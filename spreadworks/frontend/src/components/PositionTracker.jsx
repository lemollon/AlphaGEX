import { useState, useEffect, useCallback } from 'react';
import { STRAT_LABELS } from '../lib/strategies';

import { API_URL } from '../lib/api';

export default function PositionTracker() {
  const [positions, setPositions] = useState([]);
  const [pnlData, setPnlData] = useState({});

  const fetchPositions = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/spreadworks/positions`);
      if (res.ok) {
        const data = await res.json();
        setPositions(data.positions || []);
      }
    } catch (err) {
      console.error('Fetch positions failed:', err);
    }
  }, []);

  const fetchPnl = useCallback(async (id) => {
    try {
      const res = await fetch(`${API_URL}/api/spreadworks/positions/${id}/pnl`);
      if (res.ok) {
        const data = await res.json();
        setPnlData((prev) => ({ ...prev, [id]: data }));
      }
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    fetchPositions();
  }, [fetchPositions]);

  // Refresh P&L for all open positions every 30s
  useEffect(() => {
    if (positions.length === 0) return;
    const refresh = () => positions.forEach((p) => fetchPnl(p.id));
    refresh();
    const timer = setInterval(refresh, 30000);
    return () => clearInterval(timer);
  }, [positions, fetchPnl]);

  const handleDelete = async (id) => {
    try {
      await fetch(`${API_URL}/api/spreadworks/positions/${id}`, { method: 'DELETE' });
      setPositions((prev) => prev.filter((p) => p.id !== id));
      setPnlData((prev) => {
        const copy = { ...prev };
        delete copy[id];
        return copy;
      });
    } catch (err) {
      console.error('Delete position failed:', err);
    }
  };

  const stratLabel = (s) => STRAT_LABELS[s] || s;

  return (
    <div className="panel position-panel">
      <h3>Saved Positions</h3>

      {positions.length === 0 ? (
        <p className="placeholder-text">
          No saved positions. Click &ldquo;Save Position&rdquo; after calculating a spread.
        </p>
      ) : (
        <div className="position-list">
          {positions.map((pos) => {
            const pnl = pnlData[pos.id];
            return (
              <div key={pos.id} className="position-card">
                <div className="position-header">
                  <span className="position-label">
                    {pos.symbol} {stratLabel(pos.strategy)} x{pos.contracts}
                  </span>
                  <button className="alert-delete" onClick={() => handleDelete(pos.id)}>
                    &times;
                  </button>
                </div>
                <div className="position-details">
                  <span>Entry debit: ${pos.net_debit.toFixed(2)}</span>
                  <span>Spot at entry: ${pos.spot_at_entry.toFixed(2)}</span>
                </div>
                {pnl && (
                  <div className="position-pnl">
                    <span>Current: ${pnl.current_price?.toFixed(2)}</span>
                    <span className={pnl.unrealised_pnl >= 0 ? 'positive' : 'negative'}>
                      P&L: ${pnl.unrealised_pnl.toFixed(2)} ({pnl.pnl_pct.toFixed(1)}%)
                    </span>
                  </div>
                )}
                {pos.notes && <div className="position-notes">{pos.notes}</div>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// Export the save function for use from App
export async function savePosition({ symbol, strategy, contracts, legs, net_debit, spot_price, notes }) {
  const res = await fetch(`${API_URL}/api/spreadworks/positions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      symbol,
      strategy,
      contracts,
      legs,
      net_debit,
      spot_at_entry: spot_price,
      notes: notes || '',
    }),
  });
  if (!res.ok) throw new Error('Failed to save position');
  return res.json();
}
