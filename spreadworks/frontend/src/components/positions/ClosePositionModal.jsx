import { useState } from 'react';

const s = {
  overlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.7)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
    fontFamily: "'Courier New', monospace",
  },
  modal: {
    background: '#0d0d18',
    border: '1px solid #1a1a2e',
    borderRadius: 8,
    padding: '20px 24px',
    width: 380,
    maxWidth: '90vw',
    color: '#ccc',
    fontSize: 12,
  },
  title: {
    color: '#fff',
    fontWeight: 700,
    fontSize: 14,
    marginBottom: 12,
  },
  subtitle: {
    color: '#888',
    fontSize: 11,
    marginBottom: 16,
  },
  label: {
    color: '#555',
    fontSize: 10,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    marginBottom: 4,
  },
  input: {
    width: '100%',
    padding: '8px 10px',
    border: '1px solid #1a1a2e',
    borderRadius: 4,
    background: '#080810',
    color: '#e0e0e0',
    fontSize: 14,
    fontFamily: "'Courier New', monospace",
    outline: 'none',
    boxSizing: 'border-box',
    marginBottom: 12,
  },
  preview: (positive) => ({
    background: positive ? '#00e67610' : '#ff174410',
    border: `1px solid ${positive ? '#00e67633' : '#ff174433'}`,
    borderRadius: 4,
    padding: '10px 12px',
    marginBottom: 16,
    fontSize: 13,
    fontWeight: 700,
    color: positive ? '#00e676' : '#ff5252',
    textAlign: 'center',
  }),
  buttons: {
    display: 'flex',
    gap: 8,
  },
  btn: (color, filled) => ({
    flex: 1,
    padding: '8px',
    border: `1px solid ${color}`,
    borderRadius: 4,
    background: filled ? color : 'transparent',
    color: filled ? '#fff' : color,
    fontWeight: 600,
    fontSize: 12,
    fontFamily: "'Courier New', monospace",
    cursor: 'pointer',
    textAlign: 'center',
  }),
};

export default function ClosePositionModal({ position, onConfirm, onCancel }) {
  const [closePrice, setClosePrice] = useState('');

  const cp = parseFloat(closePrice) || 0;
  const realizedPnl = (position.entry_price - cp) * 100 * position.contracts;
  const pctOfMax = position.max_profit
    ? (realizedPnl / Math.abs(position.max_profit) * 100)
    : 0;

  const handleConfirm = () => {
    if (!closePrice || cp <= 0) return;
    onConfirm(position.id, cp);
  };

  const strat = position.strategy === 'double_diagonal' ? 'DD'
    : position.strategy === 'double_calendar' ? 'DC' : 'IC';

  return (
    <div style={s.overlay} onClick={onCancel}>
      <div style={s.modal} onClick={(e) => e.stopPropagation()}>
        <div style={s.title}>Close Position</div>
        <div style={s.subtitle}>
          {position.symbol} {strat} {position.long_put}/{position.short_put}/{position.short_call}/{position.long_call}
        </div>

        <div style={s.label}>Enter debit to close (per contract)</div>
        <input
          type="number"
          step="0.01"
          min="0"
          placeholder="0.59"
          value={closePrice}
          onChange={(e) => setClosePrice(e.target.value)}
          style={s.input}
          autoFocus
        />

        {closePrice && (
          <div style={s.preview(realizedPnl >= 0)}>
            Realized P&L: {realizedPnl >= 0 ? '+' : ''}${realizedPnl.toFixed(2)}
            {position.max_profit ? ` (${pctOfMax >= 0 ? '+' : ''}${pctOfMax.toFixed(1)}% of max profit)` : ''}
          </div>
        )}

        <div style={s.buttons}>
          <button style={s.btn('#555', false)} onClick={onCancel}>Cancel</button>
          <button
            style={s.btn('#ff5252', true)}
            onClick={handleConfirm}
            disabled={!closePrice || cp <= 0}
          >
            Confirm Close
          </button>
        </div>
      </div>
    </div>
  );
}
