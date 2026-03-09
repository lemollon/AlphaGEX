import { useState } from 'react';
import usePositions from '../hooks/usePositions';
import PositionCard from './PositionCard';
import PortfolioSummary from './PortfolioSummary';

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
  title: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 700,
  },
  filterRow: {
    display: 'flex',
    gap: 6,
  },
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
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
    gap: 10,
  },
  empty: {
    textAlign: 'center',
    padding: '40px 0',
    color: '#444',
    fontSize: 14,
  },
  emptySlot: {
    background: '#0d0d18',
    border: '1px dashed #1a1a2e',
    borderRadius: 6,
    padding: 20,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#333',
    fontSize: 11,
    fontFamily: "'Courier New', monospace",
    minHeight: 100,
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
  const {
    positions,
    summary,
    loading,
    error,
    closePosition,
    deletePosition,
    refetch,
  } = usePositions(filter);

  const emptySlots = filter === 'open' && summary
    ? Math.max(0, summary.slots_total - (summary.slots_used || 0))
    : 0;

  return (
    <div style={s.page}>
      <div style={s.header}>
        <span style={s.title}>Positions</span>
        <div style={s.filterRow}>
          {['open', 'closed', 'all'].map((f) => (
            <button
              key={f}
              style={s.filterBtn(filter === f)}
              onClick={() => setFilter(f)}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {error && <div style={s.error}>{error}</div>}

      <PortfolioSummary summary={summary} />

      {loading ? (
        <div style={s.empty}>Loading positions...</div>
      ) : positions.length === 0 && emptySlots === 0 ? (
        <div style={s.empty}>
          No {filter === 'all' ? '' : filter} positions yet.
          <br />
          <span style={{ fontSize: 12, color: '#333' }}>
            Use the Builder tab to create and save a spread.
          </span>
        </div>
      ) : (
        <div style={s.grid}>
          {positions.map((pos) => (
            <PositionCard
              key={pos.id}
              position={pos}
              onClose={closePosition}
              onDelete={deletePosition}
              onRefresh={refetch}
            />
          ))}
          {Array.from({ length: emptySlots }).map((_, i) => (
            <div key={`empty-${i}`} style={s.emptySlot}>
              Empty Slot {(summary?.slots_used || 0) + i + 1}/{summary?.slots_total || 10}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
