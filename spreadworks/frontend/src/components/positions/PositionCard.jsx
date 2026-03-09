import { useState, useEffect } from 'react';

const API_URL = import.meta.env.VITE_API_URL || '';

const STRAT_LABELS = {
  double_diagonal: 'DD',
  double_calendar: 'DC',
  iron_condor: 'IC',
};

const s = {
  card: (pnl, status) => ({
    background: '#0d0d18',
    border: `1px solid ${status === 'closed' ? '#2a2a3a' : pnl > 0 ? '#00e67625' : pnl < 0 ? '#ff174425' : '#1a1a2e'}`,
    borderRadius: 6,
    padding: '14px 16px',
    fontFamily: "'Courier New', monospace",
    fontSize: 12,
    color: '#ccc',
    opacity: status === 'closed' ? 0.6 : 1,
  }),
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },
  title: { color: '#fff', fontWeight: 700, fontSize: 13 },
  badge: (color) => ({
    fontSize: 9,
    padding: '2px 6px',
    borderRadius: 3,
    background: color + '22',
    color: color,
    fontWeight: 600,
    textTransform: 'uppercase',
  }),
  strikesRow: {
    display: 'flex',
    gap: 4,
    marginBottom: 10,
    flexWrap: 'wrap',
  },
  chip: (type) => ({
    fontSize: 10,
    padding: '2px 8px',
    borderRadius: 3,
    fontWeight: 600,
    fontFamily: "'Courier New', monospace",
    background: type === 'long' ? '#00e67615' : '#ff174415',
    border: `1px solid ${type === 'long' ? '#00e67633' : '#ff174433'}`,
    color: type === 'long' ? '#00e676' : '#ff5252',
  }),
  metricsGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '4px 12px',
    marginBottom: 8,
  },
  metric: {
    display: 'flex',
    justifyContent: 'space-between',
    padding: '2px 0',
    fontSize: 11,
  },
  dim: { color: '#555' },
  pnl: (v) => ({ fontWeight: 700, color: v >= 0 ? '#00e676' : '#ff5252' }),
  actions: {
    display: 'flex',
    gap: 6,
    marginTop: 10,
    borderTop: '1px solid #1a1a2e',
    paddingTop: 8,
  },
  btn: (color) => ({
    padding: '4px 10px',
    border: `1px solid ${color}44`,
    borderRadius: 4,
    background: 'transparent',
    color: color,
    fontSize: 10,
    fontFamily: "'Courier New', monospace",
    cursor: 'pointer',
  }),
  btnDisabled: {
    opacity: 0.3,
    cursor: 'not-allowed',
  },
  expRow: {
    fontSize: 10,
    color: '#555',
    marginBottom: 8,
  },
};

