import { useState } from 'react';
import usePositions from '../hooks/usePositions';
import PositionCard from '../components/positions/PositionCard';
import PortfolioSummary from '../components/positions/PortfolioSummary';
import ClosePositionModal from '../components/positions/ClosePositionModal';
import EmptySlot from '../components/positions/EmptySlot';

const s = {
  page: {
    flex: 1,
    padding: '16px 20px',
    overflowY: 'auto',
    fontFamily: "'Courier New', monospace",
    color: '#ccc',
    background: '#080810',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  title: { color: '#fff', fontSize: 18, fontWeight: 700 },
  right: { display: 'flex', gap: 8, alignItems: 'center' },
  filterRow: { display: 'flex', gap: 4 },
  filterBtn: (active) => ({
    padding: '4px 12px',
    border: `1px solid ${active ? '#448aff' : '#1a1a2e'}`,
    borderRadius: 4,
    background: active ? '#448aff22' : 'transparent',
    color: active ? '#448aff' : '#555',
    fontSize: 11,
    fontFamily: "'Courier New', monospace",
    cursor: 'pointer',
  }),
  discordBtn: {
    padding: '4px 10px',
    border: '1px solid #5865F244',
    borderRadius: 4,
    background: 'transparent',
    color: '#5865F2',
    fontSize: 10,
    fontFamily: "'Courier New', monospace",
    cursor: 'pointer',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
    gap: 10,
  },
  empty: {
    textAlign: 'center',
    padding: '40px 0',
    color: '#444',
    fontSize: 14,
  },
  error: {
    background: '#1a0a0a',
    border: '1px solid #ff1744',
    borderRadius: 4,
    padding: '8px 12px',
    fontSize: 12,
    color: '#ff5252',
    marginBottom: 12,
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
          <span style={{ fontSize: 12, color: '#555', marginTop: 6, display: 'inline-block' }}>
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
