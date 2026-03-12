import { useState } from 'react';
import usePositions from '../hooks/usePositions';
import PositionCard from '../components/positions/PositionCard';
import PortfolioSummary from '../components/positions/PortfolioSummary';
import ClosePositionModal from '../components/positions/ClosePositionModal';
import EmptySlot from '../components/positions/EmptySlot';

const s = {
  page: {
    flex: 1,
    padding: '20px 24px',
    overflowY: 'auto',
    fontFamily: 'var(--font-ui)',
    color: 'var(--text-primary)',
    background: 'var(--bg-base)',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  title: {
    color: '#fff',
    fontSize: 20,
    fontWeight: 800,
    letterSpacing: '-0.3px',
  },
  right: { display: 'flex', gap: 8, alignItems: 'center' },
  filterRow: {
    display: 'flex',
    gap: 3,
    background: 'var(--bg-elevated)',
    borderRadius: 'var(--radius-md)',
    padding: 3,
  },
  filterBtn: (active) => ({
    padding: '5px 14px',
    border: 'none',
    borderRadius: 'var(--radius-sm)',
    background: active
      ? 'linear-gradient(135deg, var(--accent) 0%, #5c9bff 100%)'
      : 'transparent',
    color: active ? '#fff' : 'var(--text-tertiary)',
    fontSize: 12,
    fontFamily: 'var(--font-ui)',
    fontWeight: active ? 600 : 500,
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
    boxShadow: active ? '0 2px 8px rgba(68, 138, 255, 0.2)' : 'none',
  }),
  discordBtn: {
    padding: '5px 12px',
    border: '1px solid rgba(124, 77, 255, 0.25)',
    borderRadius: 'var(--radius-sm)',
    background: 'var(--purple-dim)',
    color: 'var(--purple)',
    fontSize: 11,
    fontFamily: 'var(--font-ui)',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
    gap: 12,
  },
  empty: {
    textAlign: 'center',
    padding: '48px 0',
    color: 'var(--text-tertiary)',
    fontSize: 15,
    fontWeight: 500,
  },
  error: {
    background: 'var(--red-dim)',
    border: '1px solid rgba(255, 82, 82, 0.3)',
    borderRadius: 'var(--radius-md)',
    padding: '10px 16px',
    fontSize: 13,
    color: 'var(--red)',
    fontWeight: 500,
    marginBottom: 14,
  },
};

export default function PositionsPage() {
  const [filter, setFilter] = useState('open');
  const [closingPos, setClosingPos] = useState(null);
  const {
    positions, summary, loading, error,
    closePosition, deletePosition, refetch,
    postDiscordOpen, postDiscordEod,
  } = usePositions(filter);

  const emptySlots = filter === 'open' && summary
    ? Math.max(0, summary.slots_total - (summary.slots_used || 0))
    : 0;

  const handleClose = async (id, closePrice) => {
    try {
      await closePosition(id, closePrice);
      setClosingPos(null);
    } catch { /* silent */ }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this position permanently?')) return;
    try { await deletePosition(id); } catch { /* silent */ }
  };

  return (
    <div style={s.page}>
      <div style={s.header}>
        <span style={s.title}>Positions</span>
        <div style={s.right}>
          <button style={s.discordBtn} onClick={postDiscordOpen} title="Post open summary to Discord">
            Post Open
          </button>
          <button style={s.discordBtn} onClick={postDiscordEod} title="Post EOD summary to Discord">
            Post EOD
          </button>
          <div style={s.filterRow}>
            {['open', 'closed', 'all'].map((f) => (
              <button key={f} style={s.filterBtn(filter === f)} onClick={() => setFilter(f)}>
                {f.charAt(0).toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && (
        <div style={s.error}>
          Unable to connect to database. Check that DATABASE_URL is set in Render environment variables.
        </div>
      )}
      <PortfolioSummary summary={summary} />

      {loading ? (
        <div style={s.empty}>Loading positions...</div>
      ) : positions.length === 0 && emptySlots === 0 ? (
        <div style={s.empty}>
          No open positions yet.
          <br />
          <span style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 8, display: 'inline-block' }}>
            Build a spread in the Builder tab and hit Save to track it here.
          </span>
        </div>
      ) : (
        <div style={s.grid}>
          {positions.map((pos) => (
            <PositionCard
              key={pos.id}
              position={pos}
              onClose={(p) => setClosingPos(p)}
              onDelete={handleDelete}
            />
          ))}
          {Array.from({ length: emptySlots }).map((_, i) => (
            <EmptySlot
              key={`empty-${i}`}
              number={(summary?.slots_used || 0) + i + 1}
              total={summary?.slots_total || 10}
            />
          ))}
        </div>
      )}

      {closingPos && (
        <ClosePositionModal
          position={closingPos}
          onConfirm={handleClose}
          onCancel={() => setClosingPos(null)}
        />
      )}
    </div>
  );
}