export default function PositionCard({ position, onClose, onDelete }) {
  const [pnl, setPnl] = useState(null);

  const isOpen = position.status === 'open';
  const strat = STRAT_LABELS[position.strategy] || position.strategy;
  const stratFull = position.strategy === 'double_diagonal' ? 'Double Diagonal'
    : position.strategy === 'double_calendar' ? 'Double Calendar' : 'Iron Condor';

  useEffect(() => {
    if (!isOpen) return;
    const fetchPnl = async () => {
      try {
        const res = await fetch(`${API_URL}/api/spreadworks/positions/${position.id}/pnl`);
        if (res.ok) setPnl(await res.json());
      } catch { /* silent */ }
    };
    fetchPnl();
    const iv = setInterval(fetchPnl, 60000);
    return () => clearInterval(iv);
  }, [position.id, isOpen]);

  const unrealized = pnl?.unrealized_pnl ?? 0;
  const currentValue = pnl?.current_value;
  const pnlPct = pnl?.pnl_pct ?? 0;

  return (
    <div style={s.card(isOpen ? unrealized : (position.realized_pnl || 0), position.status)}>
      {/* Header */}
      <div style={s.header}>
        <div>
          <span style={s.title}>{position.label || `#${position.id}`}</span>
          <span style={{ color: '#555', fontSize: 10, marginLeft: 6 }}>{strat}</span>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {position.dte != null && (
            <span style={s.badge('#448aff')}>{position.dte}DTE</span>
          )}
          <span style={s.badge(isOpen ? '#00e676' : '#888')}>
            {isOpen ? 'OPEN' : 'CLOSED'}
          </span>
        </div>
      </div>

      {/* Strike Chips */}
      <div style={s.strikesRow}>
        <span style={s.chip('long')}>LP {position.long_put}</span>
        <span style={s.chip('short')}>SP {position.short_put}</span>
        <span style={s.chip('short')}>SC {position.short_call}</span>
        <span style={s.chip('long')}>LC {position.long_call}</span>
      </div>

      {/* Expirations */}
      <div style={s.expRow}>
        Short: {position.short_exp}
        {position.long_exp && ` | Long: ${position.long_exp}`}
      </div>

      {/* 7 Metrics */}
      <div style={s.metricsGrid}>
        <div style={s.metric}>
          <span style={s.dim}>Entry Credit</span>
          <span style={{ color: '#00e676', fontWeight: 600 }}>+${position.entry_credit?.toFixed(2)}</span>
        </div>
        <div style={s.metric}>
          <span style={s.dim}>Current Value</span>
          <span>{currentValue != null ? `$${currentValue.toFixed(4)}` : '\u2014'}</span>
        </div>
        <div style={s.metric}>
          <span style={s.dim}>P&L $</span>
          {isOpen ? (
            <span style={s.pnl(unrealized)}>${unrealized >= 0 ? '+' : ''}{unrealized.toFixed(2)}</span>
          ) : (
            <span style={s.pnl(position.realized_pnl || 0)}>
              ${(position.realized_pnl || 0) >= 0 ? '+' : ''}{(position.realized_pnl || 0).toFixed(2)}
            </span>
          )}
        </div>
        <div style={s.metric}>
          <span style={s.dim}>P&L %</span>
          <span style={s.pnl(isOpen ? unrealized : (position.realized_pnl || 0))}>
            {isOpen
              ? `${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(1)}%`
              : position.max_profit
                ? `${((position.realized_pnl || 0) / Math.abs(position.max_profit) * 100).toFixed(1)}%`
                : '\u2014'
            }
          </span>
        </div>
        <div style={s.metric}>
          <span style={s.dim}>Max Profit</span>
          <span>${position.max_profit != null ? position.max_profit.toFixed(2) : '\u2014'}</span>
        </div>
        <div style={s.metric}>
          <span style={s.dim}>Max Loss</span>
          <span style={{ color: '#ff5252' }}>
            ${position.max_loss != null ? position.max_loss.toFixed(2) : '\u2014'}
          </span>
        </div>
        <div style={s.metric}>
          <span style={s.dim}>Contracts</span>
          <span>{position.contracts}</span>
        </div>
      </div>

      {/* Notes */}
      {position.notes && (
        <div style={{ fontSize: 10, color: '#666', fontStyle: 'italic', marginBottom: 6 }}>
          {position.notes}
        </div>
      )}

      {/* Date info */}
      <div style={{ fontSize: 10, color: '#444' }}>
        Opened {position.entry_date || '\u2014'}
        {position.close_date && ` \u2022 Closed ${position.close_date}`}
      </div>

      {/* Actions */}
      {isOpen && (
        <div style={s.actions}>
          <button style={s.btn('#ff5252')} onClick={() => onClose(position)}>
            \u2715 Close
          </button>
          <button style={s.btn('#555')} onClick={() => onDelete(position.id)}>
            Delete
          </button>
          <button style={{ ...s.btn('#555'), ...s.btnDisabled }} disabled title="Coming soon">
            \u21bb Roll
          </button>
        </div>
      )}
    </div>
  );
}
