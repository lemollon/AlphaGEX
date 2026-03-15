import { useState } from 'react';

const s = {
  overlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(6, 6, 14, 0.8)',
    backdropFilter: 'blur(4px)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
    fontFamily: 'var(--font-ui)',
    animation: 'sw-fadeIn 0.15s ease',
  },
  modal: {
    background: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)',
    padding: '24px 28px',
    width: 400,
    maxWidth: '90vw',
    color: 'var(--text-primary)',
    fontSize: 13,
    boxShadow: 'var(--shadow-lg)',
  },
  title: {
    color: '#fff',
    fontWeight: 700,
    fontSize: 16,
    marginBottom: 8,
  },
  subtitle: {
    color: 'var(--text-secondary)',
    fontSize: 12,
    marginBottom: 20,
    fontFamily: 'var(--font-mono)',
    fontWeight: 500,
  },
  label: {
    color: 'var(--text-tertiary)',
    fontSize: 10,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.1em',
    marginBottom: 6,
  },
  input: {
    width: '100%',
    padding: '10px 12px',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    background: 'var(--bg-elevated)',
    color: 'var(--text-primary)',
    fontSize: 15,
    fontFamily: 'var(--font-mono)',
    fontWeight: 600,
    outline: 'none',
    boxSizing: 'border-box',
    marginBottom: 14,
    transition: 'border-color var(--transition-fast), box-shadow var(--transition-fast)',
  },
  preview: (positive) => ({
    background: positive ? 'var(--green-dim)' : 'var(--red-dim)',
    border: `1px solid ${positive ? 'rgba(0, 230, 118, 0.2)' : 'rgba(255, 82, 82, 0.2)'}`,
    borderRadius: 'var(--radius-md)',
    padding: '12px 14px',
    marginBottom: 18,
    fontSize: 15,
    fontWeight: 700,
    fontFamily: 'var(--font-mono)',
    color: positive ? 'var(--green)' : 'var(--red)',
    textAlign: 'center',
  }),
  buttons: {
    display: 'flex',
    gap: 10,
  },
  btnCancel: {
    flex: 1,
    padding: '10px',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    background: 'transparent',
    color: 'var(--text-secondary)',
    fontWeight: 600,
    fontSize: 13,
    fontFamily: 'var(--font-ui)',
    cursor: 'pointer',
    textAlign: 'center',
    transition: 'all var(--transition-fast)',
  },
  btnConfirm: {
    flex: 1,
    padding: '10px',
    border: 'none',
    borderRadius: 'var(--radius-md)',
    background: 'var(--red)',
    color: '#fff',
    fontWeight: 600,
    fontSize: 13,
    fontFamily: 'var(--font-ui)',
    cursor: 'pointer',
    textAlign: 'center',
    transition: 'all var(--transition-fast)',
    boxShadow: '0 2px 8px rgba(255, 82, 82, 0.25)',
  },
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
          <button style={s.btnCancel} onClick={onCancel}>Cancel</button>
          <button
            style={{ ...s.btnConfirm, ...((!closePrice || cp <= 0) ? { opacity: 0.4, cursor: 'not-allowed' } : {}) }}
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
