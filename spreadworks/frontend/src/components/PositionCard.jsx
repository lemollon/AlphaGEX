import { useState, useEffect } from 'react';

const API_URL = import.meta.env.VITE_API_URL || '';

const s = {
  card: {
    background: '#0d0d18',
    border: '1px solid #1a1a2e',
    borderRadius: 6,
    padding: '12px 14px',
    fontFamily: "'Courier New', monospace",
    fontSize: 12,
    color: '#ccc',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  label: {
    color: '#fff',
    fontWeight: 700,
    fontSize: 13,
  },
  badge: (color) => ({
    fontSize: 10,
    padding: '2px 6px',
    borderRadius: 3,
    background: color + '22',
    color: color,
    fontWeight: 600,
  }),
  row: {
    display: 'flex',
    justifyContent: 'space-between',
    padding: '2px 0',
    fontSize: 11,
  },
  dim: { color: '#555' },
  legs: {
    background: '#080810',
    borderRadius: 4,
    padding: '6px 8px',
    margin: '6px 0',
    fontSize: 11,
    lineHeight: 1.5,
  },
  pnl: (val) => ({
    fontWeight: 700,
    color: val >= 0 ? '#00e676' : '#ff5252',
  }),
  actions: {
    display: 'flex',
    gap: 6,
    marginTop: 8,
  },
  btn: (color) => ({
    flex: 1,
    padding: '5px 8px',
    border: `1px solid ${color}`,
    borderRadius: 4,
    background: color + '15',
    color: color,
    fontSize: 10,
    fontFamily: "'Courier New', monospace",
    cursor: 'pointer',
    textAlign: 'center',
  }),
};

export default function PositionCard({ position, onClose, onDelete, onRefresh }) {
  const [pnl, setPnl] = useState(null);
  const [loadingPnl, setLoadingPnl] = useState(false);
  const [showClose, setShowClose] = useState(false);
  const [closePrice, setClosePrice] = useState('');

  const isOpen = position.status === 'open';
  const strat = position.strategy === 'double_diagonal' ? 'Dbl Diagonal' : 'Dbl Calendar';
  const legs = position.legs || {};

  useEffect(() => {
    if (!isOpen) return;
    const fetchPnl = async () => {
      setLoadingPnl(true);
      try {
        const res = await fetch(`${API_URL}/api/spreadworks/positions/${position.id}/pnl`);
        if (res.ok) {
          const data = await res.json();
          setPnl(data);
        }
      } catch {
        // silent
      } finally {
        setLoadingPnl(false);
      }
    };
    fetchPnl();
    const interval = setInterval(fetchPnl, 60000); // refresh every 60s
    return () => clearInterval(interval);
  }, [position.id, isOpen]);

  const handleClose = async () => {
    if (!closePrice) return;
    try {
      await onClose(position.id, parseFloat(closePrice));
      setShowClose(false);
    } catch {
      // silent
    }
  };

  const formatLegs = () => {
    if (position.strategy === 'double_diagonal') {
      const lp = legs.longPutStrike || legs.long_put_strike || '?';
      const sp = legs.shortPutStrike || legs.short_put_strike || '?';
      const sc = legs.shortCallStrike || legs.short_call_strike || '?';
      const lc = legs.longCallStrike || legs.long_call_strike || '?';
      const sExp = legs.shortExpiration || legs.short_expiration || '?';
      const lExp = legs.longExpiration || legs.long_expiration || '?';
      return (
        <>
          <div>Put: {lp}L / {sp}S</div>
          <div>Call: {sc}S / {lc}L</div>
          <div style={{ color: '#555' }}>Short: {sExp} | Long: {lExp}</div>
        </>
      );
    }
    const ps = legs.putStrike || legs.put_strike || '?';
    const cs = legs.callStrike || legs.call_strike || '?';
    const fExp = legs.frontExpiration || legs.front_expiration || '?';
    const bExp = legs.backExpiration || legs.back_expiration || '?';
    return (
      <>
        <div>Put: {ps} | Call: {cs}</div>
        <div style={{ color: '#555' }}>Front: {fExp} | Back: {bExp}</div>
      </>
    );
  };

  return (
    <div style={s.card}>
      <div style={s.header}>
        <span style={s.label}>{position.label || `#${position.id}`}</span>
        <span style={s.badge(isOpen ? '#00e676' : '#ff5252')}>
          {isOpen ? 'OPEN' : 'CLOSED'}
        </span>
      </div>

      <div style={s.row}>
        <span style={s.dim}>Strategy</span>
        <span>{strat}</span>
      </div>
      <div style={s.row}>
        <span style={s.dim}>Symbol</span>
        <span>{position.symbol} x{position.contracts}</span>
      </div>
      <div style={s.row}>
        <span style={s.dim}>Net Debit</span>
        <span>${position.net_debit?.toFixed(2)}</span>
      </div>
      <div style={s.row}>
        <span style={s.dim}>Spot at Entry</span>
        <span>${position.spot_at_entry?.toFixed(2)}</span>
      </div>

      <div style={s.legs}>{formatLegs()}</div>

      {isOpen && pnl && (
        <div style={s.row}>
          <span style={s.dim}>Unrealised P&L</span>
          <span style={s.pnl(pnl.unrealised_pnl)}>
            ${pnl.unrealised_pnl?.toFixed(2)} ({pnl.pnl_pct?.toFixed(1)}%)
          </span>
        </div>
      )}
      {isOpen && loadingPnl && !pnl && (
        <div style={{ ...s.row, color: '#555' }}>Loading P&L...</div>
      )}

      {!isOpen && position.realized_pnl != null && (
        <div style={s.row}>
          <span style={s.dim}>Realized P&L</span>
          <span style={s.pnl(position.realized_pnl)}>
            ${position.realized_pnl?.toFixed(2)}
          </span>
        </div>
      )}

      {position.notes && (
        <div style={{ ...s.row, color: '#888', fontStyle: 'italic', marginTop: 4 }}>
          {position.notes}
        </div>
      )}

      <div style={{ ...s.row, color: '#444', fontSize: 10, marginTop: 4 }}>
        Opened {position.opened_at ? new Date(position.opened_at).toLocaleDateString() : '—'}
        {position.closed_at && ` | Closed ${new Date(position.closed_at).toLocaleDateString()}`}
      </div>

      {isOpen && (
        <div style={s.actions}>
          {!showClose ? (
            <>
              <button style={s.btn('#ff5252')} onClick={() => setShowClose(true)}>Close</button>
              <button style={s.btn('#555')} onClick={() => onDelete(position.id)}>Delete</button>
            </>
          ) : (
            <>
              <input
                type="number"
                step="0.01"
                placeholder="Close $ value"
                value={closePrice}
                onChange={(e) => setClosePrice(e.target.value)}
                style={{
                  flex: 2,
                  padding: '4px 6px',
                  border: '1px solid #ff525244',
                  borderRadius: 3,
                  background: '#080810',
                  color: '#e0e0e0',
                  fontSize: 11,
                  fontFamily: "'Courier New', monospace",
                }}
              />
              <button style={s.btn('#ff5252')} onClick={handleClose}>Confirm</button>
              <button style={s.btn('#555')} onClick={() => setShowClose(false)}>Cancel</button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
